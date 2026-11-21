# mzShop — Claude 工作契约（入口）

电商统一数据管理后台。本文件每次对话自动加载；细则见 `.claude/rules/`（按改动路径自动加载）和 `contracts/`（业务/接口/表结构的权威契约，由多个 AI 工具与人工共同维护）。

## 1. 技术栈（以代码为准）

| 层 | 技术 |
|---|---|
| 后端 | Python 3 · FastAPI 0.162 · SQLAlchemy 2.1（同步，PyMySQL）· Jinja2 · Starlette SessionMiddleware（Cookie `mz_admin`） |
| 数据库 | MySQL 8，库 `pdc_shop`，utf8mb4 / utf8mb4_unicode_ci，**无外键，级联在应用层** |
| 前端 | 服务端渲染 Jinja2 + jQuery 3.7 + DevExtreme 24.1.3（material blue light compact）+ FontAwesome；**无打包/构建**，库自托管在 `admin/static/js/plugins/<name>@<version>/`，不用 CDN |
| 外壳 | `index.html` 菜单 + 标签页，每个标签是 iframe，内页继承 `page.html` |
| 采集器 | `tool/crawler/`，独立进程（Playwright + httpx，eBay），**只通过数据库与 admin 通信** |

目录：`admin/app/`（main、models、listquery、menu、routers/*）· `admin/templates/`（一页一文件）· `admin/static/js/lib/`（dxGrid、shop、supplierCatalog、api、adminTab、adminLayout）· `contracts/`（契约 + `ddl/` 编号脚本）。

## 2. 运行与验证

- 启动：`preview_start` 名称 `mzshop-admin`（`.claude/launch.json`，uvicorn `app.main:app` 端口 8000，**无 `--reload`**，改 Python 后必须重启）。用 admin 自带 `.venv`。
- 无测试套件、无 lint 配置：验证 = 重启后端 + 在浏览器里实测（登录账号见 `admin/app/config.py`，**不要把口令抄进任何文档/提交/聊天**）。
- 静态 JS/CSS 基本没有版本号，改完 `dxGrid.js` 等后强制刷新（`fetch(url,{cache:'reload'})` 或 Ctrl+F5）再验。
- 页面验证：测试数据用完清理；UI 改动截图/读取 DOM 作证。
- `.env` 在 `admin/.env`（已 gitignore），连接信息**禁止**出现在代码、契约、提交、聊天里。

## 3. 铁律（违反即返工）

1. **DDL 只出脚本，由人工审核执行**：写 `contracts/ddl/NNN_xxx.sql`（编号接续，现到 024），文件头写用途/影响/预览/执行/回滚；**不要自己去连库执行 DDL 或数据修复**。
2. **不引入新框架/新依赖**（含 npm 构建链、ORM 替换、前端框架），除非用户确认。版本固定在 `admin/requirements.txt`。
3. **表格一律用 `DxGrid`**（`static/js/lib/dxGrid.js`），不要直接 `new dxDataGrid`；公共行为改 DxGrid 一处，页面里不重复实现。树形用 `dxTreeList` + `DxGrid.treeOptions()`。
4. **接口统一 `{code, data, msg}`**，失败 `raise HTTPException(status, 中文msg)`，由 `main.py` 转换；路由默认挂 `require_user`。
5. **服务端分页/筛选/排序一律走 `listquery.py` 白名单**，绝不把前端字段名拼进 SQL。
6. **不确定的业务规则先问，不按名字猜**；契约与代码冲突时先问负责人，不擅自二选一。
7. 注释、界面文案、DB Comment 用中文；标识符（表、字段、变量、路径）用英文。
8. 密码 scrypt 哈希；敏感信息不入普通业务字段、不进日志；上传文件校验扩展名 + 文件头。

## 4. 标准工作流

1. 读 `contracts/TODO.md`（已知偏差）+ 与任务相关的契约；改前先读同类现有实现并**照抄其风格**（见 §5 参考实现）。
2. 先用一两句话说明方案；涉及表结构先出 DDL 方案等审核。
3. 小步修改，只动任务需要的文件。**工作区有大量其他 AI 工具留下的未提交改动**（见 git status），不要还原、不要顺手"整理"不属于本任务的文件。
4. 实测验证（§2）。
5. **同步契约**：新表 → `contracts/TABLES.md` + `ddl/`；新接口 → `contracts/API.md`；新页面/菜单 → `contracts/ADMIN.md`、`FRONTEND.md`；新发现的偏差 → `contracts/TODO.md`。
6. 不主动 commit；提交信息遵循仓库历史风格（中文/英文均可，简洁说明改了什么）。

## 5. 参考实现（新代码照这些写）

| 要做的事 | 抄谁 |
|---|---|
| 标准 CRUD 接口（校验、唯一、被引用不可删、i18n、拖动排序） | `admin/app/routers/brands.py` |
| 服务端分页大表接口 | `routers/shop.py`（goods）、`routers/supplier_catalog.py`（items） |
| 弹窗 CRUD 列表页 | `templates/brands.html`、`users.html`、`platforms.html` |
| 服务端分页列表页 | `templates/goods.html`、`supplierCatalog.html` |
| 详情页（内容标签页打开） | `templates/goodsEdit.html`、`supplierCatalogEdit.html` |
| 树形页 | `templates/goodsCategories.html` |
| 多语言 | `static/js/lib/shop.js`（`Shop.ready/langColumns/withLang/langItems`）+ `routers/shop_i18n.py` |

## 6. 已知漂移（动手前心里有数，详情见 `contracts/TODO.md`）

- `main.py` lifespan 里 `create_all` + `ensure_catalog_purchase_price`（运行时 `ALTER TABLE`）+ 种子/回填，**与"DDL 人工执行"冲突**。不要再往 lifespan 加新的 ALTER；新增结构只出 DDL。
- `contracts/ADMIN.md` 的 routers 清单与 models 说明已落后（实际 router 有 attrs、brands、geo、platforms、supplier_catalog、grid_filters、grid_layouts 等）；`TABLES.md` 抬头"电商业务表尚未设计"已过期。以代码为准，改到相关处时顺手更正。
- 超级管理员口令硬编码在 `config.py`（TODO 已记录）；`.claude/launch.json` 监听 `0.0.0.0`，契约写的是 127.0.0.1。
- `ok()` / `fail()` / `_fmt()` 在每个 router 里各复制一份；新 router 沿用同样写法保持一致，**不要单独重构**，要抽公共模块先问。
- `admin/templates/_extract_js.py`、`_gcheck.js` 是调试残留，不是页面，勿当作模板参考。
- `admin/requirements.txt`、`.env.example` 带 UTF-8 BOM。

## 7. 其他 AI 工具遗留

- `.qoder/rules/grid-conventions.md`：Qoder 写的 Grid 公共规则，内容有效，已被 `.claude/rules/frontend.md` 吸收并以其为准；两处冲突时以 `contracts/FRONTEND.md` + 代码为准。
