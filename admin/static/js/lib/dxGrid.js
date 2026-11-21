/**
 * DxGrid —— 继承 DevExtreme dxDataGrid 的自建表格组件，所有页面统一用它，后续表格层面的扩展都加在这里。
 *
 * 用法:
 *   var grid = new DxGrid(document.querySelector('#grid'), {
 *       dataSource: DxGrid.restStore('/api/v1/users', 'id'),
 *       columns: [...]
 *   });
 *   // 或 jQuery 方式: $('#grid').dxGrid({...}); $('#grid').dxGrid('instance')
 *
 * 默认值见 _getDefaultOptions；页面传入的 options 会覆盖默认值。
 * 服务端响应约定 {code, data, msg}，code != 0 视为失败。
 */
(function ($) {
    'use strict';

    var Base = DevExpress.ui.dxDataGrid;

    var DxGrid = Base.inherit({
        // 拖动排序的 rowDragging 必须在创建时就带上（建好后再设，拖动手柄列不会出现）
        ctor: function (el, options) {
            options = options || {};
            if (typeof options.rowReorder === 'function') { options = $.extend({}, options, { rowDragging: DxGrid._rowDragging(options.rowReorder) }); }
            // 公共列契约要在创建时写进列定义（visible 只在页面没写时补默认值）。
            // 不能放到 customizeColumns 里强制改 visible：那里每次重算列都会跑，会盖掉列选择器和已记住的布局。
            var masterDetail = options.masterDetail === true || !!(options.masterDetail && options.masterDetail.enabled);
            // 带展开行时，DevExtreme 24.1 会把展开列钉住后把图标清成 &nbsp;。
            // 默认关掉列固定。页面传 keepColumnFixing:true 时保留固定列，并在行渲染后把图标补回去。
            var keepFix = masterDetail && options.keepColumnFixing === true;
            if (Array.isArray(options.columns)) {
                options = $.extend({}, options, {
                    columns: DxGrid.prepareColumns(options.columns, { skipFix: (masterDetail && !keepFix) || options.dxFeatures === false })
                });
            }
            if (masterDetail && !keepFix) {
                var mdFixes = {};
                if (!(options.columnFixing && options.columnFixing.enabled === false)) {
                    mdFixes.columnFixing = { enabled: false };
                }
                var mdPageCC = options.customizeColumns;
                mdFixes.customizeColumns = function (columns) {
                    if (typeof mdPageCC === 'function') { mdPageCC.call(this, columns); }
                    (columns || []).forEach(function (c) { c.fixed = false; });
                };
                options = $.extend({}, options, mdFixes);
            }
            if (keepFix) {
                var pageRowPrepared = options.onRowPrepared;
                options = $.extend({}, options, {
                    onRowPrepared: function (e) {
                        DxGrid.repairDetailExpandRow(e);
                        if (typeof pageRowPrepared === 'function') { pageRowPrepared.apply(this, arguments); }
                    }
                });
            }
            this.callBase(el, options);
            // 高度必须在 DevExtreme 构造完成后接管；放在 _init 里会被组件后续初始化覆盖回 null。
            if (this.option('autoHeight') && this.option('height') == null) {
                var self = this;
                this._autoHeightManaged = true;
                this.option('height', DxGrid.autoHeight(this.element()));
                this._onWinResize = function () { DxGrid.syncAutoHeight(self); };
                $(window).on('resize', this._onWinResize);
            }
            // 独立业务栏要等 DataGrid 完成初始化后再挂到根元素前；在 _init 中创建会被组件后续渲染覆盖。
            if (this.option('businessToolbar')) {
                DxGrid._initBusinessToolbar(this);
                this.updateDimensions();
            }
        },

        _getDefaultOptions: function () {
            var self = this;
            return $.extend(true, this.callBase(), {
                autoHeight: true, // 撑满窗口剩余高度；页面自己传了 height 就不再自动算
                showBorders: true,
                showRowLines: true,
                rowAlternationEnabled: true,
                hoverStateEnabled: true,
                columnAutoWidth: true,
                allowColumnResizing: true,
                columnResizingMode: 'widget',
                allowColumnReordering: true,
                wordWrapEnabled: false,
                filterRow: { visible: true },
                headerFilter: { visible: true, search: { enabled: true, editorOptions: { placeholder: '搜索...' } } }, // 表头筛选里带搜索框
                sorting: { mode: 'multiple' },
                searchPanel: { visible: false },    // 公共规则：工具栏默认不显示搜索框，用筛选行 / 表头筛选；页面需要时自己传 visible: true
                paging: { pageSize: 20 },
                pager: {
                    visible: true,
                    showPageSizeSelector: true,
                    allowedPageSizes: [20, 50, 100],
                    showInfo: true
                },
                noDataText: '暂无数据',
                // 以下是「标准功能」默认全开；子表 / 小表格传 dxFeatures: false 关掉整套
                dxFeatures: true,
                selection: { mode: 'multiple', showCheckBoxesMode: 'always', selectAllMode: 'page' }, // 默认多选列
                columnFixing: { enabled: true },   // 列头右键：固定（向左、向右）/ 不固定
                filterPanel: { visible: true },    // 过滤器：底部过滤面板，点开是过滤器构建器（带「模板」）
                groupPanel: { visible: true },     // 拖动列标题到此处分组（服务端分页的表格会自动关掉面板）
                grouping: { contextMenuEnabled: true }, // 列头右键：通过该列分组 / 取消所有分组

                columnChooser: { enabled: true, mode: 'select' },
                customizeColumns: DxGrid.fixCommandColumns,
                stateStoring: DxGrid._stateOptions(self)
            }, DxGrid.styleOptions());
        },

        _init: function () {
            this.callBase();
            var self = this;
            $(this.element()).data('dxGrid', this); // new DxGrid(el) 和 $(el).dxGrid() 两种创建方式都能 $(el).dxGrid('instance') 取到
            if (!this.option('dxFeatures')) {
                this.option({
                    selection: { mode: 'none' }, filterPanel: { visible: false }, groupPanel: { visible: false },
                    columnChooser: { enabled: false }, columnFixing: { enabled: false }, stateStoring: { enabled: false }
                });
                return;
            }
            // 尚未迁移到两行布局的服务端分页表格继续隐藏分组面板。
            // 启用 businessToolbar 的新布局保留分组区，页面须把 remoteOperations.grouping 设为 false，分组仅作用于当前已加载数据。
            var ro = this.option('remoteOperations');
            if (!this.option('businessToolbar') && ro && typeof ro === 'object' && (ro.paging || ro.filtering)) {
                this.option({ groupPanel: { visible: false } });
            }
            this._gridKey = this.option('gridKey') || location.pathname;
            this._stateKey = 'dxGrid:' + this._gridKey;
            this._defaultEditMode = this.option('editing.mode');
            var edOpt = this.option('editing') || {};
            if (edOpt.allowAdding || edOpt.allowUpdating || edOpt.allowDeleting) {
                var savedMode = null;
                try { savedMode = localStorage.getItem(this._stateKey + ':editMode'); } catch (e) { }
                if (savedMode && DxGrid.EDIT_MODES.some(function (m) { return m.id === savedMode; })) { this.option('editing.mode', savedMode); }
            }
            DxGrid._initFilterBuilderPopup(this);
            // Grid 工具栏：左侧刷新 / 查询已选 / 重置 / 分组区；右侧导出 / 编辑模式 / 设置 / 列选择器。
            var userToolbar = this.option('onToolbarPreparing');
            this.option('onToolbarPreparing', function (e) {
                DxGrid._buildToolbar(self, e);
                if (userToolbar) { userToolbar.apply(this, arguments); }
                DxGrid._placeGroupPanel(e.toolbarOptions.items);
                DxGrid._placeColumnChooser(e.toolbarOptions.items, self);
            });
        },

        _dispose: function () {
            if (this._onWinResize) { $(window).off('resize', this._onWinResize); }
            if (this._businessToolbarResizeObserver) { this._businessToolbarResizeObserver.disconnect(); }
            if (this._businessToolbarEl) { this._businessToolbarEl.remove(); this._businessToolbarEl = null; }
            this.callBase();
        }
    });

    // inherit 出来的类没经过 registerComponent，NAME 会变成 dxPrivateComponentN，
    // 根元素上的 dx-datagrid 等样式类名跟着全变，主题 css 整个失效，所以沿用父类的名字
    // 构造函数里会给 this.NAME 赋值，setter 忽略它，getter 始终返回父类名字
    Object.defineProperty(DxGrid.prototype, 'NAME', {
        get: function () { return 'dxDataGrid'; },
        set: function () { },
        configurable: true
    });

    /**
     * 把当前用户的「Grid 配置」（APP.GRID_STYLE，页面渲染时注入）翻成 dxDataGrid 选项。
     * 颜色 / 行高 / 字号 / 对齐等外观走 <body> 上的 class 和 CSS 变量（见 dxCustom.css），这里只管组件自己的开关。
     * Grid 配置页的预览表格也用这个函数，保证预览和实际一致。
     */
    DxGrid.styleOptions = function (s) {
        s = s || (window.APP && APP.GRID_STYLE);
        if (!s) { return {}; }
        var options = {
            showColumnLines: s.columnLines,
            showRowLines: s.rowLines,
            rowAlternationEnabled: s.stripe,
            hoverStateEnabled: s.hoverRow,
            showBorders: s.showBorders,
            columnAutoWidth: s.autoWidth,
            wordWrapEnabled: s.textOverflow === 'wrap',
            filterRow: { visible: s.filterRow },
            paging: { pageSize: s.pageSize },
            pager: {
                displayMode: s.pagerMode,
                showInfo: s.pagerInfo,
                allowedPageSizes: [10, 20, 50, 100, 500]
            }
        };
        return options;
    };

    /**
     * 列头右键菜单（图 1）：升序排序、降序排序、清除排序、通过该列分组、取消所有分组、固定（向左 / 向右）、不固定。
     * 排序来自 sorting，分组来自 grouping.contextMenuEnabled，固定来自 columnFixing。
     * 没走 DxGrid 的 dxDataGrid / dxTreeList 用 $.extend({}, DxGrid.headerMenuOptions(), { ...页面选项 })。
     * withChooser 传 false 时不打开列选择器（窄列表、没有默认隐藏列时）。
     */
    DxGrid.headerMenuOptions = function (withChooser) {
        var options = {
            sorting: { mode: 'multiple' },
            grouping: { contextMenuEnabled: true },
            columnFixing: { enabled: true }
        };
        if (withChooser !== false) { options.columnChooser = { enabled: true, mode: 'select' }; }
        return options;
    };

    /** 树形表格（dxTreeList）用的同一套标准功能：多选列、列头右键菜单、过滤行 / 表头筛选 / 过滤面板、列选择器、固定列、布局记忆 */
    DxGrid.treeOptions = function () {
        return $.extend({}, DxGrid.headerMenuOptions(), {
            selection: { mode: 'multiple', showCheckBoxesMode: 'always', recursive: false },
            filterRow: { visible: true },
            headerFilter: { visible: true, search: { enabled: true, editorOptions: { placeholder: '搜索...' } } },
            filterPanel: { visible: true },
            customizeColumns: DxGrid.fixCommandColumns,
            stateStoring: DxGrid._stateOptions(null)
        });
    };

    /**
     * 默认隐藏、但仍出现在列选择器里的列。
     * 只认主键 id、审计时间、创建人、最后操作人。外键（category_id、goods_id 等）和标题「商品ID」不在这里。
     */
    DxGrid.AUDIT_FIELDS = {
        id: 1,
        created_at: 1, create_time: 1, createdAt: 1,
        updated_at: 1, update_time: 1, updatedAt: 1,
        created_by: 1, creator: 1, creator_name: 1, created_by_name: 1,
        updated_by: 1, last_operator: 1, last_operator_name: 1, updated_by_name: 1
    };
    DxGrid.AUDIT_CAPTIONS = { ID: 1, '创建时间': 1, '更新时间': 1, '创建人': 1, '最后操作人': 1 };

    DxGrid.isAuditColumn = function (col) {
        if (!col || col.type === 'buttons' || col.type === 'selection' || col.command) { return false; }
        var field = col.dataField || col.name;
        if (field && DxGrid.AUDIT_FIELDS[field]) { return true; }
        return !!(col.caption && DxGrid.AUDIT_CAPTIONS[col.caption]);
    };

    DxGrid.isActionColumn = function (col) {
        return !!(col && (col.type === 'buttons' || col.command === 'edit' || col.caption === '操作'));
    };

    /**
     * 公共列契约（创建时调用一次）：
     * - ID / 创建时间 / 更新时间 / 创建人 / 最后操作人：页面没写 visible 时默认隐藏，列选择器里可以勾回来
     * - 操作列默认固定在右侧（页面写了 fixed，或 skipFix：主从展开 / dxFeatures:false，则不动）
     * 浅拷贝列对象，避免把 lookup 的 CustomStore、cellTemplate 克隆坏。
     */
    DxGrid.prepareColumns = function (columns, opts) {
        opts = opts || {};
        if (!Array.isArray(columns)) { return columns; }
        return columns.map(function (c) {
            if (typeof c === 'string') { c = { dataField: c }; }
            if (!c || typeof c !== 'object') { return c; }
            var col = $.extend({}, c);
            if (DxGrid.isAuditColumn(col)) {
                if (col.visible === undefined) { col.visible = false; }
                if (col.showInColumnChooser === undefined) { col.showInColumnChooser = true; }
            }
            if (!opts.skipFix && DxGrid.isActionColumn(col) && col.fixed === undefined) {
                col.fixed = true;
                col.fixedPosition = 'right';
            }
            return col;
        });
    };

    /** 勾选列固定在左、操作列固定在右。「Grid 配置」里关掉冻结时不改，方便右键「不固定」留下来 */
    DxGrid.fixCommandColumns = function (columns) {
        var s = (window.APP && APP.GRID_STYLE) || {};
        if (s.fixedCommand === false) { return; }
        (columns || []).forEach(function (c) {
            if (c.type === 'selection' || c.command === 'select') { c.fixed = true; c.fixedPosition = 'left'; }
            if (c.type === 'buttons' || c.command === 'edit' || c.caption === '操作') { c.fixed = true; c.fixedPosition = 'right'; }
        });
    };

    /**
     * DevExtreme 24.1：展开列一旦被钉住，固定表里的单元格内容会被清成 &nbsp;，图标和点击都没了。
     * keepColumnFixing 的表格在行画完后把箭头补上，并自己处理展开/收起。
     */
    DxGrid.repairDetailExpandRow = function (e) {
        if (!e || e.rowType !== 'data' || !e.rowElement || e.isNewRow) { return; }
        var open = !!e.isExpanded;
        $(e.rowElement).each(function () {
            $(this).children('td.dx-command-expand').each(function () {
                var $td = $(this);
                if ($td.find('.dx-datagrid-group-opened, .dx-datagrid-group-closed').length) { return; }
                $td.addClass('dx-datagrid-expand dx-selection-disabled').removeClass('dx-pointer-events-none').empty();
                $('<div>').addClass(open ? 'dx-datagrid-group-opened' : 'dx-datagrid-group-closed').appendTo($td);
                $td.on('click', function (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    var grid = e.component;
                    if (!grid) { return; }
                    if (grid.isRowExpanded(e.key)) { grid.collapseRow(e.key); }
                    else { grid.expandRow(e.key); }
                });
            });
        });
    };

    /** 列选择器放到工具栏最右侧（公共规则的最后一项） */
    DxGrid._placeColumnChooser = function (items, grid) {
        if (!items) { return; }
        var idx = -1;
        items.forEach(function (it, i) { if (it.name === 'columnChooserButton') { idx = i; } });
        if (idx >= 0 && grid) {
            var item = items[idx];
            item.options = $.extend({}, item.options, {
                onClick: function (e) {
                    var buttonEl = e && e.element ? e.element : null;
                    DxGrid.prepareColumnChooser(grid, buttonEl);
                    grid.showColumnChooser();
                }
            });
        }
        if (idx >= 0 && idx !== items.length - 1) { items.push(items.splice(idx, 1)[0]); }
    };

    /** 列选择器默认紧贴工具栏按钮下方，并延伸到接近页面底部。 */
    DxGrid.prepareColumnChooser = function (grid, buttonElement) {
        var $button = $(buttonElement || grid.element()).closest('.dx-button');
        if (!$button.length) {
            $button = $(grid.element()).find('.dx-datagrid-column-chooser-button, .dx-treelist-column-chooser-button').last();
        }
        var button = $button[0] && $button[0].getBoundingClientRect();
        var root = $(grid.element())[0] && $(grid.element())[0].getBoundingClientRect();
        if (!button || !root) { return; }
        // DevExtreme 的 ColumnChooser 自带约 18px 外层偏移，这里预抵消，最终与按钮保持约 8px 间距。
        var offsetY = Math.round(button.bottom - root.top - 10);
        var height = Math.max(220, Math.floor(window.innerHeight - button.bottom - 18));
        grid.option('columnChooser.height', height);
        grid.option('columnChooser.position', {
            my: 'right top', at: 'right top', offset: '-2 ' + offsetY, collision: 'fit'
        });
    };

    /** 分组区放在左侧三个公共按钮之后；DevExtreme 默认会把它插在最前。 */
    DxGrid._placeGroupPanel = function (items) {
        if (!items) { return; }
        var idx = -1;
        items.forEach(function (it, i) { if (it.name === 'groupPanel') { idx = i; } });
        if (idx >= 0) { items.push(items.splice(idx, 1)[0]); }
    };


    /* ================================================================ 布局记忆 */
    // 列宽、顺序、显隐、固定、排序、每页条数记在浏览器本地（按页面路径）；筛选 / 搜索 / 页码 / 选中行不记，免得下次打开莫名其妙是过滤后的结果
    DxGrid._stateKeyOf = function (grid) {
        var gridKey = '';
        try { gridKey = grid && grid.option ? grid.option('gridKey') : ''; } catch (e) { gridKey = ''; }
        return 'dxGrid:' + (gridKey || location.pathname);
    };

    /**
     * 读本地布局。旧布局是在审计列默认显示时存下来的，第一次读取把这些列的 visible 收成 false 并打标记，
     * 之后列选择器再勾出来的选择会留下来。没存过必须返回 {}，返回 null 会把列清空。
     * masterDetail 表格不能带 fixed（展开图标不渲染），读出来时去掉。
     */
    DxGrid._readGridState = function (storageKey, grid) {
        var state = {};
        try { state = JSON.parse(localStorage.getItem(storageKey) || '{}') || {}; } catch (e) { state = {}; }
        if (!state || typeof state !== 'object') { state = {}; }
        var flagKey = storageKey + ':auditHide';
        var done = false;
        try { done = localStorage.getItem(flagKey) === '1'; } catch (e) { done = false; }
        if (!done) {
            (state.columns || []).forEach(function (col) {
                if (DxGrid.isAuditColumn(col)) { col.visible = false; }
            });
            try { localStorage.setItem(flagKey, '1'); } catch (e) { /* 记不住就每次打开再收一次 */ }
        }
        var md = false;
        try {
            var master = grid && grid.option ? grid.option('masterDetail') : null;
            md = master === true || !!(master && master.enabled);
        } catch (e) { md = false; }
        var keepFix = false;
        try { keepFix = grid && grid.option && grid.option('keepColumnFixing') === true; } catch (e2) { keepFix = false; }
        if (md && !keepFix && state.columns) {
            state.columns.forEach(function (col) { delete col.fixed; delete col.fixedPosition; });
        }
        return state;
    };

    DxGrid._writeGridState = function (storageKey, state) {
        try { localStorage.setItem(storageKey, JSON.stringify(DxGrid._sanitizeState(state))); } catch (e) { /* 存不了就只对本次有效 */ }
    };

    DxGrid._stateOptions = function (grid) {
        return {
            enabled: true, type: 'custom',
            customLoad: function () { return DxGrid._readGridState(DxGrid._stateKeyOf(grid), grid); },
            customSave: function (state) { DxGrid._writeGridState(DxGrid._stateKeyOf(grid), state); }
        };
    };

    /** 去掉筛选 / 搜索 / 页码 / 选中等一次性状态，只留列宽、顺序、显隐、固定、分组、排序、每页条数；本地记忆和服务端「保存布局」共用 */
    DxGrid._sanitizeState = function (state) {
        var c = $.extend({}, state || {});
        ['filterValue', 'filterPanel', 'searchText', 'pageIndex', 'selectedRowKeys', 'focusedRowKey', 'expandedRowKeys'].forEach(function (k) { delete c[k]; });
        if (c.columns) {
            c.columns = c.columns.map(function (col) {
                col = $.extend({}, col);
                ['filterValue', 'filterValues', 'filterType', 'selectedFilterOperation'].forEach(function (k) { delete col[k]; });
                return col;
            });
        }
        return c;
    };

    /** 重置筛选、搜索、排序、分组、选中 */
    DxGrid.resetView = function (grid) {
        grid._selectedOnly = false;
        grid._selectedOnlyReturn = null;
        DxGrid._repaintBatchMenu(grid);
        (grid._businessQueryResetters || []).forEach(function (reset) { reset(); });
        grid.clearFilter();
        grid.option('filterValue', null);
        grid.clearSorting();
        grid.clearGrouping();
        grid.searchByText('');
        grid.deselectAll();
        grid.pageIndex(0);
    };

    /** 数据源主键字段（单个时可用），「查看已选」拼 key anyof (keys) 过滤用（DevExtreme 对数值列会把 in 归一成 =，多值要用 anyof） */
    DxGrid._keyField = function (grid) {
        try {
            var k = grid.getDataSource().store().key();
            if (typeof k === 'string') { return k; }
            if (k && k.keyProperties && k.keyProperties.length === 1) { return k.keyProperties[0]; }
        } catch (e) { }
        return null;
    };

    /** 重绘批量菜单，刷新「查看已选」的打勾（同编辑方式菜单：弹层 DOM 会缓存，得给它新数组才会重新渲染） */
    DxGrid._repaintBatchMenu = function (grid) {
        if (grid._batchDD) { grid._batchDD.option('items', (grid._batchDD.option('items') || []).slice()); }
        if (grid._selectedButton) {
            grid._selectedButton.option({
                type: grid._selectedOnly ? 'default' : 'normal',
                hint: grid._selectedOnly ? '退出查询已选' : '查询已选'
            });
        }
    };

    /** 查看已选：只显示勾选过的行。在当前筛选上叠加主键 anyof 过滤，再点一次回到之前的筛选；勾选的行在退出前记下来，翻页 / 取消勾选不影响 */
    DxGrid.toggleSelectedOnly = function (grid) {
        if (grid._selectedOnly) {
            grid._selectedOnly = false;
            grid.option('filterValue', grid._selectedOnlyReturn);
            grid._selectedOnlyReturn = null;
            DxGrid._repaintBatchMenu(grid);
            return;
        }
        var keys = grid.getSelectedRowKeys();
        if (!keys.length) { DevExpress.ui.notify('请先勾选要查看的行', 'warning', 1800); return; }
        var kf = DxGrid._keyField(grid);
        if (!kf) { DevExpress.ui.notify('表格没有可用的主键列，无法只看已选', 'error', 2200); return; }
        grid._selectedOnlyReturn = grid.option('filterValue') || null;
        grid._selectedOnly = true;
        var f = [kf, 'anyof', keys];
        grid.option('filterValue', grid._selectedOnlyReturn ? ['and', grid._selectedOnlyReturn, f] : f);
        DxGrid._repaintBatchMenu(grid);
    };

    /** 恢复默认布局：清掉本地记忆的列宽、顺序、固定等 */
    DxGrid.resetLayout = function (grid) {
        try { localStorage.removeItem(grid._stateKey); localStorage.removeItem(grid._stateKey + ':editMode'); } catch (e) { }
        grid.cancelEditData();
        grid.option('editing.mode', grid._defaultEditMode || 'popup');
        grid.state(null);
        DxGrid.resetView(grid);
    };

    /** 保存布局：当前列宽 / 顺序 / 显隐 / 固定 / 排序 / 每页条数 + 编辑模式，按用户 + 表格存服务端（sys_grid_layout），覆盖保存 */
    DxGrid.saveLayout = function (grid) {
        var st = DxGrid._sanitizeState(grid.state());
        if (!Object.keys(st).length) { DevExpress.ui.notify('表格还没有可保存的布局', 'warning', 1800); return; }
        DxGrid.layoutApi('POST', '', { grid_key: grid._gridKey, layout: { state: st, editMode: grid.option('editing.mode') || null } }).then(function () {
            DevExpress.ui.notify('布局已保存', 'success', 1800);
        }, function (msg) { DevExpress.ui.notify('保存布局失败：' + msg, 'error', 3000); });
    };

    /** 恢复布局：取回服务端保存的布局并应用；先清掉筛选 / 搜索 / 选中等一次性状态 */
    DxGrid.loadLayout = function (grid) {
        DxGrid.layoutApi('GET', '?grid_key=' + encodeURIComponent(grid._gridKey)).then(function (row) {
            if (!row || !row.layout) { DevExpress.ui.notify('这个表格还没有保存过布局', 'warning', 1800); return; }
            DxGrid.resetView(grid);
            if (row.layout.editMode) { DxGrid.setEditMode(grid, row.layout.editMode); }
            var st = row.layout.state || {};
            var master = grid.option('masterDetail');
            if ((master === true || (master && master.enabled)) && grid.option('keepColumnFixing') !== true) {
                st = $.extend(true, {}, st);
                (st.columns || []).forEach(function (col) { delete col.fixed; delete col.fixedPosition; });
            }
            grid.state(st);
            grid.refresh();
            DevExpress.ui.notify('已恢复保存的布局', 'success', 1800);
        }, function (msg) { DevExpress.ui.notify('恢复布局失败：' + msg, 'error', 3000); });
    };

    /* ================================================================ 工具栏 */
    /** 独立业务工具栏：查询控件在左，新增 / 编辑 / 删除 / 批量动作统一收进右侧「操作」。 */
    DxGrid._initBusinessToolbar = function (grid, suppliedConfig) {
        var cfg = suppliedConfig !== undefined ? suppliedConfig : grid.option('businessToolbar');
        cfg = cfg === true ? {} : (cfg || {});
        grid._hasBusinessToolbar = true;
        if (grid._businessToolbarEl) { grid._businessToolbarEl.remove(); }
        var $bar = $('<div class="dxgrid-business-toolbar"></div>').insertBefore(grid.element());
        grid._businessToolbarEl = $bar;
        var items = (cfg.queryItems || []).map(function (it) { return $.extend({ location: 'before' }, it); });
        var menuItems = [];
        var custom = cfg.actions || [];
        custom.forEach(function (a) { menuItems.push({ id: 'custom:' + a.id, text: a.text, icon: a.icon, beginGroup: !!a.beginGroup }); });
        var ed = grid.option('editing') || {};
        var editTexts = ed.texts || {};
        if (ed.allowAdding) {
            menuItems.push({ id: '__add', text: editTexts.addRow || '新增', icon: 'add', beginGroup: custom.length > 0 });
        }
        if (ed.allowUpdating) {
            menuItems.push({ id: '__edit', text: editTexts.editRow || '编辑选中', icon: 'edit' });
        }
        if (grid.option('batchDelete') || ed.allowDeleting) {
            menuItems.push({ id: '__delete', text: cfg.deleteText || '删除选中', icon: 'trash', beginGroup: custom.length > 0 && !ed.allowAdding && !ed.allowUpdating });
        }
        var batchActions = grid.option('batchActions') || [];
        batchActions.forEach(function (a, i) {
            menuItems.push({ id: 'batch:' + a.id, text: a.text, icon: a.icon, beginGroup: i === 0 && menuItems.length > 0 });
        });
        if (menuItems.length) {
            items.push({
                location: 'after', widget: 'dxDropDownButton',
                options: {
                    text: cfg.actionText || '操作', icon: cfg.actionIcon || 'edit', stylingMode: 'text', showArrowIcon: true,
                    items: menuItems, displayExpr: 'text', keyExpr: 'id', useSelectMode: false,
                    dropDownOptions: { width: cfg.actionMenuWidth || 210 },
                    onItemClick: function (e) {
                        var id = e.itemData.id;
                        if (id === '__add') { grid.addRow(); return; }
                        if (id === '__edit') {
                            var keys = grid.getSelectedRowKeys();
                            if (keys.length !== 1) { DevExpress.ui.notify('请勾选一条要编辑的记录', 'warning', 1800); return; }
                            var rowIndex = grid.getRowIndexByKey(keys[0]);
                            if (rowIndex < 0) { DevExpress.ui.notify('选中记录不在当前页，请先查询已选', 'warning', 2200); return; }
                            grid.editRow(rowIndex);
                            return;
                        }
                        if (id === '__delete') { DxGrid.batchDelete(grid); return; }
                        if (id.indexOf('custom:') === 0) {
                            var ca = custom.filter(function (x) { return x.id === id.slice(7); })[0];
                            if (ca && typeof ca.run === 'function') { ca.run(grid); }
                            return;
                        }
                        if (id.indexOf('batch:') === 0) {
                            var ba = batchActions.filter(function (x) { return x.id === id.slice(6); })[0];
                            if (ba) { DxGrid.runBatchAction(grid, ba); }
                        }
                    }
                }
            });
        }
        $bar.dxToolbar({ items: items });
        // 挂载后元素 top 已改变，立即按新位置重算；工具栏换行时继续自动重算。
        DxGrid.syncAutoHeight(grid);
        if (window.ResizeObserver && grid._autoHeightManaged) {
            if (grid._businessToolbarResizeObserver) { grid._businessToolbarResizeObserver.disconnect(); }
            grid._businessToolbarResizeObserver = new ResizeObserver(function () { DxGrid.syncAutoHeight(grid); });
            grid._businessToolbarResizeObserver.observe($bar[0]);
        }
    };

    DxGrid._buildToolbar = function (grid, e) {
        var items = e.toolbarOptions.items;
        // 两行布局中，新增 / 编辑 / 删除属于业务动作，不能再留在 Grid 自带工具栏。
        if (grid._hasBusinessToolbar || grid.option('businessToolbar')) {
            for (var i = items.length - 1; i >= 0; i--) {
                if (items[i].name === 'addRowButton') { items.splice(i, 1); }
            }
        }
        function btn(location, icon, hint, onClick, initialized) {
            return { location: location, widget: 'dxButton', options: { icon: icon, hint: hint, stylingMode: 'text', onClick: onClick, onInitialized: initialized } };
        }
        function menu(icon, hint, list, onItem) {
            return {
                location: 'after', widget: 'dxDropDownButton',
                options: {
                    icon: icon, hint: hint, stylingMode: 'text', showArrowIcon: true, items: list, displayExpr: 'text', keyExpr: 'id',
                    useSelectMode: false, dropDownOptions: { width: 190 }, onItemClick: function (a) { onItem(a.itemData.id); }
                }
            };
        }
        items.push(btn('before', 'refresh', '刷新', function () { grid.refresh(); }));
        items.push(btn('before', 'selectall', '查询已选', function () { DxGrid.toggleSelectedOnly(grid); }, function (a) {
            grid._selectedButton = a.component;
        }));
        items.push(btn('before', 'revert', '重置：清除筛选、搜索、排序、分组和选中', function () { DxGrid.resetView(grid); }));
        // 批量操作（勾选框图标）：「查看已选」永远排第一；之后是删除（表格允许删除或页面给了 batchDelete）+ 页面自定义的 batchActions: [{id, text, confirm?, successText?, run(keys)}]
        var actions = grid.option('batchActions') || [];
        var ed = grid.option('editing') || {};
        if (!(grid._hasBusinessToolbar || grid.option('businessToolbar'))) {
            var batch = [];
            if (grid.option('batchDelete') || ed.allowDeleting) { batch.push({ id: '__delete', text: '删除选中行' }); }
            actions.forEach(function (a) { batch.push({ id: a.id, text: a.text }); });
            if (batch.length) {
                items.push({
                    location: 'before', widget: 'dxDropDownButton',
                    options: {
                        icon: 'more', hint: '批量操作（对勾选的行）', stylingMode: 'text', showArrowIcon: true, items: batch, displayExpr: 'text', keyExpr: 'id',
                        useSelectMode: false, dropDownOptions: { width: 190 },
                        onItemClick: function (a) {
                            var id = a.itemData.id;
                            if (id === '__delete') { DxGrid.batchDelete(grid); return; }
                            var x = actions.filter(function (v) { return v.id === id; })[0];
                            if (x) { DxGrid.runBatchAction(grid, x); }
                        }
                    }
                });
            }
        }
        items.push(menu('export', '导出（CSV，Excel 可直接打开）', [
            { id: 'page', text: '导出当前页' }, { id: 'selected', text: '导出选中行' }, { id: 'all', text: '导出全部（按当前筛选）' }
        ], function (id) { DxGrid.exportCsv(grid, id); }));
        // 编辑模式（铅笔）：行 / 弹窗 / 单元格 / 表单 / 批量，当前模式打勾；只在表格允许增删改时出现
        if (ed.allowAdding || ed.allowUpdating || ed.allowDeleting) {
            items.push({
                location: 'after', widget: 'dxDropDownButton',
                options: {
                    icon: 'edit', hint: '编辑模式', stylingMode: 'text', showArrowIcon: true, items: DxGrid.EDIT_MODES, keyExpr: 'id', displayExpr: 'text',
                    useSelectMode: false, dropDownOptions: { width: 170 },
                    itemTemplate: function (it) { return $('<div></div>').text((grid.option('editing.mode') === it.id ? '\u2713 ' : '\u3000') + it.text); },
                    onItemClick: function (a) { DxGrid.setEditMode(grid, a.itemData.id); }
                }
            });
        }
        items.push(menu('preferences', '表格设置', [
            { id: 'layout', text: '恢复默认布局' }, { id: 'saveLayout', text: '保存布局' }, { id: 'loadLayout', text: '恢复布局' },
            { id: 'style', text: '表格外观（UI配置）' }
        ], function (id) {
            if (id === 'layout') { DxGrid.resetLayout(grid); }
            if (id === 'saveLayout') { DxGrid.saveLayout(grid); }
            if (id === 'loadLayout') { DxGrid.loadLayout(grid); }
            if (id === 'style' && typeof openAdminTab === 'function') { openAdminTab('/uiStyle?tab=grid', 'UI配置'); }
        }));
    };

    /* ================================================================ 拖动排序
     * 页面传 rowReorder: function (info) { return promise }，info = {key, data, targetKey, after}（after=true 表示放到目标行之后）。
     * 列表带了筛选 / 搜索 / 排序 / 分组时拖动顺序和真实顺序对不上，这时不允许拖。 */
    DxGrid._rowDragging = function (fn) {
        return {
            allowReordering: true, showDragIcons: true, dropFeedbackMode: 'push',
            onDragStart: function (e) {
                var grid = e.component;
                var sorted = grid.getVisibleColumns().some(function (c) { return c.sortOrder || c.groupIndex !== undefined; });
                if (grid.getCombinedFilter() || sorted) {
                    e.cancel = true;
                    DevExpress.ui.notify('请先清除筛选、搜索和排序（点工具栏的「重置」）再拖动排序', 'warning', 2500);
                }
            },
            onReorder: function (e) {
                var grid = e.component;
                var rows = grid.getVisibleRows();
                var from = rows[e.fromIndex], target = rows[e.toIndex];
                if (!from || !target || from.key === target.key) { return; }
                var d = $.Deferred();
                e.promise = d.promise();
                $.when(fn({ key: from.key, data: from.data, targetKey: target.key, after: e.toIndex > e.fromIndex })).then(function () {
                    grid.refresh().always(function () { d.resolve(); });
                }, function (err) {
                    DevExpress.ui.notify(String(err && err.message ? err.message : err), 'error', 3000);
                    d.resolve();
                });
            }
        };
    };

    /* ================================================================ 编辑模式 */
    DxGrid.EDIT_MODES = [
        { id: 'row', text: '行编辑' }, { id: 'popup', text: '弹窗编辑' }, { id: 'cell', text: '单元格编辑' },
        { id: 'form', text: '表单编辑' }, { id: 'batch', text: '批量编辑' }
    ];

    DxGrid.setEditMode = function (grid, mode) {
        grid.cancelEditData();
        grid.option('editing.mode', mode);
        try { localStorage.setItem(grid._stateKey + ':editMode', mode); } catch (e) { /* 存不了就只对本次有效 */ }
        if (mode === 'batch') { DevExpress.ui.notify('批量编辑：改完后点工具栏的「保存」一次性提交', 'info', 2500); }
    };

    /** 批量操作：对勾选的行执行页面给的动作（run 返回 promise）；没勾选先提示，需要确认的先确认 */
    DxGrid.runBatchAction = function (grid, action) {
        var keys = grid.getSelectedRowKeys();
        if (!keys.length) { DevExpress.ui.notify('请先勾选要操作的行', 'warning', 1800); return; }
        function go() {
            $.when(action.run(keys)).then(function () {
                grid.deselectAll();
                grid.refresh();
                DevExpress.ui.notify((action.successText || '操作完成') + '（' + keys.length + ' 条）', 'success', 2000);
            }, function (err) { DevExpress.ui.notify(String(err && err.message ? err.message : err), 'error', 3000); });
        }
        if (action.confirm) {
            DevExpress.ui.dialog.confirm(action.confirm.replace('{n}', keys.length), action.text).then(function (yes) { if (yes) { go(); } });
        } else { go(); }
    };

    /** 批量删除选中行：页面给了 batchDelete(keys) 就用它（返回 promise），否则逐个走数据源的 remove */
    DxGrid.batchDelete = function (grid) {
        var keys = grid.getSelectedRowKeys();
        if (!keys.length) { DevExpress.ui.notify('请先勾选要删除的行', 'warning', 1800); return; }
        DevExpress.ui.dialog.confirm('确定删除选中的 ' + keys.length + ' 条记录吗？删除后不可恢复', '批量删除').then(function (yes) {
            if (!yes) { return; }
            var custom = grid.option('batchDelete');
            var store = grid.getDataSource().store();
            var chain = $.Deferred().resolve().promise();
            var failed = 0;
            keys.forEach(function (k) {
                chain = chain.then(function () {
                    var r = custom ? custom(k) : store.remove(k);
                    return $.when(r).then(null, function () { failed++; return $.Deferred().resolve().promise(); });
                });
            });
            chain.then(function () {
                grid.deselectAll();
                grid.refresh();
                DevExpress.ui.notify(failed ? '已处理，其中 ' + failed + ' 条删除失败' : '已删除 ' + keys.length + ' 条', failed ? 'warning' : 'success', 2200);
            });
        });
    };

    /* ================================================================ 导出 CSV */
    function pathGetter(field) {
        var parts = String(field).split('.');
        return function (row) {
            var v = row;
            for (var i = 0; i < parts.length && v !== null && v !== undefined; i++) { v = v[parts[i]]; }
            return v;
        };
    }

    function csvCell(v) {
        if (v === null || v === undefined) { return ''; }
        if (Array.isArray(v)) { v = v.join('、'); } else if (typeof v === 'object') { v = JSON.stringify(v); }
        v = String(v);
        // 防 CSV 公式注入：以 = + - @ 开头的文本前面补一个单引号（数字本身除外）
        if (/^[=+\-@]/.test(v) && isNaN(Number(v))) { v = "'" + v; }
        return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    }

    /** 当前筛选 / 搜索 / 排序条件下的全部数据（服务端分页的表格按 500 一批取完，其余在本地过滤排序） */
    function loadAllRows(grid) {
        var ds = grid.getDataSource();
        var store = ds.store();
        var filter = grid.getCombinedFilter(true);
        var sort = ds.sort();
        sort = sort ? [].concat(sort) : [];
        var ro = grid.option('remoteOperations');
        var remote = ro && typeof ro === 'object' && ro.paging;
        var d = $.Deferred();
        if (remote) {
            var all = [];
            (function next(skip) {
                store.load({ skip: skip, take: 500, filter: filter, sort: sort.length ? sort : undefined, requireTotalCount: true }).done(function (res, extra) {
                    // 自定义 store 返回 {data, totalCount}（processed 模式下原样透传），其它 store 返回数组 + extra
                    var data = Array.isArray(res) ? res : (res && res.data) || [];
                    all = all.concat(data);
                    var total = !Array.isArray(res) && res && res.totalCount !== undefined ? res.totalCount
                        : (extra && extra.totalCount !== undefined ? extra.totalCount : all.length);
                    if (data.length && all.length < total) { next(skip + 500); } else { d.resolve(all); }
                }).fail(function (err) { d.reject(err); });
            })(0);
        } else {
            store.load().done(function (rows) {
                var q = DevExpress.data.query(rows);
                if (filter) { q = q.filter(filter); }
                sort.forEach(function (x, i) { q = i ? q.thenBy(x.selector, !!x.desc) : q.sortBy(x.selector, !!x.desc); });
                d.resolve(q.toArray());
            }).fail(function (err) { d.reject(err); });
        }
        return d.promise();
    }

    DxGrid.exportCsv = function (grid, mode) {
        var cols = grid.getVisibleColumns().filter(function (c) { return c.dataField && !c.type; });
        if (!cols.length) { return; }
        var source;
        if (mode === 'page') {
            source = $.Deferred().resolve(grid.getVisibleRows().filter(function (r) { return r.rowType === 'data'; }).map(function (r) { return r.data; })).promise();
        } else if (mode === 'selected') {
            source = $.when(grid.getSelectedRowsData());
        } else {
            source = loadAllRows(grid);
        }
        source.done(function (rows) {
            if (!rows || !rows.length) { DevExpress.ui.notify('没有可导出的数据', 'warning', 1800); return; }
            var getters = cols.map(function (c) { return pathGetter(c.dataField); });
            var lines = [cols.map(function (c) { return csvCell(c.caption); }).join(',')];
            rows.forEach(function (row) {
                lines.push(cols.map(function (c, i) {
                    var v = getters[i](row);
                    if (c.lookup && c.lookup.calculateCellValue) { v = c.lookup.calculateCellValue(v); }
                    else if (c.dataType === 'boolean') { v = v === true || v === 1 ? '是' : v === false || v === 0 ? '否' : ''; }
                    return csvCell(v);
                }).join(','));
            });
            var blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });  // BOM 让 Excel 正确识别 UTF-8
            var a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            var d = new Date(), pad = function (n) { return (n < 10 ? '0' : '') + n; };
            a.download = (document.title || 'export') + '_' + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + pad(d.getHours()) + pad(d.getMinutes()) + '.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
            DevExpress.ui.notify('已导出 ' + rows.length + ' 条', 'success', 1800);
        }).fail(function (err) { DevExpress.ui.notify('导出失败：' + (err && err.message ? err.message : err), 'error', 3000); });
    };

    /* ================================================================ 表格个性化接口（过滤器模板 / 布局，均按用户 + 表格存服务端） */
    function gridApi(method, base, path, body) {
        return $.ajax({
            url: APP.HOST + base + path, method: method,
            contentType: 'application/json', data: body === undefined ? undefined : JSON.stringify(body)
        }).then(function (res) {
            if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
            return res.data;
        }, function (xhr) {
            if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
            return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
        });
    }

    function filterApi(method, path, body) { return gridApi(method, '/api/v1/grid-filters', path, body); }

    DxGrid.layoutApi = function (method, path, body) { return gridApi(method, '/api/v1/grid-layouts', path, body); };

    function notifyError(msg) { DevExpress.ui.notify(String(msg), 'error', 3000); }

    /** 过滤器构建器弹窗：底部加「选择模板」「保存为模板」，并补上「确定」「取消」（自定义底部按钮会替换默认的） */
    DxGrid._initFilterBuilderPopup = function (grid) {
        var gridKey = grid.option('gridKey') || location.pathname;
        var popup;
        function builder() { return popup.$content().find('.dx-filterbuilder').dxFilterBuilder('instance'); }

        function pickTemplate() {
            var b = builder();
            var $el = $('<div></div>').appendTo(document.body);
            var pk = $el.dxPopup({
                title: '选择过滤器模板', width: '90%', maxWidth: 420, height: '70%', showTitle: true, showCloseButton: true,
                hideOnOutsideClick: true, onHidden: function () { $el.remove(); },
                contentTemplate: function (content) {
                    var $list = $('<div></div>').appendTo(content);
                    filterApi('GET', '?grid_key=' + encodeURIComponent(gridKey)).then(function (rows) {
                        if (!rows.length) { $list.text('还没有保存过模板，在过滤器里设好条件后点「保存为模板」'); return; }
                        $list.dxList({
                            items: rows, height: 'auto', noDataText: '暂无模板',
                            itemTemplate: function (item, _, el) {
                                $('<span></span>').text(item.name).appendTo(el);
                                $('<span class="tpl-del" title="删除模板">✕</span>').css({ float: 'right', color: '#d9363e', cursor: 'pointer', padding: '0 4px' })
                                    .on('click', function (ev) {
                                        ev.stopPropagation();
                                        DevExpress.ui.dialog.confirm('确定删除模板「' + item.name + '」吗？', '删除模板').then(function (yes) {
                                            if (!yes) { return; }
                                            filterApi('DELETE', '/' + item.id).then(function () {
                                                $list.dxList('instance').option('items', $list.dxList('instance').option('items').filter(function (x) { return x.id !== item.id; }));
                                            }, notifyError);
                                        });
                                    }).appendTo(el);
                            },
                            onItemClick: function (a) { b.option('value', a.itemData.filter_value); pk.hide(); }
                        });
                    }, function (msg) { $list.text('加载失败：' + msg); });
                }
            }).dxPopup('instance');
            pk.show();
        }

        function saveTemplate() {
            var value = builder().option('value');
            if (!Array.isArray(value) || !value.length) { DevExpress.ui.notify('过滤器里还没有条件，没有可保存的内容', 'warning', 2200); return; }
            var $el = $('<div></div>').appendTo(document.body);
            var tb;
            var pk = $el.dxPopup({
                title: '保存为模板', width: '90%', maxWidth: 380, height: '70%', showTitle: true, showCloseButton: true, hideOnOutsideClick: false,
                onHidden: function () { $el.remove(); },
                toolbarItems: [
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '保存', type: 'default', stylingMode: 'contained', onClick: doSave } },
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '取消', onClick: function () { pk.hide(); } } }
                ],
                contentTemplate: function (content) {
                    $('<div style="margin-bottom:6px">模板名称（同名会覆盖）</div>').appendTo(content);
                    tb = $('<div></div>').appendTo(content).dxTextBox({ maxLength: 50, placeholder: '如：本月上架的香水', onEnterKey: doSave }).dxTextBox('instance');
                }
            }).dxPopup('instance');
            pk.show();
            function doSave() {
                var name = String(tb.option('value') || '').trim();
                if (!name) { DevExpress.ui.notify('请输入模板名称', 'warning', 1800); return; }
                filterApi('POST', '', { grid_key: gridKey, name: name, filter_value: value }).then(function () {
                    pk.hide();
                    DevExpress.ui.notify('模板「' + name + '」已保存', 'success', 1800);
                }, notifyError);
            }
        }

        grid.option('filterBuilderPopup', {
            width: 760,
            onInitialized: function (e) { popup = e.component; },
            toolbarItems: [
                { toolbar: 'bottom', location: 'before', widget: 'dxButton', options: { text: '选择模板', icon: 'folder', stylingMode: 'text', onClick: pickTemplate } },
                { toolbar: 'bottom', location: 'before', widget: 'dxButton', options: { text: '保存为模板', icon: 'save', stylingMode: 'text', onClick: saveTemplate } },
                { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '确定', type: 'default', stylingMode: 'contained', onClick: function () { grid.option('filterValue', builder().option('value')); popup.hide(); } } },
                { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '取消', onClick: function () { popup.hide(); } } }
            ]
        });
    };

    /**
     * 计算表格容器到可视区底部的剩余高度（至少 200），页面里让表格撑满窗口用。
     * 在 height 回调里 this 是 dxDataGrid 实例，也可直接传选择器 / 元素。
     */
    DxGrid.autoHeight = function (target) {
        var $el = $(target && target.element ? target.element() : target);
        // 使用相对视口的位置，避免页面曾经滚动后 offset.top 仍按文档坐标计算。
        var top = $el.length && $el[0].getBoundingClientRect ? $el[0].getBoundingClientRect().top : 0;
        var bottom = 0;
        $el.parentsUntil('html').each(function () {
            var $p = $(this);
            bottom += (parseFloat($p.css('padding-bottom')) || 0) + (parseFloat($p.css('border-bottom-width')) || 0);
        });
        return Math.max(200, Math.floor($(window).height() - top - bottom));
    };

    /** 自动高度主 Grid 在业务栏、窗口尺寸或其它上方布局变化后统一调用。 */
    DxGrid.syncAutoHeight = function (grid) {
        if (!grid || typeof grid.updateDimensions !== 'function') { return; }
        if (grid._autoHeightManaged) { grid.option('height', DxGrid.autoHeight(grid.element())); }
        grid.updateDimensions();
    };

    /** 让复用 DxGrid 公共工具栏的 TreeList 也接入主页面自动高度。 */
    DxGrid.enableAutoHeight = function (grid) {
        if (!grid) { return; }
        grid._autoHeightManaged = true;
        DxGrid.syncAutoHeight(grid);
    };

    /**
     * 对接 REST 风格接口的 CustomStore:
     *   GET {url} 取全部 → data 数组；POST {url} 新增；PUT {url}/{key} 修改；DELETE {url}/{key} 删除
     */
    DxGrid.restStore = function (url, key) {
        function call(method, path, body) {
            return $.ajax({
                url: APP.HOST + path,
                method: method,
                contentType: 'application/json',
                data: body === undefined ? undefined : JSON.stringify(body)
            }).then(function (res) {
                if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
                return res.data;
            }, function (xhr) {
                var msg = (xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error';
                if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
                return $.Deferred().reject(msg).promise();
            });
        }
        return new DevExpress.data.CustomStore({
            key: key,
            load: function () { return call('GET', url); },
            insert: function (values) { return call('POST', url, values); },
            update: function (k, values) { return call('PUT', url + '/' + encodeURIComponent(k), values); },
            remove: function (k) { return call('DELETE', url + '/' + encodeURIComponent(k)); }
        });
    };

    /**
     * 服务端分页 / 筛选 / 排序的 CustomStore，配合表格的 remoteOperations: {paging, filtering, sorting: true}。
     *   GET {url}?skip=&take=&sort=<JSON>&filter=<JSON>  →  data: {items, total}
     * 增删改和 restStore 一样。表头筛选（headerFilter）要按列去重取值，服务端没有提供，用这个 store 的表格请关掉它。
     */
    DxGrid.remoteStore = function (url, key, extraParams) {
        var base = DxGrid.restStore(url, key);
        function get(path) {
            return $.ajax({ url: APP.HOST + path, method: 'GET' }).then(function (res) {
                if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
                return res.data;
            }, function (xhr) {
                if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
                return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
            });
        }
        return new DevExpress.data.CustomStore({
            key: key,
            load: function (o) {
                var q = {};
                if (o.take) { q.take = o.take; q.skip = o.skip || 0; }
                if (o.sort) { q.sort = JSON.stringify(o.sort); }
                if (o.filter) { q.filter = JSON.stringify(o.filter); }
                $.extend(q, typeof extraParams === 'function' ? (extraParams(o) || {}) : (extraParams || {}));
                var qs = $.param(q);
                return get(url + (qs ? '?' + qs : '')).then(function (res) {
                    return Array.isArray(res) ? { data: res, totalCount: res.length } : { data: res.items, totalCount: res.total };
                });
            },
            insert: function (values) { return base.insert(values); },
            update: function (k, values) { return base.update(k, values); },
            remove: function (k) { return base.remove(k); }
        });
    };

    DevExpress.ui.dxGrid = DxGrid;

    // 注册 jQuery 插件 $(el).dxGrid(options)
    $.fn.dxGrid = function (options) {
        var args = arguments;
        var result;
        this.each(function () {
            var inst = $(this).data('dxGrid');
            if (typeof options === 'string') {
                if (options === 'instance') { result = inst; return false; }
                if (inst) { result = inst[options].apply(inst, Array.prototype.slice.call(args, 1)); }
            } else if (inst) {
                inst.option(options);
            } else {
                $(this).data('dxGrid', new DxGrid(this, options));
            }
        });
        return result === undefined ? this : result;
    };

    window.DxGrid = DxGrid;
})(jQuery);
