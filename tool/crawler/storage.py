"""落库：product 覆盖更新（保留 first_crawled_at）、snapshot 追加、review 去重更新。"""
from datetime import datetime

from sqlalchemy import select

from base import CollectError
from models import Product, ProductReview, ProductSnapshot

_PRODUCT_COLS = {c.name for c in Product.__table__.columns}
# 这些列由采集器显式管理，不接受 item 字典覆盖
_PROTECTED = {"id", "platform", "item_id", "first_crawled_at", "created_at", "updated_at"}


def upsert_product(s, item: dict, task_id: int | None, run_id: int | None) -> int:
    """(platform,item_id) 唯一；已存在则新数据覆盖旧数据，刷新 last_crawled_at、保留 first_crawled_at。返回 product.id。"""
    platform = (item.get("platform") or "ebay").strip()
    item_id = str(item.get("item_id") or "").strip()
    if not item_id:
        raise CollectError("商品缺少 item_id")
    prod = s.scalar(select(Product).where(Product.platform == platform, Product.item_id == item_id))
    now = datetime.now()
    if prod is None:
        prod = Product(platform=platform, item_id=item_id, first_crawled_at=now, last_crawled_at=now)
        s.add(prod)
    else:
        prod.last_crawled_at = now
    prod.task_id = task_id
    prod.run_id = run_id
    for k, v in item.items():
        if k in _PRODUCT_COLS and k not in _PROTECTED:
            setattr(prod, k, v)
    s.flush()
    return prod.id


def append_snapshot(s, product_id: int, item: dict, run_id: int | None) -> None:
    """每次采集追加一行价格/热度快照；product 表本身仍是覆盖更新。"""
    s.add(ProductSnapshot(
        product_id=product_id,
        run_id=run_id,
        price=item.get("price"),
        currency=item.get("currency") or "",
        shipping_price=item.get("shipping_price"),
        view_count=item.get("view_count"),
        watcher_count=item.get("watcher_count"),
        sold_count=item.get("sold_count"),
        available_qty=item.get("available_qty"),
        review_count=item.get("review_count"),
        review_avg=item.get("review_avg"),
    ))


def upsert_reviews(s, product_id: int, reviews: list[dict]) -> int:
    """(product_id,review_type,review_key) 唯一，重复评价更新；返回新增条数。"""
    added = 0
    for r in reviews or []:
        key = (r.get("review_key") or "").strip()
        if not key:
            continue
        rtype = (r.get("review_type") or "product").strip()
        rev = s.scalar(select(ProductReview).where(
            ProductReview.product_id == product_id,
            ProductReview.review_type == rtype,
            ProductReview.review_key == key,
        ))
        if rev is None:
            rev = ProductReview(product_id=product_id, review_type=rtype, review_key=key)
            s.add(rev)
            added += 1
        rev.reviewer_name = r.get("reviewer_name") or ""
        rev.rating = r.get("rating")
        rev.title = r.get("title") or ""
        rev.content = r.get("content")
        rev.reviewed_at = r.get("reviewed_at")
        rev.helpful_count = r.get("helpful_count") or 0
        rev.is_verified = 1 if r.get("is_verified") else 0
    return added