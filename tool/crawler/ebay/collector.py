"""eBay 采集器（契约 §3 统一接口）。

分类与左侧属性值都在运行时从搜索页 refine 区读取，并复用 eBay 自己的筛选 href（含 _sacat/aspect 参数）。
httpx 快路径 + Playwright 兜底，限速/退避在 FetchSession 内统一处理。
"""
import logging
from urllib.parse import quote

import config
from base import BaseCollector
from ebay import parse
from ebay.browser import FetchSession
from ebay.parse import item_id_from_url

log = logging.getLogger("crawler.ebay")


class EbayCollector(BaseCollector):
    platform = "ebay"

    def __init__(self):
        self._fetch = FetchSession()
        self._base = config.EBAY_BASE
        self._cat_href: dict[str, str] = {}
        self._aspect_href: dict[tuple[str, str], str] = {}
        self._last_item_id = ""
        self._last_html = ""

    def close(self):
        self._fetch.close()

    def _keyword_url(self, task, page: int = 1) -> str:
        return f"{self._base}/sch/i.html?_nkw={quote(task.keyword or '')}&_pgn={page}"

    def _resolve_category(self, task, category: str) -> str:
        """从关键字搜索页的 Category facet 解析分类筛选 href；解析不到则退回关键字搜索（局限见 TODO）。"""
        if category in self._cat_href:
            return self._cat_href[category]
        html = self._fetch.fetch_html(self._keyword_url(task), wait_selector=".x-refine__item, li.s-item")
        href = ""
        for o in parse.parse_refine_options(html, "Category", self._base):
            if o["value"].strip().lower() == category.strip().lower():
                href = o["href"]
                break
        if not href:
            log.warning("未能从 facet 解析分类「%s」的筛选链接，退回关键字搜索", category)
            href = self._keyword_url(task)
        self._cat_href[category] = href
        return href

    def list_attr_values(self, task, category: str) -> list[str]:
        if not task.attr_name:
            return [""]
        cat_url = self._resolve_category(task, category)
        html = self._fetch.fetch_html(cat_url, wait_selector=".x-refine__item, li.s-item")
        opts = parse.parse_refine_options(html, task.attr_name, self._base)
        for o in opts:
            if o["href"]:
                self._aspect_href[(category, o["value"])] = o["href"]
        return [o["value"] for o in opts]

    def _search_url(self, task, category: str, attr_value: str, page: int) -> str:
        if attr_value and (category, attr_value) in self._aspect_href:
            url = self._aspect_href[(category, attr_value)]
        elif attr_value:
            url = self._resolve_category(task, category) + f"&{quote(task.attr_name)}={quote(attr_value)}"
        elif category:
            url = self._resolve_category(task, category)
        else:
            url = self._keyword_url(task)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}_pgn={page}"

    def search(self, task, category: str, attr_value: str, page: int) -> list[dict]:
        url = self._search_url(task, category, attr_value, page)
        html = self._fetch.fetch_html(url, wait_selector="li.s-item, .srp-results")
        return parse.parse_search(html, self._base)

    def parse_item(self, stub: dict, task, category: str, attr_value: str) -> dict:
        url = stub.get("product_url") or f"{self._base}/itm/{stub.get('item_id')}"
        html = self._fetch.fetch_html(url, wait_selector="h1, .x-item-title__mainTitle")
        self._last_item_id = str(stub.get("item_id") or item_id_from_url(url))
        self._last_html = html  # 供紧随其后的 fetch_reviews 复用，避免重复请求
        item = parse.parse_item_detail(html, url, self._base)
        for k in ("title", "price", "currency", "image_url"):
            if not item.get(k) and stub.get(k):
                item[k] = stub[k]
        item["platform"] = task.platform
        item["item_id"] = self._last_item_id
        item["category_name"] = (category or "")[:200]
        if task.attr_name and attr_value:
            item["search_attrs"] = {task.attr_name: attr_value}
            attrs = dict(item.get("attributes") or {})
            attrs.pop(task.attr_name, None)  # 遍历属性归 search_attrs，不进 attributes（契约 §2.1）
            item["attributes"] = attrs or None
        else:
            item["search_attrs"] = None
        return item

    def fetch_reviews(self, item: dict) -> list[dict]:
        item_id = str(item.get("item_id") or "")
        if item_id and item_id == self._last_item_id and self._last_html:
            html = self._last_html
        else:
            url = item.get("product_url")
            if not url:
                return []
            html = self._fetch.fetch_html(url, wait_selector="h1")
        return parse.parse_reviews(html)