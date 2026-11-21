# Shopify 主动推送契约

> 当前范围：同一组织下不限店铺；mzShop 为商品、价格、库存主数据源；包含固定组合、订单/退款镜像和 Webhook，不反向覆盖商品资料。

## 1. 认证与版本

- 使用 GraphQL Admin API，版本由 `SHOPIFY_API_VERSION` 固定，当前为 `2026-10`。
- Custom App 的 `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET` 只在 `admin/.env` 保存。
- worker 通过 Client Credentials 为目标 `*.myshopify.com` 店铺取得短期令牌；令牌只缓存在进程内存，不入库、不进日志。
- 权限：`write_products`、`write_inventory`、`read_locations`、`read_publications`、`read_metaobjects`、`write_metaobjects`、`read_metaobject_definitions`、`write_metaobject_definitions`。

## 2. 店铺配置

- 只有所属平台 `code=shopify` 或 `name_en=shopify` 的店铺可以配置。
- `shop_domain` 必须是稳定的 `xxx.myshopify.com` 域名。
- 每家店铺必须选择一个 `sys_region`，价格取对应 `shop_goods_region.price`；价格缺失或区域币种与 Shopify 店铺币种不一致时拒绝推送，禁止猜汇率或把 CNY 数字直接作为 USD。
- 每家店铺还必须把 Shopify `default_location_gid` 绑定到一个本地 `stock_location_id`；普通 SKU 使用 `inventorySetQuantities` 推送 `stock_balance` 的绝对可售量并回读远端校验，组合父 SKU 库存由 Shopify 组件关系计算。
- `language_code` 为空时使用商品默认语言；非空时优先取 `shop_translation(goods)` 的名称和描述，缺失字段退回默认语言。
- 库存推送到 `default_location_gid`；商品启用时发布到 `publication_gid`。

## 3. 商品映射

- 商品使用 `productSet` 完整状态同步；已有映射时用 Product GID 更新，没有映射时创建。
- Product：标题、原始描述、品牌、上架状态、全部商品图片，以及 `mzshop.goods_id/goods_no` metafield。SKU 专用图片仍先作为 Product media 上传，再关联到对应 Shopify Variant；共用图片不绑定单个 Variant。商品属性不得拼入描述 HTML，也不使用 `mzshop.attributes` 自定义 JSON 代替 Shopify 原生类别属性。
- 商品分类通过显式映射设置 `Product.category`。属性仅按“mzShop 分类 + 属性”的已审核映射写入 Shopify 标准 category metafield；选项值必须映射到 Shopify `TaxonomyValue`，未映射内容跳过并告警，禁止按名称自动猜测。实际映射结构见 `ddl/031_shopify_taxonomy.sql` 与 `ddl/032_shopify_taxonomy_attributes.sql`。
- Shopify `Product type` 仅作末级分类兜底：末级分类有有效直接映射时清空；没有直接映射时（包括继承上级映射）写入末级分类的英文译文。英文译文缺失时拒绝推送，不回退中文。
- SKU：规格、SKU 编码、成本、库存跟踪、绝对可售库存；售价按“`shop_goods_sku_region` SKU 区域覆盖价 → `shop_goods_region` 商品区域基础价”取值，币种同样按覆盖值优先。
- `sku_type=bundle` 的父 SKU 在商品推送成功后使用 `productVariantRelationshipBulkUpdate` 整体重建组件关系；同时用 `priceInput.calculation=FIXED` 写入父 SKU 的区域有效售价并校验返回价格，禁止 Shopify 默认按组件价格合计覆盖固定组合价。所有组件必须先在该店铺存在 Variant 映射。组合同步版本和摘要保存到 `shopify_bundle_map`。
- 当前商品至少要有一个启用 SKU。绝对 HTTP(S) 图片直接推送；`/static/uploads/` 本地图片由 worker 通过 Shopify staged upload 直接上传，不依赖公网回调地址。其他相对图片通过 `SHOPIFY_ASSET_BASE_URL` 转为公网地址，该项留空时复用 `SHOPIFY_WEBHOOK_BASE_URL`；无法形成可用图片源时任务失败并显示原因，不得静默跳过。
- 商品与 SKU 的 Shopify GID 按店铺分别保存在映射表，同一商品可推送多个店铺。
- Shopify 标准分类从官方 `Shopify/product-taxonomy` 中与 `SHOPIFY_API_VERSION` 同版本的稳定 release 导入，避免较新 TaxonomyValue 被当前 Admin API 拒绝；更新不物理删除官方已移除分类，而是标记失效。
- mzShop 分类可直接绑定一个有效 Shopify 标准分类。商品推送时从商品本级开始逐级向上继承最近绑定，并把 TaxonomyCategory GID 写入 `ProductSetInput.category`；无任何绑定时不传分类。
- 官方属性和预定义值随标准分类更新一并导入。映射以“mzShop 分类 + Shopify 分类属性”为范围，本地属性必须适用于该分类；固定选项逐项绑定 TaxonomyValue。
- 分类属性页通过通用商品分类单选弹窗切换 mzShop 分类；表格固定左侧 Shopify 属性列、右侧 mzShop 属性列。香水分类只绑定语义可靠且能生成官方值的属性，当前为适用季节、香调和产品形态；无等价标准属性的本地字段不强行绑定。
- 推送映射完整的类别属性时，worker 自动启用店铺标准元字段定义、按 TaxonomyValue 创建/复用标准 Metaobject，并把 Metaobject GID 列表写入 `shopify.<attribute-handle>` 类别元字段。存在多个 taxonomy reference 字段而无法安全自动选择的复合属性会明确失败，不猜测字段。

