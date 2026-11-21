/**
 * 后台框架：左侧菜单折叠、多标签 + iframe 浏览、工具条下拉
 * 依赖: jQuery, window.APP = {HOST, STATIC_URL, LOCALE}
 */
(function ($) {
    var tabs = [{ id: 'home', title: '', url: '', closable: false }];
    var activeId = 'home';
    // 标签激活顺序（最近激活的在最后）：关闭当前标签后回到「上一个选中的标签」，不是左邻的标签
    var activeHistory = [];
    // 拖动排序刚结束时，紧跟着的那次 click 不切换标签
    var suppressClick = false;

    // 记录打开的所有标签（顺序 + 当前激活的），浏览器刷新/切换中英文（整页刷新）后原样恢复
    var TABS_STORAGE_KEY = 'adminOpenTabs';

    function saveTabs() {
        var active = tabs.find(function (t) { return t.id === activeId; });
        var data = {
            active: active && active.url ? active.url : '',
            tabs: tabs.filter(function (t) { return t.url; }).map(function (t) {
                return { url: t.url, title: t.title };
            })
        };
        try {
            localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(data));
        } catch (e) {
            // 存不了就只对本次有效
        }
    }

    // 只有当前标签立刻加载，其余标签先建标签头和空面板，第一次激活时才建 iframe，刷新时不会一口气加载所有页面
    function restoreTabs() {
        var saved = null;
        try {
            saved = JSON.parse(localStorage.getItem(TABS_STORAGE_KEY) || 'null');
        } catch (e) {
            saved = null;
        }
        if (!saved || !Array.isArray(saved.tabs)) {
            return;
        }
        saved.tabs.forEach(function (t) {
            if (t && t.url) {
                addTab(t.url, t.title || '');
            }
        });
        var activeTabId = saved.active ? tabIdForUrl(saved.active) : 'home';
        activateTab(tabs.some(function (t) { return t.id === activeTabId; }) ? activeTabId : 'home');
    }

    function tabIdForUrl(url) {
        return 'tab_' + url.replace(/[^a-zA-Z0-9]/g, '_');
    }

    // 普通页面标签图标与对应的叶子菜单项一致。
    function iconForUrl(url) {
        var icon = '';
        $('.menu-item').each(function () {
            if ($(this).data('url') === url) {
                icon = $(this).attr('data-icon') || '';
                return false;
            }
        });
        return icon;
    }

    // 详情页用业务类型的彩色圆形图标；标题只显示业务名称/编号，不再重复类型前缀。
    var DETAIL_DOTS = [
        { match: /^\/goodsEdit(?:\?|$)/, kind: 'goods', icon: 'fa-cog' },
        { match: /^\/supplierCatalogEdit(?:\?|$)/, kind: 'product', icon: 'fa-cube' }
    ];

    function detailDotFor(url) {
        for (var i = 0; i < DETAIL_DOTS.length; i++) {
            if (DETAIL_DOTS[i].match.test(url)) { return DETAIL_DOTS[i]; }
        }
        return null;
    }

    // 建标签头和空面板（不加载 iframe、不激活），返回标签 id
    function addTab(url, title) {
        var id = tabIdForUrl(url);

        if (!tabs.some(function (t) { return t.id === id; })) {
            tabs.push({ id: id, title: title, url: url, closable: true });

            // 标题可能来自业务数据（如数据单标题），用 .text() 写入，不能拼进 HTML 字符串
            var $tab = $(
                '<div class="tab-item" data-id="' + id + '">' +
                    '<i class="tab-icon"></i>' +
                    '<span class="tab-title"></span>' +
                    '<span class="tab-close"><i class="fa fa-times"></i></span>' +
                '</div>'
            );
            // 标题长了在标签上截断显示（CSS 管），完整的挂 title 属性，鼠标悬停看得到
            $tab.attr('title', title).find('.tab-title').text(title);
            var icon = iconForUrl(url);
            var dot = detailDotFor(url);
            if (dot) {
                $tab.find('.tab-icon').addClass('tab-dot tab-dot-' + dot.kind).append($('<i class="fa"></i>').addClass(dot.icon));
            } else if (icon) {
                $tab.find('.tab-icon').addClass('fa ' + icon);
            } else {
                $tab.find('.tab-icon').remove();
            }
            $('#tabs').append($tab);

            $('#contentArea').append($('<div class="tab-pane"></div>').attr('data-id', id));
        }
        return id;
    }

    function ensureLoaded(id) {
        var tab = tabs.find(function (t) { return t.id === id; });
        var $pane = $('.tab-pane[data-id="' + id + '"]');
        if (tab && tab.url && $pane.length && !$pane.children('iframe').length) {
            $('<iframe></iframe>').attr('src', APP.HOST + tab.url).appendTo($pane);
        }
    }

    function openTab(url, title) {
        activateTab(addTab(url, title));
    }

    function activateTab(id) {
        activeId = id;
        activeHistory = activeHistory.filter(function (h) { return h !== id; });
        activeHistory.push(id);
        $('.tab-item').removeClass('active');
        $('.tab-item[data-id="' + id + '"]').addClass('active');
        $('.tab-pane').removeClass('active');
        $('.tab-pane[data-id="' + id + '"]').addClass('active');
        $('.menu-item').removeClass('active');

        var tab = tabs.find(function (t) { return t.id === id; });
        if (tab && tab.url) {
            $('.menu-item[data-url="' + tab.url + '"]').addClass('active');
        }

        ensureLoaded(id);
        revealTab(id);
        saveTabs();
    }

    // 把标签滚进标签栏可视区，保证完整看到（新开的、切到已有的、关闭后回退到的都走 activateTab）
    function revealTab(id) {
        var tabEl = $('.tab-item[data-id="' + id + '"]')[0];
        var box = document.getElementById('tabs');
        if (!tabEl || !box) {
            return;
        }
        // 先让激活态的宽度 / 关闭图标生效再量（上面已经切了 active class，读 rect 会触发同步布局）
        var rect = tabEl.getBoundingClientRect();
        var boxRect = box.getBoundingClientRect();
        if (rect.left < boxRect.left) {
            box.scrollLeft -= boxRect.left - rect.left + 2;
        } else if (rect.right > boxRect.right) {
            box.scrollLeft += rect.right - boxRect.right + 2;
        }
    }

    function removeTabDom(id) {
        $('.tab-item[data-id="' + id + '"]').remove();
        $('.tab-pane[data-id="' + id + '"]').remove();
    }

    function closeTab(id) {
        if (id === 'home') {
            return;
        }
        var index = tabs.findIndex(function (t) { return t.id === id; });
        if (index === -1) {
            return;
        }
        var wasActive = activeId === id;
        tabs.splice(index, 1);
        removeTabDom(id);
        activeHistory = activeHistory.filter(function (h) { return h !== id; });
        saveTabs();

        if (wasActive) {
            // 回到上一个选中的标签；没有历史（如刷新后恢复的）才退到左邻标签
            var previous = activeHistory.length ? activeHistory[activeHistory.length - 1] : null;
            var fallback = tabs.find(function (t) { return t.id === previous; }) || tabs[index - 1] || tabs[0];
            activateTab(fallback.id);
        }
    }

    function closeOthers(id) {
        tabs.slice().forEach(function (t) {
            if (t.closable && t.id !== id) {
                closeTab(t.id);
            }
        });
        activateTab(id);
    }

    function closeRight(id) {
        var index = tabs.findIndex(function (t) { return t.id === id; });
        tabs.slice(index + 1).forEach(function (t) {
            if (t.closable) {
                closeTab(t.id);
            }
        });
    }

    function closeLeft(id) {
        var index = tabs.findIndex(function (t) { return t.id === id; });
        tabs.slice(0, index).forEach(function (t) {
            if (t.closable) {
                closeTab(t.id);
            }
        });
    }

    function closeAll() {
        tabs.slice().forEach(function (t) {
            if (t.closable) {
                closeTab(t.id);
            }
        });
        activateTab('home');
    }

    function refreshActiveTab() {
        var $iframe = $('.tab-pane[data-id="' + activeId + '"] iframe');
        $iframe.attr('src', $iframe.attr('src'));
    }

    // ── 标签拖动排序 ──────────────────────────────────────
    // 用鼠标事件自己做，不用 HTML5 拖放：内容区是 iframe，原生拖放的事件会掉进 iframe 里收不到。
    // 首页标签不参与（既不能拖，也不能被插到它前面），拖完把 tabs 数组的顺序同步过来，
    // 「关闭左侧 / 右侧」这些按顺序算的操作才不会错。
    var DRAG_THRESHOLD = 4;
    var drag = null;

    function tabOrderFromDom() {
        var order = [];
        $('#tabs .tab-item').each(function () {
            var id = $(this).data('id');
            var tab = tabs.find(function (t) { return t.id === id; });
            if (tab) {
                order.push(tab);
            }
        });
        // 万一有标签没画出来（正常不会），补在后面，别把数据弄丢
        tabs.forEach(function (t) {
            if (order.indexOf(t) === -1) {
                order.push(t);
            }
        });
        tabs = order;
    }

    // 按鼠标横坐标找该落在哪个标签前面，返回 null 表示放到最后
    function dropTarget(x) {
        var target = null;
        $('#tabs .tab-item').each(function () {
            var $other = $(this);
            if ($other.is(drag.$tab) || $other.data('id') === 'home') {
                return;
            }
            var rect = this.getBoundingClientRect();
            if (x < rect.left + rect.width / 2) {
                target = $other;
                return false;
            }
        });
        return target;
    }

    function startDrag(e) {
        var $tab = $(e.target).closest('.tab-item');
        if (!$tab.length || $tab.data('id') === 'home' || $(e.target).closest('.tab-close').length) {
            return;
        }
        drag = { $tab: $tab, startX: e.clientX, moved: false };
    }

    function moveDrag(e) {
        if (!drag) {
            return;
        }
        if (!drag.moved) {
            if (Math.abs(e.clientX - drag.startX) < DRAG_THRESHOLD) {
                return;
            }
            drag.moved = true;
            drag.$tab.addClass('dragging');
            // 拖动中盖住 iframe，鼠标滑到内容区上也收得到 mousemove
            $('body').addClass('tabs-dragging');
        }
        e.preventDefault();

        var $target = dropTarget(e.clientX);
        if ($target) {
            drag.$tab.insertBefore($target);
        } else {
            $('#tabs').append(drag.$tab);
        }
    }

    function endDrag() {
        if (!drag) {
            return;
        }
        var moved = drag.moved;
        drag.$tab.removeClass('dragging');
        $('body').removeClass('tabs-dragging');
        drag = null;
        if (moved) {
            tabOrderFromDom();
            saveTabs();
            // 拖完紧跟着来的那次 click 不当成「切标签」
            suppressClick = true;
            setTimeout(function () { suppressClick = false; }, 0);
        }
    }

    function closeDropdowns() {
        $('.toolbar-dropdown').removeClass('open');
    }

    $(function () {
        // 左侧菜单：分组展开/收起；收拢时悬停一级图标，在右侧显示子菜单。
        var MENU_COLLAPSED_KEY = 'adminSidebarCollapsed';
        var $appShell = $('#appShell');
        var $menuFlyout = $('<div id="collapsedMenuFlyout"></div>').appendTo('body');
        var flyoutTimer = null;

        function saveMenuCollapsed() {
            try { localStorage.setItem(MENU_COLLAPSED_KEY, $appShell.hasClass('collapsed') ? '1' : '0'); } catch (e) { /* 存不了就只对本次有效 */ }
        }

        function hideMenuFlyout(delay) {
            clearTimeout(flyoutTimer);
            flyoutTimer = setTimeout(function () { $menuFlyout.removeClass('show').empty(); }, delay || 0);
        }

        function addFlyoutNodes($list, depth) {
            $list.children('li').each(function () {
                var $node = $(this);
                if ($node.hasClass('menu-group')) {
                    if (depth > 0) {
                        $('<div class="flyout-section"></div>').text($node.children('.menu-group-title').find('.menu-text').first().text()).appendTo($menuFlyout);
                    }
                    addFlyoutNodes($node.children('.menu-children'), depth + 1);
                    return;
                }
                var $item = $node;
                $('<div class="flyout-item"></div>')
                    .text($item.data('title'))
                    .toggleClass('active', $item.hasClass('active'))
                    .data({ url: $item.data('url'), title: $item.data('title'), external: $item.data('external') })
                    .appendTo($menuFlyout);
            });
        }

        function showMenuFlyout(title) {
            if (!$appShell.hasClass('collapsed')) {
                return;
            }
            clearTimeout(flyoutTimer);
            var rect = this.getBoundingClientRect();
            $menuFlyout.empty();
            $('<div class="flyout-title"></div>').text(title).appendTo($menuFlyout);
            addFlyoutNodes($(this).siblings('.menu-children'), 0);
            $menuFlyout.css({ left: rect.right, top: rect.top }).addClass('show');
            var flyoutRect = $menuFlyout[0].getBoundingClientRect();
            if (flyoutRect.bottom > window.innerHeight - 8) {
                $menuFlyout.css('top', Math.max(8, window.innerHeight - flyoutRect.height - 8));
            }
        }

        var savedCollapsed = false;
        try { savedCollapsed = localStorage.getItem(MENU_COLLAPSED_KEY) === '1'; } catch (e) { savedCollapsed = false; }
        $appShell.toggleClass('collapsed', savedCollapsed);

        $('.menu-root > .menu-group > .menu-group-title').on('mouseenter', function () {
            showMenuFlyout.call(this, $(this).find('.menu-text').first().text());
        }).on('mouseleave', function () { hideMenuFlyout(120); });
        $menuFlyout.on('mouseenter', function () { clearTimeout(flyoutTimer); })
            .on('mouseleave', function () { hideMenuFlyout(120); })
            .on('click', '.flyout-item', function () {
                if ($(this).data('external')) {
                    window.open($(this).data('url'), '_blank', 'noopener');
                } else {
                    openTab($(this).data('url'), $(this).data('title'));
                }
                hideMenuFlyout();
            });

        $('.menu-group-title').on('click', function () {
            var $group = $(this).closest('.menu-group');
            if ($appShell.hasClass('collapsed')) {
                return;
            }
            $group.toggleClass('open');
        });

        // 左侧菜单：点子项打开标签
        $('.menu-item').on('click', function () {
            // 外部网址（如在线目录站点）新窗口打开，不进标签页
            if ($(this).data('external')) {
                window.open($(this).data('url'), '_blank', 'noopener');
                return;
            }
            openTab($(this).data('url'), $(this).data('title'));
        });

        // 白天/夜晚色调切换，记住选择
        var THEME_KEY = 'adminSidebarTheme';
        // FontAwesome 4 的 fa-sun-o 长得像齿轮，这里用 SVG 画太阳（圆 + 八条光线）和月牙
        var THEME_ICON_SUN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.2" fill="currentColor" stroke="none"/><path d="M12 2.5v2.6M12 18.9v2.6M2.5 12h2.6M18.9 12h2.6M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/></svg>';
        var THEME_ICON_MOON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5a8.5 8.5 0 1 0 11.1 11.1z"/></svg>';
        function applySidebarTheme(light) {
            $('#sidebar').toggleClass('light', light);
            $('#themeToggle').html(light ? THEME_ICON_SUN : THEME_ICON_MOON);
        }
        // 默认白天，只有用户选过夜晚才用夜晚
        var savedLight = true;
        try { savedLight = localStorage.getItem(THEME_KEY) !== 'dark'; } catch (e) { savedLight = true; }
        applySidebarTheme(savedLight);
        $('#themeToggle').on('click', function (e) {
            e.stopPropagation();
            var light = !$('#sidebar').hasClass('light');
            applySidebarTheme(light);
            try { localStorage.setItem(THEME_KEY, light ? 'light' : 'dark'); } catch (err) { /* 存不了就只对本次有效 */ }
        });

        // 点 LOGO 收拢/展开侧边栏
        $('#sidebarHeader').on('click', function () {
            $appShell.toggleClass('collapsed');
            hideMenuFlyout();
            saveMenuCollapsed();
        });

        // 标签拖动排序
        $('#tabs').on('mousedown', '.tab-item', startDrag);
        $(document).on('mousemove', moveDrag).on('mouseup', endDrag);

        // 点标签切换
        $('#tabs').on('click', '.tab-item', function (e) {
            if (suppressClick || $(e.target).closest('.tab-close').length) {
                return;
            }
            activateTab($(this).data('id'));
        });

        // 标签关闭按钮
        $('#tabs').on('click', '.tab-close', function (e) {
            e.stopPropagation();
            closeTab($(this).closest('.tab-item').data('id'));
        });

        // 标签右键菜单：作用于被右键的那个标签（跟右上角下拉不同，那个作用于当前标签）
        var $contextMenu = $('#tabContextMenu');
        var contextTabId = null;

        function hideContextMenu() {
            $contextMenu.removeClass('open');
            contextTabId = null;
        }

        // 取 iframe 当前地址；跨域或尚未加载时退回标签初始地址。
        function tabHref(id) {
            var tab = tabs.find(function (t) { return t.id === id; });
            if (!tab || !tab.url) return '';

            var href = APP.HOST + tab.url;
            var frame = $('.tab-pane[data-id="' + id + '"] iframe')[0];
            try {
                var current = frame && frame.contentWindow ? frame.contentWindow.location.href : '';
                if (current && current !== 'about:blank') href = current;
            } catch (err) {
                // 跨域取不到就用原地址
            }
            return href;
        }

        function openInBrowser(id) {
            var href = tabHref(id);
            if (href) window.open(href, '_blank', 'noopener');
        }

        function copyFallback(text) {
            var $input = $('<textarea readonly></textarea>').css({ position: 'fixed', left: '-9999px' }).val(text).appendTo('body');
            $input[0].select();
            document.execCommand('copy');
            $input.remove();
        }

        function copyTabLink(id) {
            var href = tabHref(id);
            if (!href) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(href).catch(function () { copyFallback(href); });
            } else {
                copyFallback(href);
            }
        }

        $('#tabs').on('contextmenu', '.tab-item', function (e) {
            e.preventDefault();
            closeDropdowns();
            contextTabId = $(this).data('id');
            var contextTab = tabs.find(function (t) { return t.id === contextTabId; });
            $contextMenu.find('[data-action="openInBrowser"], [data-action="copyLink"], .menu-sep').toggle(!!(contextTab && contextTab.url));
            // 菜单是 position:fixed，靠右 / 靠下时往回收，别被窗口切掉
            $contextMenu.addClass('open');
            var left = Math.min(e.clientX, window.innerWidth - $contextMenu.outerWidth() - 4);
            var top = Math.min(e.clientY, window.innerHeight - $contextMenu.outerHeight() - 4);
            $contextMenu.css({ left: Math.max(0, left), top: Math.max(0, top) });
        });

        $contextMenu.on('click', '[data-action]', function () {
            var action = $(this).data('action');
            var id = contextTabId;
            hideContextMenu();
            if (id === null) return;
            if (action === 'openInBrowser') openInBrowser(id);
            else if (action === 'copyLink') copyTabLink(id);
            else if (action === 'closeOthers') closeOthers(id);
            else if (action === 'closeRight') closeRight(id);
            else if (action === 'closeLeft') closeLeft(id);
            else if (action === 'closeAll') closeAll();
        });
        $contextMenu.on('contextmenu', function (e) { e.preventDefault(); });
        // 点别处 / 滚动 / 点进 iframe（父窗口 blur）都收起
        $(document).on('click contextmenu', function (e) {
            if (!$(e.target).closest('#tabContextMenu, #tabs .tab-item').length) {
                hideContextMenu();
            }
        });
        $('#tabs').on('scroll', hideContextMenu);
        $(window).on('blur resize', hideContextMenu);

        // 刷新当前标签
        $('#refreshBtn').on('click', refreshActiveTab);

        // 工具条下拉（标签操作 / 用户 / 语言）统一处理
        $('.toolbar-dropdown-label').on('click', function (e) {
            e.stopPropagation();
            var $dropdown = $(this).closest('.toolbar-dropdown');
            var isOpen = $dropdown.hasClass('open');
            closeDropdowns();
            if (!isOpen) {
                $dropdown.addClass('open');
            }
        });
        $(document).on('click', closeDropdowns);

        // 标签操作菜单：作用于当前激活的标签
        $('#tabActionsMenu').on('click', '[data-action]', function () {
            var action = $(this).data('action');
            if (action === 'close') closeTab(activeId);
            else if (action === 'closeOthers') closeOthers(activeId);
            else if (action === 'closeRight') closeRight(activeId);
            else if (action === 'closeLeft') closeLeft(activeId);
            else if (action === 'closeAll') closeAll();
        });

        // 用户菜单
        $('#userMenu').on('click', '[data-action="logout"]', function () {
            window.location.href = APP.HOST + '/logout';
        });

        // 浏览器刷新后的整页重新加载：恢复刷新前打开的所有标签，选中刷新前的那个
        restoreTabs();
    });

    window.AdminLayout = {
        openTab: openTab,
        closeTab: closeTab,
        // 详情页保存后关闭自己：传打开时用的同一个 url
        closeTabByUrl: function (url) { closeTab(tabIdForUrl(url)); }
    };
})(jQuery);
