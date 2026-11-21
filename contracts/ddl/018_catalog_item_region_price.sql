-- ============================================================
-- 018 产品目录：采购价，以及按区域保存的售价（随本次需求执行）
-- 用途：采购价是目录条目上的独立金额。
--       价格、建议售价、最低售价、最高售价、币种改到区域价格表，
--       同一行再记运费、最快/最慢到达天数、税费。
--       条目上原来的价格和币种列保留，保存时写入排序最前的那个区域，列表筛选仍可用。
-- 影响：supplier_catalog_item 增加 purchase_price；新增 supplier_catalog_item_region
-- 兼容性：MySQL 8；在线加列；不建外键
-- 回滚：DROP TABLE IF EXISTS supplier_catalog_item_region;
--       ALTER TABLE supplier_catalog_item DROP COLUMN purchase_price;
-- ============================================================

ALTER TABLE supplier_catalog_item
  ADD COLUMN purchase_price DECIMAL(12,2) NULL COMMENT '采购价' AFTER price;

CREATE TABLE supplier_catalog_item_region (
  id                INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  item_id           INT UNSIGNED NOT NULL COMMENT 'supplier_catalog_item.id',
  region_id         INT UNSIGNED NOT NULL COMMENT 'sys_region.id',
  price             DECIMAL(12,2) NULL COMMENT '价格',
  suggested_price   DECIMAL(12,2) NULL COMMENT '建议售价',
  min_price         DECIMAL(12,2) NULL COMMENT '最低售价',
  max_price         DECIMAL(12,2) NULL COMMENT '最高售价',
  currency          VARCHAR(3)   NOT NULL DEFAULT '' COMMENT '币种，取通用属性 currency 的编码',
  shipping_fee      DECIMAL(12,2) NULL COMMENT '运费',
  arrival_days_min  INT          NULL COMMENT '最快到达天数',
  arrival_days_max  INT          NULL COMMENT '最慢到达天数',
  tax               DECIMAL(12,2) NULL COMMENT '税费',
  created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_catalog_item_region (item_id, region_id),
  KEY idx_catalog_item_region_region (region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='供应商产品目录的区域价格';
