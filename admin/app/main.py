from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .attr_dict import ensure_currency
from .config import BASE_DIR, SECRET_KEY
from .db import Base, SessionLocal, engine
from .routers import attrs, auth, brands, crawl_tasks, grid_filters, grid_layouts, pages, products, shop, shop_i18n, style, supplier_catalog, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # 表还少（sys_user、sys_ui_style），先用 create_all；表多了再换 Alembic 迁移
    with SessionLocal() as db:
        ensure_currency(db)
    yield


app = FastAPI(title="mzShop Admin", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="mz_admin", max_age=86400, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(style.router)
app.include_router(crawl_tasks.router)
app.include_router(products.router)
app.include_router(shop.router)
app.include_router(shop_i18n.router)
app.include_router(brands.router)
app.include_router(supplier_catalog.router)
app.include_router(attrs.router)
app.include_router(grid_filters.router)
app.include_router(grid_layouts.router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"code": exc.status_code, "data": None, "msg": exc.detail}, status_code=exc.status_code)
