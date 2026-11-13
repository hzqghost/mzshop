# 现有表清单

> 新增/修改表必须同步本文件。库：`pdc_shop`。目前仅后台系统表，**电商业务表尚未设计**。

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
| kind | varchar(20) | grid / form；与 user_id 唯一（`uq_ui_style_user_kind`） |
| data | json | 样式值，校验见 `ui_style.py` |
| updated_at | datetime | |

## 采集系统表（2026-11-10 已按 ddl/001_crawl_tables.sql 在 pdc_shop 创建）
字段以 DDL 文件为准（含中文 Comment），设计说明见 [CRAWLER.md](CRAWLER.md)。

| 表 | 说明 |
|---|---|
| crawl_task | 采集任务（含定时设置，默认不定时） |
| crawl_run | 任务执行记录 |
| crawl_run_unit | 展开的采集单元（分类 × 属性值） |
| product | 商品，(platform, item_id) 唯一，覆盖更新 |
| product_review | 商品评价 / 卖家反馈（review_type 区分） |
| product_snapshot | 价格浏览量快照，每次采集追加 |

## 自有商品目录（DDL：`ddl/002_shop_tables.sql`，已执行；无外键，级联在应用层）
| 表 | 说明 |
|---|---|
| shop_category | 商品分类，多级（parent_id），(parent_id, name) 唯一 |
| shop_attribute | 属性定义，category_ids JSON 数组（多选，空=通用）；input_type text/textarea/select/multiselect/number；options JSON |
| shop_goods | 商品 SPU：goods_no 唯一、cost_price 拿货价、sale_price 销售价、shipping_fee 运费、attr_values JSON、main_image_url 冗余首图、status 默认下架；brand_id/supplier_id 结构化引用（0=未设置），旧字符串列 brand/supplier 待应用切换后删除 |
| shop_goods_image | 商品图片，按 sort_order，首张为主图 |
| shop_goods_sku | 规格 SKU：sku_code 唯一、cost_price、sale_price、stock |

## 商品内容多语言（DDL：`ddl/003_shop_i18n.sql`，已执行）
| 表 | 说明 |
|---|---|
| shop_language | 语言，code 唯一，is_default 仅一条，基础表内容即默认语言 |
| shop_translation | 译文，(entity_type, entity_id, lang_code, field_name) 唯一；options / attr_values 存 JSON 文本 |

## 供应商产品目录（DDL：`ddl/010_supplier_catalog.sql`，已执行；无外键，级联在应用层）
| 表 | 说明 |
|---|---|
| supplier | 供应商档案：name 唯一、website/联系人、default_currency、excel_mapping JSON（Excel 列映射模板，导入时自动套用） |
| brand | 品牌字典：name 唯一（默认语言）、logo_url、website、remark、sort_order（拖动排序，越小越靠前）、status；其他语言的品牌名存 shop_translation（entity_type=brand, field_name=name，无 DDL 变更）；被 shop_goods.brand_id / supplier_catalog_item.brand_id 引用时不能删（应用层守卫） |
| supplier_catalog_item | 供应商产品目录条目（选品池）：(supplier_id, supplier_sku) 唯一；品牌为公共字段（brand_id 结构化 + brand_name 原文）；attrs JSON 供应商原文（溯源）、mapped_attrs JSON 映射 shop_attribute 后的标准化值；description 为导入原文，remark 为资料 HTML；status 0待核对/1已核对/2已选品/3已忽略，选品后回填 goods_id |

## 种子数据
- `ddl/004_seed_perfume_attributes.py`：给根分类「香水」写入 15 个常用属性（中英文，按重要性排序：浓度*、容量*、香调、香名/系列、成色、包装、前/中/后调、适用季节、持久度、产品形态、条形码、产地、保质期；*必填）。按「属性名 + 适用分类集合」判重（脚本已适配 `category_ids`），可重复执行。性别未建属性：由子分类（女士/男士/中性）表达。

## 变更记录
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
