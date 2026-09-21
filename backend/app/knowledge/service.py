"""Knowledge seeding, versioned candidate→verified governance, and RAG retrieval."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.knowledge.catalog import catalog_entries
from app.llm.embeddings import get_embedder, tokenize
from app.models.knowledge import KnowledgeItem

_SYNONYMS = {
    "投产": "ROI 投入产出比",
    "投入产出": "ROI 投入产出比",
    "roi": "ROI 投入产出比 盈亏",
    "点击率": "CTR 点击率 素材",
    "转化率": "CVR 转化率 商品 详情页",
    "千次": "CPM 流量成本",
    "流量贵": "CPM 上涨 流量成本 竞价",
    "花不出去": "预算消耗率 出价 冷启动",
    "烧钱": "花费 ROI 成本 止损",
    "没单": "CVR 转化率 商品评分 承接页",
    "没成交": "CVR 转化率 商品评分",
    "疲劳": "素材疲劳 CTR 下滑 迭代",
    "换素材": "素材疲劳 迭代 卖点",
    "加预算": "预算 提预算 CPM 20%",
    "新品": "新品 爬坡 扶持期 CVR",
    "换季": "季节性 需求 衰退 应季",
    "大促": "大促 蓄水 节后 CPM",
    "复购": "复购率 LTV 首单 CPA",
    "案例": "案例 合成世界 因果链",
    "定义": "指标定义 口径",
}

_TYPE_HINTS = {
    "metric_definition": ["定义", "是什么", "怎么算", "口径", "意思"],
    "case": ["案例", "例子", "有没有商家", "故事"],
    "diagnostic_rule": ["为什么", "原因", "诊断", "下降", "下滑", "异常"],
    "best_practice": ["怎么", "如何", "建议", "优化", "提升"],
    "business_rule": ["规则", "限制", "幅度", "能不能", "允许"],
    "industry_insight": ["行业", "类目", "女装", "美妆", "食品", "3c", "家居"],
}


def _new_id() -> str:
    return f"KN{uuid.uuid4().hex[:14]}"


def rewrite_query(query: str) -> str:
    additions = []
    lowered = query.lower()
    for trigger, expansion in _SYNONYMS.items():
        if trigger in lowered:
            additions.append(expansion)
    if not additions:
        return query
    return query + " " + " ".join(dict.fromkeys(additions))


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db
        # Local hash vectors are always maintained for the 256-d column.
        self.local_embedder = get_embedder("local")
        self.settings = get_settings()
        self.embedding_provider = (self.settings.knowledge_embedding_provider or "local").lower()
        self.retrieval_strategy = (self.settings.knowledge_retrieval_strategy or "vector").lower()

    @property
    def embedder(self):
        """Backward-compatible alias (default local hash embedder)."""
        return self.local_embedder

    def _deep_embedder(self):
        """Pretrained/online embedder for the 512-d column, or None."""
        if self.embedding_provider in ("bge", "openai"):
            return get_embedder(self.embedding_provider)
        return None

    def _deep_vector(self, text: str):
        embedder = self._deep_embedder()
        if embedder is None:
            return None
        return embedder.embed(text)

    # ---------------- seeding & governance ----------------
    def seed_catalog(self, entries: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
        entries = entries if entries is not None else catalog_entries()
        inserted = 0
        for entry in entries:
            source_text = f"{entry['title']} {entry['content']} {entry.get('recommendation') or ''}"
            vector = self.local_embedder.embed(source_text)
            deep_vector = self._deep_vector(source_text)
            stmt = pg_insert(KnowledgeItem).values(
                knowledge_id=_new_id(),
                slug=entry["slug"],
                version=entry["version"],
                type=entry["type"],
                industry=entry["industry"],
                title=entry["title"],
                content=entry["content"],
                condition=entry.get("condition"),
                recommendation=entry.get("recommendation"),
                evidence=entry.get("evidence"),
                embedding=vector,
                embedding_deep=deep_vector,
                status="verified",
                source="curated",
                quality_score=0.85,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_knowledge_slug_version",
                set_={
                    "title": stmt.excluded.title,
                    "content": stmt.excluded.content,
                    "condition": stmt.excluded.condition,
                    "recommendation": stmt.excluded.recommendation,
                    "evidence": stmt.excluded.evidence,
                    "embedding": stmt.excluded.embedding,
                    "embedding_deep": stmt.excluded.embedding_deep,
                },
            )
            self.db.execute(stmt)
            inserted += 1
        self.db.flush()
        archived = self._archive_old_versions()
        self.db.commit()
        return {"entries": inserted, "archived_old_versions": archived}

    def _archive_old_versions(self, slugs: Optional[List[str]] = None) -> int:
        stmt = select(KnowledgeItem).where(KnowledgeItem.source == "curated")
        if slugs:
            stmt = stmt.where(KnowledgeItem.slug.in_(slugs))
        items = list(self.db.scalars(stmt).all())
        latest = {}
        for item in items:
            if item.version > latest.get(item.slug, 0):
                latest[item.slug] = item.version
        count = 0
        for item in items:
            target = "verified" if item.version == latest[item.slug] else "archived"
            if item.status != target:
                item.status = target
                count += 1
        return count

    def propose_candidate(self, candidate: Dict[str, Any]) -> KnowledgeItem:
        version = self._next_version(candidate["slug"])
        source_text = f"{candidate['title']} {candidate['content']}"
        vector = self.local_embedder.embed(source_text)
        item = KnowledgeItem(
            knowledge_id=_new_id(),
            slug=candidate["slug"],
            version=version,
            type=candidate["type"],
            industry=candidate.get("industry"),
            title=candidate["title"],
            content=candidate["content"],
            condition=candidate.get("condition"),
            recommendation=candidate.get("recommendation"),
            evidence=candidate.get("evidence"),
            embedding=vector,
            embedding_deep=self._deep_vector(source_text),
            status="candidate",
            source=candidate.get("source", "multi_merchant_observation"),
            merchant_count=candidate.get("merchant_count", 0),
            quality_score=candidate.get("quality_score", 0.6),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def propose_from_merchant_patterns(self) -> Optional[KnowledgeItem]:
        """Detect a cross-merchant pattern (material fatigue + CTR decline) and
        propose it as a candidate knowledge item pending verification."""
        from sqlalchemy import func

        from app.models.material import Material
        from app.models.performance import PerformanceDaily

        end_date = self.db.scalar(func.max(PerformanceDaily.date))
        if end_date is None:
            return None
        from datetime import timedelta

        def avg_ctr(start_offset: int, end_offset: int) -> Dict[str, float]:
            start = end_date - timedelta(days=start_offset)
            end = end_date - timedelta(days=end_offset)
            rows = self.db.execute(
                select(
                    PerformanceDaily.merchant_id,
                    func.sum(PerformanceDaily.clicks)
                    / func.nullif(func.sum(PerformanceDaily.impressions), 0),
                )
                .where(PerformanceDaily.date.between(start, end))
                .group_by(PerformanceDaily.merchant_id)
            ).all()
            return {merchant_id: float(ctr) for merchant_id, ctr in rows}

        recent = avg_ctr(6, 0)
        previous = avg_ctr(13, 7)
        declining = [
            merchant_id
            for merchant_id, ctr in recent.items()
            if merchant_id in previous
            and ctr < previous[merchant_id] * 0.95
            and self.db.scalar(
                select(func.count())
                .select_from(Material)
                .where(
                    Material.merchant_id == merchant_id,
                    Material.status == "fatigued",
                )
            )
            >= 1
        ]
        if len(declining) < 2:
            return None
        return self.propose_candidate(
            {
                "slug": "derived_fatigue_ctr_pattern",
                "type": "diagnostic_rule",
                "industry": None,
                "title": f"跨商家观察：{len(declining)} 个商家在素材疲劳同时 CTR 下滑超 5%",
                "content": (
                    "在多商家样本中观察到：存在疲劳状态素材的商家，其近 7 日 CTR 较前 7 日下滑超过 5%，"
                    "支持素材疲劳→点击率下降的因果假设，候选规则待审核转正。"
                ),
                "condition": "存在 fatigued 素材且近 7 日 CTR 环比下降 >5%",
                "recommendation": "优先迭代素材而非调整预算",
                "evidence": f"观察商家：{', '.join(sorted(declining)[:10])}",
                "merchant_count": len(declining),
                "quality_score": 0.65,
            }
        )

    def verify(self, knowledge_id: str) -> KnowledgeItem:
        item = self.db.get(KnowledgeItem, knowledge_id)
        if item is None:
            raise KeyError(knowledge_id)
        if item.status == "verified":
            return item
        new_version = self._next_version(item.slug)
        source_text = f"{item.title} {item.content} {item.recommendation or ''}"
        vector = self.local_embedder.embed(source_text)
        verified = KnowledgeItem(
            knowledge_id=_new_id(),
            slug=item.slug,
            version=new_version,
            type=item.type,
            industry=item.industry,
            title=item.title,
            content=item.content,
            condition=item.condition,
            recommendation=item.recommendation,
            evidence=item.evidence,
            embedding=vector,
            embedding_deep=self._deep_vector(source_text) or item.embedding_deep,
            status="verified",
            source=item.source,
            merchant_count=item.merchant_count,
            quality_score=max(item.quality_score, 0.75),
        )
        previous_verified = list(
            self.db.scalars(
                select(KnowledgeItem).where(
                    KnowledgeItem.slug == item.slug,
                    KnowledgeItem.status == "verified",
                )
            ).all()
        )
        for previous in previous_verified:
            previous.status = "archived"
        item.status = "archived"
        self.db.add(verified)
        self.db.commit()
        self.db.refresh(verified)
        return verified

    def _next_version(self, slug: str) -> int:
        versions = list(
            self.db.scalars(select(KnowledgeItem.version).where(KnowledgeItem.slug == slug)).all()
        )
        return (max(versions) + 1) if versions else 1

    # ---------------- RAG retrieval ----------------
    def retrieve(
        self,
        query: str,
        industry: Optional[str] = None,
        top_k: Optional[int] = None,
        types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        top_k = top_k or self.settings.knowledge_top_k
        rewritten = rewrite_query(query)
        query_tokens = set(tokenize(rewritten))
        pool_limit = max(top_k * 4, 20)

        if self.retrieval_strategy == "bm25":
            candidates, semantic_proxy = self._bm25_rank(rewritten, types, pool_limit)
        elif self.retrieval_strategy == "hybrid":
            candidates, semantic_proxy = self._hybrid_rank(rewritten, types, pool_limit)
        else:
            candidates, semantic_proxy = self._vector_rank(rewritten, types, pool_limit)

        max_version_by_slug = {}
        for item in candidates:
            max_version_by_slug[item.slug] = max(
                max_version_by_slug.get(item.slug, 1), item.version
            )

        scored = []
        for item in candidates:
            semantic = semantic_proxy.get(item.knowledge_id, 0.0)
            industry_match = 1.0 if (industry and item.industry == industry) else 0.0
            if item.industry is None:
                industry_match = 0.4
            doc_tokens = set(tokenize(f"{item.title} {item.content} {item.recommendation or ''}"))
            overlap = (
                len(query_tokens & doc_tokens) / min(6, max(1, len(query_tokens)))
                if query_tokens
                else 0.0
            )
            keyword = min(1.0, overlap)
            type_boost = self._type_boost(query, item.type)
            freshness = item.version / max_version_by_slug[item.slug]
            score = (
                0.55 * semantic
                + 0.15 * industry_match
                + 0.15 * keyword
                + 0.10 * type_boost
                + 0.05 * freshness
            )
            scored.append(
                {
                    "knowledge_id": item.knowledge_id,
                    "slug": item.slug,
                    "version": item.version,
                    "type": item.type,
                    "industry": item.industry,
                    "title": item.title,
                    "content": item.content,
                    "recommendation": item.recommendation,
                    "evidence": item.evidence,
                    "score": round(score, 4),
                    "score_breakdown": {
                        "semantic": round(semantic, 4),
                        "industry": round(industry_match, 4),
                        "keyword": round(keyword, 4),
                        "type": round(type_boost, 4),
                        "freshness": round(freshness / 2, 4),
                        "strategy": self.retrieval_strategy,
                    },
                }
            )
        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:top_k]

    def _verified_items(self, types: Optional[List[str]] = None) -> List[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(KnowledgeItem.status == "verified")
        items = list(self.db.scalars(stmt).all())
        if types:
            items = [item for item in items if item.type in types]
        return items

    def _vector_rank(self, query, types, limit):
        """Dense vector recall: pgvector cosine over selected embedding column."""
        use_deep = self.embedding_provider in ("bge", "openai")
        column = KnowledgeItem.embedding_deep if use_deep else KnowledgeItem.embedding
        query_vector = (
            self._deep_vector(query) if use_deep else self.local_embedder.embed(query)
        )
        if use_deep and query_vector is None:
            use_deep, column = False, KnowledgeItem.embedding
            query_vector = self.local_embedder.embed(query)

        distance = column.cosine_distance(query_vector).label("distance")
        stmt = (
            select(KnowledgeItem, distance)
            .where(KnowledgeItem.status == "verified")
            .where(column.isnot(None))
            .order_by(distance)
            .limit(limit)
        )
        rows = list(self.db.execute(stmt).all())
        if types:
            rows = [row for row in rows if row[0].type in types]
        # Degraded safety net: deep column not reindexed yet -> local vectors.
        if use_deep and not rows:
            return self._vector_rank_local(query, types, limit)
        candidates = [row[0] for row in rows]
        proxy = {row[0].knowledge_id: max(0.0, 1.0 - float(row[1])) for row in rows}
        return candidates, proxy

    def _vector_rank_local(self, query, types, limit):
        distance = KnowledgeItem.embedding.cosine_distance(
            self.local_embedder.embed(query)
        ).label("distance")
        stmt = (
            select(KnowledgeItem, distance)
            .where(KnowledgeItem.status == "verified")
            .order_by(distance)
            .limit(limit)
        )
        rows = list(self.db.execute(stmt).all())
        if types:
            rows = [row for row in rows if row[0].type in types]
        candidates = [row[0] for row in rows]
        proxy = {row[0].knowledge_id: max(0.0, 1.0 - float(row[1])) for row in rows}
        return candidates, proxy

    def _bm25_rank(self, query, types, limit):
        """Lexical BM25 over latin-word + CJK-bigram tokens (k1=1.5, b=0.75)."""
        import math

        items = self._verified_items(types)
        docs = {
            item.knowledge_id: tokenize(
                f"{item.title} {item.content} {item.recommendation or ''}"
            )
            for item in items
        }
        n_docs = max(1, len(docs))
        frequencies = {}
        lengths = {}
        for kid, tokens in docs.items():
            lengths[kid] = len(tokens)
            frequencies[kid] = {}
            for token in tokens:
                frequencies[kid][token] = frequencies[kid].get(token, 0) + 1
        avg_length = (sum(lengths.values()) / n_docs) if lengths else 0.0

        document_frequency = {}
        for kid, counts in frequencies.items():
            for token in counts:
                document_frequency[token] = document_frequency.get(token, 0) + 1

        query_tokens = tokenize(query)
        k1, b = 1.5, 0.75
        scores = {kid: 0.0 for kid in docs}
        for token in query_tokens:
            df = document_frequency.get(token, 0)
            if df == 0:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for kid, counts in frequencies.items():
                freq = counts.get(token, 0)
                if freq == 0:
                    continue
                normalization = 1.0 - b + b * (lengths[kid] / (avg_length or 1.0))
                scores[kid] += idf * (freq * (k1 + 1.0)) / (freq + k1 * normalization)
        ranked = sorted(
            ((kid, score) for kid, score in scores.items() if score > 0),
            key=lambda row: row[1],
            reverse=True,
        )[:limit]
        by_id = {item.knowledge_id: item for item in items}
        candidates = [by_id[kid] for kid, _score in ranked]
        top = ranked[0][1] if ranked else 1.0
        proxy = {kid: (score / top if top else 0.0) for kid, score in ranked}
        return candidates, proxy

    def _hybrid_rank(self, query, types, limit):
        """Dense vector + BM25 fused by Reciprocal Rank Fusion (k=60)."""
        vector_candidates, _ = self._vector_rank(query, types, limit)
        bm25_candidates, _ = self._bm25_rank(query, types, limit)
        rrf_k = 60
        fused: Dict[str, float] = {}
        for rank, item in enumerate(vector_candidates):
            fused[item.knowledge_id] = fused.get(item.knowledge_id, 0.0) + 1.0 / (rrf_k + rank + 1)
        for rank, item in enumerate(bm25_candidates):
            fused[item.knowledge_id] = fused.get(item.knowledge_id, 0.0) + 1.0 / (rrf_k + rank + 1)
        ordered_ids = sorted(fused, key=lambda kid: fused[kid], reverse=True)[:limit]
        all_items = {item.knowledge_id: item for item in self._verified_items(types)}
        candidates = [all_items[kid] for kid in ordered_ids if kid in all_items]
        top = fused[ordered_ids[0]] if ordered_ids else 1.0
        proxy = {kid: fused[kid] / top for kid in ordered_ids}
        return candidates, proxy

    def get_by_slugs(self, slugs: List[str]) -> List[Dict[str, Any]]:
        """Deterministic grounding lookup (not semantic recall): fetch the
        current verified version of each slug referenced by a diagnosis."""
        if not slugs:
            return []
        rows = self.db.scalars(
            select(KnowledgeItem)
            .where(KnowledgeItem.slug.in_(slugs), KnowledgeItem.status == "verified")
            .order_by(KnowledgeItem.slug)
        ).all()
        return [
            {
                "knowledge_id": item.knowledge_id,
                "slug": item.slug,
                "version": item.version,
                "type": item.type,
                "industry": item.industry,
                "title": item.title,
                "content": item.content,
                "recommendation": item.recommendation,
                "evidence": item.evidence,
                "score": 1.0,
                "score_breakdown": {"grounded": 1.0},
            }
            for item in rows
        ]

    def _type_boost(self, query: str, ktype: str) -> float:
        for hint_type, triggers in _TYPE_HINTS.items():
            if any(trigger in query.lower() for trigger in triggers):
                return 1.0 if ktype == hint_type else 0.2
        return 0.5
