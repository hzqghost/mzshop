from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, Date, DateTime, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, func
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


# 采集系统表：建表以 contracts/ddl/001_crawl_tables.sql 为准（已执行），这里只映射后台用到的列
_CRAWL_TABLE = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class CrawlTask(Base):
    __tablename__ = "crawl_task"
    __table_args__ = {**_CRAWL_TABLE, "comment": "采集任务"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20), default="ebay")
    name: Mapped[str] = mapped_column(String(100))
    keyword: Mapped[str] = mapped_column(String(200))
    max_pages: Mapped[int] = mapped_column(SmallInteger, default=1)
    category_names: Mapped[list] = mapped_column(JSON)
    attr_name: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    schedule_enabled: Mapped[int] = mapped_column(SmallInteger, default=0)
    schedule_cron: Mapped[str] = mapped_column(String(100), default="")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CrawlRun(Base):
    __tablename__ = "crawl_run"
    __table_args__ = {**_CRAWL_TABLE, "comment": "采集执行记录"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_units: Mapped[int] = mapped_column(Integer, default=0)
    done_units: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str] = mapped_column(String(500), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CrawlRunUnit(Base):
    __tablename__ = "crawl_run_unit"
    __table_args__ = {**_CRAWL_TABLE, "comment": "采集单元"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    category_name: Mapped[str] = mapped_column(String(200))
    attr_value: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    pages_done: Mapped[int] = mapped_column(SmallInteger, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str] = mapped_column(String(500), default="")



class Product(Base):
    """商品（采集落库，(platform, item_id) 唯一）。admin 只做查看、少量字段修正和删除，写入由采集器负责。"""

    __tablename__ = "product"
    __table_args__ = {**_CRAWL_TABLE, "comment": "商品"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20))
    item_id: Mapped[str] = mapped_column(String(40))
    task_id: Mapped[int | None] = mapped_column(nullable=True)
    run_id: Mapped[int | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    product_url: Mapped[str] = mapped_column(String(500), default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    category_name: Mapped[str] = mapped_column(String(200), default="")
    search_attrs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    brand: Mapped[str] = mapped_column(String(100), default="")
    item_condition: Mapped[str] = mapped_column(String(50), default="")
    mpn: Mapped[str] = mapped_column(String(100), default="")
    upc: Mapped[str] = mapped_column(String(50), default="")
    country_of_origin: Mapped[str] = mapped_column(String(100), default="")
    listing_type: Mapped[str] = mapped_column(String(30), default="")
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="")
    shipping_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    view_count: Mapped[int | None] = mapped_column(nullable=True)
    watcher_count: Mapped[int | None] = mapped_column(nullable=True)
    sold_count: Mapped[int | None] = mapped_column(nullable=True)
    available_qty: Mapped[int | None] = mapped_column(nullable=True)
    review_count: Mapped[int | None] = mapped_column(nullable=True)
    review_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    seller_name: Mapped[str] = mapped_column(String(100), default="")
    seller_feedback_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    seller_feedback_cnt: Mapped[int | None] = mapped_column(nullable=True)
    item_location: Mapped[str] = mapped_column(String(100), default="")
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ProductReview(Base):
    __tablename__ = "product_review"
    __table_args__ = {**_CRAWL_TABLE, "comment": "商品评价（含商品评价与卖家反馈）"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int]
    review_type: Mapped[str] = mapped_column(String(20), default="product")
    review_key: Mapped[str] = mapped_column(String(64))
    reviewer_name: Mapped[str] = mapped_column(String(100), default="")
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    helpful_count: Mapped[int] = mapped_column(default=0)
    is_verified: Mapped[int] = mapped_column(SmallInteger, default=0)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProductSnapshot(Base):
    __tablename__ = "product_snapshot"
    __table_args__ = {**_CRAWL_TABLE, "comment": "商品价格热度快照"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int]
    run_id: Mapped[int | None] = mapped_column(nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="")
    shipping_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    view_count: Mapped[int | None] = mapped_column(nullable=True)
    watcher_count: Mapped[int | None] = mapped_column(nullable=True)
    sold_count: Mapped[int | None] = mapped_column(nullable=True)
    available_qty: Mapped[int | None] = mapped_column(nullable=True)
    review_count: Mapped[int | None] = mapped_column(nullable=True)
    review_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# 自有商品目录：建表以 contracts/ddl/002_shop_tables.sql 为准（已执行）
_SHOP_TABLE = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class ShopCategory(Base):
    __tablename__ = "shop_category"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品分类"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(default=0)
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
    attr_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ShopGoodsImage(Base):
    __tablename__ = "shop_goods_image"
    __table_args__ = {**_SHOP_TABLE, "comment": "商品图片"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_id: Mapped[int]
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
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    stock: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


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
    name: Mapped[str] = mapped_column(String(100))
    website: Mapped[str] = mapped_column(String(255), default="")
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    contact_phone: Mapped[str] = mapped_column(String(50), default="")
    contact_email: Mapped[str] = mapped_column(String(100), default="")
    default_currency: Mapped[str] = mapped_column(String(3), default="", comment="默认币种，取通用属性 currency 的编码")
    excel_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Brand(Base):
    __tablename__ = "brand"
    __table_args__ = {**_SHOP_TABLE, "comment": "品牌字典"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


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
