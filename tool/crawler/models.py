"""采集系统全部 6 表的完整列映射（与 contracts/ddl/001_crawl_tables.sql 一致）。

admin 只映射它用到的子集；采集器需要写 product / product_review / product_snapshot，故在此完整映射。
独立 Base，不与 admin 共享 metadata；表已存在，采集器不调用 create_all。
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class CrawlTask(Base):
    __tablename__ = "crawl_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    category_name: Mapped[str] = mapped_column(String(200))
    attr_value: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    pages_done: Mapped[int] = mapped_column(SmallInteger, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str] = mapped_column(String(500), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20), default="ebay")
    item_id: Mapped[str] = mapped_column(String(40))
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watcher_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sold_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    seller_name: Mapped[str] = mapped_column(String(100), default="")
    seller_feedback_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    seller_feedback_cnt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_location: Mapped[str] = mapped_column(String(100), default="")
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ProductReview(Base):
    __tablename__ = "product_review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer)
    review_type: Mapped[str] = mapped_column(String(20), default="product")
    review_key: Mapped[str] = mapped_column(String(64))
    reviewer_name: Mapped[str] = mapped_column(String(100), default="")
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    is_verified: Mapped[int] = mapped_column(SmallInteger, default=0)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProductSnapshot(Base):
    __tablename__ = "product_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="")
    shipping_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watcher_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sold_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())