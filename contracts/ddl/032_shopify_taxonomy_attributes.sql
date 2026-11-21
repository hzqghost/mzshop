-- ============================================================
-- 032 Shopify 官方分类属性、属性值及 mzShop 映射
-- 用途：缓存 Shopify product-taxonomy 属性/预定义值/分类适用关系，保存本地属性映射及店铺 Metaobject 映射。
-- 影响：新增 5 张表；不修改现有表；无外键，级联由应用层处理。
-- 预览：SELECT COUNT(*) FROM shopify_taxonomy_category; SELECT COUNT(*) FROM shop_attribute;
-- 执行：人工审核后执行本文件，再重启 admin，并在「标准分类」重新执行“从 Shopify 更新”。
-- 回滚前预览：SELECT COUNT(*) FROM shopify_attribute_map; SELECT COUNT(*) FROM shopify_taxonomy_attribute;
-- 回滚：DROP TABLE IF EXISTS shopify_taxonomy_metaobject_map, shopify_attribute_map,
--   shopify_taxonomy_category_attribute, shopify_taxonomy_attribute_value, shopify_taxonomy_attribute;
-- ============================================================

CREATE TABLE shopify_taxonomy_attribute (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  taxonomy_gid VARCHAR(100) NOT NULL COMMENT 'TaxonomyAttribute GID',
  handle VARCHAR(180) NOT NULL DEFAULT '' COMMENT '基础属性 handle',
  name_zh VARCHAR(255) NOT NULL DEFAULT '' COMMENT '中文名称',
  name_en VARCHAR(255) NOT NULL DEFAULT '' COMMENT '英文名称',
  description_zh VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '中文说明',
  description_en VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '英文说明',
  is_active TINYINT NOT NULL DEFAULT 1 COMMENT '1当前版本有效 0已移除',
  version VARCHAR(30) NOT NULL DEFAULT '' COMMENT '分类版本',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id), UNIQUE KEY uq_shopify_taxonomy_attribute_gid (taxonomy_gid),
  KEY idx_shopify_taxonomy_attribute_active (is_active, handle)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 官方分类属性';

CREATE TABLE shopify_taxonomy_attribute_value (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  attribute_id INT UNSIGNED NOT NULL COMMENT 'shopify_taxonomy_attribute.id',
  taxonomy_gid VARCHAR(100) NOT NULL COMMENT 'TaxonomyValue GID',
  handle VARCHAR(255) NOT NULL DEFAULT '' COMMENT '官方值 handle',
  name_zh VARCHAR(255) NOT NULL DEFAULT '' COMMENT '中文名称',
  name_en VARCHAR(255) NOT NULL DEFAULT '' COMMENT '英文名称',
  is_active TINYINT NOT NULL DEFAULT 1 COMMENT '1当前版本有效 0已移除',
  version VARCHAR(30) NOT NULL DEFAULT '' COMMENT '分类版本',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id), UNIQUE KEY uq_shopify_taxonomy_value_gid (taxonomy_gid),
  KEY idx_shopify_taxonomy_value_attribute (attribute_id, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 官方分类属性预定义值';

CREATE TABLE shopify_taxonomy_category_attribute (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  taxonomy_category_id INT UNSIGNED NOT NULL COMMENT 'shopify_taxonomy_category.id',
  taxonomy_attribute_id INT UNSIGNED NOT NULL COMMENT 'shopify_taxonomy_attribute.id',
  handle VARCHAR(180) NOT NULL COMMENT '该分类实际标准元字段 key',
  name_zh VARCHAR(255) NOT NULL DEFAULT '' COMMENT '该分类中的中文名称',
  name_en VARCHAR(255) NOT NULL DEFAULT '' COMMENT '该分类中的英文名称',
  description_zh VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '该分类中的中文说明',
  description_en VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '该分类中的英文说明',
  is_extended TINYINT NOT NULL DEFAULT 0 COMMENT '1扩展属性 0基础属性',
  is_active TINYINT NOT NULL DEFAULT 1 COMMENT '1当前版本适用 0历史关系',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id), UNIQUE KEY uq_shopify_category_attribute (taxonomy_category_id, handle),
  KEY idx_shopify_category_attribute_attr (taxonomy_attribute_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 标准分类适用属性';

CREATE TABLE shopify_attribute_map (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  category_id INT UNSIGNED NOT NULL COMMENT 'shop_category.id，本地映射生效分类',
  category_attribute_id INT UNSIGNED NOT NULL COMMENT 'shopify_taxonomy_category_attribute.id',
  local_attribute_id INT UNSIGNED NOT NULL COMMENT 'shop_attribute.id',
  value_map JSON NULL COMMENT '本地选项文本到 shopify_taxonomy_attribute_value.id 的映射',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id), UNIQUE KEY uq_shopify_attribute_map (category_id, category_attribute_id),
  KEY idx_shopify_attribute_map_local (local_attribute_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='mzShop 属性与 Shopify 分类属性映射';

CREATE TABLE shopify_taxonomy_metaobject_map (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id INT UNSIGNED NOT NULL COMMENT 'store.id',
  category_attribute_id INT UNSIGNED NOT NULL COMMENT 'Shopify 分类属性关系 id',
  taxonomy_value_id INT UNSIGNED NOT NULL COMMENT 'Shopify 官方属性值 id',
  metaobject_gid VARCHAR(100) NOT NULL COMMENT '店铺中的 Metaobject GID',
  metaobject_type VARCHAR(180) NOT NULL DEFAULT '' COMMENT '标准 Metaobject type',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id), UNIQUE KEY uq_shopify_taxonomy_metaobject (store_id, category_attribute_id, taxonomy_value_id),
  KEY idx_shopify_taxonomy_metaobject_gid (store_id, metaobject_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 店铺标准分类属性值 Metaobject 映射';
