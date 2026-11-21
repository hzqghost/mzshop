-- ============================================================
-- 031 Shopify Taxonomy 分类与类别属性映射
-- 用途：
--   1. 将 mzShop 商品分类显式映射到 Shopify TaxonomyCategory；
--   2. 在分类上下文中，将 mzShop 属性映射到 Shopify TaxonomyAttribute / 标准 category metafield；
--   3. 将本地选项值显式映射到一个或多个 Shopify TaxonomyValue，禁止按名称猜测。
-- 影响：新增两张映射表；不修改商品、分类、属性及现有 Shopify 映射数据。
-- 预览：
--   SELECT id, parent_id, name FROM shop_category ORDER BY parent_id, id;
--   SELECT id, name, input_type, options FROM shop_attribute ORDER BY sort_order, id;
-- 执行：人工审核后执行本文件；执行完成后再启用 Shopify Taxonomy 映射接口与同步。
-- 回滚前预览：
--   SELECT * FROM shopify_taxonomy_attribute_map ORDER BY category_id, attribute_id;
--   SELECT * FROM shopify_taxonomy_category_map ORDER BY category_id;
-- 回滚：
--   DROP TABLE shopify_taxonomy_attribute_map;
--   DROP TABLE shopify_taxonomy_category_map;
-- 注意：
--   无外键；删除分类/属性时由应用层级联删除映射。
--   value_map 格式：
--   {"本地值":[{"taxonomy_value_gid":"gid://shopify/TaxonomyValue/…",
--                "metaobject_gid":"gid://shopify/Metaobject/…","name":"Shopify value"}]}
-- ============================================================

CREATE TABLE shopify_taxonomy_category_map (
  id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  category_id            INT UNSIGNED NOT NULL COMMENT 'shop_category.id',
  taxonomy_category_gid  VARCHAR(120) NOT NULL COMMENT 'Shopify TaxonomyCategory GID',
  taxonomy_category_name VARCHAR(500) NOT NULL DEFAULT '' COMMENT 'Shopify 分类完整英文路径，仅展示',
  created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_taxonomy_category (category_id),
  KEY idx_shopify_taxonomy_category_gid (taxonomy_category_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='mzShop 分类到 Shopify Taxonomy 分类映射';

CREATE TABLE shopify_taxonomy_attribute_map (
  id                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  category_id                 INT UNSIGNED NOT NULL COMMENT 'shop_category.id，映射上下文',
  attribute_id                INT UNSIGNED NOT NULL COMMENT 'shop_attribute.id',
  taxonomy_attribute_gid      VARCHAR(120) NOT NULL COMMENT 'Shopify TaxonomyAttribute GID',
  taxonomy_attribute_name     VARCHAR(200) NOT NULL DEFAULT '' COMMENT 'Shopify 属性英文名，仅展示',
  metafield_namespace         VARCHAR(100) NOT NULL DEFAULT 'shopify' COMMENT 'Shopify 标准 metafield namespace',
  metafield_key               VARCHAR(100) NOT NULL COMMENT 'Shopify 标准 category metafield key',
  metafield_type              VARCHAR(100) NOT NULL DEFAULT 'list.metaobject_reference' COMMENT 'Shopify metafield 类型',
  metaobject_type             VARCHAR(100) NOT NULL DEFAULT '' COMMENT '启用后的 Shopify 标准 metaobject 类型',
  value_map                   JSON NULL COMMENT '本地值到 TaxonomyValue 及店铺 Metaobject 的显式映射',
  created_at                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_taxonomy_attribute (category_id, attribute_id),
  KEY idx_shopify_taxonomy_attribute_gid (taxonomy_attribute_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='mzShop 属性到 Shopify 类别属性映射';
