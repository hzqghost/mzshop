"""eBay 页面解析：搜索结果卡、左侧 facet 属性值、商品详情（JSON-LD 优先）、评价。

eBay  markup 随版本变化，这里用「JSON-LD 优先 + 多组 CSS 兜底」尽量稳健；
取不到的数值存 None、文本存空串（契约 §2.4）。选择器需在有浏览器环境的网络下校准（见 TODO.md）。
"""
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# 单独成列的 Item Specifics（其余进 attributes）；键按小写匹配
_SPECIFIC_TO_COLUMN = {
    "brand": "brand",
    "mpn": "mpn",
    "manufacturer part number": "mpn",
    "upc": "upc",
    "ean": "upc",
    "gtin": "upc",
    "country/region of manufacture": "country_of_origin",
    "country of origin": "country_of_origin",
    "country/region of origin": "country_of_origin",
    "listing type": "listing_type",
}
_CONDITION_MAP = {
    "newcondition": "New", "new": "New", "usedcondition": "Pre-owned",
    "used": "Pre-owned", "pre-owned": "Pre-owned", "openbox": "Open box",
    "refurbished": "Refurbished", "forparts": "For parts or not working",
}
_CURRENCY_MAP = [
    ("US $", "USD"), ("USD", "USD"), ("$", "USD"), ("£", "GBP"), ("GBP", "GBP"),
    ("€", "EUR"), ("EUR", "EUR"), ("C $", "CAD"), ("CAD", "CAD"),
    ("AU $", "AUD"), ("AUD", "AUD"), ("¥", "JPY"), ("JPY", "JPY"),
]


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def text(node) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def select_first(root, *selectors):
    for sel in selectors:
        node = root.select_one(sel)
        if node is not None:
            return node
    return None


