# FRONTEND 契约

- 内页一律继承 `templates/page.html`，通过 `render_page`（经 `routers/pages._inner_page`）渲染，自动注入当前用户的 Grid/Form 样式（body class + CSS 变量，样式在 `static/css/dxCustom.css`）。
- 页面运行在 `index.html` 外壳的标签页 iframe 内；打开标签用 `adminTab.js`。
- 内部标签右键菜单依次为「新窗口打开 / 复制链接 / 关闭其他 / 关闭右侧 / 关闭左侧 / 关闭全部」；链接优先使用 iframe 当前地址。
- 系统管理下的「UI配置」统一维护菜单、Grid 和 Form 外观；菜单宽度默认 150px，按当前用户保存。Grid 工具栏的“表格外观”入口直接打开 UI配置的「Grid 表格」Tab。
- 左侧菜单的展开/收拢状态由浏览器本地记忆。收拢时悬停一级菜单图标，在其右侧展示该组的可点击子菜单，点击后仍在内容标签页中打开。
- 左侧每个叶子菜单配置与业务含义相符的 FontAwesome 图标，普通内容标签复用对应菜单图标；商品/产品详情标签分别使用青绿色商品图标和紫色产品图标，详情标题直接显示名称或编号，不重复“商品 / 产品”前缀。内容标签文字统一为 12px 常规字重。
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
- SKU 表只维护编码、规格、成本、库存和启用状态；单规格商品可一键创建默认 SKU，默认 SKU 的规格名称留空。商品详情「价格」先维护商品区域基础价，再用「SKU 区域价格覆盖」小表只录差异价，未录的 SKU 自动继承基础价。
- 商品详情页的标题及「保存 / 推送」操作栏固定在 iframe 顶部，页面滚动时始终可见；「推送」为可扩展的下拉按钮，当前支持 Shopify，新商品保存后才可使用；正文用顶部间距避让，右侧章节导航从操作栏下方开始吸附。
- **服务端分页的表格**：`dataSource: DxGrid.remoteStore(url, 'id')` + `remoteOperations: {paging:true, filtering:true, sorting:true}`，并关闭 `headerFilter`（表头筛选要按列去重取值，服务端没提供，用筛选行代替）。见 `templates/goods.html`。

- **别覆盖表格编辑弹窗表单的 `onFieldDataChanged`**（以及 `onContentReady`）：表格靠它记录改动/初始化，覆盖后保存不会带上改动。需要联动字段显隐时，包一层对应列编辑器的 `onValueChanged`（在 `onEditorPreparing` 里取原 handler 再调用），弹窗打开时的初始状态用 `editing.popup.onShown`；带点号的 dataField（如 `i18n.en.unit`）不能直接 `itemOption`，放进命名分组整组显隐，且表单项保持字符串，不要加 `name`。见 `templates/goodsAttributes.html`。

