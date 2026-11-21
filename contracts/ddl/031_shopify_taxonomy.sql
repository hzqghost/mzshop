-- ============================================================
-- 031 Shopify 官方标准分类及本地分类关联
-- 用途：
--   1. 保存 Shopify 官方 product-taxonomy 发布的中英文标准分类树；
--   2. 保存 mzShop 商品分类与 Shopify 标准分类的一对一绑定。
-- 数据源：https://github.com/Shopify/product-taxonomy/releases/latest
-- 影响：新增 2 张表，不修改现有表；无外键，关联清理由应用层负责。
-- 导入：执行后在「店铺 → Shopify → 标准分类」点击“从 Shopify 更新”。
-- 预览：
--   SELECT COUNT(*) FROM shop_category;
--   SELECT id, name, parent_id FROM shop_category ORDER BY id LIMIT 100;
-- 执行：人工审核后在测试库执行本文件，再重启 admin。
-- 回滚前预览：
--   SELECT COUNT(*) AS category_count FROM shopify_taxonomy_category;
--   SELECT COUNT(*) AS mapping_count FROM shopify_category_map;
-- 回滚（会丢失 Shopify 标准分类缓存及全部分类绑定）：
--   DROP TABLE IF EXISTS shopify_category_map, shopify_taxonomy_category;
-- ============================================================

CREATE TABLE shopify_taxonomy_category (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  taxonomy_gid  VARCHAR(100)  NOT NULL COMMENT 'Shopify TaxonomyCategory GID',
  category_id   VARCHAR(60)   NOT NULL COMMENT '分类短 ID，如 hb-1-1',
  parent_gid    VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '上级 TaxonomyCategory GID，顶级为空',
  level         SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '树层级，顶级为 0',
  name_zh       VARCHAR(255)  NOT NULL DEFAULT '' COMMENT '简体中文名称',
  full_name_zh  VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '简体中文完整路径',
  name_en       VARCHAR(255)  NOT NULL DEFAULT '' COMMENT '英文名称',
  full_name_en  VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '英文完整路径',
  is_leaf       TINYINT       NOT NULL DEFAULT 0 COMMENT '1末级分类 0仍有下级',
  is_active     TINYINT       NOT NULL DEFAULT 1 COMMENT '1当前版本有效 0已被官方移除',
  version       VARCHAR(30)   NOT NULL DEFAULT '' COMMENT 'Shopify taxonomy 发布版本',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_taxonomy_gid (taxonomy_gid),
  UNIQUE KEY uq_shopify_taxonomy_category_id (category_id),
  KEY idx_shopify_taxonomy_parent (parent_gid),
  KEY idx_shopify_taxonomy_active_level (is_active, level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 官方标准产品分类';

CREATE TABLE shopify_category_map (
  id                    INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  category_id           INT UNSIGNED NOT NULL COMMENT 'shop_category.id',
  taxonomy_category_id  INT UNSIGNED NOT NULL COMMENT 'shopify_taxonomy_category.id',
  created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_category_map_category (category_id),
  KEY idx_shopify_category_map_taxonomy (taxonomy_category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='mzShop 分类与 Shopify 标准分类关联';
