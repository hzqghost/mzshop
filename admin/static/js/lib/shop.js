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
                if (k === 0 && rootText) { return root; }
                return call('GET', '/categories').then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, full_name: '(已删除 #' + k + ')' };
                });
            }
        });
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
                if (k === 0 && rootText) { return root; }
                return fetchAll().then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, name: '(已删除 #' + k + ')' };
                });
            }
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
                title: '多语言翻译 - ' + title, width: 720, height: '85%', showTitle: true, dragEnabled: true,
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
    var Shop = { call: call, categorySource: categorySource, leafCategorySource: leafCategorySource, brandSource: brandSource, money: money, openTranslate: openTranslate, translateButton: translateButton, langs: [] };
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
    Shop.skuGrid = function (el, goodsId) {
        return new DxGrid($('<div></div>').appendTo(el)[0], {
            dataSource: DxGrid.restStore('/api/v1/shop/goods/' + goodsId + '/skus', 'id'),
            keyExpr: 'id', height: 'auto', autoHeight: false, dxFeatures: false, searchPanel: { visible: false }, filterRow: { visible: false },
            editing: {
                mode: 'row', allowAdding: true, allowUpdating: true, allowDeleting: true, useIcons: true,
                texts: { addRow: '新增规格', editRow: '编辑', deleteRow: '删除', saveRowChanges: '保存', cancelRowChanges: '取消', confirmDeleteMessage: '确定删除该规格吗？' }
            },
            onInitNewRow: function (e) { e.data.status = true; e.data.stock = 0; },
            onRowInserted: function () { DevExpress.ui.notify('规格已新增（价格不填则取商品价）', 'success', 1800); Shop.notifyChanged('goods'); },
            onRowUpdated: function () { DevExpress.ui.notify('规格已保存', 'success', 1800); Shop.notifyChanged('goods'); },
            onRowRemoved: function () { DevExpress.ui.notify('规格已删除', 'success', 1800); Shop.notifyChanged('goods'); },
            columns: Shop.withLang([
                { dataField: 'sku_code', caption: 'SKU编码', width: 160, validationRules: [{ type: 'required', message: '请输入SKU编码' }] },
                { dataField: 'spec_name', caption: '规格（如 红色/XL）' },
                { dataField: 'cost_price', caption: '拿货价', dataType: 'number', width: 100, format: '#,##0.00', editorOptions: { min: 0, format: '#,##0.00' } },
                { dataField: 'sale_price', caption: '销售价', dataType: 'number', width: 100, format: '#,##0.00', editorOptions: { min: 0, format: '#,##0.00' } },
                { dataField: 'stock', caption: '库存', dataType: 'number', width: 90 },
                { dataField: 'status', caption: '启用', dataType: 'boolean', width: 80 },
                { type: 'buttons', width: 80, buttons: ['edit', 'delete'] }
            ], 'spec_name', Shop.langColumns('spec_name', '规格'))
        });
    };

    window.Shop = Shop;
})(jQuery);
