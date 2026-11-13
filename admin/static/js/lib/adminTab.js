/**
 * 在后台框架的标签页里打开一个页面。
 * 页面跑在 adminLayout.js 的 iframe 里，要调父窗口的 AdminLayout.openTab；
 * 页面被单独打开（没有父框架）时退回本页跳转，options.newWindow 为 true 则开新窗口。
 *
 * @param {string} url 以 / 开头的站内路径（不含 APP.HOST）
 * @param {string} title 标签页标题
 */
function openAdminTab(url, title, options) {
    if (window.parent !== window && window.parent.AdminLayout) {
        window.parent.AdminLayout.openTab(url, title);
        return;
    }
    if (options && options.newWindow) {
        window.open(APP.HOST + url);
        return;
    }
    window.location.href = APP.HOST + url;
}
