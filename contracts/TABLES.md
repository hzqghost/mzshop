# 现有表清单

> 新增/修改表必须同步本文件。库：`pdc_shop`。包含后台系统、商品、店铺、库存、订单及 Shopify 对接表。

## sys_user 后台用户
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK 自增 | |
| username | varchar(50) 唯一 | 登录名，创建后不可改 |
| password_hash | varchar(255) | `scrypt$salt$digest` |
| real_name | varchar(50) 默认'' | 姓名 |
| email | varchar(100) 默认'' | |
| phone | varchar(30) 默认'' | |
| status | smallint 默认1 | 1启用 0禁用 |
| created_at / updated_at | datetime | 默认 now，updated 随更新 |

## sys_ui_style 用户界面样式配置
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK 自增 | |
| user_id | int 索引 | 0 为内置超级管理员 |
| kind | varchar(20) | menu / grid / form；与 user_id 唯一（`uq_ui_style_user_kind`） |
| data | json | 样式值，校验见 `ui_style.py` |
| updated_at | datetime | |

## 自有商品目录（DDL：`ddl/002_shop_tables.sql`，已执行；无外键，级联在应用层）
| 表 | 说明 |
|---|---|
| shop_category | 商品分类，多级（parent_id），(parent_id, name) 唯一；code 为商品编码中的品类段，允许多个分类相同 |
| shop_attribute | 属性定义，category_ids JSON 数组（多选，空=通用）；input_type text/textarea/select/multiselect/number；options JSON |
| shop_goods | 商品 SPU：goods_no 唯一、cost_price 拿货价、sale_price 销售价、shipping_fee 运费、attr_values JSON、main_image_url 冗余首图、status 默认下架；brand_id/supplier_id 结构化引用（0=未设置），旧字符串列 brand/supplier 待应用切换后删除 |
| shop_goods_no_sequence | 商品编码流水（DDL `028`，已执行）：prefix 为品牌段与品类段拼接后的最终前缀；current_seq 为已占用流水，点击生成即原子递增，不回收 |
| shop_goods_image | 商品图片（DDL `033`）：按 sort_order；sku_id 为空是商品共用图片，非空是该 SKU 专用图片；第一张共用图片为商品主图 |
| shop_goods_sku | 规格 SKU：sku_code 唯一、cost_price、sale_price、stock |
| shop_goods_sku_region | SKU 区域价格覆盖（DDL `026`，币种冗余列由 `027` 删除）：(sku_id, region_id) 唯一；price/suggested/min/max 为空时继承商品区域价格对应字段，币种始终取 `shop_goods_region.currency` |

## 销售运费与包装（DDL：`ddl/037_shipping_template.sql`、`038_shipping_chargeable_weight.sql` 已执行；`039_shipping_packages.sql` 待人工执行）
| 表 | 说明 |
|---|---|
| shipping_template | 销售运费模板：币种、固定/实际重量/计费重量、体积重系数、分组满额免邮、最低/最高运费、未匹配区域处理和启用状态 |
| shipping_template_rule | 模板区域规则；region_id=0 是默认规则；固定计费保存 fixed_fee，重量计费保存首重/续重参数；priority 越小越优先 |
| shipping_package_box | 包装箱档案：外部长宽高以厘米 `DECIMAL(10,2)` 保存，另存空箱重量和启用状态 |
| shipping_package_group | 包装组：指向当前使用的包装箱；采购更换箱型时只修改此处 |
| shipping_package_group_image | 包装组参考图片，按 sort_order 排序，一个包装组最多由应用层限制为 20 张 |

`shop_goods_region.shipping_template_id` 保存商品在具体销售区域使用的模板，0 表示未绑定。模板仅参与运费试算和订单运费计算，不影响商品或店铺上架、SKU 保存、Shopify 推送。原 `shop_goods_store.shipping_template_id` 暂时保留用于核对旧数据，应用不再读写。

## 商品内容多语言（DDL：`ddl/003_shop_i18n.sql`，已执行）
| 表 | 说明 |
|---|---|
| shop_language | 语言，code 唯一，is_default 仅一条，基础表内容即默认语言 |
| shop_translation | 译文，(entity_type, entity_id, lang_code, field_name) 唯一；options / attr_values 存 JSON 文本 |

