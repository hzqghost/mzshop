/**
 * DevExtreme 全局默认值（自己的封装层，不改第三方源码）：
 * 1. 编辑表单里布尔字段默认「标签一行、复选框另起一行」，统一改成一行——复选框在左、标签在右。
 * 2. 弹窗挂在 body 下但不在页面根容器里，给它的 wrapper 也挂上 .mdm-ui2，皮肤才对弹窗生效。
 */
(function () {
    function markBooleanItem(item) {
        var column = item && item.column;
        if (!column || column.dataType !== 'boolean') { return; }
        if (item.label && item.label.visible === false) { return; }
        item.cssClass = (item.cssClass ? item.cssClass + ' ' : '') + 'mdm-field-inline-check';
    }

    ['dxDataGrid', 'dxTreeList'].forEach(function (widget) {
        DevExpress.ui[widget].defaultOptions({
            options: { editing: { form: { customizeItem: markBooleanItem } } }
        });
    });

    DevExpress.ui.dxPopup.defaultOptions({ options: { wrapperAttr: { class: 'mdm-ui2' } } });
})();
