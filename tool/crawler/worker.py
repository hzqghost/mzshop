"""采集 worker：领取 pending run、展开单元、逐单元采集、回写进度与 run 状态。

admin 与采集器只通过数据库通信。网络请求都在短会话之外进行，避免长事务占用连接。
"""
import logging
import time
from datetime import datetime

from sqlalchemy import func, select, update

import config
import scheduler
import storage
from base import BlockedError, CollectError
from db import session_scope
from models import CrawlRun, CrawlRunUnit, CrawlTask
from registry import get_collector

log = logging.getLogger("crawler.worker")
_DONE_STATUSES = ("success", "failed", "skipped")


def claim_next_run() -> int | None:
    """原子领取最早的一个 pending run：UPDATE ... WHERE status='pending' 判断影响行数，避免多进程重复执行。"""
    with session_scope() as s:
        rid = s.scalar(select(CrawlRun.id).where(CrawlRun.status == "pending").order_by(CrawlRun.id).limit(1))
        if rid is None:
            return None
        res = s.execute(update(CrawlRun).where(CrawlRun.id == rid, CrawlRun.status == "pending")
                        .values(status="running", started_at=datetime.now()))
        return rid if res.rowcount == 1 else None


def claim_run(run_id: int) -> bool:
    with session_scope() as s:
        res = s.execute(update(CrawlRun).where(CrawlRun.id == run_id, CrawlRun.status == "pending")
                        .values(status="running", started_at=datetime.now()))
        return res.rowcount == 1


def _is_cancelled(run_id: int) -> bool:
    with session_scope() as s:
        return s.scalar(select(CrawlRun.status).where(CrawlRun.id == run_id)) == "cancelled"


def _expand_units(task, collector) -> list[dict]:
    """展开「分类 × 属性值」。属性值运行时从搜索页左侧读取；读取失败就该分类建一个 failed 单元，不影响其它分类。"""
    units: list[dict] = []
    for raw in (task.category_names or []):
        category = str(raw).strip()
        if not category:
            continue
        if not task.attr_name:
            units.append({"category_name": category, "attr_value": "", "status": "pending", "error_msg": ""})
            continue
        try:
            values = collector.list_attr_values(task, category)
            values = list(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))
            if not values:
                units.append({"category_name": category, "attr_value": "", "status": "failed", "error_msg": "未读取到属性值"})
                continue
            for v in values:
                units.append({"category_name": category, "attr_value": v[:200], "status": "pending", "error_msg": ""})
        except Exception as e:  # 单元失败不影响其它单元
            log.warning("分类 %s 读取属性值失败: %s", category, e)
            units.append({"category_name": category, "attr_value": "", "status": "failed", "error_msg": f"读取属性值失败: {e}"[:500]})
    return units


def _ensure_units(run_id: int, task, collector) -> None:
    with session_scope() as s:
        if s.scalar(select(func.count()).select_from(CrawlRunUnit).where(CrawlRunUnit.run_id == run_id)):
            return  # 已展开（断点重试时复用）
    units = _expand_units(task, collector)  # 网络请求在会话之外
    with session_scope() as s:
        if s.scalar(select(func.count()).select_from(CrawlRunUnit).where(CrawlRunUnit.run_id == run_id)):
            return
        for u in units:
            s.add(CrawlRunUnit(run_id=run_id, category_name=u["category_name"], attr_value=u["attr_value"],
                               status=u["status"], error_msg=u["error_msg"]))
        run = s.get(CrawlRun, run_id)
        if run is not None:
            run.total_units = len(units)


def _execute_unit(run_id: int, task, collector, unit_id: int, category: str, attr_value: str) -> None:
    with session_scope() as s:
        u = s.get(CrawlRunUnit, unit_id)
        if u is None:
            return
        u.status = "running"
        u.started_at = datetime.now()

    pages = min(int(task.max_pages or 1), config.MAX_PAGES)  # 防御性硬上限，即使库里被改大也只取 10 页
    item_count = 0
    pages_done = 0
    status = "success"
    err = ""
    try:
        for page in range(1, pages + 1):
            stubs = collector.search(task, category, attr_value, page)
            if not stubs:
                break
            for stub in stubs:
                item = collector.parse_item(stub, task, category, attr_value)
                if not item or not item.get("item_id"):
                    continue
                reviews = collector.fetch_reviews(item)
                with session_scope() as s:
                    pid = storage.upsert_product(s, item, task.id, run_id)
                    storage.append_snapshot(s, pid, item, run_id)
                    storage.upsert_reviews(s, pid, reviews)
                item_count += 1
            pages_done = page
            with session_scope() as s:
                u = s.get(CrawlRunUnit, unit_id)
                if u is not None:
                    u.pages_done = pages_done
                    u.item_count = item_count
    except BlockedError as e:
        status, err = "failed", f"访问受阻（退避后不破解）: {e}"
        log.warning("单元 %s 受阻: %s", unit_id, e)
    except CollectError as e:
        status, err = "failed", str(e)
        log.warning("单元 %s 采集失败: %s", unit_id, e)
    except Exception as e:
        status, err = "failed", f"{type(e).__name__}: {e}"
        log.exception("单元 %s 异常", unit_id)

    with session_scope() as s:
        u = s.get(CrawlRunUnit, unit_id)
        if u is not None:
            u.status = status
            u.pages_done = pages_done
            u.item_count = item_count
            u.error_msg = err[:500]
            u.finished_at = datetime.now()
        run = s.get(CrawlRun, run_id)
        if run is not None and run.status == "running":
            run.done_units = (run.done_units or 0) + 1
            run.item_count = (run.item_count or 0) + item_count