## DxGrid 标准功能（所有表格默认带，页面不用再写）
- **列表工具栏采用两行布局**：所有后台主列表通过 `businessToolbar: true` 或 `businessToolbar: {queryItems, actions}` 启用。第一行是独立业务区，左侧放页面查询控件，右侧统一为「操作」下拉；`DxGrid` 自动把新增、编辑、删除收进菜单，页面只补充导入、批量业务等特殊动作。第二行是 Grid 自带工具栏：左侧固定顺序为刷新、查询已选、重置、分组区；右侧固定顺序为导出、编辑模式（允许增删改时）、表格设置（恢复默认布局 / 保存布局 / 恢复布局 / 打开「Grid 配置」）、列选择器。详情页内嵌表格、弹窗内小表格和样式预览不强制增加业务栏；页面不要重复添加这些公共按钮。
- **单主 Grid 页面禁止页面级滚动条**：未显式设置 `height` 的主 Grid 保持 `autoHeight:true`，由 `DxGrid.autoHeight()` 按 Grid 相对视口的实际顶部位置，扣除祖先容器底部 padding / border 后计算剩余高度；业务栏挂载、换行、窗口缩放和分类侧栏切换后由 `DxGrid.syncAutoHeight()` 重算。主 `dxTreeList` 通过 `DxGrid.enableAutoHeight(tree)` 接入同一机制。数据区内部滚动，`html/body` 不应因业务栏或 Grid 高度产生纵向滚动条；详情页内嵌表格按自身容器高度处理。
- **分类查询是公共业务查询项**：涉及商品分类的列表统一复用 `Shop.categoryQueryItem({getGrid, field?})`。第一次点击“分类”在列表左侧展开固定的可搜索分类树并压缩右侧列表，再次点击关闭；单选上级分类自动包含全部下级。“多选”打开与店铺「绑定分类」一致的大弹窗（默认宽 90%、高 80%，包含选择分类 / 查询分类、全选/全不选、已选数量、保存/取消），弹窗宽高必须使用相对页面的百分比，保证小屏完整显示；“全部分类”清除分类条件。筛选写入目标 Grid 的 `category_id`（或 `field` 指定字段）列过滤状态，与其它筛选条件叠加。
- **通用分类单选弹窗**：表单或页面需要选择一个商品分类时复用 `Shop.openCategoryPicker({value, title, onSelected})`，弹窗与分类多选保持相同的树形、查询页签和 90% × 80% 尺寸；Shopify 分类属性页使用该入口选择 mzShop 分类。
- **店铺查询复用公共多选弹窗**：商品列表业务区在「分类」右侧放「店铺」，复用 `Shop.storeQueryItem({getGrid, onChanged})`；弹窗宽 90%、高 80%，支持选择店铺 / 查询店铺、全选/全不选、已选数量、保存/取消。多个店铺按“绑定任一所选店铺”查询，并与分类及 Grid 其它筛选条件叠加。
- **商品列表默认隐藏辅助列**：「商品名称(en)」「店铺数」「店铺」「绑定产品」首次默认隐藏，仍保留在列选择器中；用户之后手动调整的列显隐继续由布局记忆保存。「绑定产品」和「绑定货号」有值时均显示为链接，点击后在内部标签打开对应产品详情。
- **弹窗尺寸使用页面百分比**：`dxPopup` 和 Grid 编辑弹窗的 `width` / `height` 使用百分比，避免小屏超出视口；普通表单统一以 `width:'90%', height:'80%'` 为基础，并可用 `maxWidth` / `maxHeight` 保留宽屏下的合适尺寸。分类选择和商品分类弹窗固定为宽 90%、高 80%。
- **多选列**默认开（`selection: multiple`，勾选框，固定在左）；**操作列**用图标按钮（`editing.useIcons: true`，自定义按钮写 `{icon, hint, onClick}`，不要写 `text`），默认固定在右（`type:'buttons'` 或标题「操作」；页面写了 `fixed` 则以页面为准）。「Grid 配置」里「冻结勾选列和操作列」默认已开，打开时右键「不固定」不会改掉这两列。
- **审计列默认隐藏**：`id`、创建时间（`created_at` / `create_time`）、更新时间（`updated_at` / `update_time`）、创建人（`created_by` / `creator`）、最后操作人（`updated_by` / `last_operator`），以及标题正好是「ID / 创建时间 / 更新时间 / 创建人 / 最后操作人」的列。页面没写 `visible` 时 DxGrid 在创建时设 `visible: false`、`showInColumnChooser: true`，用工具栏最右侧的「列选择器」勾回来。外键（`category_id`、`goods_id` 等）和标题「商品ID」不在此列。页面写了 `visible: true/false` 以页面为准。已有本地布局会在第一次打开时把这些列收起来（`localStorage` 键 `dxGrid:<gridKey>:auditHide`），之后列选择器的选择会记住。
- **列头右键菜单**（点列标题）：升序排序、降序排序、清除排序、通过该列分组、取消所有分组、固定（向左 / 向右）、不固定。排序来自 `sorting`，分组来自 `grouping.contextMenuEnabled`，固定来自 `columnFixing`。没走 DxGrid 的表格用 `DxGrid.headerMenuOptions()`。
- **列选择器弹层位置**：由 `DxGrid.prepareColumnChooser()` 在点击时动态计算，默认紧贴工具栏最右侧列选择器按钮下方并留少量间距，右侧与 Grid 对齐；高度按按钮到视口底部的剩余空间计算，延伸至接近页面底部，列表内容在弹层内部滚动。DataGrid 与主 TreeList 必须复用该规则。
- **过滤器默认全开**：过滤行、表头筛选、底部过滤面板（点「创建过滤器」打开构建器）、分组面板（拖列标题到面板分组）。
- **工具栏搜索框默认不显示**（`searchPanel.visible: false`，公共规则）：用筛选行 / 表头筛选 / 过滤面板代替；页面确实需要时自己传 `searchPanel: { visible: true, ... }`。
- **过滤器模板**：构建器弹窗底部「选择模板 / 保存为模板」，按**用户 + 表格**保存（`sys_grid_filter`，接口 `/api/v1/grid-filters`）；同名覆盖，每表格最多 50 个。表格标识默认是页面路径，同一页多个表格或路径带参数时传 `gridKey` 选项区分。
- **布局记忆**：列宽、顺序、显隐、固定、排序、每页条数记在浏览器本地（localStorage，键 `dxGrid:<页面路径>`）；筛选 / 搜索 / 页码 / 选中行**不记**。「恢复默认布局」清除。
- **服务端布局**：「保存布局」把同一套状态 + 当前编辑模式按**用户 + 表格**覆盖存到 `sys_grid_layout`（接口 `/api/v1/grid-layouts`），换浏览器也能「恢复布局」；恢复时先清一次性状态再应用。
- **服务端分页的表格**：尚未迁移两行布局的旧页面暂时自动关闭分组面板；启用 `businessToolbar` 的新布局保留分组区，并设置 `remoteOperations.grouping:false`，分组只发生在浏览器里、针对当前已加载的数据。批量删除要自定义时给 `batchDelete: function (key) { return promise }`，不给就走数据源的 `remove`。
- **子表 / 小表格**传 `dxFeatures: false` 关掉整套（无勾选列、无工具栏扩展、无过滤面板、不记布局），如 SKU 子表、语言表、预览表格。
- **树形表格**用 `dxTreeList` + `DxGrid.treeOptions()`（多选、列头右键菜单、过滤行/面板、固定列），见 `goodsCategories.html`。
- 坑：`stateStoring` 必须在创建时的默认选项里（在 `_init` 里再设会让列整体消失）；自定义 `customLoad` 没存过要返回 `{}`，不能返回 `null`。
- 坑：`masterDetail` 开启时 DevExtreme 24.1 会把展开列钉住后把图标清成 `&nbsp;`。DxGrid 默认在创建时关掉 `columnFixing`、不钉操作列、读布局时去掉 `fixed`（商品列表仍走这条）。产品目录传 `keepColumnFixing: true`：多选列和图片列钉左、操作列钉右，行画完后把展开箭头补回去并可点击。
- **编辑模式（工具栏铅笔图标）**：行编辑 / 弹窗编辑 / 单元格编辑 / 表单编辑 / 批量编辑，当前模式打勾，仅在表格允许增删改（`editing.allowAdding/Updating/Deleting`）时出现；选择记在浏览器本地（`dxGrid:<路径>:editMode`），「恢复默认布局」还原成页面里写的模式。批量编辑是改完点工具栏「保存」一次性提交。**页面里为弹窗写的专属逻辑（如属性页按录入方式显隐字段）只在弹窗模式下生效**，其它模式下是表格默认行为。
- **查询已选 / 批量操作**：「查询已选」是 Grid 工具栏左侧独立按钮，只显示勾选过的行（在当前筛选上叠加主键 `anyof` 过滤，再点一次退出）。页面可加 `batchActions: [{id, text, icon?, confirm?: '确定…{n}…', successText?, run(keys) → promise}]`；启用 `businessToolbar` 后，删除选中和这些批量动作自动进入第一行右侧「操作」菜单，没启用的旧页面暂保留 Grid 工具栏批量菜单。商品列表用它做批量上架、批量下架和推送 Shopify。

