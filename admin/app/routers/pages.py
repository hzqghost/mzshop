from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..menu import MENU
from ..templating import render_page, templates
from ..ui_style import KINDS

router = APIRouter()

LOGIN_ERRORS = {"credentials": "用户名或密码错误", "disabled": "账号已禁用"}


def _inner_page(template: str, extra=None):
    """后台内页：未登录跳登录页，已登录渲染模板（自带用户样式）。"""

    def view(request: Request, db: Session = Depends(get_db)):
        if not current_user(request):
            return RedirectResponse("/login", status_code=303)
        return render_page(request, db, template, extra(request, db) if extra else None)

    return view


def _style_context(kind: str):
    def ctx(request: Request, db: Session):
        from .. import style_store

        return {"style": style_store.load(db, current_user(request)["id"], kind), "presets": KINDS[kind].full_presets()}

    return ctx


@router.get("/login")
def login_page(request: Request, error: str = ""):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": LOGIN_ERRORS.get(error, "")})


@router.get("/")
def index(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"menu": MENU, "user": current_user(request)})


router.add_api_route("/home", _inner_page("home.html"), methods=["GET"])
router.add_api_route("/crawlTasks", _inner_page("crawlTasks.html"), methods=["GET"])
router.add_api_route("/goods", _inner_page("goods.html"), methods=["GET"])
router.add_api_route("/goodsEdit", _inner_page("goodsEdit.html"), methods=["GET"])
router.add_api_route("/goodsCategories", _inner_page("goodsCategories.html"), methods=["GET"])
router.add_api_route("/goodsLanguages", _inner_page("goodsLanguages.html"), methods=["GET"])
router.add_api_route("/goodsAttributes", _inner_page("goodsAttributes.html"), methods=["GET"])
router.add_api_route("/brands", _inner_page("brands.html"), methods=["GET"])
router.add_api_route("/suppliers", _inner_page("suppliers.html"), methods=["GET"])
router.add_api_route("/supplierCatalog", _inner_page("supplierCatalog.html"), methods=["GET"])
router.add_api_route("/supplierCatalogEdit", _inner_page("supplierCatalogEdit.html"), methods=["GET"])
router.add_api_route("/products", _inner_page("products.html"), methods=["GET"])
router.add_api_route("/attrTypes", _inner_page("attrTypes.html"), methods=["GET"])
router.add_api_route("/attrValues", _inner_page("attrValues.html"), methods=["GET"])
router.add_api_route("/users", _inner_page("users.html"), methods=["GET"])
router.add_api_route("/gridStyle", _inner_page("gridStyle.html", _style_context("grid")), methods=["GET"])
router.add_api_route("/formStyle", _inner_page("formStyle.html", _style_context("form")), methods=["GET"])