## 供应商产品目录（DDL：`ddl/010_supplier_catalog.sql`，已执行；无外键，级联在应用层）
| 表 | 说明 |
|---|---|
| supplier | 供应商档案：name 唯一、website/联系人、default_currency、excel_mapping JSON（Excel 列映射模板，导入时自动套用） |
| brand | 品牌字典：code 可空且唯一（空编码不占唯一，DDL `019_brand_code.sql`）、name 唯一；brand_type 区分 own 自有品牌 / third_party 第三方品牌；include_in_goods_no=0 时商品编码品牌段固定为 TH；其他字段与引用守卫不变 |
| supplier_catalog_item | 供应商产品目录条目（选品池）：(supplier_id, supplier_sku) 唯一；品牌为公共字段（brand_id 结构化 + brand_name 原文）；attrs JSON 供应商原文（溯源）、mapped_attrs JSON 映射 shop_attribute 后的标准化值；description 为导入原文，remark 为资料 HTML；status 0待核对/1已核对/2已选品/3已忽略，选品后回填 goods_id |
| supplier_document | 供应商文档（DDL `014_supplier_document.sql`）：supplier_id、title、doc_type（license/qualification/contract/pricelist/catalog/other）、file_url、file_name、file_size、remark。有文档的供应商不能删 |

## 销售平台与店铺（DDL：`ddl/021_platform_store.sql`）
| 表 | 说明 |
|---|---|
| platform | 销售平台。code、name 各自唯一；name_en、website、market、feature、remark；is_independent 1=独立站 |
| store | 店铺。platform_id 指向 platform；(platform_id, code)、(platform_id, name) 唯一。不保存独立站，列表里的值取所属平台 |
| store_category | 店铺绑定的商品分类。(store_id, category_id) 唯一；删除店铺或分类时由应用层清掉 |

## Shopify 主动推送（DDL：`ddl/025_shopify_push.sql`，已执行）
| 表 | 说明 |
|---|---|
| shopify_store_config | Shopify 店铺配置：store 一对一；固定 myshopify 域名、价格区域、内容语言、默认 Location、Publication、币种、连接状态。Client ID / Client Secret 不入库，只放 `.env` |
| shopify_product_map | mzShop 商品与各 Shopify 店铺 Product 的映射；保存内容摘要、同步状态、最后成功时间和远端改动告警 |
| shopify_variant_map | mzShop SKU 与各 Shopify 店铺 ProductVariant / InventoryItem 的映射 |
| shopify_sync_task | 持久化主动推送任务；支持领取、重试、失败记录。不得记录密钥、令牌或完整鉴权请求头 |

## Shopify 标准分类（DDL：`ddl/031_shopify_taxonomy.sql`，已执行）
| 表 | 说明 |
|---|---|
| shopify_taxonomy_category | Shopify 官方标准产品分类本地缓存；保存中英文名称/完整路径、TaxonomyCategory GID、父级、层级、末级标记、发布版本和有效状态；官方移除的分类保留并标记失效 |
| shopify_category_map | mzShop `shop_category` 与 Shopify 标准分类的一对一直接绑定；商品推送时本级未绑定会向上继承最近的绑定 |

## Shopify 分类属性（DDL：`ddl/032_shopify_taxonomy_attributes.sql`，已执行）
| 表 | 说明 |
|---|---|
| shopify_taxonomy_attribute | Shopify 官方分类属性基础定义，中英文名称、说明、handle、版本和有效状态 |
| shopify_taxonomy_attribute_value | 官方预定义 TaxonomyValue 及中英文名称；归属基础属性 |
| shopify_taxonomy_category_attribute | 分类实际适用属性；保留扩展属性在特定分类中的名称和标准元字段 key |
| shopify_attribute_map | 指定 mzShop 分类下，本地属性与 Shopify 分类属性以及本地选项与官方值的映射 |
| shopify_taxonomy_metaobject_map | 各 Shopify 店铺中已创建的标准属性值 Metaobject 稳定映射 |

## 固定组合、库存与订单（DDL：`034` / `035`，已执行）

> 业务口径见 `BUNDLE.md`。

