"""左侧菜单：支持任意层级，有 children 的是分组，只有 url 的是叶子（在标签页里以 iframe 打开）。"""

MENU = [
    {
        "title": "商品管理",
        "icon": "fa-box",
        "children": [
            {"title": "商品列表", "url": "/goods"},
            {"title": "商品分类", "url": "/goodsCategories"},
            {"title": "商品属性", "url": "/goodsAttributes"},
            {"title": "商品语言", "url": "/goodsLanguages"},
            {"title": "品牌管理", "url": "/brands"},
        ],
    },
    {
        "title": "产品池",
        "icon": "fa-truck-field",
        "children": [
            {"title": "供应商", "url": "/suppliers"},
            {"title": "产品目录", "url": "/supplierCatalog"},
        ],
    },
    {
        "title": "数据采集",
        "icon": "fa-spider",
        "children": [
            {"title": "采集任务", "url": "/crawlTasks"},
            {"title": "采集商品", "url": "/products"},
        ],
    },
    {
        "title": "系统管理",
        "icon": "fa-cog",
        "children": [
            {"title": "属性类型", "url": "/attrTypes"},
            {"title": "属性值", "url": "/attrValues"},
            {"title": "用户管理", "url": "/users"},
            {"title": "Grid 配置", "url": "/gridStyle"},
            {"title": "Form 配置", "url": "/formStyle"},
        ],
    },
]
