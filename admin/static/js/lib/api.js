/** 调后端 JSON 接口（响应 {code, data, msg}，code != 0 时 reject 出 msg）。 */
function apiPost(url, body) {
    return $.ajax({
        url: APP.HOST + url,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(body || {})
    }).then(function (res) {
        if (res.code !== 0) { return $.Deferred().reject(res.msg).promise(); }
        return res.data;
    }, function (xhr) {
        if (xhr.status === 401) { (window.top || window).location.href = APP.HOST + '/login'; }
        return $.Deferred().reject((xhr.responseJSON && xhr.responseJSON.msg) || xhr.statusText || 'Error').promise();
    });
}

/** 弹出错误提示（reject 的是字符串 msg）。 */
function apiError(msg) {
    DevExpress.ui.notify(String(msg), 'error', 3000);
}
