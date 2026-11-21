# ADMIN 契约 — 管理后台（`admin/`）

## 1. 技术栈
FastAPI 0.162 · SQLAlchemy 2.x（PyMySQL）· Jinja2 · SessionMiddleware（Cookie `mz_admin`，24h，lax）· jQuery 3.7 · DevExtreme 24.1.3（material blue light compact）· FontAwesome。依赖见 `requirements.txt`（版本固定）。

## 2. 目录
```
admin/
  .env / .env.example     DB_*、SECRET_KEY；Shopify App 凭据与主动同步参数（密钥不入库）
  app/
    main.py               应用入口，注册 router、统一 HTTPException 为 {code,data,msg}
    config.py             读取 .env；DB_URL；SUPER_ADMIN
    db.py                 engine / SessionLocal / Base / get_db
    deps.py               current_user / require_user
    models.py             ORM 模型（sys_user, sys_ui_style）
    security.py           scrypt 哈希与校验
    menu.py               左侧菜单（MENU）
    templating.py         render_page：渲染内页并注入用户样式
    ui_style.py / style_store.py   菜单/Grid/Form 样式配置的校验、默认值、存取
    shopify_client.py      Shopify Client Credentials + GraphQL 客户端（短期令牌仅内存缓存）
    shopify_sync.py        商品、价格、库存完整状态推送与映射回写
    routers/              pages(页面) auth(登录退出) users style shop shop_i18n platforms
  templates/              page.html 为内页基类；index.html 为外壳(菜单+标签页)
  static/{css,js/lib,js/plugins}
tool/shopify/run.py        Shopify 持久化同步任务 worker
```
启动：见 `.Codex/launch.json` / `.claude/launch.json`。公网入口为 `https://admin.monozex.com:10086`：路由器将公网 10086 转发到本机 Apache TLS 8000，Apache 反向代理到仅监听 `127.0.0.1:8001` 的 Uvicorn。Windows 手工重启可双击项目根目录 `重启后台.cmd`，或执行 `powershell -ExecutionPolicy Bypass -File tool/admin/restart.ps1`；脚本只处理本项目 Uvicorn，隐藏启动后检查 `/login`。

SSL 使用 Let’s Encrypt DNS-01，不依赖公网 80/443。win-acme 和 Aliyun DNS 插件安装在 `E:/httpserver/win-acme`，证书输出到 `E:/httpserver/certs/mzshop`；首次以管理员身份执行 `tool/ssl/setup.ps1`，在本机窗口录入阿里云 RAM AccessKey。凭据保存在 win-acme vault，不得进入仓库、日志或聊天。首次签发和自动续期成功后都会调用 `tool/ssl/deploy.ps1`，更新 PEM、检查并重载 Apache；`tool/ssl/setup-renewal-task.ps1` 以 SYSTEM 身份创建每日 09:00、随机延迟最多 4 小时的续期任务。

## 3. 认证
- 登录 `POST /login/do`（表单），成功写 `session["user"] = {id, username, real_name, super}`，退出 `GET /logout`。
- 内置超级管理员：id=0，写在 `config.SUPER_ADMIN`，不入库、不出现在用户列表。
- 页面未登录 → 303 到 `/login`；API 未登录 → 401（`require_user`）。
- 目前**没有角色/权限**，登录即可访问全部功能。

## 4. 新增一个业务模块（标准步骤）
1. 模型：在 `models.py`（模块多了拆文件）定义，表名用模块前缀（系统表 `sys_`），字段全部写中文 comment，遵守 DB.md。
2. 接口：`routers/<module>.py`，`APIRouter(prefix="/api/v1/<module>", dependencies=[Depends(require_user)])`，响应遵守 API.md；在 `main.py` 注册。
3. 页面：`templates/<module>.html` 继承 `page.html`，在 `routers/pages.py` 用 `_inner_page` 注册 GET 路由；
4. 菜单：在 `menu.py` 加条目（叶子 `{title,url,icon}`，分组 `{title,icon,children}`，叶子图标同时显示在菜单和内容标签中，页面在标签页 iframe 中打开）。
5. 更新 TABLES.md / API.md。

## 5. 建表策略
当前 `main.py` lifespan 使用 `Base.metadata.create_all`，仅为早期方便；与 DB.md「DDL 须人工审核执行」存在冲突，见 TODO.md。新增表一律同时提供 DDL 脚本给人工审核。

## 6. Shopify

- 「店铺 → Shopify」为二级菜单，下设三级菜单「标准分类」「标准属性值」「分类关联」「分类属性」「同步任务」。
- `/shippingTemplates` 维护固定、实际重量、计费重量模板及区域规则；商品详情可在「区域销售价格」选择模板。模板为可选配置，不影响上架、SKU 保存或 Shopify 推送。
- 「店铺」下增加 `/shippingPackages`「包装管理」，分别维护包装箱与包装组；商品、SKU、店铺引用包装组，换箱只修改包装组当前箱；包装组可上传最多 20 张参考图片。
- `/shopifyTaxonomy`：Shopify 官方标准分类服务端分页列表，可从 Shopify 官方 product-taxonomy 最新稳定版本更新中英文分类。
- `/shopifyTaxonomyAttributes`：Shopify 官方属性服务端分页列表；展开属性查看官方属性值，支持从官方稳定版整体更新分类、属性、值和关系。
- `/shopifyCategoryMaps`：管理 mzShop 分类与 Shopify 官方标准分类的绑定、更换和解绑；支持中文、英文路径和分类 ID 搜索。
- `/shopifyCategoryAttributes`：按 mzShop 分类查看 Shopify 专属属性，映射本地属性，并逐项映射本地固定选项与官方 TaxonomyValue。
- `/shopifyTasks`：同步任务，使用 `DxGrid` 服务端分页。
- 展示等待/处理中/成功/失败/已取消状态、商品、店铺、动作、重试、各时间、Request ID 和错误信息。
- 失败或取消任务可从操作列重新加入等待队列；批量操作提供批量重试和删除选中行。等待中/处理中任务禁止删除；长时间 pending 时页面提示检查独立 worker。

## 7. 组合、库存与订单

- 商品管理新增 `/bundles`「组合装」：版本列表、父/组件 SKU 子 Grid、草稿新增/编辑/删除和本地配方启用。列表展示父 SKU 区域有效售价、各地点实时可用库存；子 Grid 的 SKU 编码可直接打开所属商品详情；已启用版本不可修改，替换组件必须新建版本。
- 新增一级菜单「库存」，下设 `/inventory`「库存管理」。库存管理按 SKU、库存地点展示当前余额；顶部业务栏右侧“操作”菜单提供“地点管理”和“调整 SKU 库存”，已有余额也可从行操作调整；列表的“调整说明”默认隐藏。旧 SKU 汇总库存不再编辑。
- 新增「订单管理 → Shopify订单」 `/orders`：订单服务端分页、组件明细、极简退货入库确认；不提供本地下单、改价、发货或主动退款。
- 店铺 Shopify 配置增加 mzShop 库存地点绑定和“注册订单 Webhook”动作。

## 8. UI配置

- 系统管理菜单下仅保留 `/uiStyle`「UI配置」入口，页面包含「菜单 Menu」「Grid 表格」「Form 表单」三个 Tab；原 `/gridStyle`、`/formStyle` 页面作为后两个 Tab 的内容载体保留，不再单独显示在菜单中。
- 菜单宽度按用户保存为 `sys_ui_style.kind=menu`，默认 150px，可配置范围 120~480px；保存后立即更新当前后台外壳，刷新后继续生效。
