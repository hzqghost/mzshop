"""定时执行（契约 §4）：按 schedule_cron 维护 next_run_at，到期且无 active run 时创建 schedule run。"""
import logging
from datetime import datetime

from croniter import croniter
from sqlalchemy import select

from models import CrawlRun, CrawlTask

log = logging.getLogger("crawler.scheduler")
ACTIVE = ("pending", "running")


def compute_next(cron: str, base: datetime | None = None) -> datetime | None:
    base = base or datetime.now()
    try:
        return croniter(cron, base).get_next(datetime)
    except (ValueError, KeyError):
        return None


def tick(s) -> int:
    """处理所有启用定时的任务；返回本次新建的 schedule run 数。在调用方的会话内执行。"""
    now = datetime.now()
    created = 0
    tasks = s.scalars(select(CrawlTask).where(
        CrawlTask.status == 1, CrawlTask.schedule_enabled == 1,
    )).all()
    for t in tasks:
        cron = (t.schedule_cron or "").strip()
        if not cron:
            continue
        if t.next_run_at is None:
            nxt = compute_next(cron, now)
            if nxt is not None:
                t.next_run_at = nxt
            continue
        if t.next_run_at > now:
            continue
        # 到期：同一任务已有 pending/running 时不重复创建，也不推进 next_run_at（下轮再试）
        active = s.scalar(select(CrawlRun.id).where(
            CrawlRun.task_id == t.id, CrawlRun.status.in_(ACTIVE),
        ).limit(1))
        if active is not None:
            continue
        s.add(CrawlRun(task_id=t.id, trigger_type="schedule", status="pending"))
        t.last_run_at = now
        t.next_run_at = compute_next(cron, now)
        created += 1
        log.info("任务 %s 定时到期，新建 schedule run", t.id)
    return created