def decimal_from(s: str) -> Decimal | None:
    if not s:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", s.replace("\xa0", " "))
    if not m:
        return None
    try:
        return Decimal(m.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def currency_from(s: str) -> str:
    if not s:
        return ""
    for token, code in _CURRENCY_MAP:
        if token in s:
            return code
    m = re.search(r"\b([A-Z]{3})\b", s)
    return m.group(1) if m else ""


def int_from(s: str) -> int | None:
    if not s:
        return None
    m = re.search(r"\d[\d,]*", s)
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None


def abs_url(href: str, base: str) -> str:
    return urljoin(base, href) if href else ""


def item_id_from_url(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"/itm/(?:[^/?#]+/)?(\d{6,})", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&](?:item|item_id|iid)=(\d{6,})", url)
    return m.group(1) if m else ""


def json_ld_blocks(root) -> list[dict]:
    out: list[dict] = []
    for sc in root.select('script[type="application/ld+json"]'):
        raw = sc.string or sc.get_text() or ""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                out.append(cur)
                if isinstance(cur.get("@graph"), list):
                    stack.extend(cur["@graph"])
    return out


def find_product_ld(blocks: list[dict]) -> dict:
    for b in blocks:
        t = b.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(x in ("Product", "IndividualProduct", "ProductGroup") for x in types if x):
            return b
    return {}


def make_review_key(reviewer: str, reviewed, content: str, rid: str = "") -> str:
    if rid:
        return str(rid)[:64]
    basis = f"{reviewer}|{reviewed}|{content}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:64]


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    s = s.strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d %b %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_search(html: str, base: str) -> list[dict]:
    """搜索结果卡 → stub 列表（item_id/product_url/title/price/currency/image_url）。"""
    root = soup(html)
    cards = root.select("li.s-item, div.s-item__wrapper, .srp-results .s-item")
    stubs: list[dict] = []
    seen = set()
    for card in cards:
        a = select_first(card, "a.s-item__link", "a[href*='/itm/']")
        href = abs_url(a.get("href") if a else "", base)
        item_id = item_id_from_url(href)
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        title_node = select_first(card, ".s-item__title span[role='text']", ".s-item__title", "h3")
        title = text(title_node)
        title = re.sub(r"^New Listing\s*", "", title).strip()
        price_node = select_first(card, ".s-item__price")
        price_text = text(price_node)
        img = select_first(card, ".s-item__image img", "img")
        stubs.append({
            "item_id": item_id,
            "product_url": href.split("?")[0],
            "title": title[:500],
            "price": decimal_from(price_text),
            "currency": currency_from(price_text),
            "image_url": abs_url((img.get("src") or img.get("data-src") or "") if img else "", base)[:500],
        })
    return stubs


def parse_refine_options(html: str, name: str, base: str) -> list[dict]:
    """读取搜索页左侧某个 refine 组（如 Category / Fragrance Name）的选项：{value, href}。

    href 是 eBay 自己的筛选链接（含 _sacat / aspect 参数），优先复用它而非猜测 URL 参数。
    """
    root = soup(html)
    want = (name or "").strip().lower()
    if not want:
        return []
    out: list[dict] = []
    for group in root.select(".x-refine__item, .srp-refine__item, .refine__item"):
        title_node = select_first(group, ".x-refine__main__title--value", ".x-refine__main__title", "h3", ".refine__title")
        if want not in text(title_node).lower():
            continue
        for opt in group.select(".x-refine__main__value, .x-refine__value, li"):
            a = opt.select_one("a[href]") or (opt if opt.name == "a" and opt.get("href") else None)
            label = text(select_first(opt, "label", "span.x-refine__value__label", "a")) or text(opt)
            label = re.sub(r"\(\d[\d,]*\)\s*$", "", label).strip()  # 去掉计数 "(123)"
            if not label or label.lower() == want:
                continue
            out.append({"value": label[:200], "href": abs_url(a.get("href"), base) if a else ""})
    seen = set()
    res = []
    for o in out:
        if o["value"] not in seen:
            seen.add(o["value"])
            res.append(o)
    return res


def _parse_specifics(root) -> dict:
    specifics: dict[str, str] = {}
    rows = root.select(".ux-layout-section-evo__item, .ux-layout-section__item")
    for row in rows:
        label = select_first(row, ".ux-labels-values__labels")
        value = select_first(row, ".ux-labels-values__values")
        k, v = text(label), text(value)
        if k and v:
            specifics[k.rstrip(":").strip()] = v
    if not specifics:
        for row in root.select("#itemSpecifics tr, .itemSpecifics tr, .ux-labels-values"):
            label = select_first(row, ".ux-labels-values__labels", "td.attrLabels", "th")
            value = select_first(row, ".ux-labels-values__values", "td.attrValues", "td")
            k, v = text(label), text(value)
            if k and v:
                specifics[k.rstrip(":").strip()] = v
    return specifics


def parse_item_detail(html: str, url: str, base: str) -> dict:
    """商品详情 → 统一 product 字段字典（不含 platform/item_id/category_name/search_attrs，由 collector 补）。"""
    root = soup(html)
    blocks = json_ld_blocks(root)
    ld = find_product_ld(blocks)
    offers = ld.get("offers") if isinstance(ld.get("offers"), dict) else (
        ld.get("offers")[0] if isinstance(ld.get("offers"), list) and ld.get("offers") else {}
    )
    offers = offers or {}
    specifics = _parse_specifics(root)

    title = str(ld.get("name") or "") or text(select_first(root, "h1.x-item-title__mainTitle span", "h1#itemTitle", "h1"))
    image = ld.get("image")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl") or ""
    if not image:
        img_node = select_first(root, ".x-image-carousel img", "#icImg")
        image = abs_url(img_node.get("src") or img_node.get("data-src") or "", base) if img_node else ""
    image = str(image or "")

    brand = ""
    if isinstance(ld.get("brand"), dict):
        brand = str(ld.get("brand", {}).get("name") or "")
    elif isinstance(ld.get("brand"), str):
        brand = ld["brand"]

    condition_raw = str(offers.get("itemCondition") or "")
    condition = _CONDITION_MAP.get(condition_raw.rsplit("/", 1)[-1].lower(), "")
    if not condition:
        condition = text(select_first(root, ".x-item-condition-label span", "#vi-itm-cond"))

    price = decimal_from(str(offers.get("price") or "")) if offers.get("price") is not None else None
    price_text = text(select_first(root, ".x-price-primary span", "#prcIsum", ".x-price-primary"))
    if price is None:
        price = decimal_from(price_text)
    currency = str(offers.get("priceCurrency") or "") or currency_from(price_text)

    original_price = decimal_from(text(select_first(root, ".x-price__original span", ".x-price__original", "#prcIsumOrig")))
    shipping_text = text(select_first(root, ".x-shipping__message", "#fshippingCost", ".ux-labels-values__values [class*='shipping']"))
    if re.search(r"\bfree\b", shipping_text, re.I):
        shipping_price = Decimal("0")
    else:
        shipping_price = decimal_from(shipping_text)

    agg = ld.get("aggregateRating") if isinstance(ld.get("aggregateRating"), dict) else {}
    review_avg = decimal_from(str(agg.get("ratingValue") or "")) if agg else None
    review_count = int_from(str(agg.get("reviewCount") or agg.get("ratingCount") or "")) if agg else None

    sold_text = text(select_first(root, ".x-sold-count span", ".x-sold-count", "span.vi-qty-hotbid"))
    sold_count = int_from(sold_text) if re.search(r"sold", sold_text, re.I) else None
    watcher_text = text(select_first(root, ".x-watch-count span", ".x-watch-count", ".vi-VR-watchCnt"))
    watcher_count = int_from(watcher_text)
    view_text = text(select_first(root, ".x-view-count span", ".x-view-count"))
    view_count = int_from(view_text)
    qty_text = text(select_first(root, ".x-quantity__availability", "#qtySubTxt", ".ux-labels-values__values [class*='quantity']"))
    available_qty = int_from(qty_text)

    seller_name = text(select_first(root, ".ux-seller-info__name span", ".ux-seller-info__name", ".mbg vi-VR-mtbMgr a span", "#mbgLink span"))
    seller_text = text(select_first(root, ".ux-seller-info__feedback", ".ux-seller-info", "#si-fbFeedback"))
    pct_m = re.search(r"([\d.]+)\s*%", seller_text)
    seller_feedback_pct = Decimal(pct_m.group(1)) if pct_m else None
    cnt_m = re.search(r"\(([\d,]+)\)", seller_text)
    seller_feedback_cnt = int_from(cnt_m.group(1)) if cnt_m else None
    item_location = text(select_first(root, ".ux-labels-values__values [class*='location']", "#vi-VR-mtbMgr-itmLoc")) or specifics.get("Located in", "")

    buy_box = text(select_first(root, ".x-buy-box", ".vi-buy-box", "#vi-wide-body"))
    if re.search(r"buy it now", buy_box, re.I):
        listing_type = "Buy It Now"
    elif re.search(r"auction|\bbid\b|\bbids\b", buy_box, re.I):
        listing_type = "Auction"
    else:
        listing_type = specifics.get("Listing Type", "")

    # 分层：已知公共属性单独成列，其余进 attributes
    attributes = dict(specifics)
    mapped = {
        "brand": brand or specifics.get("Brand", ""),
        "mpn": str(ld.get("mpn") or "") or specifics.get("MPN", ""),
        "upc": str(ld.get("gtin12") or ld.get("gtin") or ld.get("isbn") or "") or specifics.get("UPC", "") or specifics.get("EAN", "") or specifics.get("GTIN", ""),
        "country_of_origin": specifics.get("Country/Region of Manufacture", "") or specifics.get("Country of Origin", ""),
    }
    for k in list(attributes):
        col = _SPECIFIC_TO_COLUMN.get(k.lower())
        if col:
            if not mapped.get(col):
                mapped[col] = attributes[k]
            del attributes[k]
    if not condition:
        condition = specifics.get("Condition", "")
    attributes.pop("Condition", None)

    return {
        "title": (title or "")[:500],
        "product_url": (url or "")[:500],
        "image_url": (image or "")[:500],
        "brand": mapped["brand"][:100],
        "item_condition": (condition or specifics.get("Condition", ""))[:50],
        "mpn": mapped["mpn"][:100],
        "upc": mapped["upc"][:50],
        "country_of_origin": mapped["country_of_origin"][:100],
        "listing_type": (listing_type or "")[:30],
        "price": price,
        "currency": (currency or "")[:3],
        "shipping_price": shipping_price,
        "original_price": original_price,
        "view_count": view_count,
        "watcher_count": watcher_count,
        "sold_count": sold_count,
        "available_qty": available_qty,
        "review_count": review_count,
        "review_avg": review_avg,
        "seller_name": (seller_name or "")[:100],
        "seller_feedback_pct": seller_feedback_pct,
        "seller_feedback_cnt": seller_feedback_cnt,
        "item_location": (item_location or "")[:100],
        "attributes": attributes or None,
    }


def parse_reviews(html: str) -> list[dict]:
    """商品评价（review_type=product）。JSON-LD review 优先，CSS 兜底。卖家反馈见 TODO。"""
    root = soup(html)
    ld = find_product_ld(json_ld_blocks(root))
    reviews: list[dict] = []
    ld_reviews = ld.get("review") if isinstance(ld.get("review"), list) else ([ld["review"]] if ld.get("review") else [])
    for r in ld_reviews:
        if not isinstance(r, dict):
            continue
        author = r.get("author")
        reviewer = str(author.get("name") if isinstance(author, dict) else author or "")[:100]
        rating_obj = r.get("reviewRating") if isinstance(r.get("reviewRating"), dict) else {}
        rating = int_from(str(rating_obj.get("ratingValue") or ""))
        content = str(r.get("reviewBody") or r.get("description") or "")
        reviewed = _parse_date(str(r.get("datePublished") or ""))
        title = str(r.get("name") or "")[:300]
        reviews.append({
            "review_type": "product",
            "review_key": make_review_key(reviewer, reviewed, content, str(r.get("@id") or r.get("identifier") or "")),
            "reviewer_name": reviewer,
            "rating": rating if rating and 1 <= rating <= 5 else None,
            "title": title,
            "content": content or None,
            "reviewed_at": reviewed,
            "helpful_count": int_from(str(r.get("positiveFeedbackCount") or "")) or 0,
            "is_verified": 0,
        })
    if reviews:
        return reviews
    for node in root.select("[data-hook='review'], .review-item, .x-review-details__item"):
        reviewer = text(select_first(node, ".review-author, [data-hook='review-author']"))[:100]
        content = text(select_first(node, ".review-content, [data-hook='review-body']"))
        rating = int_from(text(select_first(node, ".review-rating, [data-hook='review-star-rating']")))
        reviewed = _parse_date(text(select_first(node, ".review-date, [data-hook='review-date']")))
        title = text(select_first(node, ".review-title, [data-hook='review-title']"))[:300]
        if not (reviewer or content):
            continue
        reviews.append({
            "review_type": "product",
            "review_key": make_review_key(reviewer, reviewed, content),
            "reviewer_name": reviewer,
            "rating": rating if rating and 1 <= rating <= 5 else None,
            "title": title,
            "content": content or None,
            "reviewed_at": reviewed,
            "helpful_count": 0,
            "is_verified": 1 if re.search(r"verified", text(node), re.I) else 0,
        })
    return reviews