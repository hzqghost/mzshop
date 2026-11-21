from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "sys_user"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci", "comment": "后台用户"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, comment="登录名")
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希")
    real_name: Mapped[str] = mapped_column(String(50), default="", comment="姓名")
    email: Mapped[str] = mapped_column(String(100), default="", comment="邮箱")
    phone: Mapped[str] = mapped_column(String(30), default="", comment="手机")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1启用 0禁用")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "real_name": self.real_name,
            "email": self.email,
            "phone": self.phone,
            "status": bool(self.status),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class UiStyle(Base):
    """用户的表格 / 表单样式配置，每个用户每种 kind（grid / form）一行；user_id 0 是内置超级管理员。"""

    __tablename__ = "sys_ui_style"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="uq_ui_style_user_kind"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci", "comment": "用户界面样式配置"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 自有商品目录：建表以 contracts/ddl/002_shop_tables.sql 为准（已执行）
_SHOP_TABLE = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class ShopCategory(Base):
    __tablename__ = "shop_category"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品分类"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(default=0)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="商品编码中的品类段，允许重复")
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopAttribute(Base):
    __tablename__ = "shop_attribute"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品属性定义"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    input_type: Mapped[str] = mapped_column(String(20), default="text")
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    decimal_places: Mapped[int] = mapped_column(SmallInteger, default=0)
    unit: Mapped[str] = mapped_column(String(30), default="")
    is_required: Mapped[int] = mapped_column(SmallInteger, default=0)
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopGoods(Base):
    __tablename__ = "shop_goods"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品（SPU）"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_no: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(default=0)
    brand: Mapped[str] = mapped_column(String(100), default="")
    supplier: Mapped[str] = mapped_column(String(100), default="")
    brand_id: Mapped[int] = mapped_column(default=0)
    supplier_id: Mapped[int] = mapped_column(default=0)
    source_url: Mapped[str] = mapped_column(String(500), default="")
    main_image_url: Mapped[str] = mapped_column(String(500), default="")
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    shipping_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    weight_g: Mapped[int | None] = mapped_column(nullable=True)
    shipping_package_group_id: Mapped[int] = mapped_column(default=0, comment="默认包装组，0表示未设置")
    attr_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopGoodsRegion(Base):
    """价格、建议售价、最低售价、最高售价、币种，以及运费、到达天数、税费，按区域各存一行。拿货价仍在商品上。"""

    __tablename__ = "shop_goods_region"
    __table_args__ = (
        UniqueConstraint("goods_id", "region_id", name="uq_shop_goods_region"),
        Index("idx_shop_goods_region_region", "region_id"),
        {**_SHOP_TABLE, "comment": "商品的区域价格"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_id: Mapped[int] = mapped_column(comment="shop_goods.id")
    region_id: Mapped[int] = mapped_column(comment="sys_region.id")
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="价格")
    suggested_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="建议售价")
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最低售价")
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最高售价")
    currency: Mapped[str] = mapped_column(String(3), default="", comment="币种，取通用属性 currency 的编码")
    shipping_template_id: Mapped[int] = mapped_column(default=0, comment="shipping_template.id，0表示未绑定")
    shipping_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="运费")
    arrival_days_min: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最快到达天数")
    arrival_days_max: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最慢到达天数")
    tax: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="税费")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopGoodsImage(Base):
    __tablename__ = "shop_goods_image"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品图片"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_id: Mapped[int]
    sku_id: Mapped[int | None] = mapped_column(nullable=True, comment="专用 SKU，空表示商品共用图片")
    url: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ShopGoodsSku(Base):
    __tablename__ = "shop_goods_sku"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品规格（SKU）"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_id: Mapped[int]
    sku_code: Mapped[str] = mapped_column(String(64))
    spec_name: Mapped[str] = mapped_column(String(200), default="")
    sku_type: Mapped[str] = mapped_column(String(20), default="normal", comment="SKU类型：normal普通 bundle组合父SKU")
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="SKU重量（克），空值继承商品重量")
    shipping_package_group_id: Mapped[int] = mapped_column(default=0, comment="包装组，0表示继承商品/店铺")
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    stock: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopGoodsSkuRegion(Base):
    __tablename__ = "shop_goods_sku_region"
    __table_args__ = (
        UniqueConstraint("sku_id", "region_id", name="uq_shop_goods_sku_region"),
        Index("idx_shop_goods_sku_region_goods_region", "goods_id", "region_id"),
        {**_SHOP_TABLE, "comment": "SKU 区域价格覆盖"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_id: Mapped[int] = mapped_column(comment="shop_goods.id")
    sku_id: Mapped[int] = mapped_column(comment="shop_goods_sku.id")
    region_id: Mapped[int] = mapped_column(comment="sys_region.id")
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    suggested_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopGoodsStore(Base):
    """商品在店铺上的上架许可：有记录后商品的上下架才生效；allowed=1 可以上架，0 不可以上架。"""

    __tablename__ = "shop_goods_store"
    __table_args__ = (
        UniqueConstraint("goods_id", "store_id", name="uq_shop_goods_store"),
        Index("idx_shop_goods_store_store", "store_id"),
        {**_SHOP_TABLE, "comment": "商品的店铺上架许可"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_id: Mapped[int] = mapped_column(comment="shop_goods.id")
    store_id: Mapped[int] = mapped_column(comment="store.id")
    shipping_template_id: Mapped[int] = mapped_column(default=0, comment="shipping_template.id，0表示未绑定")
    allowed: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1可以上架 0不可以上架")
    product_url: Mapped[str] = mapped_column(String(500), default="", comment="该商品在店铺中的商品网址")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShippingTemplate(Base):
    __tablename__ = "shipping_template"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shipping_template_name"),
        {**_SHOP_TABLE, "comment": "销售运费模板"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), comment="模板名称")
    currency: Mapped[str] = mapped_column(String(3), comment="币种")
    calc_type: Mapped[str] = mapped_column(String(20), comment="计费方式：fixed固定 weight实际重量 chargeable计费重量")
    volume_divisor: Mapped[int] = mapped_column(default=5000, comment="体积重系数，仅按计费重量使用")
    free_threshold: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="分组商品金额满此值免邮")
    min_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最低运费")
    max_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最高运费")
    no_match_action: Mapped[str] = mapped_column(String(20), default="reject", comment="区域未匹配处理：reject禁止配送 default使用默认规则")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1启用 0停用")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShippingTemplateRule(Base):
    __tablename__ = "shipping_template_rule"
    __table_args__ = (
        UniqueConstraint("template_id", "region_id", name="uq_shipping_rule_template_region"),
        Index("idx_shipping_rule_region", "region_id"),
        {**_SHOP_TABLE, "comment": "销售运费模板区域规则"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(comment="shipping_template.id")
    region_id: Mapped[int] = mapped_column(default=0, comment="sys_region.id，0表示默认规则")
    priority: Mapped[int] = mapped_column(default=100, comment="匹配优先级，越小越优先")
    fixed_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="固定运费")
    first_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="首重克数")
    first_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="首重费用")
    additional_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="续重单位克数")
    additional_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="每个续重单位费用")
    arrival_days_min: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最快到达天数")
    arrival_days_max: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最慢到达天数")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShippingPackageBox(Base):
    __tablename__ = "shipping_package_box"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shipping_package_box_name"),
        {**_SHOP_TABLE, "comment": "物流包装箱档案"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), comment="箱型名称")
    length_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), comment="外部长（厘米）")
    width_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), comment="外部宽（厘米）")
    height_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), comment="外部高（厘米）")
    empty_weight_g: Mapped[int] = mapped_column(default=0, comment="空箱重量（克）")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1启用 0停用")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShippingPackageGroup(Base):
    __tablename__ = "shipping_package_group"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shipping_package_group_name"),
        {**_SHOP_TABLE, "comment": "物流包装组"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), comment="包装组名称")
    current_box_id: Mapped[int] = mapped_column(default=0, comment="当前 shipping_package_box.id")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1启用 0停用")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShippingPackageGroupImage(Base):
    __tablename__ = "shipping_package_group_image"
    __table_args__ = (
        Index("idx_shipping_package_group_image_group", "group_id"),
        {**_SHOP_TABLE, "comment": "物流包装组图片"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(comment="shipping_package_group.id")
    url: Mapped[str] = mapped_column(String(500), comment="图片地址")
    sort_order: Mapped[int] = mapped_column(default=0, comment="排序")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# 商品内容多语言：建表以 contracts/ddl/003_shop_i18n.sql 为准（已执行）
class ShopLanguage(Base):
    __tablename__ = "shop_language"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品内容语言"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(50))
    is_default: Mapped[int] = mapped_column(SmallInteger, default=0)
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopTranslation(Base):
    __tablename__ = "shop_translation"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品内容译文"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int]
    lang_code: Mapped[str] = mapped_column(String(20))
    field_name: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 表格过滤器模板：建表以 contracts/ddl/006_sys_grid_filter.sql 为准（已执行）
class GridFilter(Base):
    __tablename__ = "sys_grid_filter"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci", "comment": "表格过滤器模板"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int]
    grid_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(50))
    filter_value: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 表格布局：建表以 contracts/ddl/008_sys_grid_layout.sql 为准（已执行）
class GridLayout(Base):
    __tablename__ = "sys_grid_layout"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci", "comment": "表格布局"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int]
    grid_key: Mapped[str] = mapped_column(String(100))
    layout: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 供应商产品目录：建表以 contracts/ddl/010_supplier_catalog.sql 为准（已执行）
class Supplier(Base):
    __tablename__ = "supplier"
    __table_args__ = {**_SHOP_TABLE, "comment": "供应商档案"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="供应商编码，空为未设置")
    name: Mapped[str] = mapped_column(String(100))
    website: Mapped[str] = mapped_column(String(255), default="")
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    contact_phone: Mapped[str] = mapped_column(String(50), default="")
    contact_email: Mapped[str] = mapped_column(String(100), default="")
    default_currency: Mapped[str] = mapped_column(String(3), default="", comment="默认币种，取通用属性 currency 的编码")
    excel_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    remark: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True, comment="备注（HTML）")
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Brand(Base):
    __tablename__ = "brand"
    __table_args__ = {**_SHOP_TABLE, "comment": "品牌字典"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="品牌编码，空为未设置")
    name: Mapped[str] = mapped_column(String(100))
    brand_type: Mapped[str] = mapped_column(String(20), default="third_party", comment="品牌类型：own自有品牌 third_party第三方品牌")
    include_in_goods_no: Mapped[int] = mapped_column(SmallInteger, default=1, comment="是否参与商品编码：1参与 0使用TH")
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class GoodsNoSequence(Base):
    __tablename__ = "shop_goods_no_sequence"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品编码流水"}

    prefix: Mapped[str] = mapped_column(String(60), primary_key=True, comment="品牌段与品类段拼接后的最终前缀")
    current_seq: Mapped[int] = mapped_column(comment="当前已占用的四位流水号")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class SupplierCatalogItem(Base):
    __tablename__ = "supplier_catalog_item"
    __table_args__ = {**_SHOP_TABLE, "comment": "供应商产品目录条目"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int]
    supplier_sku: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))
    brand_id: Mapped[int] = mapped_column(default=0)
    brand_name: Mapped[str] = mapped_column(String(100), default="")
    category_name: Mapped[str] = mapped_column(String(200), default="")
    category_id: Mapped[int] = mapped_column(default=0)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="采购价")
    suggested_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="建议售价")
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最低售价")
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最高售价")
    price_rule: Mapped[str] = mapped_column(Text, default="", comment="价格规则，多行文本")
    lead_time: Mapped[str] = mapped_column(String(100), default="", comment="交期")
    currency: Mapped[str] = mapped_column(String(3), default="", comment="币种，取通用属性 currency 的编码")
    stock: Mapped[int | None] = mapped_column(nullable=True)
    moq: Mapped[str] = mapped_column(String(50), default="")
    main_image_url: Mapped[str] = mapped_column(String(500), default="", comment="主图地址，取图片列表第一张")
    images: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="图片列表 [{url,name}]")
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="附件列表 [{url,name}]")
    source_type: Mapped[str] = mapped_column(String(20), default="manual")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_row: Mapped[int | None] = mapped_column(nullable=True)
    attrs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mapped_attrs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    status: Mapped[int] = mapped_column(SmallInteger, default=0)
    goods_id: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 目录条目的区域价格：建表以 contracts/ddl/018_catalog_item_region_price.sql 为准
