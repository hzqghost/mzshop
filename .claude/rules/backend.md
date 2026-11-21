---
paths:
  - "admin/app/**"
---

# 后端契约（admin/app）

## 新增模块 / 接口

1. 模型 `models.py`：表名带模块前缀（系统表 `sys_`），`__table_args__` 带 `mysql_charset=utf8mb4`、`mysql_collate=utf8mb4_unicode_ci`、表 `comment`；**每个字段写中文 `comment`**；时间列 `created_at/updated_at` 用 `server_default=func.now()`，更新列加 `onupdate=func.now()`；布尔存 `SmallInteger 1/0`，对外转 `bool`。
2. 同时在 `contracts/ddl/` 出对应 DDL（见 database.md），**模型改动不等于表已存在**。
3. 路由 `routers/<module>.py`：
   ```python
   router = APIRouter(prefix="/api/v1/<module>", dependencies=[Depends(require_user)])
   def ok(data=None): return {"code": 0, "data": data, "msg": "ok"}
   def fail(msg, status=400): raise HTTPException(status_code=status, detail=msg)
   ```
   在 `main.py` 里 `include_router`；页面路由在 `routers/pages.py` 用 `_inner_page` 注册；菜单在 `menu.py`。
4. REST 资源形态（DxGrid.restStore 依赖）：`GET ""` 数组、`POST ""` 返回新记录、`PUT /{id}` 只改传了的字段并返回更新后记录、`DELETE /{id}` 返回 `ok()`。
5. 详情/不存在 → 404；参数/业务校验 → 400，`msg` 是给用户看的中文。

## 写法约定（从现有代码归纳）

- 校验在 `_apply(db, obj, values, creating)`：`if "字段" in values or creating:`，**未传的字段保持原值**；文本用 `_text(values, f, label, size, required)` 统一 strip + 长度 + 必填。
- 唯一性靠库唯一索引 + 捕获 `IntegrityError` 转中文提示（`db.flush()` → 失败 `rollback()` → `fail`），不要先查后写。
- **无外键**：删除前在应用层检查被引用（`fail("该X已被 N 个Y 使用，不能删除")`），并级联清理子表/译文（`purge_translations`）/上传文件引用。
- 冗余快照字段（如 `shop_goods.brand`）在上游改名时同步更新。
- 多语言：译文存 `shop_translation`，接口 body 带 `i18n: {lang: {field: value}}`，与主体**同一事务**（`save_inline` 后再 `commit`），任一失败整体回滚。
- 拖动排序统一 `POST /<res>/move`，body `{id, target_id, after}`，全部 `sort_order` 重排为 10、20、30…；`id==target_id` → 400「参数不合法」，不存在 → 404。
- 批量动作：ids 1~500 个整数，返回 `{updated: n}`，不存在的 id 忽略。
- 时间输出 `YYYY-MM-DD HH:MM:SS`（`_fmt`）。
- 上传：`/shop/upload`、`supplier-catalog/uploads` 白名单扩展名 + 校验文件头 + 随机文件名，存 `admin/static/uploads/YYYYMM/`；删除/替换引用后，仅当无任何地方再引用时才删磁盘文件。保存失败走 `/uploads/discard`。

## 列表 / 大表

- 数据量可能上千行的列表必须支持服务端分页：`?take=&skip=&sort=<JSON>&filter=<JSON>`，不带 `take` 返回全部数组（兼容），带 `take` 返回 `{items, total}`。
- 用 `listquery.py`：`parse_json` → `build_filter(filter, FIELDS)` / `build_sort(sort, FIELDS)` / `clamp_page(skip, take)`；`FIELDS = {字段名: (SQL表达式, "num"|"str")}` 即白名单，计算列用 SQL 表达式；`MAX_TAKE=500`；`in`/`anyof` 值 1–1000 个。字段不在白名单、操作符不支持一律 400。
- 数值列的筛选多值用 `anyof`（`in` 会被 DevExtreme 规范成 `=`）。

## 认证

- 登录写 `session["user"] = {id, username, real_name, super}`；超管 `id=0` 不入库；API 未登录 401（`require_user`），页面未登录 303 → `/login`。目前**无角色权限**，登录即全权。
- 用户私有数据（样式、过滤器模板、布局）按 `user_id` 隔离，只能读写自己的。

## 启动期（lifespan）

- 现状有 `create_all`、`ensure_*`、种子/回填；**不要新增运行时 ALTER**。新增种子必须幂等（已有数据不覆盖）。
- 需要在现有库加列/表：出 DDL 给人工执行，同时代码要能在列尚未存在时给出明确报错而非静默失败（先确认 DDL 已执行再合并依赖它的代码）。

## 禁区

- 不在 SQL 中拼接用户输入；不在日志/响应里输出 `password_hash`、`.env`、口令。
- 不改 `requirements.txt` 版本、不加依赖，除非用户确认。
- 不把采集器逻辑塞进 admin：`tool/crawler` 与 admin 只通过表通信（`crawl_task/run/unit`、`product*`）。
