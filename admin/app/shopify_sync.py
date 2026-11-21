"""把 mzShop 商品完整状态推送到 Shopify。"""
import hashlib
import json
import mimetypes
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from . import config
from .catalog import applicable_attributes
from .inventory import available
from .models import (Brand, BundleComponent, BundleRevision, ShopAttribute, ShopCategory, ShopGoods, ShopGoodsImage, ShopGoodsRegion,
                     ShopGoodsSku, ShopGoodsSkuRegion, ShopGoodsStore, ShopLanguage, ShopTranslation,
                     ShopifyAttributeMap, ShopifyBundleMap, ShopifyCategoryMap, ShopifyProductMap, ShopifyStoreConfig,
                     ShopifySyncTask, ShopifyTaxonomyAttributeValue, ShopifyTaxonomyCategory,
                     ShopifyTaxonomyCategoryAttribute, ShopifyTaxonomyMetaobjectMap, ShopifyVariantMap, StockBalance)
from .shopify_client import ShopifyError, graphql

PRODUCT_SET = """
mutation SyncProduct($input: ProductSetInput!, $identifier: ProductSetIdentifiers) {
  productSet(synchronous: true, input: $input, identifier: $identifier) {
    product {
      id handle onlineStoreUrl updatedAt
      options { id name position }
      variants(first: 250) { nodes { id sku inventoryItem { id } } }
      media(first: 250) { nodes { id } }
    }
    userErrors { code field message }
  }
}
"""

STANDARD_DEFINITION = """
query StandardDefinition($key: String!) {
  metafieldDefinitions(first: 1, ownerType: PRODUCT, namespace: "shopify", key: $key) {
    nodes { id type { name } validations { name value } }
  }
}
"""
ENABLE_STANDARD_DEFINITION = """
mutation EnableStandardDefinition($key: String!) {
  standardMetafieldDefinitionEnable(namespace: "shopify", key: $key, ownerType: PRODUCT) {
    createdDefinition { id } userErrors { field message }
  }
}
"""
METAOBJECT_DEFINITION = """
query MetaobjectDefinition($id: ID!) {
  node(id: $id) { ... on MetaobjectDefinition { id type fieldDefinitions { key type { name } } } }
}
"""
METAOBJECT_UPSERT = """
mutation UpsertTaxonomyValue($handle: MetaobjectHandleInput!, $metaobject: MetaobjectUpsertInput!) {
  metaobjectUpsert(handle: $handle, metaobject: $metaobject) {
    metaobject { id type handle } userErrors { field message code }
  }
}
"""

OPTION_UPDATE = """
mutation RenameOption($productId: ID!, $option: OptionUpdateInput!) {
  productOptionUpdate(productId: $productId, option: $option) {
    product { id }
    userErrors { code field message }
  }
}
"""

STAGED_UPLOAD = """
mutation StageImage($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } }
    userErrors { field message }
  }
}
"""

PUBLISH = """
mutation PublishProduct($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { field message } }
}
"""

PRODUCT_URL = """
query ProductUrl($id: ID!) {
  product(id: $id) { handle onlineStoreUrl }
}
"""

VARIANT_APPEND_MEDIA = """
mutation AppendVariantMedia($productId: ID!, $variantMedia: [ProductVariantAppendMediaInput!]!) {
  productVariantAppendMedia(productId: $productId, variantMedia: $variantMedia) {
    product { id }
    userErrors { code field message }
  }
}
"""

BUNDLE_RELATIONSHIPS = """
mutation UpdateBundle($input: [ProductVariantRelationshipUpdateInput!]!) {
  productVariantRelationshipBulkUpdate(input: $input) {
    parentProductVariants { id price }
    userErrors { code field message }
  }
}
"""

INVENTORY_SET = """
mutation SetInventory($input: InventorySetQuantitiesInput!, $idempotencyKey: String!) {
  inventorySetQuantities(input: $input) @idempotent(key: $idempotencyKey) {
    inventoryAdjustmentGroup { changes { name quantityAfterChange } }
    userErrors { code field message }
  }
}
"""

INVENTORY_VERIFY = """
query VerifyInventory($ids: [ID!]!, $locationId: ID!) {
  nodes(ids: $ids) {
    ... on InventoryItem {
      id
      inventoryLevel(locationId: $locationId) {
        quantities(names: ["available"]) { name quantity }
      }
    }
  }
}
"""


def _errors(payload: dict, field: str) -> None:
    errors = (payload.get(field) or {}).get("userErrors") or []
    if errors:
        raise ShopifyError("；".join(str(x.get("message") or x) for x in errors[:10]))


