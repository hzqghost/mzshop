# FRONTEND 契约

- 内页一律继承 `templates/page.html`，通过 `render_page`（经 `routers/pages._inner_page`）渲染，自动注入当前用户的 Grid/Form 样式（body class + CSS 变量，样式在 `static/css/dxCustom.css`）。
- 页面运行在 `index.html` 外壳的标签页 iframe 内；打开标签用 `adminTab.js`。
- **表格一律用 `DxGrid`**（`static/js/lib/dxGrid.js`，继承 dxDataGrid），不要直接 new dxDataGrid；数据源用 `DxGrid.restStore('/api/v1/<res>', 'id')`，与 API.md 的 REST 约定及 `{code,data,msg}` 配套。表格层面的通用扩展加在 DxGrid 里。
- 调接口用 `apiPost` / `apiError`（`lib/api.js`）；401 自动跳登录页。
- 全局：`window.APP = {HOST, LOCALE:'zh-CN', GRID_STYLE}`；DevExtreme 中文本地化。
- 参考实现：`templates/users.html`（弹窗编辑、校验、工具栏按钮、提示语）。新列表页照此风格。
- 第三方库放 `static/js/plugins/<name>@<version>/`，版本写进目录名，不用 CDN。

## 商品管理页面约定
- **树形表格**用 `dxTreeList`（DxGrid 基于 dataGrid，不支持树），外观选项复用 `DxGrid.styleOptions()`；见 `templates/goodsCategories.html`（`parentIdExpr`+`rootValue:0`，行按钮 `add/edit/delete`）。
- **详情页在内容标签页里打开**：用 `openAdminTab(url, title)`，页面是普通内页（如 `/goodsEdit?id=..`，不要弹窗）。详情页自己关闭用 `AdminLayout.closeTabByUrl(打开时的 url)`；详情页与列表页之间用 `Shop.notifyChanged('goods')` / `Shop.onChanged('goods', cb)`（BroadcastChannel）通知刷新。
- 多语言列/表单项：`Shop.ready` → `Shop.langColumns / withLang / langItems`，见 API.md §6。
- 静态 JS/CSS 没有版本号，更新后浏览器可能读缓存，验证时需强制刷新（Ctrl+F5）。
- **服务端分页的表格**：`dataSource: DxGrid.remoteStore(url, 'id')` + `remoteOperations: {paging:true, filtering:true, sorting:true}`，并关闭 `headerFilter`（表头筛选要按列去重取值，服务端没提供，用筛选行代替）。见 `templates/goods.html`。

- **别覆盖表格编辑弹窗表单的 `onFieldDataChanged`**（以及 `onContentReady`）：表格靠它记录改动/初始化，覆盖后保存不会带上改动。需要联动字段显隐时，包一层对应列编辑器的 `onValueChanged`（在 `onEditorPreparing` 里取原 handler 再调用），弹窗打开时的初始状态用 `editing.popup.onShown`；带点号的 dataField（如 `i18n.en.unit`）不能直接 `itemOption`，放进命名分组整组显隐，且表单项保持字符串，不要加 `name`。见 `templates/goodsAttributes.html`。

