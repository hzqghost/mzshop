"""数据库引擎与会话。表已由 contracts/ddl/001_crawl_tables.sql 人工建好，采集器不建表。"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import DB_URL

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=1800, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()