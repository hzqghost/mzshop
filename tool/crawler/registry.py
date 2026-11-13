"""平台 → 采集器 registry。懒加载，避免为其它平台引入不必要的依赖。"""
from base import BaseCollector, CollectError


def get_collector(platform: str) -> BaseCollector:
    p = (platform or "").strip().lower()
    if p == "ebay":
        from ebay.collector import EbayCollector
        return EbayCollector()
    raise CollectError(f"不支持的平台: {platform}")