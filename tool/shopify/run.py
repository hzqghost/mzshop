"""Shopify 主动同步 worker：使用 admin/.venv 运行，只通过数据库与后台协作。"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "admin"))

from sqlalchemy import or_, select  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import ShopifySyncTask  # noqa: E402
from app.shopify_sync import run_task  # noqa: E402


def claim():
    db = SessionLocal()
    try:
        task = db.scalar(select(ShopifySyncTask).where(
            ShopifySyncTask.status == "pending",
            or_(ShopifySyncTask.next_retry_at.is_(None), ShopifySyncTask.next_retry_at <= datetime.now()))
            .order_by(ShopifySyncTask.id).with_for_update(skip_locked=True).limit(1))
        if not task:
            db.rollback()
            return None, None
        task.status = "running"
        task.locked_at = task.started_at = datetime.now()
        db.commit()
        db.refresh(task)
        return db, task
    except Exception:
        db.close()
        raise


def once() -> bool:
    db, task = claim()
    if not task:
        return False
    try:
        print(f"处理 Shopify 同步任务 {task.id}，商品 {task.goods_id}，店铺 {task.store_id}")
        run_task(db, task)
        return True
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="处理一个任务后退出")
    parser.add_argument("--interval", type=int, default=5, help="空闲轮询秒数")
    args = parser.parse_args()
    if args.once:
        once()
        return
    while True:
        if not once():
            time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