## DxGrid 标准功能（所有表格默认带，页面不用再写）
- **工具栏**（右侧，公共规则的固定顺序）：刷新、批量操作（勾选框图标，菜单见下）、重置（图标 `revert`，清筛选/搜索/排序/分组/选中）、导出（CSV：当前页 / 选中行 / 全部按当前筛选，UTF-8 带 BOM，Excel 直接开）、编辑模式（允许增删改时）、表格设置（恢复默认布局 / 保存布局 / 恢复布局 / 打开「Grid 配置」）、列选择器。页面**不要再自己加「刷新」按钮**；页面自己的 `onToolbarPreparing` 在后面执行，仍可增删。
- **多选列**默认开（`selection: multiple`，勾选框，固定在左）；**操作列**用图标按钮（`editing.useIcons: true`，自定义按钮写 `{icon, hint, onClick}`，不要写 `text`），固定在右。「Grid 配置」里「冻结勾选列和操作列」默认已开。
- **列头右键菜单**：升序 / 降序 / 清除排序 / 固定（向左、向右）/ 不固定（`columnFixing`）。
- **过滤器默认全开**：过滤行、表头筛选、底部过滤面板（点「创建过滤器」打开构建器）、分组面板（拖列标题到面板分组）。
- **工具栏搜索框默认不显示**（`searchPanel.visible: false`，公共规则）：用筛选行 / 表头筛选 / 过滤面板代替；页面确实需要时自己传 `searchPanel: { visible: true, ... }`。
- **过滤器模板**：构建器弹窗底部「选择模板 / 保存为模板」，按**用户 + 表格**保存（`sys_grid_filter`，接口 `/api/v1/grid-filters`）；同名覆盖，每表格最多 50 个。表格标识默认是页面路径，同一页多个表格或路径带参数时传 `gridKey` 选项区分。
- **布局记忆**：列宽、顺序、显隐、固定、排序、每页条数记在浏览器本地（localStorage，键 `dxGrid:<页面路径>`）；筛选 / 搜索 / 页码 / 选中行**不记**。「恢复默认布局」清除。
- **服务端布局**：「保存布局」把同一套状态 + 当前编辑模式按**用户 + 表格**覆盖存到 `sys_grid_layout`（接口 `/api/v1/grid-layouts`），换浏览器也能「恢复布局」；恢复时先清一次性状态再应用。
- **服务端分页的表格**（`remoteOperations.paging`）自动关闭分组面板；批量删除要自定义时给 `batchDelete: function (key) { return promise }`，不给就走数据源的 `remove`。
- **子表 / 小表格**传 `dxFeatures: false` 关掉整套（无勾选列、无工具栏扩展、无过滤面板、不记布局），如 SKU 子表、语言表、预览表格。
- **树形表格**用 `dxTreeList` + `DxGrid.treeOptions()`（多选、列头右键菜单、过滤行/面板、固定列），见 `goodsCategories.html`。
- 坑：`stateStoring` 必须在创建时的默认选项里（在 `_init` 里再设会让列整体消失）；自定义 `customLoad` 没存过要返回 `{}`，不能返回 `null`。
- 坑：`masterDetail` 开启时 `columnFixing.enabled` 或任何 `fixed` 列都会让展开图标不渲染（单元格只剩 `&nbsp;`，只能靠 `expandRow` API），且修复必须在**创建时**做——DxGrid 已在 ctor 里处理（masterDetail 打开时自动关 `columnFixing`、勾选列/操作列不固定，页面自己的 `customizeColumns` 仍执行），页面无需处理。
- **编辑模式（工具栏铅笔图标）**：行编辑 / 弹窗编辑 / 单元格编辑 / 表单编辑 / 批量编辑，当前模式打勾，仅在表格允许增删改（`editing.allowAdding/Updating/Deleting`）时出现；选择记在浏览器本地（`dxGrid:<路径>:editMode`），「恢复默认布局」还原成页面里写的模式。批量编辑是改完点工具栏「保存」一次性提交。**页面里为弹窗写的专属逻辑（如属性页按录入方式显隐字段）只在弹窗模式下生效**，其它模式下是表格默认行为。
- **批量操作（工具栏勾选框图标，对勾选的行）**：菜单第一项永远是「**查看已选**」——只显示勾选过的行（在当前筛选上叠加主键 `in` 过滤，再点一次退出，激活时菜单项打勾）；之后是自带「删除选中行」（表格允许删除或页面给了 `batchDelete`）；页面可加自定义动作 `batchActions: [{id, text, confirm?: '确定…{n}…', successText?, run(keys) → promise}]`，没勾选会先提示，成功后自动取消勾选并刷新。商品列表用它做「批量上架 / 批量下架」。

## DxGrid：拖动排序、表头筛选搜索
- **拖动排序**：页面传 `rowReorder: function (info) { return promise }`，`info = {key, data, targetKey, after}`（`after=true` 放到目标行之后）；表格自动出现拖动手柄列，成功后刷新。带筛选 / 搜索 / 排序 / 分组时拒绝拖动（提示先点「重置」）。该选项必须在创建时传（内部在构造函数里转成 `rowDragging`，建好后再设手柄列不出现）。例：商品属性页 `POST /attributes/move`；选项弹窗表格直接调整本地数组。
- **表头筛选默认带搜索框**（`headerFilter.search.enabled`，占位「搜索...」）。
- **商品属性的可选值**：表单里只放「编辑选项」按钮，弹窗内是一个 DxGrid（序号 / 默认语言名称 / 各语言名称 / 编辑删除图标 / 拖动排序，行编辑模式）；改动即时写回属性行（`options` 与各语言 `i18n.<语言>.options` 按行顺序一一对应）；列表里的「可选值」只显示默认语言，超过 20 字符省略（悬停看全文）。
- **商品属性的适用分类**：多选（`editorType: 'dxTagBox'`，数据源 `Shop.categorySource()`），不选 = 通用（所有分类）；该列关闭筛选（JSON 数组值不参与客户端筛选），列表单元格用分类完整路径拼接显示；数据见 `category_ids`（DDL `009_shop_attribute_categories.sql`），页面布局键为 `/goodsAttributes#v3`（v2 里存着旧的 `category_id` 列）。