| 表 | 说明 |
|---|---|
| shop_bundle_revision | 独立组合父 SKU 的不可变版本；同一父 SKU 的版本号唯一，发布唯一性由应用层保证 |
| shop_bundle_component | 组合版本的普通组件 SKU、每套数量与顺序；一期禁止嵌套组合 |
| stock_location | 本地库存地点；一期只有一个业务地点，但所有余额和流水保留 location_id |
| stock_balance | 普通 SKU 地点库存余额：在库、占用、不可售、安全库存 |
| stock_ledger | 库存变化流水；唯一幂等键防止 Webhook 重复扣减 |
| shopify_bundle_map | 各店铺最近成功同步的组合版本、摘要和状态 |
| shop_order | Shopify 订单镜像，不保存客户姓名、电话或地址 |
| shop_order_line | 普通行、组合父行及组件行；冻结版本、数量、金额、折扣、税费和成本 |
| shop_refund / shop_refund_line | Shopify 退款及组件退款行；不直接触发本地实物入库 |
| shop_return / shop_return_line | 极简退货收货与可售/不可售质检确认 |
| shopify_webhook_event | Webhook ID 幂等、主题、请求摘要和处理结果；不保存完整原文 |

## 国家地区与区域（DDL：`ddl/017_geo_region.sql`）
| 表 | 说明 |
|---|---|
| sys_geo | 国家地区树。parent_id=0 为顶级；code 全局唯一（ALL 全球、AFR/EUR/ASI/NAM/SAM/OCE/ANT 洲、ISO 国家码）；name_zh / name_en；is_leaf=1 为子节点（国家/地区，可被区域勾选），0 为分组。有下级或被区域引用时不能删。表为空时应用启动写入种子，已有数据不覆盖 |
| sys_region | 区域。name 唯一，sort_order 越小越靠前 |
| sys_region_country | 区域勾选的节点。(region_id, geo_id) 唯一；一个国家可以被多个区域勾选。geo_id 可以是国家，也可以是全球或洲（表示其下全部国家，不展开成国家 id） |

## 种子数据
- `ddl/004_seed_perfume_attributes.py`：给根分类「香水」写入 15 个常用属性（中英文，按重要性排序：浓度*、容量*、香调、香名/系列、成色、包装、前/中/后调、适用季节、持久度、产品形态、条形码、产地、保质期；*必填）。按「属性名 + 适用分类集合」判重（脚本已适配 `category_ids`），可重复执行。性别未建属性：由子分类（女士/男士/中性）表达。

