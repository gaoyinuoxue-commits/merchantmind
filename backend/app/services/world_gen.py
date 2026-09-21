"""Synthetic Merchant World generator (Phase 3).

Deterministic, event-driven generation: 10 merchants across 5 industries,
~120 products, ~30 campaigns, ~120 materials, 90 days of coherent daily
performance and a timeline of business events.

The daily metrics are *derived* from a small simulation state (active
materials fatigue with age, budget changes move spend and push CPM up,
seasonality and stage shape demand), not random.uniform(). Counts are
generated first; rate columns (ctr/cpm/cvr/aov/roi) are derived so stored
data is internally consistent for downstream diagnosis.

Everything here is SYNTHETIC. No real users, no real accounts.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.enums import (
    BusinessEventType as ET,
    CampaignStatus,
    EventSource,
    MaterialStatus,
    MaterialType,
    ProductStatus,
)

WINDOW_DAYS = 90
END_DATE = date(2026, 9, 12)
START_DATE = END_DATE - timedelta(days=WINDOW_DAYS - 1)

MATERIAL_TYPES = [
    MaterialType.VIDEO,
    MaterialType.SHORT_VIDEO,
    MaterialType.IMAGE,
    MaterialType.CAROUSEL,
    MaterialType.COPY,
]

INDUSTRY_CONFIG: Dict[str, Dict[str, Any]] = {
    "womenswear": {
        "cpm": 22.0, "aov": 260.0, "margin": 0.30,
        "categories": ["连衣裙", "衬衫", "针织衫", "外套", "T恤", "半裙"],
        "product_names": ["法式碎花连衣裙", "基础款白衬衫", "软糯针织开衫", "通勤西装外套",
                          "纯棉短袖T恤", "高腰百褶半裙", "风衣式大衣", "修身牛仔裤"],
    },
    "beauty": {
        "cpm": 28.0, "aov": 180.0, "margin": 0.45,
        "categories": ["面膜", "精华", "口红", "洁面", "防晒"],
        "product_names": ["玻尿酸补水面膜", "烟酰胺精华液", "丝绒哑光口红", "氨基酸洁面乳",
                          "清透防晒霜", "修护眼霜", "保湿面霜", "卸妆油"],
    },
    "food": {
        "cpm": 14.0, "aov": 65.0, "margin": 0.25,
        "categories": ["坚果", "零食礼盒", "代餐", "茶饮", "调味品"],
        "product_names": ["每日坚果礼盒", "低脂代餐棒", "冷萃乌龙茶包", "0卡气泡水",
                          "秘制火锅底料", "手撕面包", "坚果燕麦片", "卤味大礼包"],
    },
    "home": {
        "cpm": 16.0, "aov": 120.0, "margin": 0.30,
        "categories": ["床品", "收纳", "厨具", "灯饰", "清洁"],
        "product_names": ["60支长绒棉四件套", "抽屉式收纳箱", "不粘炒锅", "北欧台灯",
                          "酵素清洁剂", "记忆棉枕头", "折叠晾衣架", "真空保鲜盒"],
    },
    "electronics": {
        "cpm": 26.0, "aov": 320.0, "margin": 0.18,
        "categories": ["耳机", "小家电", "配件", "智能设备"],
        "product_names": ["主动降噪蓝牙耳机", "桌面加湿器", "快充数据线", "智能手环",
                          "便携榨汁杯", "机械键盘", "磁吸充电宝", "迷你投影仪"],
    },
}

MERCHANT_BLUEPRINTS: List[Dict[str, Any]] = [
    ("M001", "花间女装旗舰店", "womenswear", "growth", "100w+", "杭州", "fatigue_budget"),
    ("M002", "素笺女装专营店", "womenswear", "declining", "50w-100w", "广州", "season_decline"),
    ("M003", "肌研美学美妆店", "beauty", "growth", "100w+", "上海", "new_product_growth"),
    ("M004", "成分党美妆社", "beauty", "mature", "50w-100w", "深圳", "traffic_cost"),
    ("M005", "山野食光食品店", "food", "mature", "10w-50w", "成都", "stable"),
    ("M006", "轻卡厨房食品店", "food", "new", "1w-10w", "武汉", "new_product_growth"),
    ("M007", "木里家居生活馆", "home", "mature", "50w-100w", "佛山", "stable"),
    ("M008", "净屋收纳家居店", "home", "growth", "10w-50w", "义乌", "fatigue_budget"),
    ("M009", "极客数码配件店", "electronics", "growth", "100w+", "深圳", "traffic_cost"),
    ("M010", "智居小电旗舰店", "electronics", "declining", "10w-50w", "苏州", "season_decline"),
]

CAMPAIGN_NAMES = ["引流拉新计划", "爆款转化计划", "品类种草计划", "大促冲刺计划", "老客复购计划"]
MATERIAL_THEMES = ["痛点开场", "使用场景", "达人测评", "对比实验", "开箱展示",
                   "买家秀合集", "工艺细节", "限时福利", "剧情反转", "口碑证言"]


def _dt(day_index: int, hour: int = 10) -> datetime:
    return datetime.combine(START_DATE + timedelta(days=day_index), time(hour, 0), tzinfo=timezone.utc)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class _MerchantWorld:
    """Holds generated rows and the evolving state for one merchant."""

    def __init__(self, idx: int, blueprint: Tuple, rng: random.Random):
        (self.mid, name, industry, stage, gmv_level, city, self.archetype) = blueprint
        self.cfg = INDUSTRY_CONFIG[industry]
        self.rng = rng
        base = {
            "merchant_id": self.mid, "merchant_name": name, "industry": industry,
            "sub_industry": self.cfg["categories"][0], "business_stage": stage,
            "gmv_level": gmv_level, "city": city,
        }
        self.merchant = base
        self.industries: List[Dict[str, Any]] = [{
            "merchant_id": self.mid, "industry": industry,
            "sub_industry": self.cfg["categories"][0], "is_primary": True,
        }]
        if rng.random() < 0.5:
            secondary = rng.choice([c for c in self.cfg["categories"][1:3]])
            self.industries.append({
                "merchant_id": self.mid, "industry": industry,
                "sub_industry": secondary, "is_primary": False,
            })
        self.products: List[Dict[str, Any]] = []
        self.campaigns: List[Dict[str, Any]] = []
        self.materials: List[Dict[str, Any]] = []
        self.performance: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self._seq = 0
        self.aov = self.cfg["aov"] * rng.uniform(0.9, 1.1)
        self.margin = self.cfg["margin"]
        self.base_cvr = _clamp(rng.uniform(0.032, 0.055), 0.02, 0.08)
        self.base_daily_spend = rng.uniform(900.0, 2600.0)

    def eid(self) -> str:
        self._seq += 1
        return f"E{self.mid[1:]}{self._seq:04d}"

    def add_event(self, day: int, etype: ET, desc: str,
                  data: Optional[Dict[str, Any]] = None,
                  source: EventSource = EventSource.SIMULATOR) -> None:
        self.events.append({
            "event_id": self.eid(), "merchant_id": self.mid, "event_type": etype.value,
            "event_time": _dt(day, self.rng.randint(8, 20)), "description": desc,
            "structured_data": data or {}, "source": source.value,
        })

    def build_catalog(self) -> None:
        names = self.cfg["product_names"]
        cats = self.cfg["categories"]
        for i in range(12):
            launch_day = self.rng.choice(
                [-40, -20, -5, 0, 2, 6, 12, 20, 28, 36, 48, 60]
            )
            price = round(self.aov * self.rng.uniform(0.35, 1.6), 1)
            cost = round(price * self.rng.uniform(0.45, 0.7), 1)
            if launch_day > 0:
                status = ProductStatus.ON_SALE.value
            elif i in (9, 11):
                status = self.rng.choice(
                    [ProductStatus.PAUSED, ProductStatus.OUT_OF_STOCK, ProductStatus.ARCHIVED]
                ).value
            else:
                status = ProductStatus.ON_SALE.value
            self.products.append({
                "product_id": f"P{self.mid[1:]}{i + 1:02d}",
                "merchant_id": self.mid,
                "product_name": f"{names[i % len(names)]}·{self.cfg['categories'][i % len(cats)]}",
                "category": cats[i % len(cats)],
                "price": price, "cost": cost,
                "inventory": self.rng.choice([0, 80, 200, 500, 1200, 3000]),
                "sales": self.rng.randint(50, 4000),
                "conversion_rate": round(self.base_cvr * self.rng.uniform(0.7, 1.3), 4),
                "status": status,
                "_launch_day": launch_day,
            })
        launched = [p for p in self.products if 0 < p["_launch_day"] <= WINDOW_DAYS - 1]
        for p in sorted(launched, key=lambda x: x["_launch_day"]):
            self.add_event(
                p["_launch_day"], ET.NEW_PRODUCT,
                f"新品上架：{p['product_name']}，售价 ¥{p['price']}",
                {"product_id": p["product_id"], "price": p["price"]},
            )

    def build_campaigns(self) -> None:
        starts = [0, 28, 56]
        budgets = [self.base_daily_spend * 30 * f for f in (1.0, 0.7, 0.5)]
        for i, (start, budget) in enumerate(zip(starts, budgets)):
            cid = f"C{self.mid[1:]}{i + 1:02d}"
            status = CampaignStatus.ACTIVE.value
            pause_day: Optional[int] = None
            if self.archetype == "stable" and i == 2:
                status = CampaignStatus.PAUSED.value
                pause_day = 75
                self.add_event(pause_day, ET.CAMPAIGN_PAUSE,
                               f"暂停「{CAMPAIGN_NAMES[i]}」观察效果",
                               {"campaign_id": cid})
            if self.archetype == "season_decline" and i == 1:
                pause_day = 70
                self.add_event(pause_day, ET.CAMPAIGN_PAUSE,
                               f"转化持续下滑，暂停「{CAMPAIGN_NAMES[i]}」",
                               {"campaign_id": cid})
                self.add_event(80, ET.CAMPAIGN_RESTART,
                               f"更换素材后重启「{CAMPAIGN_NAMES[i]}」",
                               {"campaign_id": cid})
            self.campaigns.append({
                "campaign_id": cid, "merchant_id": self.mid,
                "campaign_name": f"{self.merchant['merchant_name']}·{CAMPAIGN_NAMES[i]}",
                "objective": ["traffic", "conversion", "product_sales"][i],
                "budget": round(budget, 1), "status": status,
                "_start": start, "_pause_day": pause_day,
            })

    def build_materials(self) -> None:
        for ci, camp in enumerate(self.campaigns):
            count = 5
            for mi in range(count):
                start = camp["_start"] + mi * 18 + self.rng.randint(-3, 3)
                mtype = MATERIAL_TYPES[(ci * 2 + mi) % len(MATERIAL_TYPES)]
                mid = f"MT{self.mid[1:]}{ci + 1:02d}{mi + 1:02d}"
                status = MaterialStatus.ACTIVE.value
                age = WINDOW_DAYS - 1 - start
                if start > WINDOW_DAYS - 1:
                    continue
                if age > 45:
                    status = MaterialStatus.ARCHIVED.value
                elif age > 24:
                    status = MaterialStatus.FATIGUED.value
                self.materials.append({
                    "material_id": mid, "campaign_id": camp["campaign_id"],
                    "merchant_id": self.mid, "material_type": mtype.value,
                    "material_name": f"{MATERIAL_THEMES[(ci * 4 + mi) % len(MATERIAL_THEMES)]}"
                                     f"·{self.cfg['categories'][mi % len(self.cfg['categories'])]}",
                    "status": status, "_start": start,
                    "_ctr_base": _clamp(self.rng.uniform(0.018, 0.042), 0.01, 0.06),
                })
                if 0 <= start <= WINDOW_DAYS - 1:
                    self.add_event(
                        start, ET.NEW_MATERIAL,
                        f"新增{mtype.value}素材：{self.materials[-1]['material_name']}",
                        {"material_id": mid, "campaign_id": camp["campaign_id"],
                         "material_type": mtype.value},
                    )
                fatigue_day = start + 9
                if 0 <= fatigue_day <= WINDOW_DAYS - 1 and age > 14:
                    self.add_event(
                        fatigue_day, ET.MATERIAL_FATIGUE,
                        f"素材 {mid} 连续投放 9 天，CTR 开始衰减，疑似素材疲劳",
                        {"material_id": mid, "campaign_id": camp["campaign_id"]},
                    )

    def _scenario_events(self) -> Dict[int, Dict[str, float]]:
        """Archetype-scripted events; returns day -> spend/cpm/cvr multipliers."""
        mods: Dict[int, Dict[str, float]] = {}

        def apply(day: int, **delta: float) -> None:
            mods[day] = delta

        if self.archetype == "fatigue_budget":
            self.add_event(58, ET.SALES_DECLINE, "近一周 GMV 环比下滑，核心素材点击疲软",
                           {"wow": -0.12})
            self.add_event(62, ET.BUDGET_CHANGE,
                           f"将「{self.campaigns[1]['campaign_name']}」日预算上调 50% 试图拉量",
                           {"campaign_id": self.campaigns[1]["campaign_id"],
                            "change_pct": 0.5})
            apply(62, spend=1.5, cpm=1.18)
            self.add_event(70, ET.TRAFFIC_COST_INCREASE,
                           "行业流量竞争加剧，CPM 持续走高", {"cpm_change_pct": 0.18})
            apply(70, cpm=1.12)
            self.add_event(74, ET.CONVERSION_DECLINE,
                           "进店转化下滑，流量精准度下降", {"cvr_change_pct": -0.1})
            apply(74, cvr=0.9)
        elif self.archetype == "season_decline":
            self.add_event(55, ET.SEASON_CHANGE, "季节切换，应季品类需求回落",
                           {"season": "换季"})
            apply(55, demand=0.85, cvr=0.92)
            self.add_event(66, ET.CONVERSION_DECLINE, "换季清库存，CVR 连续走低",
                           {"cvr_change_pct": -0.08})
            apply(66, cvr=0.92)
        elif self.archetype == "new_product_growth":
            self.add_event(40, ET.NEW_PRODUCT, "主推新品进入放量期", {"phase": "ramp"})
            apply(40, demand=1.12)
            self.add_event(58, ET.SALES_GROWTH, "新品爆款带动 GMV 周环比增长 25%",
                           {"wow": 0.25})
            apply(58, spend=1.25, demand=1.15)
            self.add_event(72, ET.INVENTORY_CHANGE, "爆款紧急补货 2000 件",
                           {"sku": "flagship", "delta": 2000})
        elif self.archetype == "traffic_cost":
            self.add_event(60, ET.TRAFFIC_COST_INCREASE,
                           "平台流量政策调整，整体 CPM 上行约 20%", {"cpm_change_pct": 0.2})
            apply(60, cpm=1.2)
            self.add_event(72, ET.SALES_DECLINE, "成本上升压缩投产，ROI 明显下降",
                           {"roi_change_pct": -0.18})
        else:  # stable
            self.add_event(50, ET.SEASON_CHANGE, "需求平稳，维持常规投放节奏",
                           {"season": "常规"})
            self.add_event(68, ET.INVENTORY_CHANGE, "常规补货，库存健康",
                           {"delta": 500})
        return mods

    def build_performance(self) -> None:
        scenario = self._scenario_events()
        stage_trend = {
            "growth": 0.0015, "new": 0.0035, "mature": 0.0, "declining": -0.002,
        }[self.merchant["business_stage"]]
        spend_m = cpm_m = cvr_m = demand_m = 1.0
        ctr_floor = 0.55

        for day in range(WINDOW_DAYS):
            if day in scenario:
                delta = scenario[day]
                spend_m *= delta.get("spend", 1.0)
                cpm_m *= delta.get("cpm", 1.0)
                cvr_m *= delta.get("cvr", 1.0)
                demand_m *= delta.get("demand", 1.0)

            active_campaigns = [
                c for c in self.campaigns
                if day >= c["_start"] and not (c["_pause_day"] and day >= c["_pause_day"])
            ]
            if not active_campaigns:
                spend = self.base_daily_spend * 0.35
            else:
                share = sum(
                    1.0 / (1.0 + (i + 1)) for i, _ in enumerate(active_campaigns)
                )
                spend = self.base_daily_spend * spend_m * share
            spend *= self.rng.uniform(0.96, 1.04)

            effective_ctr = 0.0
            active_materials = [m for m in self.materials if m["_start"] <= day]
            if active_materials:
                ctrs = []
                for m in active_materials:
                    age = day - m["_start"]
                    fatigue = 1.0 / (1.0 + max(0, age - 7) / 12.0)
                    ctrs.append(m["_ctr_base"] * _clamp(fatigue, ctr_floor, 1.0))
                effective_ctr = sum(ctrs) / len(ctrs)
            else:
                effective_ctr = self.rng.uniform(0.012, 0.02)

            weekend = 1.18 if (START_DATE + timedelta(days=day)).weekday() >= 5 else 1.0
            trend = 1.0 + stage_trend * day
            cpm = self.cfg["cpm"] * cpm_m * self.rng.uniform(0.97, 1.03)
            cvr = self.base_cvr * cvr_m * self.rng.uniform(0.97, 1.03)

            impressions = max(1000, int(spend / cpm * 1000))
            clicks = max(10, int(impressions * effective_ctr))
            conv_rate = _clamp(cvr * demand_m * trend * weekend, 0.005, 0.12)
            conversions = int(clicks * conv_rate)
            gmv = round(conversions * self.aov * self.rng.uniform(0.98, 1.02), 2)
            self.performance.append({
                "merchant_id": self.mid,
                "date": (START_DATE + timedelta(days=day)).isoformat(),
                "gmv": gmv,
                "ad_spend": round(spend, 2),
                "impressions": impressions,
                "clicks": clicks,
                "ctr": round(clicks / impressions, 5),
                "cpm": round(spend / impressions * 1000, 3),
                "conversions": conversions,
                "cvr": round(conversions / clicks, 5),
                "aov": round(gmv / conversions, 2) if conversions else round(self.aov, 2),
                "roi": round(gmv * self.margin / spend, 3) if spend > 0 else 0.0,
            })


def world_dataset() -> Dict[str, List[Dict[str, Any]]]:
    """Generate the full deterministic synthetic world."""
    worlds = [_MerchantWorld(i, bp, random.Random(20260913 + i))
              for i, bp in enumerate(MERCHANT_BLUEPRINTS)]

    dataset: Dict[str, List[Dict[str, Any]]] = {
        "merchants": [], "merchant_industries": [], "products": [], "campaigns": [],
        "materials": [], "performance_daily": [], "business_events": [],
    }
    for w in worlds:
        w.build_catalog()
        w.build_campaigns()
        w.build_materials()
        w.build_performance()
        dataset["merchants"].append(w.merchant)
        dataset["merchant_industries"].extend(w.industries)
        dataset["products"].extend(w.products)
        dataset["campaigns"].extend(w.campaigns)
        dataset["materials"].extend(w.materials)
        dataset["performance_daily"].extend(w.performance)
        dataset["business_events"].extend(
            sorted(w.events, key=lambda e: (e["event_time"], e["event_id"]))
        )

    for rows in (dataset["products"], dataset["campaigns"], dataset["materials"]):
        for row in rows:
            row.pop("_launch_day", None)
            row.pop("_start", None)
            row.pop("_pause_day", None)
            row.pop("_ctr_base", None)
    return dataset


WORLD_META = {
    "label": "SYNTHETIC",
    "window_days": WINDOW_DAYS,
    "start_date": START_DATE.isoformat(),
    "end_date": END_DATE.isoformat(),
    "merchants": len(MERCHANT_BLUEPRINTS),
}