class SupplierCatalogItemRegion(Base):
    """价格、建议售价、最低售价、最高售价、币种，以及运费、到达天数、税费，按区域各存一行。"""

    __tablename__ = "supplier_catalog_item_region"
    __table_args__ = (
        UniqueConstraint("item_id", "region_id", name="uq_catalog_item_region"),
        Index("idx_catalog_item_region_region", "region_id"),
        {**_SHOP_TABLE, "comment": "供应商产品目录的区域价格"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(comment="supplier_catalog_item.id")
    region_id: Mapped[int] = mapped_column(comment="sys_region.id")
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="价格")
    suggested_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="建议售价")
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最低售价")
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="最高售价")
    currency: Mapped[str] = mapped_column(String(3), default="", comment="币种，取通用属性 currency 的编码")
    shipping_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="运费")
    arrival_days_min: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最快到达天数")
    arrival_days_max: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最慢到达天数")
    tax: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="税费")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 供应商文档：建表以 contracts/ddl/014_supplier_document.sql 为准
class SupplierDocument(Base):
    __tablename__ = "supplier_document"
    __table_args__ = (
        Index("idx_supplier_document_supplier", "supplier_id"),
        Index("idx_supplier_document_type", "doc_type"),
        {**_SHOP_TABLE, "comment": "供应商文档"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(comment="供应商 supplier.id")
    title: Mapped[str] = mapped_column(String(200), comment="文档标题")
    doc_type: Mapped[str] = mapped_column(String(30), default="other", comment="license/qualification/contract/pricelist/catalog/other")
    file_url: Mapped[str] = mapped_column(String(500), comment="本系统上传地址")
    file_name: Mapped[str] = mapped_column(String(180), default="", comment="原始文件名")
    file_size: Mapped[int] = mapped_column(Integer, default=0, comment="字节数")
    remark: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 系统通用属性：建表以 contracts/ddl/012_sys_attr.sql 为准
class SysAttrType(Base):
    __tablename__ = "sys_attr_type"
    __table_args__ = (
        UniqueConstraint("code", name="uq_sys_attr_type_code"),
        {**_SHOP_TABLE, "comment": "系统通用属性类型"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), comment="类型标识码，如 currency")
    cn_name: Mapped[str] = mapped_column(String(50), comment="中文名称")
    en_name: Mapped[str] = mapped_column(String(50), default="", comment="英文名称")
    is_tree: Mapped[int] = mapped_column(SmallInteger, default=0, comment="1树型 0平铺")
    use_code: Mapped[int] = mapped_column(SmallInteger, default=0, comment="1启用编码")
    ext_schema: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="扩展字段 schema")
    sort_order: Mapped[int] = mapped_column(default=0, comment="排序，越小越靠前")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SysAttrValue(Base):
    __tablename__ = "sys_attr_value"
    __table_args__ = (
        UniqueConstraint("type_id", "code", name="uq_sys_attr_value_code"),
        Index("idx_sys_attr_value_type", "type_id"),
        Index("idx_sys_attr_value_parent", "parent_id"),
        {**_SHOP_TABLE, "comment": "系统通用属性值"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type_id: Mapped[int] = mapped_column(comment="sys_attr_type.id")
    parent_id: Mapped[int | None] = mapped_column(nullable=True, comment="上级属性值，仅树型使用")
    cn_name: Mapped[str] = mapped_column(String(100), comment="中文名称")
    en_name: Mapped[str] = mapped_column(String(100), default="", comment="英文名称")
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="编码；空存 NULL，避免唯一索引冲突")
    sort_order: Mapped[int] = mapped_column(default=0, comment="排序，越小越靠前")
    ext_values: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="扩展字段值")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1启用 0停用")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 国家地区 / 区域：建表以 contracts/ddl/017_geo_region.sql 为准
class GeoNode(Base):
    """国家地区树：全球 → 洲 → 国家。is_leaf=1 的节点才能被区域勾选。"""

    __tablename__ = "sys_geo"
    __table_args__ = (
        UniqueConstraint("code", name="uq_sys_geo_code"),
        Index("idx_sys_geo_parent", "parent_id"),
        {**_SHOP_TABLE, "comment": "国家地区"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(default=0, comment="上级 sys_geo.id，0为顶级")
    code: Mapped[str] = mapped_column(String(10), comment="编码，如 ALL、AFR、CN")
    name_zh: Mapped[str] = mapped_column(String(50), comment="中文名")
    name_en: Mapped[str] = mapped_column(String(80), default="", comment="英文名")
    is_leaf: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1子节点（国家/地区） 0分组（全球/洲）")
    sort_order: Mapped[int] = mapped_column(default=0, comment="排序，越小越靠前")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class GeoRegion(Base):
    __tablename__ = "sys_region"
    __table_args__ = (
        UniqueConstraint("name", name="uq_sys_region_name"),
        {**_SHOP_TABLE, "comment": "区域"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), comment="区域名称")
    sort_order: Mapped[int] = mapped_column(default=0, comment="排序，越小越靠前")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class GeoRegionCountry(Base):
    """区域勾选的国家地区。可以是国家，也可以是全球或洲（表示其下全部国家，不展开成国家 id）。"""

    __tablename__ = "sys_region_country"
    __table_args__ = (
        UniqueConstraint("region_id", "geo_id", name="uq_sys_region_country"),
        Index("idx_sys_region_country_geo", "geo_id"),
        {**_SHOP_TABLE, "comment": "区域包含的国家"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(comment="sys_region.id")
    geo_id: Mapped[int] = mapped_column(comment="sys_geo.id；全球或洲表示其下全部，不展开国家")


# 销售平台与店铺：建表以 contracts/ddl/021_platform_store.sql 为准（应用启动 create_all 也会建表）
class Platform(Base):
    __tablename__ = "platform"
    __table_args__ = (
        UniqueConstraint("code", name="uq_platform_code"),
        UniqueConstraint("name", name="uq_platform_name"),
        {**_SHOP_TABLE, "comment": "销售平台"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), comment="编码")
    name: Mapped[str] = mapped_column(String(100), comment="平台名称")
    name_en: Mapped[str] = mapped_column(String(100), default="", comment="平台名称（英文）")
    website: Mapped[str] = mapped_column(String(255), default="", comment="网址")
    market: Mapped[str] = mapped_column(String(100), default="", comment="市场")
    feature: Mapped[str] = mapped_column(String(500), default="", comment="特性")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    is_independent: Mapped[int] = mapped_column(SmallInteger, default=0, comment="1独立站 0否")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Store(Base):
    __tablename__ = "store"
    __table_args__ = (
        UniqueConstraint("platform_id", "code", name="uq_store_platform_code"),
        UniqueConstraint("platform_id", "name", name="uq_store_platform_name"),
        Index("idx_store_platform", "platform_id"),
        {**_SHOP_TABLE, "comment": "店铺"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(comment="platform.id")
    code: Mapped[str] = mapped_column(String(50), comment="编码")
    name: Mapped[str] = mapped_column(String(100), comment="店铺名称")
    name_en: Mapped[str] = mapped_column(String(100), default="", comment="店铺名称（英文）")
    website: Mapped[str] = mapped_column(String(255), default="", comment="网址")
    feature: Mapped[str] = mapped_column(String(500), default="", comment="特性")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    shipping_package_group_id: Mapped[int] = mapped_column(default=0, comment="默认包装组，0表示未设置")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class StoreCategory(Base):
    """店铺绑定的商品分类，多选。删除店铺或分类时由应用层清掉。"""

    __tablename__ = "store_category"
    __table_args__ = (
        UniqueConstraint("store_id", "category_id", name="uq_store_category"),
        Index("idx_store_category_cat", "category_id"),
        {**_SHOP_TABLE, "comment": "店铺绑定的商品分类"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(comment="store.id")
    category_id: Mapped[int] = mapped_column(comment="shop_category.id")


class ShopifyStoreConfig(Base):
    __tablename__ = "shopify_store_config"
    __table_args__ = (
        UniqueConstraint("store_id", name="uq_shopify_store_config_store"),
        UniqueConstraint("shop_domain", name="uq_shopify_store_config_domain"),
        {**_SHOP_TABLE, "comment": "Shopify 店铺配置"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(comment="store.id")
    shop_domain: Mapped[str] = mapped_column(String(255), comment="Shopify 固定域名")
    shop_gid: Mapped[str] = mapped_column(String(100), default="")
    region_id: Mapped[int] = mapped_column(comment="sys_region.id")
    language_code: Mapped[str] = mapped_column(String(20), default="")
    default_location_gid: Mapped[str] = mapped_column(String(100), default="")
    stock_location_id: Mapped[int] = mapped_column(default=0, comment="stock_location.id，0表示尚未绑定")
    publication_gid: Mapped[str] = mapped_column(String(100), default="")
    currency: Mapped[str] = mapped_column(String(3), default="")
    sync_enabled: Mapped[int] = mapped_column(SmallInteger, default=1)
    connection_status: Mapped[str] = mapped_column(String(20), default="unchecked")
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifyTaxonomyCategory(Base):
    __tablename__ = "shopify_taxonomy_category"
    __table_args__ = (
        UniqueConstraint("taxonomy_gid", name="uq_shopify_taxonomy_gid"),
        UniqueConstraint("category_id", name="uq_shopify_taxonomy_category_id"),
        Index("idx_shopify_taxonomy_parent", "parent_gid"),
        Index("idx_shopify_taxonomy_active_level", "is_active", "level"),
        {**_SHOP_TABLE, "comment": "Shopify 官方标准产品分类"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    taxonomy_gid: Mapped[str] = mapped_column(String(100), comment="Shopify TaxonomyCategory GID")
    category_id: Mapped[str] = mapped_column(String(60), comment="分类短 ID")
    parent_gid: Mapped[str] = mapped_column(String(100), default="", comment="上级 TaxonomyCategory GID")
    level: Mapped[int] = mapped_column(SmallInteger, default=0, comment="树层级")
    name_zh: Mapped[str] = mapped_column(String(255), default="", comment="简体中文名称")
    full_name_zh: Mapped[str] = mapped_column(String(2000), default="", comment="简体中文完整路径")
    name_en: Mapped[str] = mapped_column(String(255), default="", comment="英文名称")
    full_name_en: Mapped[str] = mapped_column(String(2000), default="", comment="英文完整路径")
    is_leaf: Mapped[int] = mapped_column(SmallInteger, default=0, comment="1末级分类 0仍有下级")
    is_active: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1当前版本有效 0已被官方移除")
    version: Mapped[str] = mapped_column(String(30), default="", comment="Shopify taxonomy 发布版本")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopifyCategoryMap(Base):
    __tablename__ = "shopify_category_map"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_shopify_category_map_category"),
        Index("idx_shopify_category_map_taxonomy", "taxonomy_category_id"),
        {**_SHOP_TABLE, "comment": "mzShop 分类与 Shopify 标准分类关联"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    category_id: Mapped[int] = mapped_column(comment="shop_category.id")
    taxonomy_category_id: Mapped[int] = mapped_column(comment="shopify_taxonomy_category.id")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopifyTaxonomyAttribute(Base):
    __tablename__ = "shopify_taxonomy_attribute"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    taxonomy_gid: Mapped[str] = mapped_column(String(100), unique=True)
    handle: Mapped[str] = mapped_column(String(180), default="")
    name_zh: Mapped[str] = mapped_column(String(255), default="")
    name_en: Mapped[str] = mapped_column(String(255), default="")
    description_zh: Mapped[str] = mapped_column(String(2000), default="")
    description_en: Mapped[str] = mapped_column(String(2000), default="")
    is_active: Mapped[int] = mapped_column(SmallInteger, default=1)
    version: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifyTaxonomyAttributeValue(Base):
    __tablename__ = "shopify_taxonomy_attribute_value"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    attribute_id: Mapped[int] = mapped_column(index=True)
    taxonomy_gid: Mapped[str] = mapped_column(String(100), unique=True)
    handle: Mapped[str] = mapped_column(String(255), default="")
    name_zh: Mapped[str] = mapped_column(String(255), default="")
    name_en: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[int] = mapped_column(SmallInteger, default=1)
    version: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifyTaxonomyCategoryAttribute(Base):
    __tablename__ = "shopify_taxonomy_category_attribute"
    __table_args__ = (UniqueConstraint("taxonomy_category_id", "handle", name="uq_shopify_category_attribute"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    taxonomy_category_id: Mapped[int] = mapped_column(index=True)
    taxonomy_attribute_id: Mapped[int] = mapped_column(index=True)
    handle: Mapped[str] = mapped_column(String(180))
    name_zh: Mapped[str] = mapped_column(String(255), default="")
    name_en: Mapped[str] = mapped_column(String(255), default="")
    description_zh: Mapped[str] = mapped_column(String(2000), default="")
    description_en: Mapped[str] = mapped_column(String(2000), default="")
    is_extended: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifyAttributeMap(Base):
    __tablename__ = "shopify_attribute_map"
    __table_args__ = (UniqueConstraint("category_id", "category_attribute_id", name="uq_shopify_attribute_map"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(index=True)
    category_attribute_id: Mapped[int] = mapped_column(index=True)
    local_attribute_id: Mapped[int] = mapped_column(index=True)
    value_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifyTaxonomyMetaobjectMap(Base):
    __tablename__ = "shopify_taxonomy_metaobject_map"
    __table_args__ = (UniqueConstraint("store_id", "category_attribute_id", "taxonomy_value_id", name="uq_shopify_taxonomy_metaobject"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(index=True)
    category_attribute_id: Mapped[int] = mapped_column(index=True)
    taxonomy_value_id: Mapped[int] = mapped_column(index=True)
    metaobject_gid: Mapped[str] = mapped_column(String(100))
    metaobject_type: Mapped[str] = mapped_column(String(180), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifyProductMap(Base):
    __tablename__ = "shopify_product_map"
    __table_args__ = (
        UniqueConstraint("goods_id", "store_id", name="uq_shopify_product_map_goods_store"),
        UniqueConstraint("product_gid", "store_id", name="uq_shopify_product_map_product_store"),
        {**_SHOP_TABLE, "comment": "Shopify 商品映射"},
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int]
    goods_id: Mapped[int]
    product_gid: Mapped[str] = mapped_column(String(100))
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    sync_status: Mapped[str] = mapped_column(String(20), default="pending")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remote_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifyVariantMap(Base):
    __tablename__ = "shopify_variant_map"
    __table_args__ = (
        UniqueConstraint("sku_id", "store_id", name="uq_shopify_variant_map_sku_store"),
        UniqueConstraint("variant_gid", "store_id", name="uq_shopify_variant_map_variant_store"),
        {**_SHOP_TABLE, "comment": "Shopify SKU 映射"},
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int]
    goods_id: Mapped[int]
    sku_id: Mapped[int]
    variant_gid: Mapped[str] = mapped_column(String(100))
    inventory_item_gid: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopifySyncTask(Base):
    __tablename__ = "shopify_sync_task"
    __table_args__ = {**_SHOP_TABLE, "comment": "Shopify 主动同步任务"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int]
    goods_id: Mapped[int]
    action: Mapped[str] = mapped_column(String(30), default="upsert_product")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    request_id: Mapped[str] = mapped_column(String(100), default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class BundleRevision(Base):
    __tablename__ = "shop_bundle_revision"
    __table_args__ = (UniqueConstraint("parent_sku_id", "version_no", name="uq_shop_bundle_revision_parent_version"),
                      {**_SHOP_TABLE, "comment": "固定组合版本"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    parent_sku_id: Mapped[int] = mapped_column(comment="组合父SKU")
    version_no: Mapped[int] = mapped_column(comment="父SKU内递增版本号")
    status: Mapped[str] = mapped_column(String(20), default="draft", comment="draft/published/disabled")
    replaced_revision_id: Mapped[int] = mapped_column(BigInteger, default=0, comment="替换的旧版本id")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="版本说明")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="发布时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class BundleComponent(Base):
    __tablename__ = "shop_bundle_component"
    __table_args__ = (UniqueConstraint("revision_id", "component_sku_id", name="uq_shop_bundle_component_revision_sku"),
                      {**_SHOP_TABLE, "comment": "固定组合版本组件"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    revision_id: Mapped[int] = mapped_column(BigInteger, comment="组合版本id")
    component_sku_id: Mapped[int] = mapped_column(comment="普通组件SKU")
    quantity: Mapped[int] = mapped_column(comment="每套所需数量")
    sort_order: Mapped[int] = mapped_column(default=0, comment="显示顺序")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class StockLocation(Base):
    __tablename__ = "stock_location"
    __table_args__ = {**_SHOP_TABLE, "comment": "库存地点"}
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    code: Mapped[str] = mapped_column(String(50), unique=True, comment="库存地点编码")
    name: Mapped[str] = mapped_column(String(100), unique=True, comment="库存地点名称")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1启用 0停用")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class StockBalance(Base):
    __tablename__ = "stock_balance"
    __table_args__ = (UniqueConstraint("sku_id", "location_id", name="uq_stock_balance_sku_location"),
                      {**_SHOP_TABLE, "comment": "SKU地点库存余额"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    sku_id: Mapped[int] = mapped_column(comment="普通SKU")
    location_id: Mapped[int] = mapped_column(comment="库存地点")
    on_hand: Mapped[int] = mapped_column(default=0, comment="在库数量")
    reserved: Mapped[int] = mapped_column(default=0, comment="已支付订单占用")
    unavailable: Mapped[int] = mapped_column(default=0, comment="不可售数量")
    safety_stock: Mapped[int] = mapped_column(default=0, comment="安全库存")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class StockLedger(Base):
    __tablename__ = "stock_ledger"
    __table_args__ = {**_SHOP_TABLE, "comment": "库存流水"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    sku_id: Mapped[int] = mapped_column(comment="普通SKU")
    location_id: Mapped[int] = mapped_column(comment="库存地点")
    event_type: Mapped[str] = mapped_column(String(30), comment="库存事件类型")
    delta_on_hand: Mapped[int] = mapped_column(default=0, comment="在库变化量")
    delta_reserved: Mapped[int] = mapped_column(default=0, comment="占用变化量")
    delta_unavailable: Mapped[int] = mapped_column(default=0, comment="不可售变化量")
    after_on_hand: Mapped[int] = mapped_column(comment="变化后在库")
    after_reserved: Mapped[int] = mapped_column(comment="变化后占用")
    after_unavailable: Mapped[int] = mapped_column(comment="变化后不可售")
    reference_type: Mapped[str] = mapped_column(String(30), default="", comment="来源类型")
    reference_id: Mapped[int] = mapped_column(BigInteger, default=0, comment="来源记录id")
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, comment="业务幂等键")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="说明")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")


class ShopifyBundleMap(Base):
    __tablename__ = "shopify_bundle_map"
    __table_args__ = (UniqueConstraint("parent_sku_id", "store_id", name="uq_shopify_bundle_map_sku_store"),
                      {**_SHOP_TABLE, "comment": "Shopify组合版本同步映射"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    store_id: Mapped[int] = mapped_column(comment="店铺id")
    parent_sku_id: Mapped[int] = mapped_column(comment="组合父SKU")
    revision_id: Mapped[int] = mapped_column(BigInteger, comment="最近同步版本")
    source_hash: Mapped[str] = mapped_column(String(64), default="", comment="组合定义摘要")
    sync_status: Mapped[str] = mapped_column(String(20), default="pending", comment="同步状态")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近成功时间")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="最近错误")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopOrder(Base):
    __tablename__ = "shop_order"
    __table_args__ = (UniqueConstraint("store_id", "external_order_gid", name="uq_shop_order_store_external"),
                      {**_SHOP_TABLE, "comment": "Shopify订单镜像"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    store_id: Mapped[int] = mapped_column(comment="店铺id")
    external_order_gid: Mapped[str] = mapped_column(String(100), comment="Shopify订单GID")
    order_no: Mapped[str] = mapped_column(String(80), comment="订单显示编号")
    financial_status: Mapped[str] = mapped_column(String(30), default="", comment="支付状态")
    fulfillment_status: Mapped[str] = mapped_column(String(30), default="", comment="履约状态")
    cancel_status: Mapped[str] = mapped_column(String(20), default="active", comment="取消状态")
    shop_currency: Mapped[str] = mapped_column(String(3), comment="店铺币种")
    presentment_currency: Mapped[str] = mapped_column(String(3), comment="顾客结算币种")
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="订单总额")
    presentment_total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="结算币种总额")
    total_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="折扣合计")
    total_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="税费合计")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="订单处理时间")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="取消时间")
    last_external_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="外部更新时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopOrderLine(Base):
    __tablename__ = "shop_order_line"
    __table_args__ = (UniqueConstraint("order_id", "external_line_gid", name="uq_shop_order_line_external"),
                      {**_SHOP_TABLE, "comment": "订单行及组合组件快照"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    order_id: Mapped[int] = mapped_column(BigInteger, comment="订单id")
    external_line_gid: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Shopify订单行GID")
    external_group_gid: Mapped[str] = mapped_column(String(100), default="", comment="组合分组GID")
    parent_line_id: Mapped[int] = mapped_column(BigInteger, default=0, comment="组合父行id")
    line_type: Mapped[str] = mapped_column(String(20), comment="normal/bundle_parent/bundle_component")
    goods_id: Mapped[int] = mapped_column(default=0, comment="商品id")
    sku_id: Mapped[int] = mapped_column(default=0, comment="SKU id")
    bundle_revision_id: Mapped[int] = mapped_column(BigInteger, default=0, comment="组合版本id")
    sku_code: Mapped[str] = mapped_column(String(64), default="", comment="SKU编码快照")
    title: Mapped[str] = mapped_column(String(300), comment="标题快照")
    spec_name: Mapped[str] = mapped_column(String(200), default="", comment="规格快照")
    quantity: Mapped[int] = mapped_column(comment="订购数量")
    reserved_quantity: Mapped[int] = mapped_column(default=0, comment="已占用数量")
    fulfilled_quantity: Mapped[int] = mapped_column(default=0, comment="已发货数量")
    cancelled_quantity: Mapped[int] = mapped_column(default=0, comment="已取消数量")
    refunded_quantity: Mapped[int] = mapped_column(default=0, comment="已退款数量")
    returned_sellable_quantity: Mapped[int] = mapped_column(default=0, comment="可售退货数量")
    returned_unavailable_quantity: Mapped[int] = mapped_column(default=0, comment="不可售退货数量")
    unit_original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="原单价")
    allocated_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="分摊成交小计")
    allocated_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="分摊折扣")
    allocated_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="分摊税费")
    presentment_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="结算币种成交小计")
    presentment_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="结算币种折扣")
    presentment_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="结算币种税费")
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="单位成本快照")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopRefund(Base):
    __tablename__ = "shop_refund"
    __table_args__ = (UniqueConstraint("store_id", "external_refund_gid", name="uq_shop_refund_store_external"),
                      {**_SHOP_TABLE, "comment": "Shopify退款镜像"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    order_id: Mapped[int] = mapped_column(BigInteger, comment="订单id")
    store_id: Mapped[int] = mapped_column(comment="店铺id")
    external_refund_gid: Mapped[str] = mapped_column(String(100), comment="Shopify退款GID")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="退款总额")
    presentment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="结算币种退款总额")
    shipping_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="退运费")
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="退税合计")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="退款处理时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopRefundLine(Base):
    __tablename__ = "shop_refund_line"
    __table_args__ = {**_SHOP_TABLE, "comment": "Shopify退款行"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    refund_id: Mapped[int] = mapped_column(BigInteger, comment="退款id")
    order_line_id: Mapped[int] = mapped_column(BigInteger, comment="订单行id")
    quantity: Mapped[int] = mapped_column(comment="退款数量")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="退款小计")
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="退税")
    presentment_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, comment="结算币种退款含税金额")
    restock_type: Mapped[str] = mapped_column(String(30), default="", comment="Shopify补库存类型")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")


class ShopReturn(Base):
    __tablename__ = "shop_return"
    __table_args__ = {**_SHOP_TABLE, "comment": "退货及入库确认"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    order_id: Mapped[int] = mapped_column(BigInteger, comment="订单id")
    store_id: Mapped[int] = mapped_column(comment="店铺id")
    external_return_gid: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Shopify退货GID")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/received/cancelled")
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="收货确认时间")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopReturnLine(Base):
    __tablename__ = "shop_return_line"
    __table_args__ = {**_SHOP_TABLE, "comment": "退货组件及质检结果"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    return_id: Mapped[int] = mapped_column(BigInteger, comment="退货id")
    order_line_id: Mapped[int] = mapped_column(BigInteger, comment="订单行id")
    quantity: Mapped[int] = mapped_column(comment="退回数量")
    sellable_quantity: Mapped[int] = mapped_column(default=0, comment="可售数量")
    unavailable_quantity: Mapped[int] = mapped_column(default=0, comment="不可售数量")
    reason: Mapped[str] = mapped_column(String(200), default="", comment="退货原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class ShopifyWebhookEvent(Base):
    __tablename__ = "shopify_webhook_event"
    __table_args__ = (UniqueConstraint("store_id", "webhook_id", name="uq_shopify_webhook_event_store_webhook"),
                      {**_SHOP_TABLE, "comment": "Shopify Webhook幂等记录"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    store_id: Mapped[int] = mapped_column(comment="店铺id")
    webhook_id: Mapped[str] = mapped_column(String(100), comment="Webhook ID")
    topic: Mapped[str] = mapped_column(String(80), comment="Webhook主题")
    external_resource_id: Mapped[str] = mapped_column(String(100), default="", comment="外部资源GID")
    payload_sha256: Mapped[str] = mapped_column(String(64), comment="请求体摘要")
    status: Mapped[str] = mapped_column(String(20), default="processed", comment="processed/ignored/failed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="接收时间")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="处理时间")