def _money(value) -> str:
    return format(Decimal(value or 0).quantize(Decimal("0.01")), "f")


def _translations(db: Session, lang: str, entity_type: str, ids: list[int]) -> dict[tuple[int, str], str]:
    if not ids:
        return {}
    rows = db.scalars(select(ShopTranslation).where(
        ShopTranslation.lang_code == lang, ShopTranslation.entity_type == entity_type,
        ShopTranslation.entity_id.in_(ids)))
    return {(row.entity_id, row.field_name): row.content for row in rows}


def _json(value: str | None, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def _localized_content(db: Session, goods: ShopGoods, skus: list[ShopGoodsSku], lang: str):
    language = db.scalar(select(ShopLanguage).where(ShopLanguage.code == lang, ShopLanguage.status == 1))
    if not language:
        raise ShopifyError(f"店铺商品语言 {lang or '（空）'} 不存在或已停用")
    is_default = bool(language.is_default)
    attrs = applicable_attributes(db, goods.category_id)
    goods_tr = {} if is_default else _translations(db, lang, "goods", [goods.id])
    sku_tr = {} if is_default else _translations(db, lang, "sku", [x.id for x in skus])
    attr_tr = {} if is_default else _translations(db, lang, "attribute", [x.id for x in attrs])
    brand = db.get(Brand, goods.brand_id) if goods.brand_id else None
    brand_tr = {} if is_default or not brand else _translations(db, lang, "brand", [brand.id])

    title = goods.name if is_default else (goods_tr.get((goods.id, "name")) or "").strip()
    if not title:
        raise ShopifyError(f"商品缺少店铺语言 {lang} 的商品名称，已停止推送以避免混入默认语言")
    description = goods.description or "" if is_default else goods_tr.get((goods.id, "description"), "")
    if not is_default and goods.description and not str(description).strip():
        raise ShopifyError(f"商品缺少店铺语言 {lang} 的商品描述，已停止推送")
    translated_attr_values = {} if is_default else _json(goods_tr.get((goods.id, "attr_values")), {})
    source_attr_values = goods.attr_values or {}
    localized_attrs = []
    for attr in attrs:
        if attr.name not in source_attr_values:
            continue
        name = attr.name if is_default else (attr_tr.get((attr.id, "name")) or "").strip()
        if not name:
            raise ShopifyError(f"属性“{attr.name}”缺少店铺语言 {lang} 的属性名译文")
        value = source_attr_values[attr.name]
        if attr.input_type == "number":
            unit = attr.unit if is_default else (attr_tr.get((attr.id, "unit")) or "")
            if not is_default and attr.unit and not unit:
                raise ShopifyError(f"属性“{attr.name}”缺少店铺语言 {lang} 的单位译文")
            value = f"{value}{unit or ''}"
        elif not is_default and attr.input_type in ("select", "multiselect"):
            base_options = attr.options or []
            translated_options = _json(attr_tr.get((attr.id, "options")), [])

            def translate_option(item):
                index = base_options.index(item) if item in base_options else -1
                return translated_options[index] if 0 <= index < len(translated_options) else ""

            values = value if isinstance(value, list) else [value]
            value = [translate_option(x) for x in values]
            value = [x for x in value if x]
            if not value:
                raise ShopifyError(f"属性“{attr.name}”的已选值缺少店铺语言 {lang} 译文")
        elif not is_default:
            value = translated_attr_values.get(attr.name, "")
            if not str(value).strip():
                raise ShopifyError(f"属性“{attr.name}”缺少店铺语言 {lang} 的属性值译文")
        if isinstance(value, list):
            value = ", ".join(str(x) for x in value)
        if str(value).strip():
            localized_attrs.append({"name": name, "value": str(value)})

    specs = {
        sku.id: ((sku.spec_name or sku.sku_code).strip() if is_default
                 else (sku_tr.get((sku.id, "spec_name")) or sku.sku_code).strip())
        for sku in skus
    }
    vendor = ""
    if brand:
        vendor = brand.name if is_default else (brand_tr.get((brand.id, "name")) or brand.code or "")
    elif is_default:
        vendor = goods.brand or ""
    return title, description, specs, vendor, localized_attrs


def _multipart_upload(url: str, parameters: list[dict], path: Path, mime_type: str) -> None:
    boundary = f"----mzshop-{uuid.uuid4().hex}"
    chunks = []
    for item in parameters:
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{item["name"]}"\r\n\r\n'.encode(),
            str(item["value"]).encode(), b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {mime_type}\r\n\r\n".encode(), path.read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    request = Request(url, data=b"".join(chunks), method="POST",
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(request, timeout=config.SHOPIFY_REQUEST_TIMEOUT_SECONDS) as response:
            if response.status not in (200, 201, 204):
                raise ShopifyError(f"Shopify 图片暂存上传失败：HTTP {response.status}")
    except HTTPError as e:
        raise ShopifyError(f"Shopify 图片暂存上传失败：HTTP {e.code}") from None
    except (URLError, TimeoutError, OSError) as e:
        raise ShopifyError(f"Shopify 图片暂存上传失败：{e}") from None


def _staged_image(shop_domain: str, path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data, _ = graphql(shop_domain, STAGED_UPLOAD, {"input": [{
        "filename": path.name, "mimeType": mime_type, "resource": "IMAGE",
        "fileSize": str(path.stat().st_size), "httpMethod": "POST",
    }]})
    _errors(data, "stagedUploadsCreate")
    targets = (data.get("stagedUploadsCreate") or {}).get("stagedTargets") or []
    if not targets or not targets[0].get("resourceUrl"):
        raise ShopifyError("Shopify 未返回图片暂存地址")
    target = targets[0]
    _multipart_upload(target["url"], target.get("parameters") or [], path, mime_type)
    return target["resourceUrl"]


def _image_source(shop_domain: str, value: str) -> str:
    value = (value or "").strip()
    if value.lower().startswith(("https://", "http://")):
        return value
    if value.startswith("/static/uploads/"):
        upload_root = (config.BASE_DIR / "static" / "uploads").resolve()
        path = (config.BASE_DIR / value.lstrip("/")).resolve()
        if not path.is_relative_to(upload_root) or not path.is_file():
            raise ShopifyError(f"商品图片文件不存在：{value}")
        return _staged_image(shop_domain, path)
    if not config.SHOPIFY_ASSET_BASE_URL:
        raise ShopifyError("商品包含本地图片，请在 admin/.env 配置 SHOPIFY_ASSET_BASE_URL 或 SHOPIFY_WEBHOOK_BASE_URL 公网访问地址")
    return urljoin(config.SHOPIFY_ASSET_BASE_URL + "/", value.lstrip("/"))


def _standard_metaobject_definition(shop_domain: str, key: str) -> tuple[str, str]:
    data, _ = graphql(shop_domain, STANDARD_DEFINITION, {"key": key})
    nodes = (data.get("metafieldDefinitions") or {}).get("nodes") or []
    if not nodes:
        enabled, _ = graphql(shop_domain, ENABLE_STANDARD_DEFINITION, {"key": key})
        _errors(enabled, "standardMetafieldDefinitionEnable")
        data, _ = graphql(shop_domain, STANDARD_DEFINITION, {"key": key})
        nodes = (data.get("metafieldDefinitions") or {}).get("nodes") or []
    if not nodes:
        raise ShopifyError(f"无法启用 Shopify 标准类别属性 shopify.{key}")
    definition_id = next((x.get("value") for x in nodes[0].get("validations") or []
                          if x.get("name") == "metaobject_definition_id"), "")
    if not definition_id:
        raise ShopifyError(f"Shopify 标准类别属性 shopify.{key} 未返回 Metaobject 定义")
    detail, _ = graphql(shop_domain, METAOBJECT_DEFINITION, {"id": definition_id})
    node = detail.get("node") or {}
    reference_fields = [x.get("key") for x in node.get("fieldDefinitions") or []
                        if x.get("type", {}).get("name") == "product_taxonomy_value_reference"]
    if len(reference_fields) != 1:
        raise ShopifyError(f"Shopify 类别属性 {key} 含 {len(reference_fields)} 个分类引用字段，暂不能自动映射")
    return str(node.get("type") or ""), reference_fields[0]


def _taxonomy_metaobject(db: Session, cfg: ShopifyStoreConfig, relation: ShopifyTaxonomyCategoryAttribute,
                         value: ShopifyTaxonomyAttributeValue) -> str:
    cached = db.scalar(select(ShopifyTaxonomyMetaobjectMap).where(
        ShopifyTaxonomyMetaobjectMap.store_id == cfg.store_id,
        ShopifyTaxonomyMetaobjectMap.category_attribute_id == relation.id,
        ShopifyTaxonomyMetaobjectMap.taxonomy_value_id == value.id))
    if cached:
        return cached.metaobject_gid
    metaobject_type, reference_field = _standard_metaobject_definition(cfg.shop_domain, relation.handle)
    stable_handle = f"mzshop-{relation.handle}-{value.taxonomy_gid.rsplit('/', 1)[-1]}"[:255]
    payload, _ = graphql(cfg.shop_domain, METAOBJECT_UPSERT, {
        "handle": {"type": metaobject_type, "handle": stable_handle},
        "metaobject": {"fields": [{"key": "label", "value": value.name_en or value.name_zh},
                                    {"key": reference_field, "value": value.taxonomy_gid}]},
    })
    _errors(payload, "metaobjectUpsert")
    remote = (payload.get("metaobjectUpsert") or {}).get("metaobject") or {}
    if not remote.get("id"):
        raise ShopifyError(f"Shopify 未返回类别属性值 {value.name_zh or value.name_en} 的 Metaobject ID")
    cached = ShopifyTaxonomyMetaobjectMap(store_id=cfg.store_id, category_attribute_id=relation.id,
        taxonomy_value_id=value.id, metaobject_gid=remote["id"], metaobject_type=metaobject_type)
    db.add(cached)
    db.flush()
    return remote["id"]


def _category_and_chain(db: Session, category_id: int):
    chain, seen, current = [], set(), db.get(ShopCategory, category_id)
    while current and current.id not in seen:
        seen.add(current.id); chain.append(current)
        mapping = db.scalar(select(ShopifyCategoryMap).where(ShopifyCategoryMap.category_id == current.id))
        if mapping:
            target = db.get(ShopifyTaxonomyCategory, mapping.taxonomy_category_id)
            if target and target.is_active:
                return target, chain
        current = db.get(ShopCategory, current.parent_id) if current.parent_id else None
    return None, chain


def _english_category_name(db: Session, category: ShopCategory) -> str:
    name = db.scalar(select(ShopTranslation.content).where(
        ShopTranslation.entity_type == "category", ShopTranslation.entity_id == category.id,
        ShopTranslation.lang_code == "en", ShopTranslation.field_name == "name"))
    name = str(name or "").strip()
    if not name:
        raise ShopifyError(f"末级分类“{category.name}”没有英文译文，不能写入 Shopify Product type")
    return name


def _category_metafields(db: Session, goods: ShopGoods, cfg: ShopifyStoreConfig,
                         target: ShopifyTaxonomyCategory, chain: list[ShopCategory]) -> list[dict]:
    category_ids = [x.id for x in chain]
    mappings = list(db.scalars(select(ShopifyAttributeMap).where(
        ShopifyAttributeMap.category_id.in_(category_ids)).order_by(ShopifyAttributeMap.category_id.desc())))
    chosen = {}
    chain_rank = {category.id: rank for rank, category in enumerate(chain)}
    for mapping in sorted(mappings, key=lambda row: chain_rank.get(row.category_id, 999)):
        chosen.setdefault(mapping.category_attribute_id, mapping)
    result = []
    for relation_id, mapping in chosen.items():
        relation = db.get(ShopifyTaxonomyCategoryAttribute, relation_id)
        local = db.get(ShopAttribute, mapping.local_attribute_id)
        if not relation or not relation.is_active or relation.taxonomy_category_id != target.id or not local:
            continue
        raw = (goods.attr_values or {}).get(local.name)
        local_values = raw if isinstance(raw, list) else [raw]
        value_ids = []
        for item in local_values:
            raw_ids = (mapping.value_map or {}).get(str(item)) if item is not None else None
            raw_ids = raw_ids if isinstance(raw_ids, list) else ([raw_ids] if raw_ids else [])
            value_ids.extend(int(value_id) for value_id in raw_ids)
        value_ids = list(dict.fromkeys(value_ids))
        if not value_ids:
            continue
        values = list(db.scalars(select(ShopifyTaxonomyAttributeValue).where(
            ShopifyTaxonomyAttributeValue.id.in_(value_ids), ShopifyTaxonomyAttributeValue.is_active == 1)))
        gids = [_taxonomy_metaobject(db, cfg, relation, value) for value in values]
        if gids:
            result.append({"namespace": "shopify", "key": relation.handle,
                           "type": "list.metaobject_reference", "value": json.dumps(gids)})
    return result


def _input(db: Session, goods: ShopGoods, cfg: ShopifyStoreConfig) -> tuple[dict, list[ShopGoodsSku], list[int | None]]:
    region = db.scalar(select(ShopGoodsRegion).where(
        ShopGoodsRegion.goods_id == goods.id, ShopGoodsRegion.region_id == cfg.region_id))
    if not region:
        raise ShopifyError("商品缺少该店铺的价格区域")
    skus = list(db.scalars(select(ShopGoodsSku).where(ShopGoodsSku.goods_id == goods.id,
                                                       ShopGoodsSku.status == 1).order_by(ShopGoodsSku.id)))
    if not skus:
        raise ShopifyError("商品没有启用的 SKU，不能推送库存")
    title, description, specs, vendor, localized_attrs = _localized_content(
        db, goods, skus, cfg.language_code)
    old_maps = {m.sku_id: m for m in db.scalars(select(ShopifyVariantMap).where(
        ShopifyVariantMap.goods_id == goods.id, ShopifyVariantMap.store_id == cfg.store_id))}
    sku_prices = {x.sku_id: x for x in db.scalars(select(ShopGoodsSkuRegion).where(
        ShopGoodsSkuRegion.goods_id == goods.id, ShopGoodsSkuRegion.region_id == cfg.region_id))}
    option_values = []
    variants = []
    if not cfg.stock_location_id:
        raise ShopifyError("Shopify 店铺尚未绑定 mzShop 库存地点")
    balances = {x.sku_id: x for x in db.scalars(select(StockBalance).where(
        StockBalance.location_id == cfg.stock_location_id,
        StockBalance.sku_id.in_([x.id for x in skus])))}
    for sku in skus:
        value = specs[sku.id]
        override = sku_prices.get(sku.id)
        effective_price = override.price if override and override.price is not None else region.price
        effective_currency = region.currency or ""
        if effective_price is None:
            raise ShopifyError(f"SKU {sku.sku_code} 缺少该店铺区域的销售价格")
        if cfg.currency and effective_currency and cfg.currency.upper() != effective_currency.upper():
            raise ShopifyError(f"SKU {sku.sku_code} 的价格币种 {effective_currency} 与 Shopify 店铺币种 {cfg.currency} 不一致")
        option_values.append({"name": value})
        variant = {
            "sku": sku.sku_code,
            "price": _money(effective_price),
            "optionValues": [{"optionName": "SKU", "name": value}],
            "inventoryItem": {"tracked": True, "requiresShipping": True,
                              "cost": _money(sku.cost_price or goods.cost_price)},
            "inventoryPolicy": "DENY",
        }
        mapped = old_maps.get(sku.id)
        if mapped:
            variant["id"] = mapped.variant_gid
        if cfg.default_location_gid and sku.sku_type == "normal":
            variant["inventoryQuantities"] = [{"locationId": cfg.default_location_gid,
                                                "name": "available", "quantity": available(balances.get(sku.id))}]
        variants.append(variant)
    images = list(db.scalars(select(ShopGoodsImage).where(ShopGoodsImage.goods_id == goods.id)
                             .order_by(ShopGoodsImage.sort_order, ShopGoodsImage.id)))
    image_values = [x.url for x in images]
    image_skus = [x.sku_id for x in images]
    if goods.main_image_url and goods.main_image_url not in image_values:
        image_values.insert(0, goods.main_image_url)
        image_skus.insert(0, None)
    files = [{"originalSource": _image_source(cfg.shop_domain, url), "alt": title, "contentType": "IMAGE"}
             for url in image_values if str(url).strip()]
    result = {
        "title": title,
        "descriptionHtml": description,
        "status": "ACTIVE" if goods.status else "DRAFT",
        "vendor": vendor,
        "productOptions": [{"name": "SKU", "position": 1, "values": option_values}],
        "variants": variants,
        "metafields": [{"namespace": "mzshop", "key": "goods_id", "type": "single_line_text_field",
                        "value": str(goods.id)},
                       {"namespace": "mzshop", "key": "goods_no", "type": "single_line_text_field",
                        "value": goods.goods_no}],
    }
    # 商品分类按“本级 → 最近上级”继承；映射完整的官方属性值同时写入标准类别元字段。
    target, category_chain = _category_and_chain(db, goods.category_id)
    if target:
        result["category"] = target.taxonomy_gid
        result["metafields"].extend(_category_metafields(db, goods, cfg, target, category_chain))
    # Product type 只作为末级分类没有直接 Shopify 分类映射时的英文兜底；继承上级映射也属于兜底场景。
    if category_chain:
        result["productType"] = "" if target and len(category_chain) == 1 else _english_category_name(db, category_chain[0])
    if files:
        result["files"] = files
    return result, skus, image_skus


def _sync_bundles(db: Session, cfg: ShopifyStoreConfig, skus: list[ShopGoodsSku]) -> str:
    request_id = ""
    for parent in [x for x in skus if x.sku_type == "bundle"]:
        revision = db.scalar(select(BundleRevision).where(
            BundleRevision.parent_sku_id == parent.id, BundleRevision.status == "published")
            .order_by(BundleRevision.version_no.desc()).limit(1))
        if not revision:
            raise ShopifyError(f"组合 SKU {parent.sku_code} 没有已发布版本")
        components = list(db.scalars(select(BundleComponent).where(
            BundleComponent.revision_id == revision.id).order_by(BundleComponent.sort_order, BundleComponent.id)))
        if not components:
            raise ShopifyError(f"组合 SKU {parent.sku_code} 没有组件")
        maps = {x.sku_id: x for x in db.scalars(select(ShopifyVariantMap).where(
            ShopifyVariantMap.store_id == cfg.store_id,
            ShopifyVariantMap.sku_id.in_([parent.id] + [x.component_sku_id for x in components])))}
        parent_map = maps.get(parent.id)
        missing = [db.get(ShopGoodsSku, x.component_sku_id).sku_code for x in components if x.component_sku_id not in maps]
        if not parent_map or missing:
            raise ShopifyError("组合组件尚未推送到该店铺：" + "、".join(missing))
        base_price = db.scalar(select(ShopGoodsRegion).where(
            ShopGoodsRegion.goods_id == parent.goods_id, ShopGoodsRegion.region_id == cfg.region_id))
        override = db.scalar(select(ShopGoodsSkuRegion).where(
            ShopGoodsSkuRegion.sku_id == parent.id, ShopGoodsSkuRegion.region_id == cfg.region_id))
        effective_price = override.price if override and override.price is not None else (base_price.price if base_price else None)
        if effective_price is None:
            raise ShopifyError(f"组合 SKU {parent.sku_code} 缺少该店铺区域的固定售价")
        removed, rid = graphql(cfg.shop_domain, BUNDLE_RELATIONSHIPS, {"input": [{
            "parentProductVariantId": parent_map.variant_gid, "removeAllProductVariantRelationships": True,
        }]})
        _errors(removed, "productVariantRelationshipBulkUpdate")
        created, rid2 = graphql(cfg.shop_domain, BUNDLE_RELATIONSHIPS, {"input": [{
            "parentProductVariantId": parent_map.variant_gid,
            "priceInput": {"calculation": "FIXED", "price": _money(effective_price)},
            "productVariantRelationshipsToCreate": [{"id": maps[x.component_sku_id].variant_gid,
                                                       "quantity": x.quantity} for x in components],
        }]})
        _errors(created, "productVariantRelationshipBulkUpdate")
        returned = (created.get("productVariantRelationshipBulkUpdate") or {}).get("parentProductVariants") or []
        remote_parent = next((x for x in returned if x.get("id") == parent_map.variant_gid), None)
        remote_price = remote_parent.get("price") if remote_parent else None
        try:
            price_matches = Decimal(str(remote_price)) == Decimal(_money(effective_price))
        except Exception:
            price_matches = False
        if not price_matches:
            remote_price = remote_price if remote_price is not None else "未返回"
            raise ShopifyError(f"组合 SKU {parent.sku_code} 固定售价校验失败：期望 {_money(effective_price)}，Shopify {remote_price}")
        digest = hashlib.sha256(json.dumps([(x.component_sku_id, x.quantity) for x in components]).encode()).hexdigest()
        mapped = db.scalar(select(ShopifyBundleMap).where(
            ShopifyBundleMap.parent_sku_id == parent.id, ShopifyBundleMap.store_id == cfg.store_id))
        if not mapped:
            mapped = ShopifyBundleMap(store_id=cfg.store_id, parent_sku_id=parent.id, revision_id=revision.id)
            db.add(mapped)
        mapped.revision_id, mapped.source_hash, mapped.sync_status = revision.id, digest, "success"
        mapped.last_synced_at, mapped.last_error = datetime.now(), None
        request_id = rid2 or rid or request_id
    return request_id


def _sync_inventory(db: Session, cfg: ShopifyStoreConfig, task: ShopifySyncTask,
                    skus: list[ShopGoodsSku]) -> str:
    """以 mzShop 为主源设置普通 SKU 绝对可售量，并回读 Shopify 验证。"""
    normal_skus = [sku for sku in skus if sku.sku_type == "normal"]
    if not normal_skus:
        return ""
    if not cfg.default_location_gid or not cfg.stock_location_id:
        raise ShopifyError("Shopify 店铺尚未完整绑定远端与 mzShop 库存地点")
    mappings = {row.sku_id: row for row in db.scalars(select(ShopifyVariantMap).where(
        ShopifyVariantMap.store_id == cfg.store_id,
        ShopifyVariantMap.sku_id.in_([sku.id for sku in normal_skus])))}
    balances = {row.sku_id: row for row in db.scalars(select(StockBalance).where(
        StockBalance.location_id == cfg.stock_location_id,
        StockBalance.sku_id.in_([sku.id for sku in normal_skus])))}
    desired = {}
    quantities = []
    for sku in normal_skus:
        mapping = mappings.get(sku.id)
        if not mapping or not mapping.inventory_item_gid:
            raise ShopifyError(f"SKU {sku.sku_code} 缺少 Shopify InventoryItem 映射")
        quantity = available(balances.get(sku.id))
        desired[mapping.inventory_item_gid] = (sku.sku_code, quantity)
        quantities.append({"inventoryItemId": mapping.inventory_item_gid,
                           "locationId": cfg.default_location_gid,
                           "quantity": quantity, "changeFromQuantity": None})
    idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_URL,
        f"mzshop://shopify/inventory/task/{task.id}/store/{cfg.store_id}"))
    data, request_id = graphql(cfg.shop_domain, INVENTORY_SET, {
        "input": {"name": "available", "reason": "correction",
                  "referenceDocumentUri": f"mzshop://shopify-sync-task/{task.id}",
                  "quantities": quantities},
        "idempotencyKey": idempotency_key,
    })
    _errors(data, "inventorySetQuantities")
    verified, verify_request_id = graphql(cfg.shop_domain, INVENTORY_VERIFY, {
        "ids": list(desired), "locationId": cfg.default_location_gid,
    })
    actual = {}
    for node in verified.get("nodes") or []:
        if not node or not node.get("id"):
            continue
        values = ((node.get("inventoryLevel") or {}).get("quantities") or [])
        actual[node["id"]] = next((int(x.get("quantity") or 0) for x in values
                                   if x.get("name") == "available"), None)
    mismatches = [f"{sku_code}：期望 {quantity}，Shopify {actual.get(item_gid, '未返回')}"
                  for item_gid, (sku_code, quantity) in desired.items()
                  if actual.get(item_gid) != quantity]
    if mismatches:
        raise ShopifyError("库存写入后校验不一致：" + "；".join(mismatches[:10]))
    return verify_request_id or request_id


