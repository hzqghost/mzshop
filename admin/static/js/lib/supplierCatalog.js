/** 供应商产品目录共用：接口调用、供应商/品牌下拉数据源、状态字典、Excel 导入向导。接口响应 {code, data, msg}。 */
(function ($) {
    'use strict';

    var BASE = '/api/v1/supplier-catalog';

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

    function upload(path, formData) {
        return $.ajax({
            url: APP.HOST + BASE + path,
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false
        }).then(function (res) {
            if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
            return res.data;
        }, function (xhr) {
            if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
            return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
        });
    }

    function apiGet(url) {
        return $.ajax({ url: APP.HOST + url, method: 'GET' }).then(function (res) {
            if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
            return res.data;
        }, function (xhr) {
            if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
            return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
        });
    }

    function supplierSource() {
        return new DevExpress.data.CustomStore({
            key: 'id',
            loadMode: 'raw',
            load: function () { return call('GET', '/suppliers'); },
            byKey: function (k) {
                return call('GET', '/suppliers').then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, name: '(已删除 #' + k + ')' };
                });
            }
        });
    }

    function brandSource(rootText) {
        var root = { id: 0, name: rootText };
        return new DevExpress.data.CustomStore({
            key: 'id',
            loadMode: 'raw',
            load: function () {
                return apiGet('/api/v1/brands').then(function (rows) {
                    return rootText ? [root].concat(rows) : rows;
                });
            },
            byKey: function (k) {
                if (k === 0 && rootText) { return root; }
                return apiGet('/api/v1/brands').then(function (rows) {
                    return rows.filter(function (r) { return r.id === k; })[0] || { id: k, name: '(已删除 #' + k + ')' };
                });
            }
        });
    }

    function currencySource() {
        return new DevExpress.data.CustomStore({
            key: 'code',
            loadMode: 'raw',
            cacheRawData: false,
            load: function () { return apiGet('/api/v1/attrs/options?code=currency'); },
            byKey: function (k) {
                if (!k) { return { code: '', label: '' }; }
                return apiGet('/api/v1/attrs/options?code=currency').then(function (rows) {
                    return rows.filter(function (r) { return r.code === k; })[0] || { code: k, label: k + '（未在币种中）' };
                });
            }
        });
    }

    var STATUSES = [
        { value: 0, text: '待核对' }, { value: 1, text: '已核对' },
        { value: 2, text: '已选品' }, { value: 3, text: '已忽略' }
    ];

    function escapeHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    var channel = window.BroadcastChannel ? new BroadcastChannel('mzshop-supplier') : null;

    var SUP = {
        call: call, upload: upload, supplierSource: supplierSource, brandSource: brandSource, currencySource: currencySource,
        STATUSES: STATUSES, escapeHtml: escapeHtml,
        notifyChanged: function (kind) { if (channel) { channel.postMessage({ kind: kind }); } },
        onChanged: function (kind, cb) {
            if (channel) { channel.addEventListener('message', function (e) { if (e.data && e.data.kind === kind) { cb(); } }); }
        },
        openImportWizard: openImportWizard
    };
    window.SUP = SUP;

    /* ================================================================ Excel 导入向导
     * 步骤：1 选供应商和文件（自动解析预览）→ 2 列映射 → 3 校验预览 + 导入 → 4 结果。
     * 映射目标：标准字段 + 「属性：xxx」（对应 shop_attribute）；没映射的列原样存进条目的 attrs（原始属性），不丢数据。 */
    var STANDARD_TARGETS = [
        { value: 'supplier_sku', text: '货号/SKU（必填）' },
        { value: 'name', text: '产品名称（必填）' },
        { value: 'brand_name', text: '品牌' },
        { value: 'category_name', text: '分类' },
        { value: 'price', text: '价格' },
        { value: 'currency', text: '币种（通用属性里的编码，如 CNY）' },
        { value: 'stock', text: '库存' },
        { value: 'moq', text: '起订量' },
        { value: 'main_image_url', text: '图片链接' },
        { value: 'source_url', text: '产品链接' },
        { value: 'description', text: '描述' }
    ];
    var TITLES = {
        1: '步骤 1/4 · 选择供应商和 Excel 文件',
        2: '步骤 2/4 · 列映射（把 Excel 列对应到字段）',
        3: '步骤 3/4 · 校验预览并导入',
        4: '步骤 4/4 · 导入结果'
    };

    function openImportWizard(grid, onDone) {
        var state = { step: 1, supplierId: null, file: null, hasHeader: true, preview: null, mapping: {}, busy: false };
        var targetItems = [{ value: '', text: '（忽略此列）' }].concat(STANDARD_TARGETS);
        call('GET', '/attributes').then(function (attrs) {
            attrs.forEach(function (a) {
                targetItems.push({ value: 'attr:' + a.name, text: '属性：' + a.name + (a.unit ? '（' + a.unit + '）' : '') });
            });
        }, function () { /* 属性加载失败不影响标准字段映射 */ });

        var btnBack, btnNext, dupMode, saveMap, fileUp;
        var $el = $('<div></div>').appendTo(document.body);
        var popup = $el.dxPopup({
            title: 'Excel 导入供应商产品', width: 960, height: '90%', showTitle: true, dragEnabled: true,
            hideOnOutsideClick: false, showCloseButton: true,
            onShown: function () { go(1); },
            onHidden: function () { $el.remove(); },
            toolbarItems: [
                {
                    toolbar: 'bottom', location: 'after', widget: 'dxButton',
                    options: { text: '取消', onClick: function () { popup.hide(); } }
                },
                {
                    toolbar: 'bottom', location: 'before', widget: 'dxButton',
                    options: {
                        text: '上一步', visible: false, onInitialized: function (e) { btnBack = e.component; },
                        onClick: function () { go(state.step - 1); }
                    }
                },
                {
                    toolbar: 'bottom', location: 'after', widget: 'dxButton',
                    options: {
                        text: '下一步', type: 'default', stylingMode: 'contained',
                        onInitialized: function (e) { btnNext = e.component; },
                        onClick: function () {
                            if (state.step === 1) {
                                if (!state.supplierId) { DevExpress.ui.notify('请先选择供应商', 'warning', 1800); return; }
                                if (!state.preview) { DevExpress.ui.notify('请先选择 Excel 文件并等待解析完成', 'warning', 2000); return; }
                                go(2);
                            } else if (state.step === 2) {
                                if (validateMapping()) { go(3); }
                            } else if (state.step === 3) {
                                doImport();
                            } else if (state.step === 4) {
                                popup.hide();
                                if (typeof onDone === 'function') { onDone(); }
                                grid.refresh();
                            }
                        }
                    }
                }
            ],
            contentTemplate: function (content) {
                content.append(
                    $('<div class="wiz-title" id="wizTitle"></div>'),
                    $('<div class="wiz-step" id="wizStep1"></div>').append(
                        $('<div class="wiz-row"></div>').append(
                            $('<label>供应商</label>'),
                            $('<div id="wizSupplier"></div>'),
                            $('<a href="javascript:;" class="wiz-link" id="wizNewSupplier">没有供应商？先去「供应商」新建</a>')
                        ),
                        $('<div class="wiz-row"></div>').append(
                            $('<label>Excel 文件</label>'),
                            $('<div id="wizFile"></div>')
                        ),
                        $('<div class="wiz-row"></div>').append(
                            $('<div id="wizHasHeader"></div>'),
                            $('<span class="wiz-status" id="wizStatus"></span>')
                        )
                    ),
                    $('<div class="wiz-step" id="wizStep2"></div>').append(
                        $('<div class="wiz-tip"></div>').text('把 Excel 列对应到字段；「货号/SKU」和「产品名称」必须映射，其余可选。没映射的列也会原样存进条目的「原始属性」，不会丢。'),
                        $('<div id="wizMapping"></div>')
                    ),
                    $('<div class="wiz-step" id="wizStep3"></div>').append(
                        $('<div class="wiz-tip" id="wizSummary"></div>'),
                        $('<div id="wizPreview"></div>'),
                        $('<div class="wiz-row wiz-row-opt"></div>').append(
                            $('<label>重复货号</label>'),
                            $('<div id="wizDupMode"></div>'),
                            $('<div id="wizSaveMapping"></div>')
                        )
                    ),
                    $('<div class="wiz-step" id="wizStep4"></div>').append($('<div id="wizResult"></div>'))
                );

                $('#wizSupplier').dxSelectBox({
                    dataSource: supplierSource(), displayExpr: 'name', valueExpr: 'id',
                    placeholder: '选择供应商', searchEnabled: true, width: 260,
                    onValueChanged: function (e) {
                        state.supplierId = e.value || null;
                        if (state.file) { loadPreview(); }
                    }
                });
                $('#wizNewSupplier').on('click', function () {
                    if (typeof openAdminTab === 'function') { openAdminTab('/suppliers', '供应商'); }
                });
                fileUp = $('#wizFile').dxFileUploader({
                    accept: '.xlsx,.xlsm', multiple: false, uploadMode: 'instantly',
                    maxFileSize: 10 * 1024 * 1024,
                    labelText: '选择 .xlsx / .xlsm 文件（最多 10MB）', labelVisible: true,
                    width: '100%',
                    uploadFile: function (file) {
                        state.file = file;
                        loadPreview();
                        return $.Deferred().resolve().promise();
                    }
                }).dxFileUploader('instance');
                $('#wizHasHeader').dxCheckBox({
                    text: '第一行是表头', value: true,
                    onValueChanged: function (e) {
                        state.hasHeader = !!e.value;
                        if (state.file) { loadPreview(); }
                    }
                });
                dupMode = $('#wizDupMode').dxRadioGroup({
                    items: [
                        { value: 'skip', text: '跳过重复货号' },
                        { value: 'overwrite', text: '覆盖更新（保留条目状态）' }
                    ],
                    value: 'skip', layout: 'horizontal', valueExpr: 'value', displayExpr: 'text'
                }).dxRadioGroup('instance');
                saveMap = $('#wizSaveMapping').dxCheckBox({
                    text: '保存该映射为此供应商的导入模板', value: true
                }).dxCheckBox('instance');

                $('.wiz-step', $el).hide();
            }
        }).dxPopup('instance');
        popup.show();

        function go(n) {
            state.step = n;
            $('.wiz-step', $el).hide();
            $('#wizStep' + n).show();
            $('#wizTitle').text(TITLES[n]);
            btnBack.option('visible', n > 1 && n < 4);
            btnNext.option('visible', true);
            if (n === 3) { btnNext.option('text', '开始导入'); }
            else if (n === 4) { btnNext.option('text', '完成'); btnBack.option('visible', false); }
            else { btnNext.option('text', '下一步'); }
            setButtons();
        }

        function setButtons() {
            btnNext.option('disabled', state.busy);
        }

        function loadPreview() {
            if (!state.supplierId || !state.file) { return; }
            state.preview = null;
            $('#wizStatus').text('正在解析文件…');
            var fd = new FormData();
            fd.append('file', state.file);
            fd.append('supplier_id', state.supplierId);
            fd.append('has_header', state.hasHeader ? '1' : '0');
            upload('/import/preview', fd).then(function (data) {
                state.preview = data;
                state.mapping = {};
                data.columns.forEach(function (c) { state.mapping[c.key] = data.suggest[c.key] || ''; });
                $('#wizStatus').text('共 ' + data.total_rows + ' 行数据，' + (data.has_template ? '已套用该供应商的导入模板' : '按表头自动猜测了映射，请核对'));
                $('#wizSummary').text('文件：' + data.file_name + '，共 ' + data.total_rows + ' 行数据');
                buildMapping();
                buildPreviewGrid();
            }, function (msg) {
                state.file = null;
                fileUp.option('value', []);
                $('#wizStatus').text('');
                DevExpress.ui.notify('解析失败：' + String(msg), 'error', 3500);
            });
        }

        function buildMapping() {
            var $box = $('#wizMapping').empty();
            if (!state.preview) { return; }
            state.preview.columns.forEach(function (col) {
                var $row = $('<div class="wiz-map-row"></div>').appendTo($box);
                $('<div class="wiz-map-col"></div>').append(
                    $('<div class="wiz-map-name"></div>').text(col.name),
                    $('<div class="wiz-map-sample"></div>').text(col.sample || '')
                ).appendTo($row);
                $('<div class="wiz-map-sel"></div>').appendTo($row).dxSelectBox({
                    items: targetItems, valueExpr: 'value', displayExpr: 'text',
                    value: state.mapping[col.key] || '',
                    searchEnabled: true, width: 280, placeholder: '忽略此列',
                    onValueChanged: function (e) { state.mapping[col.key] = e.value || ''; }
                });
            });
        }

        function validateMapping() {
            var vals = Object.keys(state.mapping).map(function (k) { return state.mapping[k]; }).filter(Boolean);
            var dup = vals.filter(function (v, i) { return vals.indexOf(v) !== i; });
            if (dup.length) {
                var text = dup[0].indexOf('attr:') === 0 ? dup[0] : (STANDARD_TARGETS.filter(function (t) { return t.value === dup[0]; })[0] || {}).text || dup[0];
                DevExpress.ui.notify('「' + text + '」映射了多列，请调整', 'error', 3000);
                return false;
            }
            if (vals.indexOf('supplier_sku') < 0 || vals.indexOf('name') < 0) {
                DevExpress.ui.notify('「货号/SKU」和「产品名称」必须各映射一列', 'error', 3000);
                return false;
            }
            return true;
        }

        function buildPreviewGrid() {
            var $c = $('#wizPreview').empty();
            if (!state.preview) { return; }
            $('<div id="wizPreviewGrid"></div>').appendTo($c);
            $('#wizPreviewGrid').dxDataGrid({
                dataSource: state.preview.rows,
                columns: state.preview.columns.map(function (c) {
                    return { dataField: c.key, caption: c.name, width: 160, allowFiltering: false, allowSorting: false };
                }),
                showBorders: true, showRowLines: true, columnAutoWidth: false, allowColumnResizing: true,
                filterRow: { visible: false }, headerFilter: { visible: false },
                paging: { pageSize: 10 }, pager: { visible: true, showInfo: true, allowedPageSizes: [10, 20] },
                height: 300, noDataText: '没有可预览的数据'
            });
        }

        function doImport() {
            if (state.busy) { return; }
            state.busy = true;
            setButtons();
            var fd = new FormData();
            fd.append('file', state.file);
            fd.append('supplier_id', state.supplierId);
            fd.append('has_header', state.hasHeader ? '1' : '0');
            fd.append('mapping', JSON.stringify(state.mapping));
            fd.append('duplicate_mode', dupMode.option('value'));
            fd.append('save_mapping', saveMap.option('value') ? '1' : '0');
            upload('/import/run', fd).then(function (rep) {
                state.busy = false;
                setButtons();
                state.file = null;
                fileUp.option('value', []);
                renderResult(rep);
                SUP.notifyChanged('catalog');
                go(4);
            }, function (msg) {
                state.busy = false;
                setButtons();
                DevExpress.ui.notify('导入失败：' + String(msg), 'error', 3500);
            });
        }

        function renderResult(rep) {
            var $r = $('#wizResult').empty();
            $('<div class="wiz-ok"></div>').appendTo($r).append(
                $('<div style="font-size:15px;font-weight:600"></div>').text(
                    '导入完成：新增 ' + rep.imported + ' 条、更新 ' + rep.updated + ' 条、跳过重复 ' + rep.skipped + ' 条、出错 ' + rep.error_count + ' 条（共 ' + rep.total + ' 行）'
                )
            );
            if (rep.errors && rep.errors.length) {
                $('<div style="margin:10px 0 4px">出错明细：</div>').appendTo($r);
                var $list = $('<div class="wiz-errbox"></div>').appendTo($r);
                rep.errors.forEach(function (e) {
                    $('<div class="wiz-err"></div>').text('第 ' + e.row + ' 行：' + e.msg).appendTo($list);
                });
            }
        }
    }
})(jQuery);
