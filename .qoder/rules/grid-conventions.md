# Grid 公共规则（源自参考项目 E:\www\mdm\pdc，已在本项目落地）

本项目所有后台表格基于 `admin/static/js/lib/dxGrid.js` 的 DxGrid（DevExtreme 24.1.3 dxDataGrid 子类）。
以下规则是**公共规则**：改 DxGrid 一处生效全站，页面里不要重复实现、不要覆盖顺序；契约同步更新 `contracts/FRONTEND.md`、`contracts/API.md`、`contracts/TABLES.md`。

## 1. 工具栏固定顺序（右侧，参考项目图1口径）

刷新 → 批量操作 → 重置 → 导出 → 编辑模式（仅允许增删改时）→ 表格设置 → 列选择器。

- 刷新：`dxButton` icon `refresh`；页面**不要再自己加刷新按钮**。
- 批量操作：`dxDropDownButton` icon `selectall`，菜单见 §2。
- 重置：icon `revert`，清除筛选/搜索/排序/分组/选中，并退出「查看已选」。
- 导出：菜单 当前页 / 选中行 / 全部（按当前筛选），CSV UTF-8 带 BOM。
- 编辑模式：菜单 行/弹窗/单元格/表单/批量，当前模式打勾；打勾靠**重新赋值 slice 后的 items 数组**（见 §6）。
- 表格设置：菜单 恢复默认布局 / 保存布局 / 恢复布局 / 表格外观（Grid 配置）。
- 搜索面板默认**不显示**（`searchPanel: { visible: false }`），用筛选行/表头筛选/过滤面板；页面确有需要才自己传 `visible: true`。
- 页面自己的 `onToolbarPreparing` 在内置按钮之后执行，可继续增删（新增按钮放 `location: 'before'`）。

## 2. 批量菜单与「查看已选」

- 「查看已选」**永远排第一**；其后是「删除选中行」（表格允许删除或页面传了 `batchDelete` 时）；再后是页面 `batchActions: [{id, text, confirm?, successText?, run(keys)}]`。
- 点击「查看已选」= 过滤只显示勾选行：`filterValue = [主键列, 'anyof', keys]`（与原有筛选 `['and', 原筛选, 新条件]` 组合），再点恢复原筛选；菜单项用 `✓ ` 前缀标记当前态。
- 主键取自 `store().key()`；无单主键时提示不支持。
- 服务端分页表格同样可用：后端 `listquery.py` 认 `in`/`anyof`（值为 1–1000 个数组，拼 SQL IN）。

## 3. 布局记忆（两层）

- 浏览器本地：列宽/顺序/显隐/固定/排序/每页条数存 localStorage，键 `dxGrid:<gridKey>`；筛选/搜索/页码/选中行**不记**（保存前过 `DxGrid._sanitizeState`）。
- 服务端「保存布局 / 恢复布局」：表 `sys_grid_layout`，接口 `GET/POST /api/v1/grid-layouts`（见 §5）；恢复 = resetView → 应用 editMode → `grid.state(...)` → refresh。
- `gridKey`：默认 `location.pathname`；同页多表格或路径带参数时页面传 `gridKey` 选项区分（如 `/goodsAttributes#v2`）。
- 参考项目对比：MDM 用表 `sys_dxdatagrid`（用户+gridName+方案名，多方案）；本项目简化为每用户每表格一份（覆盖保存），要扩展多方案时参考 MDM 的 schemeName 设计。

## 4. 过滤器模板

- 过滤面板（构建器）底部「选择模板 / 保存为模板」，表 `sys_grid_filter`（用户+grid_key+name 唯一），接口 `/api/v1/grid-filters`，每表格最多 50 个，同名覆盖。

## 5. 数据表与接口约定

- `sys_grid_filter` / `sys_grid_layout`：DDL 在 `contracts/ddl/006、008_*.sql`（已授权执行、已执行）；utf8mb4/InnoDB，不建外键，文件头写明用途/影响/回滚。
- 布局 JSON 结构固定 `{state: DevExtreme 表格状态, editMode: 编辑模式|null}`。
- 后端一律响应 `{code: 0, data, msg}`；路由只要求登录（`require_user`），数据按 `user_id` 隔离，超级管理员 id=0（test.admin，不入库）。
- 列表接口用 `listquery.py` 白名单翻译 DevExtreme 的 filter/sort JSON 为 SQLAlchemy 条件：字段不在白名单、操作符不支持一律 400，绝不拼接前端字段名。支持操作符 `= <> > >= < <= contains notcontains startswith endswith in/anyof`；`MAX_TAKE=500`。

## 6. DevExtreme 24.1 已验证的坑（务必遵守）

- 数字列的筛选操作符 `in` 会被前端规范化成 `=`（多值失效）；**多值一律用 `anyof`**。
- 本构建的 dxDataGrid **没有 `loadState`/`applyState`**，只有 `state(x)` setter；恢复布局用 `grid.state(...)`。
- `dxDropDownButton` 的弹层 DOM 跨次打开**缓存**，菜单项模板只在重新赋值**新数组**时重渲染（`dd.option('items', items.slice())`）——菜单里要打勾/变文案都用这个套路。
- 自动化验证时合成 `dispatchEvent(new MouseEvent('dxclick'))` 触发不了 DevExtreme 处理器，要用 jQuery `$(el).trigger('dxclick')`。
- 静态 JS/CSS 无版本号，改完 dxGrid.js 浏览器可能用缓存：验证前 `fetch('/static/js/lib/dxGrid.js', {cache:'reload'})` + 刷新（或 Ctrl+F5）。
- `masterDetail` 开启时，`columnFixing.enabled: true` 或表格里有任何 `fixed` 列都会导致展开图标不渲染（展开单元格只剩 `&nbsp;`，`expandRow` API 可用但 UI 无入口），且修复**必须在创建时**做（`_init` 里再改不生效）。DxGrid 已在 ctor 处理：masterDetail 打开时强制 `columnFixing: {enabled:false}`，并用不固定勾选列/操作列的 `customizeColumns` 包装替换默认的（页面自己的 `customizeColumns` 仍执行）。

## 7. 前端组件约定（本项目）

- 数据源：本地数组用 `DxGrid.restStore(url, key)`（客户端筛选）；服务端分页用 `DxGrid.remoteStore(url, key)` + `remoteOperations {paging,filtering,sorting}`，并关闭 `headerFilter`（服务端没提供按列去重取值）。
- 详情页在框架内容标签里打开用 `openAdminTab(url, title)`；列表↔详情通信用 `Shop.notifyChanged / Shop.onChanged`（BroadcastChannel）。
- 操作列用图标按钮 `{icon, hint, onClick}`（`editing.useIcons: true`），不写 text；多选列默认开。
- 弹窗宽度三档（参考项目）：小 400 / 中 700 / 大 1000。
- 表格高度：默认 `autoHeight: true` 撑满窗口；页面自己传 `height` 即关闭自动高度。
- 树形表格用 `dxTreeList` + `DxGrid.styleOptions()/treeOptions()`，不吃 DxGrid 工具栏规则。

## 8. 开发验证环境

- 后端 uvicorn 跑在 127.0.0.1:8000，**无 --reload**：改 Python 代码要重启（netstat 找 PID → taskkill → 后台重新启动）。
- 登录：POST `/login/do`（form 编码），超管 `test.admin` / `TEST@2026@2026`（见 admin/app/config.py）。
- 功能改动必须在浏览器实测（browser-use MCP），测完清理测试数据；涉及 DxGrid 公共规则的改动按本文档顺序/文案/行为验收。
