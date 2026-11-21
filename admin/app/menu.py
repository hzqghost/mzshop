"""左侧菜单：支持任意层级，有 children 的是分组，只有 url 的是叶子（在标签页里以 iframe 打开）。"""

MENU = [
    {
        "title": "商品管理",
        "icon": "fa-shopping-bag",
        "children": [
            {"title": "商品列表", "url": "/goods", "icon": "fa-shopping-bag"},
            {"title": "组合装", "url": "/bundles", "icon": "fa-cubes"},
            {"title": "商品分类", "url": "/goodsCategories", "icon": "fa-sitemap"},
            {"title": "商品属性", "url": "/goodsAttributes", "icon": "fa-tags"},
            {"title": "商品语言", "url": "/goodsLanguages", "icon": "fa-language"},
            {"title": "品牌管理", "url": "/brands", "icon": "fa-copyright"},
            {"title": "运费模板", "url": "/shippingTemplates", "icon": "fa-truck"},
        ],
    },
    {
        "title": "库存",
        "icon": "fa-archive",
        "children": [
            {"title": "库存管理", "url": "/inventory", "icon": "fa-sliders"},
        ],
    },
    {
        "title": "订单管理",
        "icon": "fa-file-text-o",
        "children": [
            {"title": "Shopify订单", "url": "/orders", "icon": "fa-list-alt"},
        ],
    },
    {
        "title": "产品池",
        "icon": "fa-cubes",
        "children": [
            {"title": "供应商", "url": "/suppliers", "icon": "fa-truck"},
            {"title": "供应商文档", "url": "/supplierDocuments", "icon": "fa-file"},
            {"title": "产品目录", "url": "/supplierCatalog", "icon": "fa-cubes"},
        ],
    },
    {
        "title": "店铺",
        "icon": "fa-building",
        "children": [
            {"title": "平台管理", "url": "/platforms", "icon": "fa-globe"},
            {"title": "店铺管理", "url": "/stores", "icon": "fa-shopping-cart"},
            {"title": "包装管理", "url": "/shippingPackages", "icon": "fa-cube"},
            {
                "title": "Shopify", "icon": "fa-shopping-bag",
                "children": [
                    {"title": "标准分类", "url": "/shopifyTaxonomy", "icon": "fa-sitemap"},
                    {"title": "标准属性值", "url": "/shopifyTaxonomyAttributes", "icon": "fa-list-alt"},
                    {"title": "分类关联", "url": "/shopifyCategoryMaps", "icon": "fa-link"},
                    {"title": "分类属性", "url": "/shopifyCategoryAttributes", "icon": "fa-tags"},
                    {"title": "同步任务", "url": "/shopifyTasks", "icon": "fa-tasks"},
                ],
            },
        ],
    },
    {
        "title": "系统管理",
        "icon": "fa-cog",
        "children": [
            {"title": "属性类型", "url": "/attrTypes", "icon": "fa-sliders"},
            {"title": "属性值", "url": "/attrValues", "icon": "fa-list"},
            {"title": "用户管理", "url": "/users", "icon": "fa-users"},
            {"title": "国家地区", "url": "/geo", "icon": "fa-globe"},
            {"title": "区域", "url": "/regions", "icon": "fa-map"},
            {"title": "UI配置", "url": "/uiStyle", "icon": "fa-paint-brush"},
        ],
    },
]