## 产品池页面约定
- 公共 JS：`static/js/lib/supplierCatalog.js`，全局 `SUP`：`SUP.call(method, path, body)` / `SUP.upload(path, formData)`（统一处理 `{code,data,msg}`，401 跳登录）；`SUP.supplierSource()` / `SUP.brandSource(rootText)`（CustomStore 下拉数据源，brandSource 数据来自 `/api/v1/brands`，传 rootText 时附 id=0 的「未关联品牌」项）；`SUP.STATUSES`（0 待核对 / 1 已核对 / 2 已选品 / 3 已忽略）；`SUP.notifyChanged('catalog'|'brand')` / `SUP.onChanged(kind, cb)`（BroadcastChannel `mzshop-supplier`，供应商页、目录页、品牌管理页互刷：新建供应商/品牌后目录页下拉、导入向导立即能看到）。
- 页面：`templates/suppliers.html`（/suppliers 供应商，DxGrid restStore 弹窗 CRUD，列含 item_count、has_mapping、website 外链，监听 onChanged 刷新）、`templates/supplierCatalog.html`（/supplierCatalog 产品目录，服务端分页 remoteStore + remoteOperations 全开 + 关 headerFilter）、`templates/supplierCatalogEdit.html`（/supplierCatalogEdit 产品编辑，在内容标签页打开，不走弹窗）。菜单「商品管理」后的组为「产品池」（子项「供应商」「产品目录」）。
- 目录列表：双击行或操作列编辑打开 `/supplierCatalogEdit?id=`（新增为 `/supplierCatalogEdit`）；`status` 列用状态徽章（st0 黄 / st1 绿 / st2 蓝 / st3 灰，CSS 在页面里）；`brand_id` 列显示品牌名，无关联时显示 `brand_name` 原文；`batchActions` 三个批量改状态动作（待核对 / 已核对 / 已忽略，`POST /items/batch-status`；「已选品」由选品流程设置，不进批量菜单）；行展开（masterDetail）显示 `attrs` / `mapped_attrs` / `description` / `remark`（资料 HTML）。
- 产品编辑：基本信息用 dxForm；「资料」用自托管 TinyMCE 8（GPL，`static/js/plugins/tinymce/`，`license_key:'gpl'`，中文 `langs/zh-CN.js`），内容存 `remark`，与导入的 `description` 原文分开。图片、文件、粘贴和拖入都先用 `blob:` 插进编辑器（`pendingFiles`），点保存才把正文里还在的文件 `POST /uploads` 并换成正式地址；保存失败则 `POST /uploads/discard`。不保存就关掉页面不会在磁盘留文件。保存成功后 `SUP.notifyChanged('catalog')`。
- **Excel 导入向导**：目录页工具栏「Excel 导入」按钮（`location:'before'`）→ `SUP.openImportWizard(grid)`，dxPopup 960×90%，4 步：① 选供应商 + 上传 .xlsx/.xlsm（dxFileUploader `uploadMode:'instantly'`，`upload` 里调 `/import/preview` 自动解析；换供应商或切「第一行是表头」自动重新解析）② 列映射（每列一个 dxSelectBox，目标=标准字段 + 「属性：xxx」，模板/关键字自动带出；「货号/SKU」「产品名称」必映射且目标不能重复）③ 校验预览（dxDataGrid 前 20 行）+ 重复货号策略（跳过 / 覆盖更新，默认跳过）+「保存为导入模板」（默认勾选）④ 结果报告（新增 / 更新 / 跳过 / 出错 + 行号明细）。完成后 `SUP.notifyChanged('catalog')` + `grid.refresh()`。未映射的列原样进 `attrs`，不丢数据。
- 列表单元格自定义文本一律走 `SUP.escapeHtml`，不要拼接 HTML。

## 品牌管理页面约定
- 页面：`templates/brands.html`（/brands，菜单在「商品管理」组）。DxGrid restStore `/api/v1/brands` 弹窗 CRUD；表单字段 name / i18n.<语言>.name / logo_url / website / remark / sort_order / status。
- 品牌名称支持多语言：列表用 `Shop.langColumns('name', '品牌名称')` 多出各语言列（`Shop.ready` 后建表格），弹窗表单里每种语言一个名称输入框，随行一起提交（后端 `entity_type=brand`）。
- Logo 上传：`logo_url` 用 dxTextBox + 右侧上传按钮（`uploadLogo(editor)`），选中图片后调 `/api/v1/shop/upload`，成功把返回地址写回编辑器；也可直接粘贴图片地址。
- 列表列：拖动排序手柄（`rowReorder` → `POST /brands/move`）、名称、Logo 缩略图、官网外链、`item_count`（目录条目引用数）、`goods_count`（商品引用数，只读）、排序、启用、备注（默认隐藏）。被引用时删除由后端 400 拒绝，DevExtreme 会显示错误信息。
- 品牌变化发 `SUP.notifyChanged('brand')`，目录页监听后刷新品牌下拉；目录 Excel 导入自动建档品牌，品牌页监听 `onChanged('catalog')` 刷新使用数。
- 商品新增 / 编辑页「品牌」字段是 `brand_id` 下拉（`Shop.brandSource('未设置')`，取品牌管理的启用品牌），不再手填名称；商品列表品牌列同样用 `brand_id` + lookup 显示。
