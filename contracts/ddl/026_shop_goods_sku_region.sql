-- ============================================================
-- 026 SKU 区域价格覆盖（已于 2026-11-19 经授权执行）
-- 用途：SKU 继续管理规格、库存、成本；本表只保存 SKU 在指定区域对商品区域基础价的覆盖。
-- 取价顺序：SKU 区域价 -> 商品区域基础价；两者都没有时拒绝渠道推送。
-- 影响：新增 shop_goods_sku_region，不修改现有商品、SKU、区域价格数据。
-- 兼容性：MySQL 8；InnoDB；utf8mb4 / utf8mb4_unicode_ci；不建外键。
-- 预览：
--   SELECT id, goods_id, sku_code, spec_name, stock, status FROM shop_goods_sku ORDER BY goods_id, id;
--   SELECT goods_id, region_id, price, currency FROM shop_goods_region ORDER BY goods_id, region_id;
-- 执行：人工审核后执行本文件；本次会话已获用户授权。
-- 回滚前预览：SELECT COUNT(*) FROM shop_goods_sku_region;
-- 回滚：DROP TABLE IF EXISTS shop_goods_sku_region;
-- ============================================================

CREATE TABLE shop_goods_sku_region (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  goods_id         INT UNSIGNED NOT NULL COMMENT 'shop_goods.id，便于应用层级联清理',
  sku_id           INT UNSIGNED NOT NULL COMMENT 'shop_goods_sku.id',
  region_id        INT UNSIGNED NOT NULL COMMENT 'sys_region.id',
  price            DECIMAL(12,2) NULL COMMENT 'SKU 区域销售价；空表示继承商品区域价格',
  suggested_price  DECIMAL(12,2) NULL COMMENT 'SKU 区域建议售价',
  min_price        DECIMAL(12,2) NULL COMMENT 'SKU 区域最低售价',
  max_price        DECIMAL(12,2) NULL COMMENT 'SKU 区域最高售价',
  currency         CHAR(3) NOT NULL DEFAULT '' COMMENT '币种；空表示继承商品区域币种',
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_goods_sku_region (sku_id, region_id),
  KEY idx_shop_goods_sku_region_goods_region (goods_id, region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU 区域价格覆盖';
