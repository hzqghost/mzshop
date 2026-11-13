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
            // DevExtreme 24.1 缺陷：masterDetail 的展开图标在 columnFixing 开启、或表格里有 fixed 列时都不渲染
            // （单元格只剩 &nbsp;，只能靠 expandRow API）。必须在创建时处理（_init 里再改不生效）：
            // 关掉列固定，并替换默认的 fixCommandColumns（不固定勾选列/操作列）；页面自己的 customizeColumns 仍执行
            if (options.masterDetail === true || (options.masterDetail && options.masterDetail.enabled)) {
                var mdFixes = {};
                if (!(options.columnFixing && options.columnFixing.enabled === false)) {
                    mdFixes.columnFixing = { enabled: false };
                }
                var mdPageCC = options.customizeColumns;
                mdFixes.customizeColumns = function (columns) {
                    if (typeof mdPageCC === 'function') { mdPageCC.call(this, columns); }
                };
                options = $.extend({}, options, mdFixes);
            }
            this.callBase(el, options);
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
                columnFixing: { enabled: true },   // 列头右键菜单：升序 / 降序 / 清除排序 / 固定（向左、向右）/ 不固定
                filterPanel: { visible: true },    // 过滤器：底部过滤面板，点开是过滤器构建器（带「模板」）
                groupPanel: { visible: true },     // 拖动列标题到此处分组（服务端分页的表格会自动关掉）
                grouping: { contextMenuEnabled: true },
                columnChooser: { enabled: true, mode: 'select' },
                customizeColumns: DxGrid.fixCommandColumns,
                stateStoring: DxGrid._stateOptions(self)
            }, DxGrid.styleOptions());
        },

        _init: function () {
            this.callBase();
            var self = this;
            $(this.element()).data('dxGrid', this); // new DxGrid(el) 和 $(el).dxGrid() 两种创建方式都能 $(el).dxGrid('instance') 取到
            if (this.option('autoHeight') && this.option('height') === undefined) {
                this.option('height', function () { return DxGrid.autoHeight(self.element()); });
                this._onWinResize = function () { self.updateDimensions(); };
                $(window).on('resize', this._onWinResize);
            }
            if (!this.option('dxFeatures')) {
                this.option({
                    selection: { mode: 'none' }, filterPanel: { visible: false }, groupPanel: { visible: false },
                    columnChooser: { enabled: false }, columnFixing: { enabled: false }, stateStoring: { enabled: false }
                });
                return;
            }
            // 服务端分页 / 筛选的表格不支持分组（分组要服务端配合），关掉分组面板
            var ro = this.option('remoteOperations');
            if (ro && typeof ro === 'object' && (ro.paging || ro.filtering)) {
                this.option({ groupPanel: { visible: false }, grouping: { contextMenuEnabled: false } });
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
            // 工具栏：刷新 / 批量（含查看已选）/ 重置 / 导出 / 编辑模式 / 设置；页面自己的 onToolbarPreparing 在后面执行，还能再增删
            var userToolbar = this.option('onToolbarPreparing');
            this.option('onToolbarPreparing', function (e) {
                DxGrid._buildToolbar(self, e);
                if (userToolbar) { userToolbar.apply(this, arguments); }
            });
        },

        _dispose: function () {
            if (this._onWinResize) { $(window).off('resize', this._onWinResize); }
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
        if (s.fixedCommand === false) {
            // 用户在「Grid 配置」里明确关掉了冻结：不固定勾选列和操作列
            options.customizeColumns = function () { };
        }
        return options;
    };

    /** 树形表格（dxTreeList）用的同一套标准功能：多选列、列头右键菜单、过滤行 / 表头筛选 / 过滤面板、列选择器、固定列 */
    DxGrid.treeOptions = function () {
        return {
            selection: { mode: 'multiple', showCheckBoxesMode: 'always', recursive: false },
            columnFixing: { enabled: true },
            filterRow: { visible: true },
            headerFilter: { visible: true, search: { enabled: true, editorOptions: { placeholder: '搜索...' } } }, // 表头筛选里带搜索框
            filterPanel: { visible: true },
            columnChooser: { enabled: true, mode: 'select' },
            sorting: { mode: 'multiple' },
            customizeColumns: DxGrid.fixCommandColumns
        };
    };

    /** 勾选列固定在左、操作列（图标按钮）固定在右 */
    DxGrid.fixCommandColumns = function (columns) {
        columns.forEach(function (c) {
            if (c.type === 'selection') { c.fixed = true; c.fixedPosition = 'left'; }
            if (c.type === 'buttons') { c.fixed = true; c.fixedPosition = 'right'; }
        });
    };


    /* ================================================================ 布局记忆 */
    // 列宽、顺序、显隐、固定、排序、每页条数记在浏览器本地（按页面路径）；筛选 / 搜索 / 页码 / 选中行不记，免得下次打开莫名其妙是过滤后的结果
    DxGrid._stateOptions = function (grid) {
        function key() { return 'dxGrid:' + (grid.option('gridKey') || location.pathname); }
        return {
            enabled: true, type: 'custom',
            customLoad: function () {
                // 没存过要返回 {} 而不是 null：返回 null 会让表格把列清空（实测整个表格空白）
                try { return JSON.parse(localStorage.getItem(key()) || '{}') || {}; } catch (e) { return {}; }
            },
            customSave: function (state) {
                try { localStorage.setItem(key(), JSON.stringify(DxGrid._sanitizeState(state))); } catch (e) { /* 存不了就只对本次有效 */ }
            }
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
            grid.state(row.layout.state);
            grid.refresh();
            DevExpress.ui.notify('已恢复保存的布局', 'success', 1800);
        }, function (msg) { DevExpress.ui.notify('恢复布局失败：' + msg, 'error', 3000); });
    };

    /* ================================================================ 工具栏 */
    DxGrid._buildToolbar = function (grid, e) {
        var items = e.toolbarOptions.items;
        function btn(icon, hint, onClick) {
            return { location: 'after', widget: 'dxButton', options: { icon: icon, hint: hint, stylingMode: 'text', onClick: onClick } };
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
        items.push(btn('refresh', '刷新', function () { grid.refresh(); }));
        // 批量操作（勾选框图标）：「查看已选」永远排第一；之后是删除（表格允许删除或页面给了 batchDelete）+ 页面自定义的 batchActions: [{id, text, confirm?, successText?, run(keys)}]
        var actions = grid.option('batchActions') || [];
        var ed = grid.option('editing') || {};
        var batch = [{ id: '__viewSelected', text: '查看已选' }];
        if (grid.option('batchDelete') || ed.allowDeleting) { batch.push({ id: '__delete', text: '删除选中行' }); }
        actions.forEach(function (a) { batch.push({ id: a.id, text: a.text }); });
        items.push({
            location: 'after', widget: 'dxDropDownButton',
            options: {
                icon: 'selectall', hint: '批量操作（对勾选的行）', stylingMode: 'text', showArrowIcon: true, items: batch, displayExpr: 'text', keyExpr: 'id',
                useSelectMode: false, dropDownOptions: { width: 190 },
                itemTemplate: function (it) {
                    return $('<div></div>').text((it.id === '__viewSelected' ? (grid._selectedOnly ? '\u2713 ' : '\u3000') : '') + it.text);
                },
                onInitialized: function (a) { grid._batchDD = a.component; },
                onItemClick: function (a) {
                    var id = a.itemData.id;
                    if (id === '__viewSelected') { DxGrid.toggleSelectedOnly(grid); return; }
                    if (id === '__delete') { DxGrid.batchDelete(grid); return; }
                    var x = actions.filter(function (v) { return v.id === id; })[0];
                    if (x) { DxGrid.runBatchAction(grid, x); }
                }
            }
        });
        items.push(btn('revert', '重置：清除筛选、搜索、排序、分组和选中', function () { DxGrid.resetView(grid); }));
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
            { id: 'style', text: '表格外观（Grid 配置）' }
        ], function (id) {
            if (id === 'layout') { DxGrid.resetLayout(grid); }
            if (id === 'saveLayout') { DxGrid.saveLayout(grid); }
            if (id === 'loadLayout') { DxGrid.loadLayout(grid); }
            if (id === 'style' && typeof openAdminTab === 'function') { openAdminTab('/gridStyle', 'Grid 配置'); }
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
                title: '选择过滤器模板', width: 420, height: 'auto', maxHeight: '70%', showTitle: true, showCloseButton: true,
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
                title: '保存为模板', width: 380, height: 'auto', showTitle: true, showCloseButton: true, hideOnOutsideClick: false,
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
        var top = $el.length && $el.offset() ? $el.offset().top : 0;
        var bottom = 0;
        $el.parentsUntil('html').each(function () {
            var $p = $(this);
            bottom += (parseFloat($p.css('padding-bottom')) || 0) + (parseFloat($p.css('border-bottom-width')) || 0);
        });
        return Math.max(200, Math.floor($(window).height() - top - bottom));
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
    DxGrid.remoteStore = function (url, key) {
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
