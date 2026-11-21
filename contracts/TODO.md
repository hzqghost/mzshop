# 已知偏差与待办（开工前先看）

## 与契约的偏差
1. **建表方式**：`main.py` 用 `create_all` 启动即建表，违背 DB.md「DDL 人工审核执行」。建议改为：模型变更输出 DDL 脚本人工执行，去掉 create_all（或仅在开发库启用）。
2. **Comment 缺失**：`sys_user` 的 id/created_at/updated_at、`sys_ui_style` 全部字段缺中文 Comment，违背 DB.md 第 5 条。补注释须走「只改 Comment」的 DDL。
3. **超级管理员口令硬编码**在 `admin/app/config.py`（明文），应改为 .env 配置（存哈希更好）；`SECRET_KEY` 也须是强随机值。
4. `requirements.txt` / `.env.example` 带 UTF-8 BOM，注意工具兼容。

## 待开发
- 电商业务域建模：平台/店铺、商品(SPU/SKU)、订单、订单明细、客户、库存、售后、广告/费用等——**需先与业务方确认范围和字段**，再出 DDL。
- 数据分析：报表/看板（指标口径待定，图表库待定，DevExtreme 自带图表可用）。
- 角色与权限；操作日志；用户列表分页；Alembic 迁移（表增多后）。

## 商品管理
- 「商品管理」菜单 = 自有商品目录（shop_* 表，见 API.md §4）。
- 待办：币种；SKU 多规格维度（颜色/尺码组合生成）；图片存储（现存本地 static/uploads，删除商品不清理文件；上线需对象存储或备份）；库存流水；批量导入导出；分类 `status` 目前不影响商品录入。
- 页面：/goods（列表+SKU 子表）、/goodsEdit（商品详情，内容标签页）、/goodsCategories（树）、/goodsAttributes、/goodsLanguages；共用 `static/js/lib/shop.js`。
- 多语言待办：批量导入导出译文、机器翻译辅助、翻译完成度展示（哪些商品缺哪种语言）、品牌/供应商是否需要多语言、价格是否按语言/地区区分（币种）——待确认。
- 多语言：列表页每多一种启用语言就多一列，语言多了表格会很宽，届时需要「按语言开关列」；商品文本属性的译文只存「属性值」，若属性名改名需同步处理（译文按属性名取键）。

## Shopify 对接
- 一期范围已确认：同一组织下不限 Shopify 店铺；mzShop 为商品、价格、库存主数据源；商品可发布到多个店铺；Shopify 后台修改不反向覆盖，只告警；订单与 Webhook 后续处理。
- `ddl/025_shopify_push.sql` 已执行；店铺连接配置、连接测试、同步任务 worker、同步任务页面、商品/变体/图片/SKU 区域价格/库存 GraphQL 推送已实现。推送严格使用店铺语言，商品属性不再拼接描述。Taxonomy 分类与类别属性同步使用已执行的 `031_shopify_taxonomy.sql` / `032_shopify_taxonomy_attributes.sql`。另一个已执行的 `031_shopify_taxonomy_mapping.sql` 所建两张简化表未接入应用，待人工确认后另出清理 DDL。待办：远端修改告警（依赖后续 Webhook 或定时对账）、远端归档。
- `ddl/026_shop_goods_sku_region.sql` 已执行：SKU 只管理规格、编码、成本、库存、启用；价格页维护商品区域基础价和 SKU 区域覆盖价；单规格商品可一键创建默认 SKU。SKU 差异价币种已改为始终继承区域币种，`ddl/027_drop_sku_region_currency.sql` 待人工执行。
- `ddl/030_shop_goods_store_product_url.sql` 待人工执行：商品店铺关联新增只读商品网址，Shopify 同步成功后自动回写。
- 2026-11-19 应用安装后真实连接成功：测试店币种 USD，启用 Location 为 `Guang Zhou Zhan`，发布渠道包含 `Online Store`，一期所需 scopes 已授权。当前业务数据仍缺 Shopify 店铺绑定和 SKU，且已有“国内”价格为 CNY；在补齐 USD 区域价和库存前不能做首件真实推送。
- Webhook HMAC 校验与投递去重已实现；公网入口确定为 `https://admin.monozex.com:10086`，采用 win-acme + Aliyun DNS-01 自动签发/续期并由 Apache TLS 反代。待完成首次凭据录入、证书签发、公网 A 记录修正和 Shopify 实际注册/投递验证。
- `ddl/031_shopify_taxonomy.sql` 已执行；Shopify product-taxonomy 已固定跟随 Admin API `2026-10` 稳定版，已导入中英文分类 64,292 条，页面、分类绑定及推送分类继承逻辑已实测。
- `ddl/032_shopify_taxonomy_attributes.sql` 已执行；已导入官方属性 12,334 条、属性值 197,413 条、分类属性关系 509,014 条。分类属性映射、单个本地选项绑定多个官方值、标准 Metaobject 创建/复用及商品推送闭环已实测。
- `ddl/033_rebuild_perfume_attributes.py` 待人工执行：删除香水分类旧属性及 36 个商品旧值，重建为 Eaux de Parfum 的 19 个官方属性代理和全部官方值映射；默认仅预览，`--apply` 自动备份，支持 `--rollback`。官方属性/值浏览与整体更新页面 `/shopifyTaxonomyAttributes` 已实现。
- 固定组合与订单库存闭环见 `BUNDLE.md`；`ddl/034_bundle_inventory.sql`、`035_shopify_order_stock.sql` 已执行，组合版本、单地点主库存、Shopify fixed bundle、普通 SKU 绝对库存写入与远端回读校验、订单/退款镜像、Webhook 幂等和极简退货入库已接入。待配置公网 HTTPS 后注册 Webhook；旧 `shop_goods_sku.stock` 不再作为主库存且未自动迁移。
