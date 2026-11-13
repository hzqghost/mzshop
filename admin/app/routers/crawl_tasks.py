"""采集任务管理。响应 {code, data, msg}。「执行」只插入一条待执行的 crawl_run，由独立的采集器进程领取。"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import CrawlRun, CrawlRunUnit, CrawlTask

router = APIRouter(prefix="/api/v1/crawl-tasks", dependencies=[Depends(require_user)])

PLATFORMS = {"ebay": "eBay"}
MAX_PAGES_LIMIT = 10  # 每个采集单元的页数硬上限；采集器取页时也必须再卡一次，见 contracts/CRAWLER.md
CRON_FIELD = re.compile(r"^[\d*/,\-]+$")
ACTIVE_RUN = ("pending", "running")


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _task_dict(t: CrawlTask, last: CrawlRun | None = None) -> dict:
    return {
        "id": t.id,
        "platform": t.platform,
        "name": t.name,
        "keyword": t.keyword,
        "max_pages": t.max_pages,
        "category_names": t.category_names or [],
        "attr_name": t.attr_name,
        "status": bool(t.status),
        "schedule_enabled": bool(t.schedule_enabled),
        "schedule_cron": t.schedule_cron,
        "next_run_at": _fmt(t.next_run_at),
        "last_run_at": _fmt(t.last_run_at),
        "last_run_status": last.status if last else None,
        "created_at": _fmt(t.created_at),
    }


def _run_dict(r: CrawlRun) -> dict:
    return {
        "id": r.id,
        "task_id": r.task_id,
        "trigger_type": r.trigger_type,
        "status": r.status,
        "total_units": r.total_units,
        "done_units": r.done_units,
        "item_count": r.item_count,
        "error_msg": r.error_msg,
        "started_at": _fmt(r.started_at),
        "finished_at": _fmt(r.finished_at),
        "created_at": _fmt(r.created_at),
    }


def _apply(task: CrawlTask, values: dict, creating: bool) -> None:
    """校验并写入可编辑字段；values 只含本次提交的字段。"""
    if "platform" in values or creating:
        platform = str(values.get("platform") or "ebay").strip()
        if platform not in PLATFORMS:
            fail("不支持的平台")
        task.platform = platform
    for f, label, size in (("name", "任务名称", 100), ("keyword", "搜索关键字", 200)):
        if f in values or creating:
            v = str(values.get(f) or "").strip()
            if not v:
                fail(f"{label}不能为空")
            if len(v) > size:
                fail(f"{label}最长 {size} 个字符")
            setattr(task, f, v)
    if "max_pages" in values or creating:
        try:
            pages = int(values.get("max_pages") or 0)
        except (TypeError, ValueError):
            pages = 0
        if not 1 <= pages <= MAX_PAGES_LIMIT:
            fail(f"页数需在 1~{MAX_PAGES_LIMIT} 之间")
        task.max_pages = pages
    if "category_names" in values or creating:
        cats = values.get("category_names")
        if not isinstance(cats, list):
            fail("分类名格式不正确")
        cats = list(dict.fromkeys(str(c).strip() for c in cats if str(c).strip()))  # 去空、去重、保序
        if not cats:
            fail("至少填写一个分类名")
        task.category_names = cats
    if "attr_name" in values:
        task.attr_name = str(values.get("attr_name") or "").strip()[:100]
    elif creating:
        task.attr_name = ""
    if "status" in values:
        task.status = 1 if values["status"] else 0
    elif creating:
        task.status = 1
    if "schedule_enabled" in values:
        task.schedule_enabled = 1 if values["schedule_enabled"] else 0
    elif creating:
        task.schedule_enabled = 0
    if "schedule_cron" in values:
        task.schedule_cron = " ".join(str(values.get("schedule_cron") or "").split())
    elif creating:
        task.schedule_cron = ""
    if task.schedule_enabled:
        parts = task.schedule_cron.split()
        if len(parts) != 5 or not all(CRON_FIELD.match(p) for p in parts):
            fail("定时表达式需为 5 段 cron，如 0 3 * * *")
    # 定时设置变了就清掉下次执行时间，由采集器重新计算
    if {"schedule_enabled", "schedule_cron"} & values.keys():
        task.next_run_at = None


def _last_runs(db: Session, task_ids: list[int]) -> dict[int, CrawlRun]:
    if not task_ids:
        return {}
    latest = select(func.max(CrawlRun.id)).where(CrawlRun.task_id.in_(task_ids)).group_by(CrawlRun.task_id)
    return {r.task_id: r for r in db.scalars(select(CrawlRun).where(CrawlRun.id.in_(latest)))}


@router.get("")
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.scalars(select(CrawlTask).order_by(CrawlTask.id.desc())).all()
    last = _last_runs(db, [t.id for t in tasks])
    return ok([_task_dict(t, last.get(t.id)) for t in tasks])


@router.post("")
def create_task(values: dict, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    task = CrawlTask(created_by=user["id"])
    _apply(task, values, creating=True)
    db.add(task)
    db.commit()
    return ok(_task_dict(task))


@router.put("/{task_id}")
def update_task(task_id: int, values: dict, db: Session = Depends(get_db)):
    task = db.get(CrawlTask, task_id) or fail("任务不存在", 404)
    _apply(task, values, creating=False)
    db.commit()
    return ok(_task_dict(task, _last_runs(db, [task.id]).get(task.id)))


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(CrawlTask, task_id) or fail("任务不存在", 404)
    if db.scalar(select(CrawlRun.id).where(CrawlRun.task_id == task_id, CrawlRun.status.in_(ACTIVE_RUN)).limit(1)):
        fail("任务有待执行或执行中的记录，不能删除")
    run_ids = select(CrawlRun.id).where(CrawlRun.task_id == task_id)
    db.execute(delete(CrawlRunUnit).where(CrawlRunUnit.run_id.in_(run_ids)))
    db.execute(delete(CrawlRun).where(CrawlRun.task_id == task_id))
    db.delete(task)  # 已采集的商品保留，其 task_id 仅作最近来源记录
    db.commit()
    return ok()


@router.post("/{task_id}/run")
def run_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(CrawlTask, task_id) or fail("任务不存在", 404)
    if not task.status:
        fail("任务已停用")
    if db.scalar(select(CrawlRun.id).where(CrawlRun.task_id == task_id, CrawlRun.status.in_(ACTIVE_RUN)).limit(1)):
        fail("该任务已有待执行或执行中的记录")
    run = CrawlRun(task_id=task_id, trigger_type="manual", status="pending")
    db.add(run)
    db.commit()
    return ok(_run_dict(run))


@router.get("/{task_id}/runs")
def list_runs(task_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(CrawlRun).where(CrawlRun.task_id == task_id).order_by(CrawlRun.id.desc()).limit(200)).all()
    return ok([_run_dict(r) for r in rows])


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    """待执行的直接取消；执行中的采集器会在单元之间检查到 cancelled 后停止（采集器实现时遵守）。"""
    run = db.get(CrawlRun, run_id) or fail("执行记录不存在", 404)
    if run.status not in ACTIVE_RUN:
        fail("该记录已结束")
    run.status = "cancelled"
    run.finished_at = func.now()
    db.commit()
    return ok()
