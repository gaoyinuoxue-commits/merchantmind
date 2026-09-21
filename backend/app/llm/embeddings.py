"""Deterministic local embedder.

No external API and no training: text is tokenized into Latin words and CJK
character bigrams, hashed into a fixed-dimensional signed bag-of-features and
L2-normalized. Texts sharing domain vocabulary (ROI / 素材 / 疲劳 ...) end up
close, which is enough for the synthetic world and keeps pgvector retrieval
fully offline. Swap in an OpenAI-compatible embedder via EMBEDDING_PROVIDER
later without touching call sites.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import List, Sequence

from app.config.settings import get_settings

_CJK = re.compile(r"[\u4e00-\u9fff]")
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    lowered = text.lower()
    tokens = _TOKEN.findall(lowered)
    cjk = "".join(_CJK.findall(text))
    tokens.extend(cjk[i : i + 2] for i in range(len(cjk) - 1))
    if len(cjk) == 1:
        tokens.append(cjk)
    return tokens


class LocalEmbedder:
    def __init__(self, dim: int):
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dim
        tokens = tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]


_embedder = None


def get_embedder(provider: str = ""):
    """Return an embedder for the chosen provider.

    Providers share the ``embed / embed_batch / dim`` interface:
      - ``local`` : signed hash bag-of-features (256-d, offline, default)
      - ``bge``   : pretrained BAAI bge-small-zh-v1.5 via ONNX (512-d)
      - ``openai``: any OpenAI-compatible /embeddings endpoint (online)

    Memory vectors are stored as 256-d hashes, so memory callers request
    ``local`` explicitly; knowledge retrieval is free to choose any provider.
    """
    global _embedder
    selected = provider or get_settings().embedding_provider or "local"
    selected = selected.lower()
    if selected in ("local", "hash"):
        if _embedder is None:
            _embedder = LocalEmbedder(get_settings().embedding_dim)
        return _embedder
    if selected == "bge":
        from app.llm.bge_embedder import BgeEmbedder

        return BgeEmbedder()
    if selected == "openai":
        from app.llm.openai_embedder import OpenAIEmbedder

        settings = get_settings()
        return OpenAIEmbedder(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.openai_embedding_model,
        )
    raise ValueError(f"unknown embedding provider: {selected!r}")


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
