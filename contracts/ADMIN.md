# ADMIN 契约 — 管理后台（`admin/`）

## 1. 技术栈
FastAPI 0.162 · SQLAlchemy 2.x（PyMySQL）· Jinja2 · SessionMiddleware（Cookie `mz_admin`，24h，lax）· jQuery 3.7 · DevExtreme 24.1.3（material blue light compact）· FontAwesome。依赖见 `requirements.txt`（版本固定）。

## 2. 目录
```
admin/
  .env / .env.example     DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD SECRET_KEY
  app/
    main.py               应用入口，注册 router、统一 HTTPException 为 {code,data,msg}
    config.py             读取 .env；DB_URL；SUPER_ADMIN
    db.py                 engine / SessionLocal / Base / get_db
    deps.py               current_user / require_user
    models.py             ORM 模型（sys_user, sys_ui_style）
    security.py           scrypt 哈希与校验
    menu.py               左侧菜单（MENU）
    templating.py         render_page：渲染内页并注入用户样式
    ui_style.py / style_store.py   Grid/Form 样式配置的校验、默认值、存取
    routers/              pages(页面) auth(登录退出) users style crawl_tasks products shop shop_i18n
  templates/              page.html 为内页基类；index.html 为外壳(菜单+标签页)
  static/{css,js/lib,js/plugins}
```
启动：见 `.claude/launch.json`（`uvicorn app.main:app`，127.0.0.1:8000）。

## 3. 认证
- 登录 `POST /login/do`（表单），成功写 `session["user"] = {id, username, real_name, super}`，退出 `GET /logout`。
- 内置超级管理员：id=0，写在 `config.SUPER_ADMIN`，不入库、不出现在用户列表。
- 页面未登录 → 303 到 `/login`；API 未登录 → 401（`require_user`）。
- 目前**没有角色/权限**，登录即可访问全部功能。

## 4. 新增一个业务模块（标准步骤）
1. 模型：在 `models.py`（模块多了拆文件）定义，表名用模块前缀（系统表 `sys_`），字段全部写中文 comment，遵守 DB.md。
2. 接口：`routers/<module>.py`，`APIRouter(prefix="/api/v1/<module>", dependencies=[Depends(require_user)])`，响应遵守 API.md；在 `main.py` 注册。
3. 页面：`templates/<module>.html` 继承 `page.html`，在 `routers/pages.py` 用 `_inner_page` 注册 GET 路由；
4. 菜单：在 `menu.py` 加条目（叶子 `{title,url}`，分组 `{title,icon,children}`，页面在标签页 iframe 中打开）。
5. 更新 TABLES.md / API.md。

## 5. 建表策略
当前 `main.py` lifespan 使用 `Base.metadata.create_all`，仅为早期方便；与 DB.md「DDL 须人工审核执行」存在冲突，见 TODO.md。新增表一律同时提供 DDL 脚本给人工审核。