## 4. 任务

- 后台只创建 `shopify_sync_task`；同一商品/店铺已有 pending 或 running 任务时跳过重复创建。
- 商品首次创建或后续同步成功后，把 Shopify 返回的在线商店网址（无返回值时使用固定店铺域名与 handle 生成）回写到 `shop_goods_store.product_url`；该字段只由同步程序维护，商品编辑页只读展示。
- worker 从 pending 任务中加锁领取，成功写 success；失败按指数退避重试，达到 `SHOPIFY_MAX_RETRIES` 后写 failed。
- 运行：`admin/.venv/Scripts/python tool/shopify/run.py`；调试单次任务加 `--once`。
- 日志和错误字段不得出现 Client Secret、访问令牌或完整鉴权请求头。

## 5. 订单、Webhook 与库存

- 店铺连接检查增加 `read_orders`；公网根地址由 `SHOPIFY_WEBHOOK_BASE_URL` 配置，只接受可信 HTTPS。
- 后台注册 `ORDERS_CREATE/UPDATED/CANCELLED/PAID`、`FULFILLMENTS_CREATE/UPDATE`、`REFUNDS_CREATE`。
- 回调固定为 `/api/v1/shopify/webhooks`，用 Client Secret 校验 HMAC，以 `(store_id, webhook_id)` 去重，只保存请求 SHA-256，不保存完整原文或客户资料。
- 收到订单/履约事件后通过 GraphQL 整单重读并差量对账：`paid` 才占用，发货同时减少在库和占用，取消释放；退款只更新财务数量，不自动入库。
- mzShop 退货确认按组件写入可售或不可售库存；所有变化与 `stock_ledger` 同事务并使用唯一幂等键。
- 库存变化合并为 `sync_inventory` 任务；任务执行时读取最新余额，因此旧任务不携带过期库存快照。
- 库存写入后必须回读绑定 Location 的 `available` 数量；与 mzShop 不一致时任务失败，不得误报成功。

## 6. 删除级联

- 删除商品：应用层先删除 Shopify task、variant map、product map。
- 删除店铺：应用层先删除 Shopify task、variant map、product map、store config。
- 删除本地记录不会主动删除 Shopify 远端商品；远端归档动作后续单独实现。
