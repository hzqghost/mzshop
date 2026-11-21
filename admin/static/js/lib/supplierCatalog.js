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

    var DOC_TYPES = [
        { value: 'license', text: '营业执照' },
        { value: 'qualification', text: '资质证书' },
        { value: 'contract', text: '合同协议' },
        { value: 'pricelist', text: '价目表' },
        { value: 'catalog', text: '产品资料' },
        { value: 'other', text: '其他' }
    ];

    function escapeHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    /* 和产品详情同一套 HTML 编辑器：图片/文件先本地预览，保存时再上传 */
    var MATERIAL_IMAGE_EXT = { jpg: 1, jpeg: 1, png: 1, gif: 1, webp: 1 };
    var MATERIAL_FILE_EXT = { pdf: 1, doc: 1, docx: 1, xls: 1, xlsx: 1, ppt: 1, pptx: 1, txt: 1, csv: 1, zip: 1 };
    var MATERIAL_IMAGE_ACCEPT = '.jpg,.jpeg,.png,.gif,.webp,image/jpeg,image/png,image/gif,image/webp';
    var MATERIAL_FILE_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip';
    var materialPending = {};

    function materialFileError(file) {
        var ext = ((file.name || '').split('.').pop() || '').toLowerCase();
        var image = !!MATERIAL_IMAGE_EXT[ext];
        if (!image && !MATERIAL_FILE_EXT[ext]) { return '仅支持图片（jpg/png/gif/webp）和文件（pdf/doc/docx/xls/xlsx/ppt/pptx/txt/csv/zip）'; }
        if (!file.size) { return '文件是空的'; }
        if (image && file.size > 8 * 1024 * 1024) { return '图片不能超过 8MB'; }
        if (!image && file.size > 20 * 1024 * 1024) { return '文件不能超过 20MB'; }
        return '';
    }

    function materialNamedFile(file) {
        if (file.name && file.name.indexOf('.') > 0) { return file; }
        var map = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif', 'image/webp': 'webp' };
        var ext = map[file.type] || 'bin';
        return new File([file], 'paste.' + ext, { type: file.type });
    }

    function rememberMaterial(file) {
        file = materialNamedFile(file);
        var err = materialFileError(file);
        if (err) { if (typeof apiError === 'function') { apiError(err); } return null; }
        var id = 'lf' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
        var url = URL.createObjectURL(file);
        var image = file.type.indexOf('image/') === 0 || !!MATERIAL_IMAGE_EXT[((file.name || '').split('.').pop() || '').toLowerCase()];
        materialPending[id] = { file: file, url: url };
        return { id: id, url: url, name: file.name, image: image };
    }

    function insertMaterial(editor, file) {
        var rec = rememberMaterial(file);
        if (!rec) { return; }
        if (rec.image) {
            editor.insertContent('<img src="' + rec.url + '" alt="' + escapeHtml(rec.name) + '" data-local="' + rec.id + '">');
        } else {
            editor.insertContent('<p><a href="' + rec.url + '" target="_blank" rel="noopener" data-local="' + rec.id + '">' + escapeHtml(rec.name) + '</a></p>');
        }
    }

    function materialFilesFromClipboard(e) {
        var cd = e.clipboardData || (e.originalEvent && e.originalEvent.clipboardData);
        if (!cd) { return []; }
        if (cd.files && cd.files.length) { return Array.prototype.slice.call(cd.files); }
        var out = [];
        if (cd.items) {
            for (var i = 0; i < cd.items.length; i++) {
                if (cd.items[i].kind === 'file') {
                    var f = cd.items[i].getAsFile();
                    if (f) { out.push(f); }
                }
            }
        }
        return out;
    }

    function pickMaterial(editor, accept) {
        var input = document.createElement('input');
        input.type = 'file';
        input.accept = accept;
        input.onchange = function () {
            if (input.files && input.files[0]) { insertMaterial(editor, input.files[0]); }
        };
        input.click();
    }

    function uploadMaterialFile(file) {
        var fd = new FormData();
        fd.append('file', file, file.name || 'file');
        return $.ajax({
            url: APP.HOST + BASE + '/uploads',
            method: 'POST', data: fd, processData: false, contentType: false
        }).then(function (res) {
            if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
            return res.data;
        }, function (xhr) {
            if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
            return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || '上传失败').promise();
        });
    }

    function flushMaterialEditor(editor) {
        if (!editor) { return $.Deferred().resolve([]).promise(); }
        var body = editor.getBody();
        var nodes = body.querySelectorAll('[data-local]');
        var kept = [];
        for (var i = 0; i < nodes.length; i++) {
            var id = nodes[i].getAttribute('data-local');
            if (materialPending[id] && kept.indexOf(id) < 0) { kept.push(id); }
        }
        Object.keys(materialPending).forEach(function (id) {
            if (kept.indexOf(id) < 0) {
                URL.revokeObjectURL(materialPending[id].url);
                delete materialPending[id];
            }
        });
        var uploaded = [];
        var chain = $.Deferred().resolve().promise();
        kept.forEach(function (id) {
            chain = chain.then(function () {
                return uploadMaterialFile(materialPending[id].file).then(function (res) {
                    var els = editor.getBody().querySelectorAll('[data-local="' + id + '"]');
                    for (var n = 0; n < els.length; n++) {
                        if (els[n].tagName === 'A') { els[n].setAttribute('href', res.url); }
                        else { els[n].setAttribute('src', res.url); }
                        els[n].removeAttribute('data-local');
                    }
                    URL.revokeObjectURL(materialPending[id].url);
                    delete materialPending[id];
                    uploaded.push(res.url);
                });
            });
        });
        return chain.then(function () { return uploaded; });
    }

    function discardMaterialPending() {
        Object.keys(materialPending).forEach(function (id) {
            URL.revokeObjectURL(materialPending[id].url);
            delete materialPending[id];
        });
    }

    function initMaterialEditor(selector, html, opts) {
        opts = opts || {};
        var height = opts.height || 800;
        if (window.tinymce) { tinymce.remove(selector); }
        return tinymce.init({
            selector: selector,
            license_key: 'gpl',
            language: 'zh-CN',
            language_url: '/static/js/plugins/tinymce/langs/zh-CN.js',
            height: height,
            min_height: height,
            menubar: false,
            branding: false,
            promotion: false,
            statusbar: false,
            toolbar_mode: 'wrap',
            convert_urls: false,
            extended_valid_elements: 'img[src|alt|width|height|style|class|data-local],a[href|target|rel|class|style|data-local]',
            paste_data_images: false,
            automatic_uploads: false,
            images_file_types: 'jpg,jpeg,png,gif,webp',
            plugins: 'advlist autolink lists link image table code wordcount fullscreen',
            toolbar: 'undo redo | blocks | bold italic underline strikethrough | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist | link uploadimage uploadfile table | removeformat code fullscreen',
            content_style: 'body{font-family:"Microsoft YaHei",Arial,sans-serif;font-size:14px;} img{max-width:100%;height:auto;}',
            setup: function (editor) {
                editor.ui.registry.addButton('uploadimage', {
                    icon: 'image',
                    tooltip: '插入图片',
                    onAction: function () { pickMaterial(editor, MATERIAL_IMAGE_ACCEPT); }
                });
                editor.ui.registry.addButton('uploadfile', {
                    text: '文件',
                    tooltip: '上传文件',
                    onAction: function () { pickMaterial(editor, MATERIAL_FILE_ACCEPT); }
                });
                editor.on('paste', function (e) {
                    var files = materialFilesFromClipboard(e);
                    if (!files.length) { return; }
                    e.preventDefault();
                    files.forEach(function (file) { insertMaterial(editor, file); });
                }, true);
                editor.on('drop', function (e) {
                    var dt = e.dataTransfer;
                    if (!dt || !dt.files || !dt.files.length) { return; }
                    e.preventDefault();
                    Array.prototype.forEach.call(dt.files, function (file) { insertMaterial(editor, file); });
                }, true);
                editor.on('init', function () {
                    if (html) { editor.setContent(html); }
                    if (editor.mode && editor.mode.get() !== 'design') { editor.mode.set('design'); }
                });
            }
        });
    }

    var channel = window.BroadcastChannel ? new BroadcastChannel('mzshop-supplier') : null;

    var SUP = {
        call: call, upload: upload, supplierSource: supplierSource, brandSource: brandSource, currencySource: currencySource,
        STATUSES: STATUSES, DOC_TYPES: DOC_TYPES, escapeHtml: escapeHtml,
        notifyChanged: function (kind) { if (channel) { channel.postMessage({ kind: kind }); } },
        onChanged: function (kind, cb) {
            if (channel) { channel.addEventListener('message', function (e) { if (e.data && e.data.kind === kind) { cb(); } }); }
        },
        openImportWizard: openImportWizard,
        initMaterialEditor: initMaterialEditor,
        flushMaterialEditor: flushMaterialEditor,
        discardMaterialPending: discardMaterialPending
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
        { value: 'purchase_price', text: '采购价' },
        { value: 'region_name', text: '区域（区域价格按这个名称对应）' },
        { value: 'price', text: '价格（按区域）' },
        { value: 'suggested_price', text: '建议售价（按区域）' },
        { value: 'min_price', text: '最低售价（按区域）' },
        { value: 'max_price', text: '最高售价（按区域）' },
        { value: 'shipping_fee', text: '运费（按区域）' },
        { value: 'arrival_days_min', text: '最快到达天数（按区域）' },
        { value: 'arrival_days_max', text: '最慢到达天数（按区域）' },
        { value: 'tax', text: '税费（按区域）' },
        { value: 'price_rule', text: '价格规则' },
        { value: 'lead_time', text: '交期' },
        { value: 'currency', text: '币种（按区域，通用属性里的编码，如 CNY）' },
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
            title: 'Excel 导入供应商产品', width: '90%', maxWidth: 960, height: '90%', showTitle: true, dragEnabled: true,
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
            $('#wizPreviewGrid').dxDataGrid($.extend({}, DxGrid.headerMenuOptions(false), {
                dataSource: state.preview.rows,
                columns: state.preview.columns.map(function (c) {
                    return { dataField: c.key, caption: c.name, width: 160, allowFiltering: false, allowSorting: false };
                }),
                showBorders: true, showRowLines: true, columnAutoWidth: false, allowColumnResizing: true,
                filterRow: { visible: false }, headerFilter: { visible: false },
                paging: { pageSize: 10 }, pager: { visible: true, showInfo: true, allowedPageSizes: [10, 20] },
                height: 300, noDataText: '没有可预览的数据'
            }));
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
