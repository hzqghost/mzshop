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


def _ui_style_context(request: Request, db: Session):
    from .. import style_store

    return {"menu_style": style_store.load(db, current_user(request)["id"], "menu")}


@router.get("/login")
def login_page(request: Request, error: str = ""):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": LOGIN_ERRORS.get(error, "")})


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    from .. import style_store

    return templates.TemplateResponse(
        request,
        "index.html",
        {"menu": MENU, "user": user, "menu_style": style_store.load(db, user["id"], "menu")},
    )


router.add_api_route("/home", _inner_page("home.html"), methods=["GET"])
router.add_api_route("/goods", _inner_page("goods.html"), methods=["GET"])
router.add_api_route("/goodsEdit", _inner_page("goodsEdit.html"), methods=["GET"])
router.add_api_route("/goodsCategories", _inner_page("goodsCategories.html"), methods=["GET"])
router.add_api_route("/goodsLanguages", _inner_page("goodsLanguages.html"), methods=["GET"])
router.add_api_route("/goodsAttributes", _inner_page("goodsAttributes.html"), methods=["GET"])
router.add_api_route("/brands", _inner_page("brands.html"), methods=["GET"])
router.add_api_route("/suppliers", _inner_page("suppliers.html"), methods=["GET"])
router.add_api_route("/supplierDocuments", _inner_page("supplierDocuments.html"), methods=["GET"])
router.add_api_route("/supplierCatalog", _inner_page("supplierCatalog.html"), methods=["GET"])
router.add_api_route("/supplierCatalogEdit", _inner_page("supplierCatalogEdit.html"), methods=["GET"])
router.add_api_route("/platforms", _inner_page("platforms.html"), methods=["GET"])
router.add_api_route("/stores", _inner_page("stores.html"), methods=["GET"])
router.add_api_route("/shippingTemplates", _inner_page("shippingTemplates.html"), methods=["GET"])
router.add_api_route("/shippingPackages", _inner_page("shippingPackages.html"), methods=["GET"])
router.add_api_route("/shopifyTasks", _inner_page("shopifyTasks.html"), methods=["GET"])
router.add_api_route("/bundles", _inner_page("bundles.html"), methods=["GET"])
router.add_api_route("/inventory", _inner_page("inventory.html"), methods=["GET"])
router.add_api_route("/orders", _inner_page("orders.html"), methods=["GET"])
router.add_api_route("/shopifyTaxonomy", _inner_page("shopifyTaxonomy.html"), methods=["GET"])
router.add_api_route("/shopifyTaxonomyAttributes", _inner_page("shopifyTaxonomyAttributes.html"), methods=["GET"])
router.add_api_route("/shopifyCategoryMaps", _inner_page("shopifyCategoryMaps.html"), methods=["GET"])
router.add_api_route("/shopifyCategoryAttributes", _inner_page("shopifyCategoryAttributes.html"), methods=["GET"])
router.add_api_route("/attrTypes", _inner_page("attrTypes.html"), methods=["GET"])
router.add_api_route("/attrValues", _inner_page("attrValues.html"), methods=["GET"])
router.add_api_route("/users", _inner_page("users.html"), methods=["GET"])
router.add_api_route("/geo", _inner_page("geo.html"), methods=["GET"])
router.add_api_route("/regions", _inner_page("regions.html"), methods=["GET"])
router.add_api_route(
    "/uiStyle",
    _inner_page("uiStyle.html", _ui_style_context),
    methods=["GET"],
)
router.add_api_route("/gridStyle", _inner_page("gridStyle.html", _style_context("grid")), methods=["GET"])
router.add_api_route("/formStyle", _inner_page("formStyle.html", _style_context("form")), methods=["GET"])