def sync_product(db: Session, task: ShopifySyncTask) -> str:
    goods = db.get(ShopGoods, task.goods_id)
    cfg = db.scalar(select(ShopifyStoreConfig).where(ShopifyStoreConfig.store_id == task.store_id))
    if not goods or not cfg or not cfg.sync_enabled or cfg.connection_status != "ok":
        raise ShopifyError("商品或可用的 Shopify 店铺配置不存在")
    payload, skus, image_skus = _input(db, goods, cfg)
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    product_map = db.scalar(select(ShopifyProductMap).where(
        ShopifyProductMap.goods_id == goods.id, ShopifyProductMap.store_id == task.store_id))
    identifier = {"id": product_map.product_gid} if product_map else None
    data, request_id = graphql(cfg.shop_domain, PRODUCT_SET, {"input": payload, "identifier": identifier})
    _errors(data, "productSet")
    remote = (data.get("productSet") or {}).get("product") or {}
    if not remote.get("id"):
        raise ShopifyError("Shopify 未返回 Product ID")
    option = next(iter(remote.get("options") or []), None)
    if option and option.get("name") != "SKU":
        renamed, rename_request_id = graphql(cfg.shop_domain, OPTION_UPDATE, {
            "productId": remote["id"], "option": {"id": option["id"], "name": "SKU"},
        })
        _errors(renamed, "productOptionUpdate")
        request_id = rename_request_id or request_id
    if not product_map:
        product_map = ShopifyProductMap(goods_id=goods.id, store_id=task.store_id,
                                         product_gid=remote["id"])
        db.add(product_map)
    product_map.product_gid = remote["id"]
    product_map.source_hash = digest
    product_map.sync_status = "success"
    product_map.last_synced_at = datetime.now()
    product_map.remote_updated_at = datetime.fromisoformat(remote["updatedAt"].replace("Z", "+00:00")).replace(tzinfo=None)
    product_map.last_error = None
    sku_by_code = {x.sku_code: x for x in skus}
    variant_gid_by_sku = {}
    returned_ids = set()
    for node in (remote.get("variants") or {}).get("nodes", []):
        sku = sku_by_code.get(node.get("sku"))
        if not sku:
            continue
        variant_gid_by_sku[sku.id] = node["id"]
        returned_ids.add(sku.id)
        mapped = db.scalar(select(ShopifyVariantMap).where(
            ShopifyVariantMap.sku_id == sku.id, ShopifyVariantMap.store_id == task.store_id))
        if not mapped:
            mapped = ShopifyVariantMap(store_id=task.store_id, goods_id=goods.id, sku_id=sku.id,
                                        variant_gid=node["id"])
            db.add(mapped)
        mapped.variant_gid = node["id"]
        mapped.inventory_item_gid = str((node.get("inventoryItem") or {}).get("id") or "")
    db.flush()
    bundle_request_id = _sync_bundles(db, cfg, skus)
    request_id = bundle_request_id or request_id
    inventory_request_id = _sync_inventory(db, cfg, task, skus)
    request_id = inventory_request_id or request_id
    remote_media = (remote.get("media") or {}).get("nodes") or []
    if any(image_skus):
        if len(remote_media) < len(image_skus):
            raise ShopifyError("Shopify 未返回完整的商品媒体，暂不能关联 SKU 专用图片")
        media_by_sku = {}
        for index, sku_id in enumerate(image_skus):
            if sku_id and index < len(remote_media) and remote_media[index].get("id"):
                media_by_sku.setdefault(sku_id, []).append(remote_media[index]["id"])
        variant_media = [{"variantId": variant_gid_by_sku[sku_id], "mediaIds": media_ids}
                         for sku_id, media_ids in media_by_sku.items() if sku_id in variant_gid_by_sku]
        if variant_media:
            associated, media_request_id = graphql(cfg.shop_domain, VARIANT_APPEND_MEDIA, {
                "productId": remote["id"], "variantMedia": variant_media,
            })
            _errors(associated, "productVariantAppendMedia")
            request_id = media_request_id or request_id
    db.execute(delete(ShopifyVariantMap).where(
        ShopifyVariantMap.goods_id == goods.id, ShopifyVariantMap.store_id == task.store_id,
        ShopifyVariantMap.sku_id.not_in(returned_ids)))
    if goods.status and cfg.publication_gid:
        published, publish_request_id = graphql(cfg.shop_domain, PUBLISH,
            {"id": remote["id"], "input": [{"publicationId": cfg.publication_gid}]})
        _errors(published, "publishablePublish")
        request_id = publish_request_id or request_id
        refreshed, url_request_id = graphql(cfg.shop_domain, PRODUCT_URL, {"id": remote["id"]})
        remote.update(refreshed.get("product") or {})
        request_id = url_request_id or request_id
    handle = str(remote.get("handle") or "").strip()
    product_url = str(remote.get("onlineStoreUrl") or "").strip()
    if not product_url and handle:
        product_url = f"https://{cfg.shop_domain}/products/{quote(handle, safe='')}"
    # DDL 030 由人工执行；执行前不得让商品同步因待落库字段而失败。
    has_product_url = db.scalar(text("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'shop_goods_store'
          AND COLUMN_NAME = 'product_url'
    """))
    if product_url and has_product_url:
        db.execute(update(ShopGoodsStore).where(
            ShopGoodsStore.goods_id == goods.id, ShopGoodsStore.store_id == task.store_id
        ).values(product_url=product_url))
    return request_id


def run_task(db: Session, task: ShopifySyncTask) -> None:
    try:
        task.request_id = sync_product(db, task)
        task.status, task.finished_at, task.error_message = "success", datetime.now(), None
        db.commit()
    except Exception as e:
        db.rollback()
        task = db.get(ShopifySyncTask, task.id)
        task.retry_count += 1
        task.error_message = str(e)[:4000]
        if task.retry_count < task.max_retries:
            task.status = "pending"
            task.next_retry_at = datetime.now() + timedelta(minutes=min(60, 2 ** task.retry_count))
        else:
            task.status, task.finished_at = "failed", datetime.now()
        mapped = db.scalar(select(ShopifyProductMap).where(
            ShopifyProductMap.goods_id == task.goods_id, ShopifyProductMap.store_id == task.store_id))
        if mapped:
            mapped.sync_status, mapped.last_error = "error", task.error_message
        db.commit()
