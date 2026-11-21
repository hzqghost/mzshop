---
paths:
  - "admin/templates/**"
  - "admin/static/js/lib/**"
  - "admin/static/css/**"
---

# 前端 / UI 契约（admin/templates、admin/static）

权威来源：`contracts/FRONTEND.md`（页面级约定）、`.qoder/rules/grid-conventions.md`（Grid 公共规则）、`static/js/lib/dxGrid.js`（实现）。以下为必须记住的要点。

## 页面骨架

- 内页 `{% extends "page.html" %}`，`{% block title %}`、`{% block body %}`；根容器 `<div class="page-pad">`，表格容器一个 `<div id="xxxGrid">`。
- `page.html` 已加载：jQuery、DevExtreme、`dxDefaults.js`、`dxGrid.js`、`api.js`、`adminTab.js`；按需再引 `shop.js`、`supplierCatalog.js`。全局 `window.APP = {HOST, LOCALE, GRID_STYLE}`。
- 页面 JS 写在模板底部 `<script>`，用 ES5 风格（`var`、`function`、jQuery），与现有页面一致，**不用模块/打包/TS/框架**。页面专属 CSS 写在同页 `<style>`，颜色用 `var(--mdm-*)`（`dxCustom.css`）。
- 新页面 3 件事：`templates/<name>.html`、`pages.py` 加 `_inner_page` 路由（路径 = 驼峰名，如 `/goodsEdit`）、`menu.py` 加菜单项。页面在 `index.html` 标签页 iframe 中运行。
- 调接口用 `apiPost`/`apiError`（`api.js`，401 自动跳登录）；非 POST（GET/PUT/DELETE/上传）在商品页参考 `shop.js` 内部的 `call`，产品池页用 `SUP.call(method, path, body)` / `SUP.upload`。用户提示用 `DevExpress.ui.notify(msg, 'success'|'error', ms)`。
- 详情/编辑大表单**不用弹窗**：`openAdminTab(url, title)` 在内容标签页打开；关闭用 `AdminLayout.closeTabByUrl`；列表与详情互刷用 `Shop.notifyChanged/onChanged`、`SUP.notifyChanged/onChanged`（BroadcastChannel）。
- 文本进 DOM 一律转义（`SUP.escapeHtml` 或 jQuery `.text()`），**不拼接 HTML**。

## DxGrid（所有表格）

- `new DxGrid(el, options)`；数据源：本地整表 `DxGrid.restStore(url, 'id')`（客户端筛选）；服务端分页 `DxGrid.remoteStore(url, 'id')` + `remoteOperations: {paging, filtering, sorting: true}` + 关 `headerFilter`。
- 默认已带（页面不要重写）：多选列、工具栏固定顺序 **刷新 → 批量操作 → 重置 → 导出 → 编辑模式 → 表格设置 → 列选择器**、过滤行/表头筛选/过滤面板/分组面板、列头右键菜单、布局记忆（localStorage `dxGrid:<gridKey>` + 服务端 `sys_grid_layout`）、过滤器模板、CSV 导出。**页面不要再加「刷新」按钮**；新增按钮用 `onToolbarPreparing` 放 `location:'before'`。搜索面板默认关。
- 审计列（`id`、`created_at/create_time`、`updated_at/update_time`、`created_by/creator`、`updated_by/last_operator`）创建时自动隐藏，页面不要自己在 `customizeColumns` 里再设 `visible:false`；外键列不隐藏。
- 操作列：`{type:'buttons', caption:'操作', buttons:['edit','delete', {icon, hint, onClick}]}`，`editing.useIcons: true`，只写图标不写 `text`，默认固定右侧。
- 标准 CRUD 编辑：`editing.mode:'popup'`，弹窗宽度三档 400 / 700 / 1000（品牌页用 640 亦可），表单 `colCount:1, labelLocation:'top'`；`onInitNewRow` 给默认值；`onRowDblClick` 进编辑；`onRowInserted/Updated/Removed` 里 notify + 通知相关页面。
- 批量动作：`batchActions: [{id, text, confirm, successText, run(keys)}]`；自定义删除 `batchDelete(key)`；拖动排序 `rowReorder(info)`（**必须在创建时传**）。
- 同页多表格或路径带参数：传 `gridKey` 区分（如 `/goodsAttributes#v3`）；列结构大改时换 gridKey 版本号，避免旧布局盖掉新列。
- 子表/小表格 `dxFeatures: false`。`masterDetail` 默认不允许 fixed 列（要固定传 `keepColumnFixing: true`，见产品目录）。
- 表高度默认 `autoHeight` 撑满，自己传 `height` 即关闭。

## 已验证的坑（DevExtreme 24.1）

- 不要覆盖编辑弹窗表单的 `onFieldDataChanged` / `onContentReady`；联动显隐包 `onValueChanged`（在 `onEditorPreparing` 里取原 handler 调用），初始状态用 `editing.popup.onShown`；带点号的 dataField（`i18n.en.name`）不能 `itemOption`。
- 数字列多值筛选用 `anyof`，不用 `in`。
- 无 `loadState/applyState`，只有 `grid.state(x)`。
- `dxDropDownButton` 菜单项变更要 `option('items', items.slice())` 才会重渲染。
- `stateStoring` 必须在创建时默认选项里；`customLoad` 没存过要返回 `{}` 不能返回 `null`。
- 自动化点击用 `$(el).trigger('dxclick')`，合成 DOM `dxclick` 事件无效。

## 多语言

- 页面里的多语言列/表单项：先 `Shop.ready.then(...)` 再建表格；列用 `Shop.withLang(columns, afterField, Shop.langColumns('name','名称'))`，表单项用 `Shop.langItems(field)` / 手写 `i18n.<code>.<field>`；`onInitNewRow` 里 `e.data.i18n = Shop.blankI18n([...])`。
- 字典类字段名 `category_id`、`supplier_id`、`brand_id` 在表单里由 `dxDefaults.js` 自动升级成带搜索的 `dxLookup`，别再手配。

## 样式

- UI 配色/尺寸来自用户级「Grid 配置 / Form 配置」（`sys_ui_style`，`ui_style.py` 校验），通过 body class + CSS 变量注入；自定义样式用 `--mdm-*` 变量，不写死色值（现有页面有少量写死，新代码避免）。
- 第三方库放 `static/js/plugins/<name>@<version>/`，版本写进目录名。富文本用自托管 TinyMCE 8（GPL，`license_key:'gpl'`）。

## 验证清单（UI 改动交付前）

重启后端 → 强刷 → 打开该页面 → 增/改/删/排序/筛选走一遍 → 控制台无报错 → 工具栏顺序与审计列符合公共规则 → 清理测试数据 → 契约同步。
