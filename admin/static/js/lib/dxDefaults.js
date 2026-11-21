/**
 * DevExtreme 全局默认值（自己的封装层，不改第三方源码）：
 * 1. 编辑表单里布尔字段默认「标签一行、复选框另起一行」，统一改成一行——复选框在左、标签在右。
 * 2. 弹窗挂在 body 下但不在页面根容器里，给它的 wrapper 也挂上 .mdm-ui2，皮肤才对弹窗生效。
 * 3. 分类 / 供应商 / 品牌表单字段统一 dxLookup（带搜索），以后的表单只要字段名是这些就生效。
 */
(function () {
    var DICT_LOOKUP_FIELDS = { category_id: 1, supplier_id: 1, brand_id: 1 };

    function fieldName(item) {
        var field = item && item.dataField;
        if (!field || typeof field !== 'string') { return ''; }
        var parts = field.split('.');
        return parts[parts.length - 1];
    }

    function applyDictLookup(item) {
        if (!item || item.itemType && item.itemType !== 'simple') { return; }
        if (!DICT_LOOKUP_FIELDS[fieldName(item)]) { return; }
        if (item.editorType && item.editorType !== 'dxSelectBox' && item.editorType !== 'dxLookup') { return; }
        item.editorType = 'dxLookup';
        item.editorOptions = $.extend({
            searchEnabled: true,
            searchPlaceholder: '搜索',
            showCancelButton: true,
            cancelButtonText: '取消',
            dropDownCentered: false
        }, item.editorOptions);
    }

    function markBooleanItem(item) {
        var column = item && item.column;
        if (!column || column.dataType !== 'boolean') { return; }
        if (item.label && item.label.visible === false) { return; }
        item.cssClass = (item.cssClass ? item.cssClass + ' ' : '') + 'mdm-field-inline-check';
    }

    function formCustomize(item) {
        applyDictLookup(item);
        markBooleanItem(item);
    }

    DevExpress.ui.dxForm.defaultOptions({ options: { customizeItem: applyDictLookup } });
    DevExpress.ui.dxLookup.defaultOptions({
        options: {
            searchEnabled: true,
            searchPlaceholder: '搜索',
            showCancelButton: true,
            cancelButtonText: '取消',
            dropDownCentered: false
        }
    });

    ['dxDataGrid', 'dxTreeList'].forEach(function (widget) {
        DevExpress.ui[widget].defaultOptions({
            options: { editing: { form: { customizeItem: formCustomize } } }
        });
    });

    DevExpress.ui.dxPopup.defaultOptions({ options: { wrapperAttr: { class: 'mdm-ui2' } } });
})();