## DxGrid：拖动排序、表头筛选搜索
- **拖动排序**：页面传 `rowReorder: function (info) { return promise }`，`info = {key, data, targetKey, after}`（`after=true` 放到目标行之后）；表格自动出现拖动手柄列，成功后刷新。带筛选 / 搜索 / 排序 / 分组时拒绝拖动（提示先点「重置」）。该选项必须在创建时传（内部在构造函数里转成 `rowDragging`，建好后再设手柄列不出现）。例：商品属性页 `POST /attributes/move`；选项弹窗表格直接调整本地数组。
- **表头筛选默认带搜索框**（`headerFilter.search.enabled`，占位「搜索...」）。
- **商品属性的可选值**：表单里只放「编辑选项」按钮，弹窗内是一个 DxGrid（序号 / 默认语言名称 / 各语言名称 / 编辑删除图标 / 拖动排序，行编辑模式）；改动即时写回属性行（`options` 与各语言 `i18n.<语言>.options` 按行顺序一一对应）；列表里的「可选值」只显示默认语言，超过 20 字符省略（悬停看全文）。
- **商品属性的适用分类**：多选（`editorType: 'dxTagBox'`，数据源 `Shop.categorySource()`），不选 = 通用（所有分类）；该列关闭筛选（JSON 数组值不参与客户端筛选），列表单元格用分类完整路径拼接显示；数据见 `category_ids`（DDL `009_shop_attribute_categories.sql`），页面布局键为 `/goodsAttributes#v3`（v2 里存着旧的 `category_id` 列）。

