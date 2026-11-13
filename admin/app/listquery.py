"""列表的服务端分页 / 筛选 / 排序：把 DevExtreme 表格传来的 sort、filter（JSON）翻译成 SQLAlchemy 条件。

只认白名单里的字段（fields: 字段名 → (SQL 表达式, 类型)，类型 num / str），其它一律 400，不会把前端传的字段名拼进 SQL。
filter 支持 DevExtreme 的写法：["字段","操作符",值]、["字段",值]、嵌套分组（"and" / "or"）、["!", 条件]；
操作符：= <> > >= < <= contains notcontains startswith endswith in/anyof。
"""
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import String, and_, cast, not_, or_

MAX_TAKE = 500
CONNECTORS = {"and": and_, "or": or_}


def _bad(msg: str = "筛选参数不合法"):
    raise HTTPException(400, msg)


def parse_json(raw: str | None, what: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        _bad(f"{what}参数不是合法的 JSON")


def _coerce(kind: str, v: Any):
    if v is None:
        return None
    if kind == "num":
        if isinstance(v, bool):
            return int(v)
        try:
            return float(v)
        except (TypeError, ValueError):
            _bad("数值筛选的值不合法")
    return str(v)


def _condition(node: list, fields: dict):
    name = node[0]
    if not isinstance(name, str) or name not in fields:
        _bad(f"不支持按 {name} 筛选")
    expr, kind = fields[name]
    if len(node) == 2:
        op, raw = "=", node[1]
    elif len(node) == 3 and isinstance(node[1], str):
        op, raw = node[1].lower(), node[2]
    else:
        _bad()
    if op in ("in", "anyof"):  # 值为数组，逐项转换后拼 IN（表格「查看已选」对服务端分页的列表用）
        if not isinstance(raw, list) or not 1 <= len(raw) <= 1000 or any(v is None for v in raw):
            _bad("in 筛选需要 1–1000 个值")
        return expr.in_([_coerce(kind, v) for v in raw])
    value = _coerce(kind, raw)
    if op in ("=", "<>"):
        if value is None:
            return expr.is_(None) if op == "=" else expr.isnot(None)
        return expr == value if op == "=" else expr != value
    if value is None:
        _bad()
    if op in (">", ">=", "<", "<="):
        return {">": expr > value, ">=": expr >= value, "<": expr < value, "<=": expr <= value}[op]
    if op in ("contains", "notcontains", "startswith", "endswith"):
        text = expr if kind == "str" else cast(expr, String)  # 数值列做「包含」按文本比
        v = str(raw)
        c = {"contains": text.contains, "notcontains": text.contains, "startswith": text.startswith,
             "endswith": text.endswith}[op](v, autoescape=True)  # 转义 % _，用户输入当普通文本
        return not_(c) if op == "notcontains" else c
    _bad(f"不支持的筛选操作符 {op}")


def build_filter(node: Any, fields: dict):
    """返回 SQLAlchemy 条件；没有条件返回 None。"""
    if node is None or node == []:
        return None
    if not isinstance(node, list):
        _bad()
    if node[0] == "!":
        inner = build_filter(node[1], fields) if len(node) == 2 else _bad()
        return not_(inner) if inner is not None else None
    if isinstance(node[0], str) and node[0].lower() not in CONNECTORS:
        return _condition(node, fields)  # 单个条件
    # 分组：条件与 "and"/"or" 交替；没写连接词按 and
    clauses, joiner = [], and_
    for item in node:
        if isinstance(item, str):
            if item.lower() not in CONNECTORS:
                _bad()
            joiner = CONNECTORS[item.lower()]
        else:
            c = build_filter(item, fields)
            if c is not None:
                clauses.append(c)
    return joiner(*clauses) if clauses else None


def build_sort(raw: Any, fields: dict) -> list:
    """sort: [{"selector": "name", "desc": false}, ...]"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        _bad("排序参数不合法")
    out = []
    for s in raw:
        sel = s.get("selector") if isinstance(s, dict) else None
        if sel not in fields:
            _bad(f"不支持按 {sel} 排序")
        expr = fields[sel][0]
        out.append(expr.desc() if s.get("desc") else expr.asc())
    return out


def clamp_page(skip: int, take: int) -> tuple[int, int]:
    return max(skip, 0), min(max(take, 1), MAX_TAKE)
