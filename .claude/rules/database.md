---
paths:
  - "contracts/ddl/**"
  - "admin/app/models.py"
  - "tool/crawler/models.py"
---

# 数据库 / DDL 契约

权威：`contracts/DB.md`、`contracts/TABLES.md`。

## 命名与结构

- 库表字段索引只用小写英文、数字、下划线；禁止拼音、无意义缩写、`field1/ext1` 预留列。
- 默认 `InnoDB` + `utf8mb4` + `utf8mb4_unicode_ci`；**表和每个业务字段都写中文 Comment**。
- **不建外键**；引用关系靠 `xxx_id` + 应用层守卫。"未设置"约定 `0`（如 `brand_id=0`、`category_id=0`、`parent_id=0`）。
- 唯一性用唯一索引兜底（命名 `uq_<table>_<cols>`），代码捕获 `IntegrityError` 转中文提示；可空唯一码（如 `brand.code`）空串存 NULL。
- 布尔 `SMALLINT/TINYINT` 1/0；状态用整数枚举并在 Comment 写明含义；金额 `DECIMAL(12,2)`；半结构化数据用 `JSON`。
- 排序列 `sort_order`，越小越靠前，拖动后重排为 10、20、30…。

## DDL 脚本规范

- 位置/命名：`contracts/ddl/NNN_<描述>.sql`（编号接续当前最大号，现为 024；数据迁移/种子用 `.py`）。
- 文件头注释必须含：**用途、影响的表字段、兼容性、预览（SELECT）、执行、回滚、注意事项**。
- 新增非空字段：先加可空 → 回填 → 改非空；删除/重命名字段前先全仓扫描引用（代码、接口、报表、采集器）。
- 只改 Comment 时不得顺带改类型/NULL/默认值/字符集/索引。
- 批量 UPDATE/DELETE 先给同条件 `SELECT` 预览。
- **只写脚本，不在对话里自行连库执行**；执行与备份由人工完成，执行后在 TABLES.md 标"已执行"。

## 同步清单

新表/新字段 → ① `models.py` 映射（含中文 comment）② `contracts/ddl/NNN_*.sql` ③ `contracts/TABLES.md` ④ 有接口则 `API.md`。

## 已知欠账

- `sys_user`、`sys_ui_style` 字段缺中文 Comment（补注释须走"只改 Comment"的 DDL）。
- `shop_goods.brand` / `supplier` 旧字符串列待应用完全切换后删除（`brand_id` / `supplier_id` 已是结构化引用）。
- 采集表（`crawl_*`、`product*`）DDL 在 `001_crawl_tables.sql`，admin 的 models 只映射用到的列；改列要同时看 `tool/crawler/models.py`。