## 产品池页面约定
- 公共 JS：`static/js/lib/supplierCatalog.js`，全局 `SUP`：`SUP.call(method, path, body)` / `SUP.upload(path, formData)`（统一处理 `{code,data,msg}`，401 跳登录）；`SUP.supplierSource()` / `SUP.brandSource(rootText)`（CustomStore 下拉数据源，brandSource 数据来自 `/api/v1/brands`，传 rootText 时附 id=0 的「未关联品牌」项）；`SUP.STATUSES`（0 待核对 / 1 已核对 / 2 已选品 / 3 已忽略）；`SUP.DOC_TYPES`（供应商文档类型）；`SUP.notifyChanged('catalog'|'brand'|'document')` / `SUP.onChanged(kind, cb)`（BroadcastChannel `mzshop-supplier`，供应商页、目录页、品牌管理页、供应商文档页互刷）。
- 页面：`templates/suppliers.html`（/suppliers 供应商，DxGrid restStore 弹窗 CRUD，列含 item_count、document_count、has_mapping、website 外链，监听 catalog/document 刷新）、`templates/supplierDocuments.html`（/supplierDocuments 供应商文档，DxGrid restStore 弹窗上传，文件列可下载；取消未保存的上传会 discard）、`templates/supplierCatalog.html`（/supplierCatalog 产品目录，服务端分页 remoteStore + remoteOperations 全开 + 关 headerFilter）、`templates/supplierCatalogEdit.html`（/supplierCatalogEdit 产品编辑，在内容标签页打开，不走弹窗）。菜单「商品管理」后的组为「产品池」（子项「供应商」「供应商文档」「产品目录」）。
- 目录列表：双击行或操作列编辑打开 `/supplierCatalogEdit?id=`（新增为 `/supplierCatalogEdit`）；`status` 列用状态徽章（st0 黄 / st1 绿 / st2 蓝 / st3 灰，CSS 在页面里）；`brand_id` 列显示品牌名，无关联时显示 `brand_name` 原文；`category_id`（商品分类）默认显示，未映射显示「未映射」；`batchActions` 三个批量改状态动作（待核对 / 已核对 / 已忽略，`POST /items/batch-status`；「已选品」由选品流程设置，不进批量菜单）；行展开（masterDetail）显示 `attrs` / `mapped_attrs` / `description` / `remark`（资料 HTML）。
- 产品编辑：基本信息用 dxForm，含建议售价、最低售价、最高售价、价格规则（多行文本）、交期（最低不能高于最高，建议售价须落在已填的区间内）。目录列表图片列钉在左侧；列表缩略图和编辑页图片缩略图点击后在新标签打开原图。「资料」用自托管 TinyMCE 8（GPL，`static/js/plugins/tinymce/`，`license_key:'gpl'`，中文 `langs/zh-CN.js`），内容存 `remark`，与导入的 `description` 原文分开。图片、文件、粘贴和拖入都先用 `blob:` 插进编辑器（`pendingFiles`），点保存才把正文里还在的文件 `POST /uploads` 并换成正式地址；保存失败则 `POST /uploads/discard`。不保存就关掉页面不会在磁盘留文件。保存成功后 `SUP.notifyChanged('catalog')`。
- **Excel 导入向导**：目录页工具栏「Excel 导入」按钮（`location:'before'`）→ `SUP.openImportWizard(grid)`，dxPopup 960×90%，4 步：① 选供应商 + 上传 .xlsx/.xlsm（dxFileUploader `uploadMode:'instantly'`，`upload` 里调 `/import/preview` 自动解析；换供应商或切「第一行是表头」自动重新解析）② 列映射（每列一个 dxSelectBox，目标=标准字段 + 「属性：xxx」，模板/关键字自动带出；「货号/SKU」「产品名称」必映射且目标不能重复）③ 校验预览（dxDataGrid 前 20 行）+ 重复货号策略（跳过 / 覆盖更新，默认跳过）+「保存为导入模板」（默认勾选）④ 结果报告（新增 / 更新 / 跳过 / 出错 + 行号明细）。完成后 `SUP.notifyChanged('catalog')` + `grid.refresh()`。未映射的列原样进 `attrs`，不丢数据。
- 列表单元格自定义文本一律走 `SUP.escapeHtml`，不要拼接 HTML。

