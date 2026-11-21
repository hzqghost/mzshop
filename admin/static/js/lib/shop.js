/** 商品管理页面共用：接口调用、分类下拉数据源。接口响应 {code, data, msg}。 */
(function ($) {
    'use strict';

    var BASE = '/api/v1/shop';

    function call(method, path, body) {
        return $.ajax({
            url: APP.HOST + BASE + path,
            method: method,
            contentType: 'application/json',
            data: body === undefined ? undefined : JSON.stringify(body)
        }).then(function (res) {
            if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
            return res.data;
        }, function (xhr) {
            if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
            return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
        });
    }

    /** 分类下拉数据源（展开时重新取，分类改了不会过期）；rootText 非空时前面加一个 id=0 的项（顶级 / 未分类 / 通用） */
    function categorySource(rootText) {
        var root = { id: 0, full_name: rootText };
        // 表格 lookup 只接受 Store / 数组，不接受 DataSource
        return new DevExpress.data.CustomStore({
            key: 'id',
            loadMode: 'raw',
            load: function () {
                return call('GET', '/categories').then(function (rows) {
                    return rootText ? [root].concat(rows) : rows;
                });
            },
            byKey: function (k) {
                if (k === 0 && rootText) { return root; }
                return call('GET', '/categories').then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, full_name: '(已删除 #' + k + ')' };
                });
            }
        });
    }

    /** 只含末级分类（没有子分类的）的下拉数据源，商品选分类用；byKey 仍能取到非末级的老值用于显示 */
    function leafCategorySource(rootText) {
        var root = { id: 0, full_name: rootText };
        return new DevExpress.data.CustomStore({
            key: 'id',
            loadMode: 'raw',
            load: function () {
                return call('GET', '/categories').then(function (rows) {
                    var parents = {};
                    rows.forEach(function (r) { parents[r.parent_id] = true; });
                    var leaves = rows.filter(function (r) { return !parents[r.id]; });
                    return rootText ? [root].concat(leaves) : leaves;
                });
            },
            byKey: function (k) {
                if (!k) { return rootText ? root : { id: 0, full_name: '' }; }
                return call('GET', '/categories').then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, full_name: '(已删除 #' + k + ')' };
                });
            }
        });
    }

    /** 通用商品分类单选弹窗；与分类多选弹窗保持相同的树形、查询和尺寸。 */
    function openCategoryPicker(options) {
        options = options || {};
        return call('GET', '/categories').then(function (source) {
            var rows = (source || []).map(function (r) {
                return $.extend({}, r, { query_name: r.name || r.full_name || ('#' + r.id) });
            });
            var kids = {}, chosenId = Number(options.value) || null, tab = 'pick', keyword = '', $win;
            rows.forEach(function (r) { (kids[r.parent_id || 0] = kids[r.parent_id || 0] || []).push(r); });
            var $host = $('<div></div>').appendTo(document.body);
            function radio(node, cls) {
                var $label = $('<label class="cat-pick-label"></label>').addClass(cls || '');
                $('<input type="radio" name="shop-category-single">').attr('data-id', node.id)
                    .prop('checked', chosenId === node.id).appendTo($label);
                $('<span></span>').text(node.query_name).attr('title', node.full_name || node.query_name).appendTo($label);
                return $label;
            }
            function renderTree($box) {
                $box.empty();
                function level(pid, $parent) {
                    (kids[pid] || []).forEach(function (node) {
                        var children = kids[node.id] || [];
                        var $group = $('<div class="cat-pick-group"></div>').appendTo($parent);
                        $('<div class="cat-pick-head"></div>').append(radio(node, 'cat-pick-parent')).appendTo($group);
                        if (children.length && children.every(function (c) { return !(kids[c.id] || []).length; })) {
                            var $items = $('<div class="cat-pick-items"></div>').appendTo($group);
                            children.forEach(function (c) { radio(c, 'cat-pick-item').appendTo($items); });
                        } else if (children.length) { level(node.id, $('<div class="cat-pick-sub"></div>').appendTo($group)); }
                    });
                }
                level(0, $box);
            }
            function renderSearch($box) {
                $box.empty();
                var q = keyword.trim().toLowerCase();
                if (!q) { $('<div class="cat-pick-empty">输入分类名称查询</div>').appendTo($box); return; }
                rows.filter(function (r) { return String(r.full_name || r.query_name).toLowerCase().indexOf(q) >= 0; })
                    .forEach(function (r) { radio(r, 'cat-pick-search-row').appendTo($box); });
            }
            function paint() {
                $win.find('.cat-pick-tab').removeClass('is-on').filter('[data-tab="' + tab + '"]').addClass('is-on');
                $win.find('.cat-pick-pane').hide().filter('[data-tab="' + tab + '"]').show();
                if (tab === 'pick') { renderTree($win.find('.cat-pick-pane[data-tab="pick"] .cat-pick-body')); }
                else { renderSearch($win.find('.cat-pick-pane[data-tab="search"] .cat-pick-body')); }
                var selected = rows.filter(function (r) { return r.id === chosenId; })[0];
                $win.find('.cat-pick-count').text(selected ? '已选 ' + (selected.full_name || selected.query_name) : '未选择');
            }
            var popup = $host.dxPopup({
                title: options.title || '选择分类（单选）', width: '90%', height: '80%', showTitle: true,
                showCloseButton: true, dragEnabled: true, hideOnOutsideClick: false,
                contentTemplate: function (content) {
                    $win = $('<div class="cat-pick"></div>').appendTo(content);
                    var $tabs = $('<div class="cat-pick-tabs"></div>').appendTo($win);
                    $('<button class="cat-pick-tab is-on" data-tab="pick">选择分类</button>').on('click', function () { tab = 'pick'; paint(); }).appendTo($tabs);
                    $('<button class="cat-pick-tab" data-tab="search">查询分类</button>').on('click', function () { tab = 'search'; paint(); }).appendTo($tabs);
                    $('<div class="cat-pick-bar"><span class="cat-pick-count"></span></div>').appendTo($win);
                    $('<div class="cat-pick-pane" data-tab="pick"><div class="cat-pick-body"></div></div>').appendTo($win);
                    var $search = $('<div class="cat-pick-pane" data-tab="search" style="display:none"><div class="cat-pick-q"></div><div class="cat-pick-body"></div></div>').appendTo($win);
                    $('<input class="cat-pick-input" placeholder="输入分类名称查询">').on('input', function () {
                        keyword = this.value; renderSearch($search.find('.cat-pick-body'));
                    }).appendTo($search.find('.cat-pick-q'));
                    $win.on('change', 'input[data-id]', function () { chosenId = Number($(this).attr('data-id')); paint(); });
                    paint();
                },
                toolbarItems: [
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '保存', type: 'default', onClick: function () {
                        if (!chosenId) { DevExpress.ui.notify('请选择分类', 'warning', 1800); return; }
                        var selected = rows.filter(function (r) { return r.id === chosenId; })[0];
                        if (options.onSelected) { options.onSelected(selected); }
                        popup.hide();
                    } } },
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '取消', onClick: function () { popup.hide(); } } }
                ],
                onHidden: function () { $host.remove(); }
            }).dxPopup('instance');
            popup.show();
            return popup;
        }, function (msg) { DevExpress.ui.notify(String(msg), 'error', 2500); });
    }

    /** 业务工具栏公共「分类查询」：左侧固定树形面板 + 店铺绑定分类同款多选弹窗。 */
    function categoryQueryItem(options) {
        options = options || {};
        var field = options.field || 'category_id';
        var title = options.text || '分类';
        var selectedIds = [];
        var rowsCache = null;
        var $side = null;
        var sideTree = null;
        function grid() { return typeof options.getGrid === 'function' ? options.getGrid() : options.grid; }
        function apply(ids) {
            selectedIds = (ids || []).map(Number).filter(Boolean);
            var g = grid();
            if (g) { g.columnOption(field, 'filterValues', selectedIds.length ? selectedIds : null); }
            if (options.onChanged) { options.onChanged(selectedIds.slice()); }
        }
        function loadTree() {
            if (rowsCache) { return $.Deferred().resolve(rowsCache).promise(); }
            return call('GET', '/categories').then(function (rows) {
                rowsCache = (rows || []).map(function (r) { return $.extend({}, r, { query_name: r.name || r.full_name || ('#' + r.id) }); });
                return rowsCache;
            });
        }
        function treeMaps(rows) {
            var kids = {};
            rows.forEach(function (r) { (kids[r.parent_id || 0] = kids[r.parent_id || 0] || []).push(r); });
            function descendants(id) {
                var out = [];
                (kids[id] || []).forEach(function (ch) { out.push(ch.id); out = out.concat(descendants(ch.id)); });
                return out;
            }
            return { kids: kids, descendants: descendants };
        }
        function closeSide() {
            if (!$side) { return; }
            var $page = $side.parent();
            $side.remove(); $side = null; sideTree = null;
            $page.removeClass('dxgrid-category-layout');
            var g = grid(); if (g) { DxGrid.syncAutoHeight(g); }
        }
        function openMulti(rows) {
            var maps = treeMaps(rows);
            var chosen = {};
            selectedIds.forEach(function (id) { chosen[id] = true; });
            var tab = 'pick', keyword = '', $win;
            var $host = $('<div></div>').appendTo(document.body);
            function ids() { return Object.keys(chosen).filter(function (k) { return chosen[k]; }).map(Number); }
            function setNode(id, on) { if (on) { chosen[id] = true; } else { delete chosen[id]; } maps.descendants(id).forEach(function (x) { if (on) { chosen[x] = true; } else { delete chosen[x]; } }); }
            function checkbox(node, cls) {
                var $label = $('<label class="cat-pick-label"></label>').addClass(cls || '');
                $('<input type="checkbox">').attr('data-id', node.id).prop('checked', !!chosen[node.id]).appendTo($label);
                $('<span></span>').text(node.query_name).attr('title', node.full_name || node.query_name).appendTo($label);
                return $label;
            }
            function renderTree($box) {
                $box.empty();
                function level(pid, $parent) {
                    (maps.kids[pid] || []).forEach(function (node) {
                        var children = maps.kids[node.id] || [];
                        var $group = $('<div class="cat-pick-group"></div>').appendTo($parent);
                        $('<div class="cat-pick-head"></div>').append(checkbox(node, 'cat-pick-parent')).appendTo($group);
                        if (children.length && children.every(function (c) { return !(maps.kids[c.id] || []).length; })) {
                            var $items = $('<div class="cat-pick-items"></div>').appendTo($group);
                            children.forEach(function (c) { checkbox(c, 'cat-pick-item').appendTo($items); });
                        } else if (children.length) { level(node.id, $('<div class="cat-pick-sub"></div>').appendTo($group)); }
                    });
                }
                level(0, $box);
            }
            function renderSearch($box) {
                $box.empty();
                var q = keyword.trim().toLowerCase();
                if (!q) { $('<div class="cat-pick-empty">输入分类名称查询</div>').appendTo($box); return; }
                rows.filter(function (r) { return String(r.full_name || r.query_name).toLowerCase().indexOf(q) >= 0; })
                    .forEach(function (r) { checkbox(r, 'cat-pick-search-row').appendTo($box); });
            }
            function paint() {
                $win.find('.cat-pick-tab').removeClass('is-on').filter('[data-tab="' + tab + '"]').addClass('is-on');
                $win.find('.cat-pick-pane').hide().filter('[data-tab="' + tab + '"]').show();
                if (tab === 'pick') { renderTree($win.find('.cat-pick-pane[data-tab="pick"] .cat-pick-body')); }
                else { renderSearch($win.find('.cat-pick-pane[data-tab="search"] .cat-pick-body')); }
                $win.find('.cat-pick-count').text('已选 ' + ids().length);
            }
            var popup = $host.dxPopup({
                title: '选择分类（可多选）', width: '90%', height: '80%', showTitle: true, showCloseButton: true, dragEnabled: true, hideOnOutsideClick: false,
                contentTemplate: function (content) {
                    $win = $('<div class="cat-pick"></div>').appendTo(content);
                    var $tabs = $('<div class="cat-pick-tabs"></div>').appendTo($win);
                    $('<button class="cat-pick-tab is-on" data-tab="pick">选择分类</button>').on('click', function () { tab = 'pick'; paint(); }).appendTo($tabs);
                    $('<button class="cat-pick-tab" data-tab="search">查询分类</button>').on('click', function () { tab = 'search'; paint(); }).appendTo($tabs);
                    var $bar = $('<div class="cat-pick-bar"></div>').appendTo($win);
                    $('<button class="cat-pick-all">全选/全不选</button>').on('click', function () {
                        var all = rows.every(function (r) { return chosen[r.id]; });
                        rows.forEach(function (r) { if (all) { delete chosen[r.id]; } else { chosen[r.id] = true; } }); paint();
                    }).appendTo($bar);
                    $('<span class="cat-pick-count"></span>').appendTo($bar);
                    $('<div class="cat-pick-pane" data-tab="pick"><div class="cat-pick-body"></div></div>').appendTo($win);
                    var $search = $('<div class="cat-pick-pane" data-tab="search" style="display:none"><div class="cat-pick-q"></div><div class="cat-pick-body"></div></div>').appendTo($win);
                    $('<input class="cat-pick-input" placeholder="输入分类名称查询">').on('input', function () { keyword = this.value; renderSearch($search.find('.cat-pick-body')); }).appendTo($search.find('.cat-pick-q'));
                    $win.on('change', 'input[data-id]', function () { setNode(Number($(this).attr('data-id')), this.checked); paint(); });
                    paint();
                },
                toolbarItems: [
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '保存', type: 'default', stylingMode: 'contained', onClick: function () { apply(ids()); popup.hide(); } } },
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '取消', onClick: function () { popup.hide(); } } }
                ],
                onHidden: function () { $host.remove(); }
            }).dxPopup('instance');
            popup.show();
        }
        function openSide(rows, $button) {
            var g = grid(), maps = treeMaps(rows);
            var $page = $(g.element()).closest('.page-pad');
            $page.addClass('dxgrid-category-layout');
            $side = $('<aside class="shop-category-side"></aside>').prependTo($page);
            var $head = $('<div class="shop-category-side-head"></div>').appendTo($side);
            $('<a href="javascript:void(0)">全部分类</a>').on('click', function () { apply([]); if (sideTree) { sideTree.unselectAll(); } }).appendTo($head);
            $('<a href="javascript:void(0)">多选</a>').on('click', function () { openMulti(rows); }).appendTo($head);
            sideTree = $('<div class="shop-category-side-tree"></div>').appendTo($side).dxTreeView({
                dataSource: rows, dataStructure: 'plain', keyExpr: 'id', parentIdExpr: 'parent_id', rootValue: 0,
                displayExpr: 'query_name', selectionMode: 'single', selectByClick: true, searchEnabled: true,
                searchEditorOptions: { placeholder: '搜索' }, onItemClick: function (e) { apply([e.itemData.id].concat(maps.descendants(e.itemData.id))); }
            }).dxTreeView('instance');
            DxGrid.syncAutoHeight(g);
        }
        return {
            template: function (_, __, element) {
                var resetRegistered = false;
                var $button = $('<div class="shop-category-query"></div>').appendTo(element).dxButton({
                    text: title, icon: 'hierarchy', stylingMode: 'text', onClick: function () {
                        var g = grid();
                        if (g && !resetRegistered) {
                            g._businessQueryResetters = g._businessQueryResetters || [];
                            g._businessQueryResetters.push(function () { selectedIds = []; if (sideTree) { sideTree.unselectAll(); } });
                            resetRegistered = true;
                        }
                        if ($side) { closeSide(); return; }
                        loadTree().then(function (rows) { openSide(rows, $button); }, function (msg) { DevExpress.ui.notify(String(msg), 'error', 2500); });
                    }
                });
            }
        };
    }

    /** 业务工具栏公共「店铺查询」：多选店铺后由页面把 ID 交给服务端查询参数。 */
    function storeQueryItem(options) {
        options = options || {};
        var title = options.text || '店铺';
        var selectedIds = [];
        var rowsCache = null;
        var button = null;
        function grid() { return typeof options.getGrid === 'function' ? options.getGrid() : options.grid; }
        function apply(ids) {
            selectedIds = (ids || []).map(Number).filter(Boolean);
            if (button) { button.option('text', selectedIds.length ? title + ' (' + selectedIds.length + ')' : title); }
            if (options.onChanged) { options.onChanged(selectedIds.slice()); }
        }
        function loadStores() {
            if (rowsCache) { return $.Deferred().resolve(rowsCache).promise(); }
            return $.ajax({ url: APP.HOST + '/api/v1/stores', method: 'GET' }).then(function (res) {
                if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
                rowsCache = res.data || [];
                return rowsCache;
            }, function (xhr) {
                if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
                return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
            });
        }
        function openMulti(rows) {
            var chosen = {}, tab = 'pick', keyword = '', $win;
            selectedIds.forEach(function (id) { chosen[id] = true; });
            var $host = $('<div></div>').appendTo(document.body);
            function ids() { return Object.keys(chosen).filter(function (k) { return chosen[k]; }).map(Number); }
            function label(row, cls) {
                var text = row.code + (row.name && row.name !== row.code ? ' · ' + row.name : '');
                var $label = $('<label class="cat-pick-label"></label>').addClass(cls || '');
                $('<input type="checkbox">').attr('data-id', row.id).prop('checked', !!chosen[row.id]).appendTo($label);
                $('<span></span>').text(text).attr('title', text).appendTo($label);
                return $label;
            }
            function renderPick($box) {
                $box.empty();
                var groups = {};
                rows.forEach(function (row) { (groups[row.platform_name || '其他平台'] = groups[row.platform_name || '其他平台'] || []).push(row); });
                Object.keys(groups).forEach(function (name) {
                    var $group = $('<div class="cat-pick-group"></div>').appendTo($box);
                    $('<div class="cat-pick-head"></div>').text(name).appendTo($group);
                    var $items = $('<div class="cat-pick-items"></div>').appendTo($group);
                    groups[name].forEach(function (row) { label(row, 'cat-pick-item').appendTo($items); });
                });
            }
            function renderSearch($box) {
                $box.empty();
                var q = keyword.trim().toLowerCase();
                if (!q) { $('<div class="cat-pick-empty">输入店铺编码或名称查询</div>').appendTo($box); return; }
                rows.filter(function (r) {
                    return [r.code, r.name, r.name_en, r.platform_name].join(' ').toLowerCase().indexOf(q) >= 0;
                }).forEach(function (row) { label(row, 'cat-pick-search-row').appendTo($box); });
            }
            function paint() {
                $win.find('.cat-pick-tab').removeClass('is-on').filter('[data-tab="' + tab + '"]').addClass('is-on');
                $win.find('.cat-pick-pane').hide().filter('[data-tab="' + tab + '"]').show();
                if (tab === 'pick') { renderPick($win.find('.cat-pick-pane[data-tab="pick"] .cat-pick-body')); }
                else { renderSearch($win.find('.cat-pick-pane[data-tab="search"] .cat-pick-body')); }
                $win.find('.cat-pick-count').text('已选 ' + ids().length);
            }
            var popup = $host.dxPopup({
                title: '选择店铺（可多选）', width: '90%', height: '80%', showTitle: true, showCloseButton: true,
                dragEnabled: true, hideOnOutsideClick: false,
                contentTemplate: function (content) {
                    $win = $('<div class="cat-pick"></div>').appendTo(content);
                    var $tabs = $('<div class="cat-pick-tabs"></div>').appendTo($win);
                    $('<button class="cat-pick-tab is-on" data-tab="pick">选择店铺</button>').on('click', function () { tab = 'pick'; paint(); }).appendTo($tabs);
                    $('<button class="cat-pick-tab" data-tab="search">查询店铺</button>').on('click', function () { tab = 'search'; paint(); }).appendTo($tabs);
                    var $bar = $('<div class="cat-pick-bar"></div>').appendTo($win);
                    $('<button class="cat-pick-all">全选/全不选</button>').on('click', function () {
                        var all = rows.length && rows.every(function (r) { return chosen[r.id]; });
                        rows.forEach(function (r) { if (all) { delete chosen[r.id]; } else { chosen[r.id] = true; } });
                        paint();
                    }).appendTo($bar);
                    $('<span class="cat-pick-count"></span>').appendTo($bar);
                    $('<div class="cat-pick-pane" data-tab="pick"><div class="cat-pick-body"></div></div>').appendTo($win);
                    var $search = $('<div class="cat-pick-pane" data-tab="search" style="display:none"><div class="cat-pick-q"></div><div class="cat-pick-body"></div></div>').appendTo($win);
                    $('<input class="cat-pick-input" placeholder="输入店铺编码或名称查询">').on('input', function () {
                        keyword = this.value; renderSearch($search.find('.cat-pick-body'));
                    }).appendTo($search.find('.cat-pick-q'));
                    $win.on('change', 'input[data-id]', function () { if (this.checked) { chosen[this.dataset.id] = true; } else { delete chosen[this.dataset.id]; } paint(); });
                    paint();
                },
                toolbarItems: [
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '保存', type: 'default', stylingMode: 'contained', onClick: function () { apply(ids()); popup.hide(); } } },
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '取消', onClick: function () { popup.hide(); } } }
                ],
                onHidden: function () { $host.remove(); }
            }).dxPopup('instance');
            popup.show();
        }
        return {
            template: function (_, __, element) {
                var resetRegistered = false;
                button = $('<div class="shop-store-query"></div>').appendTo(element).dxButton({
                    text: title, icon: 'home', stylingMode: 'text', onClick: function () {
                        var g = grid();
                        if (g && !resetRegistered) {
                            g._businessQueryResetters = g._businessQueryResetters || [];
                            g._businessQueryResetters.push(function () { if (selectedIds.length) { apply([]); } });
                            resetRegistered = true;
                        }
                        loadStores().then(openMulti, function (msg) { DevExpress.ui.notify(String(msg), 'error', 2500); });
                    }
                }).dxButton('instance');
            }
        };
    }

    /** 品牌下拉数据源（品牌管理里的品牌，只列启用的；停用 / 已删除的老值仍能按 id 显示） */
    function brandSource(rootText) {
        var root = { id: 0, name: rootText };

        function fetchAll() {
            return $.ajax({ url: APP.HOST + '/api/v1/brands', method: 'GET' }).then(function (res) {
                if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
                return res.data;
            }, function (xhr) {
                if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
                return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
            });
        }

        return new DevExpress.data.CustomStore({
            key: 'id',
            loadMode: 'raw',
            load: function () {
                return fetchAll().then(function (rows) {
                    var enabled = rows.filter(function (r) { return r.status; });
                    return rootText ? [root].concat(enabled) : enabled;
                });
            },
            byKey: function (k) {
                if (!k) { return rootText ? root : { id: 0, name: '' }; }
                return fetchAll().then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, name: '(已删除 #' + k + ')' };
                });
            }
        });
    }

    /** 供应商下拉（产品池 / 供应商档案，只列启用的；停用 / 已删除的老值仍能按 id 显示） */
    function supplierSource(rootText) {
        var root = { id: 0, name: rootText };

        function fetchAll() {
            return $.ajax({ url: APP.HOST + '/api/v1/supplier-catalog/suppliers', method: 'GET' }).then(function (res) {
                if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
                return res.data;
            }, function (xhr) {
                if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
                return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
            });
        }

        return new DevExpress.data.CustomStore({
            key: 'id',
            loadMode: 'raw',
            load: function () {
                return fetchAll().then(function (rows) {
                    var enabled = rows.filter(function (r) { return r.status; });
                    return rootText ? [root].concat(enabled) : enabled;
                });
            },
            byKey: function (k) {
                if (!k) { return rootText ? root : { id: 0, name: '' }; }
                return fetchAll().then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, name: '(已删除 #' + k + ')' };
                });
            }
        });
    }

    /** 包装组下拉：SKU 的 0 表示继续继承商品/店铺。 */
    function packageGroupSource(rootText) {
        var root = { id: 0, name: rootText || '继承上级' };
        function fetchAll() {
            return $.ajax({ url: APP.HOST + '/api/v1/shipping-packages/groups', method: 'GET' }).then(function (res) {
                if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
                return res.data || [];
            });
        }
        return new DevExpress.data.CustomStore({ key: 'id', loadMode: 'raw',
            load: function () { return fetchAll().then(function (rows) { return [root].concat(rows.filter(function (r) { return r.status; })); }); },
            byKey: function (k) { if (!k) { return root; } return fetchAll().then(function (rows) {
                return rows.filter(function (r) { return r.id === k; })[0] || { id: k, name: '(已删除 #' + k + ')' };
            }); }
        });
    }

    /**
     * 多语言翻译弹窗：每种非默认语言一个页签，逐字段录入译文；默认语言的原文显示在每个输入框上方。
     * entityType: category / attribute / goods / sku；译文留空表示删除该译文（读取时回退默认语言）。
     */
    function openTranslate(entityType, id, title) {
        call('GET', '/i18n/' + entityType + '/' + id).then(function (info) {
            if (!info.languages.length) {
                DevExpress.ui.notify('还没有其他语言，请先到「商品语言」里添加', 'warning', 2500);
                return;
            }
            var state = $.extend(true, {}, info.translations);
            info.languages.forEach(function (l) { state[l.code] = state[l.code] || {}; });
            var $el = $('<div></div>').appendTo(document.body);
            var popup = $el.dxPopup({
                title: '多语言翻译 - ' + title, width: '90%', maxWidth: 720, height: '85%', showTitle: true, dragEnabled: true,
                hideOnOutsideClick: false, showCloseButton: true,
                toolbarItems: [
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '保存', type: 'default', stylingMode: 'contained', onClick: save } },
                    { toolbar: 'bottom', location: 'after', widget: 'dxButton', options: { text: '取消', onClick: function () { popup.hide(); } } }
                ],
                contentTemplate: function (content) {
                    $('<div></div>').appendTo(content).dxTabPanel({
                        height: '100%', animationEnabled: false, deferRendering: false,
                        dataSource: info.languages,
                        itemTitleTemplate: function (l) { return l.name + ' (' + l.code + ')'; },
                        itemTemplate: function (l, _, el) { $(el).append(langForm(l.code)); }
                    });
                },
                onHidden: function () { $el.remove(); }
            }).dxPopup('instance');
            popup.show();

            function hint($p, text) {
                $('<div class="i18n-default"></div>').text('默认：' + (text === '' || text === undefined ? '（空）' : text)).appendTo($p);
            }

            function langForm(code) {
                var $wrap = $('<div class="i18n-form"></div>');
                var st = state[code];
                info.fields.forEach(function (f) {
                    var def = info.defaults[f.field];
                    var $row = $('<div class="i18n-row"></div>').appendTo($wrap);
                    $('<div class="i18n-label"></div>').text(f.label).appendTo($row);
                    if (f.kind === 'text' || f.kind === 'textarea') {
                        hint($row, def);
                        var ed = f.kind === 'text' ? 'dxTextBox' : 'dxTextArea';
                        var opt = { value: st[f.field] || '', width: '100%', onValueChanged: function (e) { st[f.field] = e.value || ''; } };
                        if (f.kind === 'textarea') { opt.minHeight = 120; opt.autoResizeEnabled = true; }
                        $('<div></div>').appendTo($row)[ed](opt);
                    } else {
                        var keys = f.kind === 'list' ? def.map(function (_, i) { return i; }) : Object.keys(def);
                        if (!keys.length) { $('<div class="muted"></div>').text('（默认语言下没有内容）').appendTo($row); }
                        var cur = st[f.field] || (f.kind === 'list' ? [] : {});
                        st[f.field] = cur;
                        keys.forEach(function (k) {
                            var $line = $('<div class="i18n-line"></div>').appendTo($row);
                            $('<div class="i18n-key"></div>').text(f.kind === 'list' ? def[k] : (k + '：' + def[k])).appendTo($line);
                            $('<div></div>').appendTo($line).dxTextBox({
                                value: cur[k] || '', width: '100%',
                                onValueChanged: function (e) { cur[k] = e.value || ''; }
                            });
                        });
                    }
                });
                return $wrap;
            }

            function save() {
                // list 字段补齐长度，保证与默认语言一一对应
                info.languages.forEach(function (l) {
                    info.fields.forEach(function (f) {
                        if (f.kind === 'list') {
                            var cur = state[l.code][f.field] || [];
                            state[l.code][f.field] = info.defaults[f.field].map(function (_, i) { return cur[i] || ''; });
                        }
                    });
                });
                call('PUT', '/i18n/' + entityType + '/' + id, { translations: state }).then(function () {
                    popup.hide();
                    DevExpress.ui.notify('译文已保存', 'success', 1800);
                }, function (msg) { DevExpress.ui.notify(String(msg), 'error', 3000); });
            }
        }, function (msg) { DevExpress.ui.notify(String(msg), 'error', 3000); });
    }

    /** 表格「翻译」按钮定义，加进 columns 的 buttons 数组 */
    function translateButton(entityType, titleOf) {
        return { text: '翻译', onClick: function (e) { openTranslate(entityType, e.row.data.id, titleOf(e.row.data)); } };
    }

    function money(v) { return v === null || v === undefined ? '' : Number(v).toFixed(2); }

    /**
     * 列表和表单里直接显示的语言 = 启用的非默认语言（默认语言就是各字段本身）。
     * 页面要等 Shop.ready.then(...) 再建表格，这样才知道有哪些语言列。
     */
    /**
     * 分类 / 品牌 / 供应商表单编辑器：dxLookup 带搜索。页面把返回值放进 editorOptions，editorType 用 'dxLookup'。
     */
    function dictLookup(opts) {
        return $.extend({
            valueExpr: 'id',
            searchEnabled: true,
            searchPlaceholder: '搜索',
            showCancelButton: true,
            cancelButtonText: '取消',
            dropDownCentered: false
        }, opts);
    }

    var Shop = { call: call, categorySource: categorySource, leafCategorySource: leafCategorySource, openCategoryPicker: openCategoryPicker, categoryQueryItem: categoryQueryItem, storeQueryItem: storeQueryItem, brandSource: brandSource, supplierSource: supplierSource, packageGroupSource: packageGroupSource, dictLookup: dictLookup, money: money, openTranslate: openTranslate, translateButton: translateButton, langs: [] };
    Shop.ready = call('GET', '/languages').then(function (rows) {
        Shop.langs = rows.filter(function (l) { return !l.is_default && l.status; });
    }, function () { Shop.langs = []; });

    /** 每种语言一列：数据在 row.i18n[code][field]，编辑弹窗里随行一起提交。extra 会合并进每一列 */
    Shop.langColumns = function (field, caption, extra) {
        return Shop.langs.map(function (l) {
            return $.extend({ dataField: 'i18n.' + l.code + '.' + field, caption: caption + ' (' + l.code + ')', minWidth: 140 }, extra);
        });
    };

    /** 把语言列插到 dataField 为 afterField 的列后面，返回新的 columns 数组 */
    Shop.withLang = function (columns, afterField, langCols) {
        var out = columns.slice();
        var i = out.findIndex(function (c) { return c.dataField === afterField; });
        out.splice(i < 0 ? out.length : i + 1, 0, ...langCols);
        return out;
    };

    /** 给「表单 items 字符串数组」用的语言项（和 langColumns 的 dataField 一致） */
    Shop.langItems = function (field) {
        return Shop.langs.map(function (l) { return 'i18n.' + l.code + '.' + field; });
    };

    /** 新建行时的空译文：{en: {name: ''}} */
    Shop.blankI18n = function (fields) {
        var o = {};
        Shop.langs.forEach(function (l) {
            o[l.code] = {};
            fields.forEach(function (f) { o[l.code][f] = f === 'attr_values' ? {} : ''; });
        });
        return o;
    };

    /** 商品标签页和列表标签页之间的通知（同源 iframe 之间用 BroadcastChannel）：编辑页保存后列表刷新 */
    var channel = window.BroadcastChannel ? new BroadcastChannel('mzshop-shop') : null;
    Shop.notifyChanged = function (kind) { if (channel) { channel.postMessage({ kind: kind }); } };
    Shop.onChanged = function (kind, cb) {
        if (channel) { channel.addEventListener('message', function (e) { if (e.data && e.data.kind === kind) { cb(); } }); }
    };

    /** 商品的 SKU 明细表（行内编辑）；列表的展开行和商品编辑页共用 */
    Shop.skuGrid = function (el, goodsId, options) {
        options = options || {};
        return new DxGrid($('<div></div>').appendTo(el)[0], {
            dataSource: DxGrid.restStore('/api/v1/shop/goods/' + goodsId + '/skus', 'id'),
            keyExpr: 'id', height: 'auto', autoHeight: false, dxFeatures: false, searchPanel: { visible: false }, filterRow: { visible: false },
            paging: { enabled: !options.hidePager },
            pager: { visible: !options.hidePager },
            editing: {
                mode: 'row', allowAdding: true, allowUpdating: true, allowDeleting: true, useIcons: true,
                texts: { addRow: '新增规格', editRow: '编辑', deleteRow: '删除', saveRowChanges: '保存', cancelRowChanges: '取消', confirmDeleteMessage: '确定删除该规格吗？' }
            },
            onInitNewRow: function (e) { e.data.status = true; },
            onRowInserted: function () { DevExpress.ui.notify('规格已新增', 'success', 1800); Shop.notifyChanged('goods'); if (options.onChanged) { options.onChanged(); } },
            onRowUpdated: function () { DevExpress.ui.notify('规格已保存', 'success', 1800); Shop.notifyChanged('goods'); if (options.onChanged) { options.onChanged(); } },
            onRowRemoved: function () { DevExpress.ui.notify('规格已删除', 'success', 1800); Shop.notifyChanged('goods'); if (options.onChanged) { options.onChanged(); } },
            onToolbarPreparing: function (e) {
                e.toolbarOptions.items.unshift({
                    location: 'before', widget: 'dxButton',
                    options: { text: '创建默认 SKU', icon: 'add', hint: '单规格商品使用商品编码创建默认 SKU，库存请到库存管理维护',
                        onClick: function () {
                            Shop.call('POST', '/goods/' + goodsId + '/skus/default', {}).then(function () {
                                DevExpress.ui.notify('默认 SKU 已创建，请到库存管理维护库存', 'success', 2200);
                                e.component.refresh(); Shop.notifyChanged('goods'); if (options.onChanged) { options.onChanged(); }
                            }, function (msg) { DevExpress.ui.notify(String(msg), 'error', 3000); });
                        }
                    }
                });
            },
            columns: Shop.withLang([
                { dataField: 'sku_code', caption: 'SKU编码', width: 160, validationRules: [{ type: 'required', message: '请输入SKU编码' }] },
                { dataField: 'spec_name', caption: '规格（如 红色/XL）' },
                { dataField: 'weight_g', caption: '重量(g)', dataType: 'number', width: 100,
                  editorOptions: { min: 1 }, headerCellTemplate: function (el) {
                      $('<span title="留空时继承商品重量；按重量模板要求两者至少填写一处">重量(g)</span>').appendTo(el);
                  } },
                { dataField: 'shipping_package_group_id', caption: '包装组', minWidth: 130,
                  lookup: { dataSource: packageGroupSource('继承商品/店铺'), valueExpr: 'id', displayExpr: 'name' } },
                { dataField: 'cost_price', caption: '拿货价', dataType: 'number', width: 100, format: '#,##0.00', editorOptions: { min: 0, format: '#,##0.00' } },
                { dataField: 'sku_type', caption: '类型', width: 90, allowEditing: false,
                  lookup: { dataSource: [{ value: 'normal', text: '普通' }, { value: 'bundle', text: '组合父 SKU' }], valueExpr: 'value', displayExpr: 'text' } },
                { dataField: 'status', caption: '启用', dataType: 'boolean', width: 80 },
                { type: 'buttons', width: 80, buttons: ['edit', 'delete'] }
            ], 'spec_name', Shop.langColumns('spec_name', '规格'))
        });
    };

    /** SKU 在不同区域的价格覆盖；没有记录时继承商品区域基础价。 */
    Shop.skuRegionPriceGrid = function (el, goodsId, regions, options) {
        options = options || {};
        var $host = $('<div></div>').appendTo(el);
        return Shop.call('GET', '/goods/' + goodsId + '/skus').then(function (skus) {
            if (!(skus || []).length) {
                $('<div class="muted"></div>').text('请先在“规格（SKU）”中新增 SKU，再维护区域价格覆盖。').appendTo($host);
                return null;
            }
            var baseStore = DxGrid.restStore('/api/v1/shop/goods/' + goodsId + '/sku-region-prices', 'id');
            var store = new DevExpress.data.CustomStore({
                key: 'id',
                load: function () { return baseStore.load().then(function (rows) {
                    return options.regionId ? rows.filter(function (r) { return r.region_id === options.regionId; }) : rows;
                }); },
                insert: function (values) {
                    if (options.regionId) { values.region_id = options.regionId; }
                    return baseStore.insert(values);
                },
                update: function (key, values) { return baseStore.update(key, values); },
                remove: function (key) { return baseStore.remove(key); }
            });
            return new DxGrid($('<div></div>').appendTo($host)[0], {
                dataSource: store,
                keyExpr: 'id', height: 'auto', autoHeight: false, dxFeatures: false,
                searchPanel: { visible: false }, filterRow: { visible: false }, headerFilter: { visible: false },
                paging: { enabled: false }, noDataText: '未设置差异价，所有 SKU 继承区域统一价格',
                editing: {
                    mode: 'row', allowAdding: true, allowUpdating: true, allowDeleting: true, useIcons: true,
                    texts: { addRow: '新增规格差异价', editRow: '编辑', deleteRow: '删除', saveRowChanges: '保存',
                        cancelRowChanges: '取消', confirmDeleteMessage: '删除后该 SKU 将继承区域统一价格，确定删除吗？' }
                },
                onInitNewRow: function (e) { if (options.regionId) { e.data.region_id = options.regionId; } },
                onRowInserted: function () { DevExpress.ui.notify('SKU 区域价格已新增', 'success', 1800); },
                onRowUpdated: function () { DevExpress.ui.notify('SKU 区域价格已保存', 'success', 1800); },
                onRowRemoved: function () { DevExpress.ui.notify('SKU 已恢复继承区域统一价格', 'success', 1800); },
                columns: [
                    { dataField: 'sku_id', caption: 'SKU / 规格', minWidth: 210,
                      lookup: { dataSource: skus, valueExpr: 'id', displayExpr: function (x) { return x ? x.sku_code + (x.spec_name ? ' · ' + x.spec_name : '') : ''; } },
                      validationRules: [{ type: 'required', message: '请选择 SKU' }] },
                    { dataField: 'region_id', caption: '区域', width: 140, allowEditing: !options.regionId, visible: !options.regionId,
                      lookup: { dataSource: regions || [], valueExpr: 'id', displayExpr: 'name' },
                      validationRules: [{ type: 'required', message: '请选择区域' }] },
                    { dataField: 'price', caption: '销售价', dataType: 'number', format: '#,##0.00', width: 105, editorOptions: { min: 0, format: '#,##0.00' } },
                    { dataField: 'suggested_price', caption: '建议售价', dataType: 'number', format: '#,##0.00', width: 105, editorOptions: { min: 0, format: '#,##0.00' } },
                    { dataField: 'min_price', caption: '最低售价', dataType: 'number', format: '#,##0.00', width: 105, editorOptions: { min: 0, format: '#,##0.00' } },
                    { dataField: 'max_price', caption: '最高售价', dataType: 'number', format: '#,##0.00', width: 105, editorOptions: { min: 0, format: '#,##0.00' } },
                    { type: 'buttons', width: 80, buttons: ['edit', 'delete'] }
                ]
            });
        }, function (msg) {
            $('<div class="muted"></div>').text('SKU 加载失败：' + msg).appendTo($host);
            return null;
        });
    };

    window.Shop = Shop;
})(jQuery);
