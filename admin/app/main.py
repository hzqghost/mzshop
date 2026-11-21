from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .attr_dict import ensure_currency
from .config import BASE_DIR, SECRET_KEY
from .db import Base, SessionLocal, engine
from .geo_seed import ensure_geo
from .models import GeoRegion, ShopGoods, ShopGoodsRegion
from .routers import attrs, auth, brands, bundles, geo, grid_filters, grid_layouts, orders, pages, platforms, shipping, shop, shop_i18n, shopify, style, supplier_catalog, users


def ensure_catalog_purchase_price() -> None:
    """已有库不会被 create_all 补列。采购价是这次加在目录条目上的独立字段。"""
    insp = inspect(engine)
    if not insp.has_table("supplier_catalog_item"):
        return
    names = {c["name"] for c in insp.get_columns("supplier_catalog_item")}
    if "purchase_price" in names:
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE supplier_catalog_item "
            "ADD COLUMN purchase_price DECIMAL(12,2) NULL COMMENT '采购价' AFTER price"
        ))


def backfill_goods_region_prices(db: Session) -> None:
    """已有商品的销售价、运费归到「国内」。已经有区域价格的不再改。"""
    region = db.scalar(select(GeoRegion).where(GeoRegion.name == "国内"))
    if region is None:
        return
    taken = select(ShopGoodsRegion.goods_id)
    rows = db.scalars(select(ShopGoods).where(
        ShopGoods.id.not_in(taken),
        (ShopGoods.sale_price != 0) | (ShopGoods.shipping_fee != 0),
    )).all()
    for g in rows:
        db.add(ShopGoodsRegion(
            goods_id=g.id, region_id=region.id, currency="",
            price=g.sale_price, shipping_fee=g.shipping_fee,
        ))
    if rows:
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 历史表仍沿用 create_all；新增 Shopify 分类结构必须先人工审核并执行 031 DDL，禁止启动时偷偷建表。
    ddl_only = {"shopify_taxonomy_category", "shopify_category_map", "shopify_taxonomy_attribute",
                "shopify_taxonomy_attribute_value", "shopify_taxonomy_category_attribute",
                "shopify_attribute_map", "shopify_taxonomy_metaobject_map", "shop_bundle_revision",
                "shop_bundle_component", "stock_location", "stock_balance", "stock_ledger",
                "shopify_bundle_map", "shop_order", "shop_order_line", "shop_refund",
                "shop_refund_line", "shop_return", "shop_return_line", "shopify_webhook_event",
                "shipping_template", "shipping_template_rule", "shipping_package_box", "shipping_package_group",
                "shipping_package_group_image"}
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in ddl_only])
    ensure_catalog_purchase_price()
    with SessionLocal() as db:
        ensure_currency(db)
        ensure_geo(db)
        backfill_goods_region_prices(db)
    yield


app = FastAPI(title="mzShop Admin", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="mz_admin", max_age=86400, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(style.router)
app.include_router(shop.router)
app.include_router(shop_i18n.router)
app.include_router(brands.router)
app.include_router(supplier_catalog.router)
app.include_router(attrs.router)
app.include_router(geo.geo_router)
app.include_router(geo.region_router)
app.include_router(platforms.platform_router)
app.include_router(platforms.store_router)
app.include_router(shipping.router)
app.include_router(shipping.package_router)
app.include_router(shopify.router)
app.include_router(bundles.router)
app.include_router(bundles.inventory_router)
app.include_router(orders.router)
app.include_router(orders.webhook_router)
app.include_router(grid_filters.router)
app.include_router(grid_layouts.router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"code": exc.status_code, "data": None, "msg": exc.detail}, status_code=exc.status_code)