## 店铺页面约定
- 菜单「店铺」位于「产品池」之后，含平台、店铺和包装管理；销售运费模板入口位于「商品管理」。相关页面都使用 DxGrid；运费模板弹窗内的区域规则也使用 DxGrid。
- 商品详情「区域销售价格」表增加可选的「运费模板」列；店铺表不再显示或提交运费模板。模板、SKU 重量和包装资料都不影响上架或推送，缺少配置只在运费计算时提示。
- 包装管理分为包装箱与包装组；包装箱长宽高使用厘米并保留两位小数。包装组选择一个启用的当前包装箱并可上传最多 20 张参考图片，列表显示首图和图片数；没有启用包装箱时，下拉明确提示先到包装箱页签新增。SKU 包装组留空时依次继承商品、店铺默认包装组；采购更换箱型时只改组内当前包装箱。按计费重量取“商品实际重量 + 空箱重量”和体积重量较大值。
- 运费模板列表使用 `masterDetail` 展开行，展示计费方式、币种、体积重系数、免邮/上下限、未匹配策略，以及各区域的首重、续重费用和时效。
- 平台列：编码、平台名称、平台名称(en)、网址、市场、特性、备注、独立站（是否为独立站）、店铺数（只读）。
- 店铺列：平台（下拉）、编码、店铺名称、店铺名称(en)、默认包装组、网址、特性、备注、独立站、绑定分类。绑定分类摘要和独立站行为保持原约定。
- **绑定分类**：操作列「绑定分类」打开大弹窗，多选商品分类。布局对照选择分类弹窗：页签「选择分类 / 查询分类」，工具条「全选/全不选」「已选 N」。选择分类按树展示（上级加粗，末级子类折行勾选）；勾选上级会带上其全部下级。查询分类按名称过滤，匹配默认语言和 `i18n` 各语言译文。保存走 `PUT /api/v1/stores/{id}/categories`。
- 平台增删改后用 `BroadcastChannel('mzshop-platform')` 通知店铺页刷新下拉和独立站。
- Shopify 同步任务页 `/shopifyTasks` 使用 `DxGrid.remoteStore('/api/v1/shopify/tasks')` 服务端分页并启用 `businessToolbar` 两行工具栏；状态用颜色徽章，错误文本转义后查看，只有 failed/cancelled 显示重试按钮。`batchActions` 提供批量重试，`batchDelete` 提供公共“删除选中行”，两者统一进入第一行右侧“操作”菜单；活动任务由后端拒绝删除。
- Shopify 标准属性页 `/shopifyTaxonomyAttributes` 主表与展开的属性值子表都使用 `DxGrid` 服务端分页；数万官方值不得一次性加载到浏览页。页面的“从 Shopify 更新全部标准数据”复用 `/taxonomy/import`。
- 商品详情「店铺」表格显示只读的店铺商品网址；Shopify 首次创建或后续同步成功后由 worker 自动回写，未同步时显示提示文本，已回写时可在新标签打开。

