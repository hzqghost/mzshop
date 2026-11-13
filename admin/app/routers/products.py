"""商品管理（通用，不区分平台）。商品由采集器写入，这里提供查看、少量字段修正和删除。响应 {code, data, msg}。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import Product, ProductReview, ProductSnapshot

router = APIRouter(prefix="/api/v1/products", dependencies=[Depends(require_user)])

# 允许人工修正的字段；其余字段以采集结果为准，修改会在下次采集时被覆盖，所以不开放
EDITABLE = {"title": 500, "brand": 100, "category_name": 200, "item_condition": 50, "mpn": 100, "upc": 50,
            "country_of_origin": 100}

NUM_FIELDS = ("price", "shipping_price", "original_price", "review_avg", "seller_feedback_pct")


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _num(v):
    return float(v) if v is not None else None


def _row(p: Product) -> dict:
    d = {c: getattr(p, c) for c in (
        "id", "platform", "item_id", "title", "product_url", "image_url", "category_name", "brand",
        "item_condition", "mpn", "upc", "country_of_origin", "listing_type", "currency", "view_count",
        "watcher_count", "sold_count", "available_qty", "review_count", "seller_name", "seller_feedback_cnt",
        "item_location", "task_id")}
    for f in NUM_FIELDS:
        d[f] = _num(getattr(p, f))
    d["first_crawled_at"] = _fmt(p.first_crawled_at)
    d["last_crawled_at"] = _fmt(p.last_crawled_at)
    return d


def _get(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "商品不存在")
    return p


@router.get("")
def list_products(db: Session = Depends(get_db)):
    rows = db.scalars(select(Product).order_by(Product.id.desc())).all()
    return ok([_row(p) for p in rows])


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = _get(db, product_id)
    return ok({**_row(p), "search_attrs": p.search_attrs or {}, "attributes": p.attributes or {}})


@router.put("/{product_id}")
def update_product(product_id: int, values: dict, db: Session = Depends(get_db)):
    p = _get(db, product_id)
    for f, size in EDITABLE.items():
        if f in values and values[f] is not None:
            v = str(values[f]).strip()
            if len(v) > size:
                raise HTTPException(400, f"{f} 最长 {size} 个字符")
            setattr(p, f, v)
    db.commit()
    return ok(_row(p))


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = _get(db, product_id)
    db.execute(delete(ProductReview).where(ProductReview.product_id == p.id))
    db.execute(delete(ProductSnapshot).where(ProductSnapshot.product_id == p.id))
    db.delete(p)
    db.commit()
    return ok()


@router.get("/{product_id}/reviews")
def list_reviews(product_id: int, db: Session = Depends(get_db)):
    _get(db, product_id)
    rows = db.scalars(select(ProductReview).where(ProductReview.product_id == product_id)
                      .order_by(ProductReview.reviewed_at.desc(), ProductReview.id.desc())).all()
    return ok([{
        "id": r.id, "review_type": r.review_type, "reviewer_name": r.reviewer_name, "rating": r.rating,
        "title": r.title, "content": r.content or "", "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "helpful_count": r.helpful_count, "is_verified": bool(r.is_verified)} for r in rows])


@router.get("/{product_id}/snapshots")
def list_snapshots(product_id: int, db: Session = Depends(get_db)):
    _get(db, product_id)
    rows = db.scalars(select(ProductSnapshot).where(ProductSnapshot.product_id == product_id)
                      .order_by(ProductSnapshot.crawled_at.desc())).all()
    return ok([{
        "id": s.id, "price": _num(s.price), "currency": s.currency, "shipping_price": _num(s.shipping_price),
        "view_count": s.view_count, "watcher_count": s.watcher_count, "sold_count": s.sold_count,
        "available_qty": s.available_qty, "review_count": s.review_count, "review_avg": _num(s.review_avg),
        "crawled_at": _fmt(s.crawled_at)} for s in rows])