def _skip_pending(run_id: int) -> None:
    with session_scope() as s:
        s.execute(update(CrawlRunUnit).where(CrawlRunUnit.run_id == run_id, CrawlRunUnit.status == "pending")
                  .values(status="skipped", finished_at=datetime.now()))


def _run_units(run_id: int, task, collector) -> None:
    with session_scope() as s:
        rows = s.scalars(select(CrawlRunUnit).where(
            CrawlRunUnit.run_id == run_id, CrawlRunUnit.status == "pending",
        ).order_by(CrawlRunUnit.id)).all()
        pending = [(u.id, u.category_name, u.attr_value) for u in rows]
    for uid, category, attr_value in pending:
        if _is_cancelled(run_id):  # 单元之间检查取消（契约 §4 / cancel 接口）
            log.info("run %s 已取消，跳过剩余单元", run_id)
            _skip_pending(run_id)
            break
        _execute_unit(run_id, task, collector, uid, category, attr_value)


def _finalize_run(run_id: int) -> None:
    with session_scope() as s:
        run = s.get(CrawlRun, run_id)
        if run is None:
            return
        units = s.scalars(select(CrawlRunUnit).where(CrawlRunUnit.run_id == run_id)).all()
        total = len(units)
        if run.status == "cancelled":
            for u in units:
                if u.status in ("pending", "running"):
                    u.status = "skipped"
                    u.finished_at = u.finished_at or datetime.now()
            run.total_units = total
            run.done_units = sum(1 for u in units if u.status in _DONE_STATUSES)
            run.item_count = sum(u.item_count or 0 for u in units)
            run.finished_at = run.finished_at or datetime.now()
            return
        failed = sum(1 for u in units if u.status == "failed")
        success = sum(1 for u in units if u.status == "success")
        run.total_units = total
        run.done_units = sum(1 for u in units if u.status in _DONE_STATUSES)
        run.item_count = sum(u.item_count or 0 for u in units)
        run.finished_at = datetime.now()
        if total == 0:
            run.status, run.error_msg = "failed", "无采集单元（分类名为空？）"
        elif failed == 0:
            run.status, run.error_msg = "success", ""
        elif success == 0:
            run.status, run.error_msg = "failed", "全部单元失败"
        else:
            run.status, run.error_msg = "partial", f"{failed}/{total} 单元失败"
        log.info("run %s 结束: %s，单元 %s/%s，商品 %s", run_id, run.status, run.done_units, total, run.item_count)


def execute_run(run_id: int) -> None:
    log.info("开始执行 run %s", run_id)
    with session_scope() as s:
        run = s.get(CrawlRun, run_id)
        if run is None or run.status != "running":
            log.warning("run %s 不存在或非 running，跳过", run_id)
            return
        task = s.get(CrawlTask, run.task_id)
        if task is None:
            run.status, run.error_msg, run.finished_at = "failed", "任务不存在", datetime.now()
            return
        task.last_run_at = datetime.now()
    # task 已 detached（expire_on_commit=False），所需列属性仍可读
    try:
        with get_collector(task.platform) as collector:
            _ensure_units(run_id, task, collector)
            _run_units(run_id, task, collector)
    except Exception as e:
        log.exception("run %s 执行异常", run_id)
        with session_scope() as s:
            run = s.get(CrawlRun, run_id)
            if run is not None and run.status == "running":
                run.status, run.error_msg = "failed", f"{type(e).__name__}: {e}"[:500]
    finally:
        _finalize_run(run_id)


def tick_schedule() -> None:
    with session_scope() as s:
        scheduler.tick(s)


def run_once(no_schedule: bool = False) -> int | None:
    if not no_schedule:
        tick_schedule()
    rid = claim_next_run()
    if rid is not None:
        execute_run(rid)
    return rid


def run_forever(no_schedule: bool = False) -> None:
    log.info("采集器启动，轮询间隔 %ss，最小请求间隔 %ss", config.POLL_INTERVAL, config.MIN_REQUEST_INTERVAL)
    while True:
        if not no_schedule:
            try:
                tick_schedule()
            except Exception:
                log.exception("定时处理异常")
        try:
            rid = claim_next_run()
            if rid is not None:
                execute_run(rid)
                continue
        except Exception:
            log.exception("领取/执行异常")
        time.sleep(config.POLL_INTERVAL)