## 商品详情页约定
- 商品详情按数据员录入顺序排列为：基本信息、图片、规格 SKU、区域销售价格、属性、店铺、中文描述、英文描述；规格必须紧跟图片，区域销售价格位于规格与属性之间。各区块使用紧凑卡片布局，模块标题使用贯穿卡片宽度的浅主题色背景以区别正文；SKU 数量较少，详情页和商品列表展开行中的 SKU 子表均不显示分页器；基本信息双列录入，右侧提供区块导航与单页 / Tabs 模式切换；保存与推送操作栏固定在页面顶部。SKU 子表不再编辑旧汇总库存，只显示普通/组合类型；实物库存统一在库存管理维护。
- 商品图片默认是商品共用图，每张图片可下拉改为当前商品某个 SKU 的专用图；只有共用图可设为商品主图，第一张共用图为主图。新商品须先保存并创建 SKU 后才能绑定专用图；SKU 仍有专用图片时不能删除。
- 价格区使用主从 Grid：主表维护「区域销售价格」，所有 SKU 默认继承「统一销售价」；展开区域行后，在子 Grid 中维护该区域的 SKU 差异价。页面不提供批量创建默认覆盖，未设置差异价的 SKU 始终按继承规则取价。

## 品牌管理页面约定
- 页面：`templates/brands.html`（/brands，菜单在「商品管理」组）。DxGrid restStore `/api/v1/brands` 弹窗 CRUD；表单字段 code / brand_type / include_in_goods_no / name / i18n.<语言>.name / logo_url / website / remark / sort_order / status。
- 品牌名称支持多语言：列表用 `Shop.langColumns('name', '品牌名称')` 多出各语言列（`Shop.ready` 后建表格），弹窗表单里每种语言一个名称输入框，随行一起提交（后端 `entity_type=brand`）。
- Logo 上传：`logo_url` 用 dxTextBox + 右侧上传按钮（`uploadLogo(editor)`），选中图片后调 `/api/v1/shop/upload`，成功把返回地址写回编辑器；也可直接粘贴图片地址。
- 列表列：拖动排序手柄（`rowReorder` → `POST /brands/move`）、编码（第一列，`visibleIndex: 0`；已有本地布局会在打开时再把编码挪到最前）、名称、Logo 缩略图、官网外链、`item_count`（目录条目引用数）、`goods_count`（商品引用数，只读）、排序、启用、备注（默认隐藏）。被引用时删除由后端 400 拒绝，DevExtreme 会显示错误信息。
- 品牌变化发 `SUP.notifyChanged('brand')`，目录页监听后刷新品牌下拉；目录 Excel 导入自动建档品牌，品牌页监听 `onChanged('catalog')` 刷新使用数。
- 商品新增 / 编辑页「品牌」字段是 `brand_id` 下拉（`Shop.brandSource('未设置')`，取品牌管理的启用品牌），不再手填名称；商品列表品牌列同样用 `brand_id` + lookup 显示。
- 商品新增 / 编辑页的商品编码输入框带“自动生成”按钮；先选分类和品牌，再调用 `/shop/goods-no/generate` 立即占用“最终前缀 + 4 位流水”，允许因未保存而跳号。

## 组合、库存与订单页面

- `/bundles` 使用 `DxGrid.restStore` 主从表；主表父 SKU 编码以及展开子 Grid 中的父/组件 SKU 编码，都可在内容标签页打开所属商品详情。展开子 Grid 后首行显示组合父 SKU，后续显示组件 SKU。组件编辑弹窗内的小表同样使用 `DxGrid`，组件只能从启用普通 SKU 候选中选择。主表展示组合父 SKU 的区域有效售价和各启用地点的实时组合可用量；界面使用“启用配方”，明确该动作只在 mzShop 本地生效。
- `/inventory` 使用 `DxGrid.remoteStore` 服务端分页；“地点管理”在弹窗 DxGrid 中维护库存地点，“调整 SKU 库存”可搜索尚无余额记录的普通 SKU 并初始化库存。已有库存可通过行操作或双击调整；表单同时维护调整后在库、不可售和安全库存，最近一笔“调整说明”在列表中默认隐藏。
- `/orders` 使用 `DxGrid.remoteStore` 服务端分页；订单明细和退货入库弹窗使用禁用公共功能的小型 `DxGrid`。退货数量按组件录入可售/不可售，不能操作组合父行。
- `/stores` Shopify 配置必须同时选择远端 Shopify Location 与本地 mzShop 库存地点；Webhook 注册错误直接显示中文原因。
