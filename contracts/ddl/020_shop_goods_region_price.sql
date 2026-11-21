-- ============================================================
-- 020 商品：拿货价留在商品上，售价和运费按区域保存（随本次需求执行）
-- 用途：商品详情的价格改成和产品目录一样。
--       拿货价仍是 shop_goods.cost_price。
--       价格、建议售价、最低售价、最高售价、币种、运费、最快/最慢到达天数、税费
--       记在 shop_goods_region，一个区域一行。
--       shop_goods.sale_price / shipping_fee 保留，保存时写入排序最前的那个区域，
--       商品列表的销售价、运费、利润筛选仍可用。
-- 影响：新增 shop_goods_region
-- 兼容性：MySQL 8；不建外键
-- 回滚：DROP TABLE IF EXISTS shop_goods_region;
-- ============================================================

CREATE TABLE shop_goods_region (
  id                INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  goods_id          INT UNSIGNED NOT NULL COMMENT 'shop_goods.id',
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
  UNIQUE KEY uq_shop_goods_region (goods_id, region_id),
  KEY idx_shop_goods_region_region (region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品的区域价格';