## 变更记录
- `ddl/041_shipping_template_by_goods_region.sql`（待人工执行）：区域销售价格增加运费模板；旧店铺模板字段保留但退出业务逻辑。
- `ddl/040_shipping_package_group_images.sql`（待人工执行）：新增包装组多图表，不改变包装组与当前包装箱的一对一关系。
- `ddl/039_shipping_packages.sql`（待人工执行）：新增包装箱与包装组；商品、SKU、店铺引用包装组；尺寸改为厘米两位小数并移除 038 的商品/SKU 毫米尺寸列。
- `ddl/038_shipping_chargeable_weight.sql`（已执行）：模板增加按计费重量和体积重系数；商品及 SKU 增加可继承的包装长宽高（由 039 调整为包装组）。
- `ddl/037_shipping_template.sql`（已执行）：新增销售运费模板和区域规则；商品店铺绑定模板；SKU 增加可继承的重量。
- `ddl/036_drop_crawl_tables.sql`（待人工执行）：删除已停用数据采集模块的 6 张表及全部数据；应用代码、页面和独立采集进程已移除。
- `ddl/035_shopify_order_stock.sql`（已执行）：新增 Shopify 订单/订单行镜像、退款、退货入库确认与 Webhook 幂等记录。
- `ddl/034_bundle_inventory.sql`（已执行）：SKU 增加 normal/bundle 类型；新增固定组合版本/组件、库存地点/余额/流水及 Shopify 组合同步映射；店铺配置绑定本地库存地点。
- `ddl/033_goods_sku_image.sql`（已执行）：商品图片新增可空 `sku_id`；空值表示商品共用，非空表示指定 SKU 专用，商品主图只取第一张共用图片。
- `ddl/032_shopify_taxonomy_attributes.sql`（已执行）：新增 Shopify 分类专属属性、官方值、本地属性/值映射及店铺 Metaobject 映射；已导入 `2026-10` 官方属性 12,334 条、属性值 197,413 条、分类属性关系 509,014 条。
- `ddl/033_rebuild_perfume_attributes.py`（待人工执行）：将香水分类现有属性及商品值备份后删除，重建为当前映射 Shopify 香水类别的全部官方属性代理和官方值映射；支持预览、应用和备份回滚。
- `ddl/031_shopify_taxonomy.sql`（已执行）：新增 Shopify 官方标准分类缓存和 mzShop 分类关联；已导入 Shopify product-taxonomy `2026-10` 中英文分类 64,292 条。
- `ddl/029_reset_goods_no.py`（2026-11-19 已执行，最近一次 15:53）：36 个现有商品按最终前缀、商品 id 升序重排四位流水；同步 1 个原同码 SKU，并把流水表校准为 THFR1=5、THFR2=6、THFR3=25。
- `ddl/028_goods_no_rule.sql`（已执行）：分类新增可重复的编码；品牌新增类型和是否参与商品编码；新增按最终前缀原子占号的四位流水表。
- `ddl/026_shop_goods_sku_region.sql`（已执行）：新增 SKU 区域价格覆盖，SKU 保留规格/库存/成本，渠道取价优先 SKU 区域价、再继承商品区域基础价。
- `ddl/027_drop_sku_region_currency.sql`（待人工执行）：删除 SKU 区域覆盖中的冗余币种列及无价格的空覆盖；SKU 币种统一取商品区域币种。
- `ddl/025_shopify_push.sql`（已执行）：新增 Shopify 店铺配置、商品/SKU 映射和主动同步任务；一期仅 mzShop → Shopify 商品、价格、库存推送，不含 Webhook 与订单。
- `ddl/030_shop_goods_store_product_url.sql`（待人工执行）：`shop_goods_store.product_url` 保存商品在对应店铺中的详情网址；Shopify 同步成功后自动回写。
- `ddl/022_store_category.sql`：新增 `store_category`，店铺多选绑定 `shop_category`。
- `ddl/021_platform_store.sql`：新增 `platform`（销售平台）、`store`（店铺）。店铺不存独立站，读取时取平台的 `is_independent`。有店铺的平台不能删。
- `ddl/019_brand_code.sql`：`brand` 新增可空 `code`（品牌编码，唯一；空值不占唯一）。
- `ddl/015_catalog_item_price.sql`：`supplier_catalog_item` 新增 `suggested_price`（建议售价）、`min_price`（最低售价）、`max_price`（最高售价）、`price_rule`（价格规则，多行文本）、`lead_time`（交期）。
- `ddl/014_supplier_document.sql`：新增 `supplier_document`，产品池「供应商文档」按供应商归档上传的资料。
- `ddl/009_shop_attribute_categories.sql`（2026-11-12 已执行）：`shop_attribute` 的 `category_id`（单分类，0=通用）改为 `category_ids` JSON 数组（多选，空数组=通用）；原数据按 `[category_id]` 回填后删除旧列和唯一键 `uq_attribute_category_name`。同名属性改由后端校验（名称 + 适用分类集合完全相同才拒绝），多级同名仍允许就近覆盖。
- `ddl/011_catalog_item_remark.sql`（已执行）：`supplier_catalog_item` 新增可空 `remark` MEDIUMTEXT（资料 HTML），与 `description` 原文分开。
- `ddl/010_supplier_catalog.sql`（已执行）：新增 `supplier` 供应商档案、`brand` 品牌字典、`supplier_catalog_item` 供应商产品目录条目；`shop_goods` 新增 `brand_id`/`supplier_id`（0=未设置）并从旧字符串列回填，旧列待应用代码切换后删除。
- `ddl/005_shop_attribute_number.sql`（已执行）：`shop_attribute` 新增 `decimal_places`（小数位数，0=整数）、`unit`（单位，默认语言）；`input_type` 增加取值 `number`（只改了 Comment）。
- 「香水/容量」已改为数字（0 位小数，单位 ml / en: ml），种子脚本 `ddl/004_seed_perfume_attributes.py` 已同步。
- 「香水/保质期」也已改为数字（0 位小数，单位 个月 / months）；条形码保持文本（UPC/EAN 有前导 0，是标识不是数量）。

## 表格过滤器模板（DDL：`ddl/006_sys_grid_filter.sql`，已执行）
| 表 | 说明 |
|---|---|
| sys_grid_filter | 过滤器模板：(user_id, grid_key, name) 唯一；filter_value JSON；user_id 0 为内置超级管理员 |

## 表格布局（DDL：`ddl/008_sys_grid_layout.sql`，已执行）
| 表 | 说明 |
|---|---|
| sys_grid_layout | 布局：(user_id, grid_key) 唯一（覆盖保存）；layout JSON = {state, editMode}；设置菜单「保存布局 / 恢复布局」用 |

## 属性录入方式扩展（DDL：`ddl/007_shop_attribute_types.sql`，已执行，仅改列注释）
shop_attribute.input_type 增加 textarea、multiselect；options 对 select / multiselect 有效。多选的商品属性值存 shop_goods.attr_values（JSON，值为数组）。
