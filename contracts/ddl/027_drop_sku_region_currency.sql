-- ============================================================
-- 027 删除 SKU 区域价格中的冗余币种
-- 用途：SKU 差异价不再单独维护币种，始终使用 shop_goods_region 的区域币种。
-- 影响：删除 shop_goods_sku_region.currency；删除仅保存币种、没有任何差异价格的无效覆盖记录。
-- 数据说明：原 SKU 覆盖币种将被丢弃，运行时代码和 Shopify 推送均已改为读取区域币种。
-- 兼容性：MySQL 8；执行前请确认应用代码已更新。
-- 预览：
--   SELECT COUNT(*) AS currency_only_rows
--   FROM shop_goods_sku_region
--   WHERE price IS NULL AND suggested_price IS NULL AND min_price IS NULL AND max_price IS NULL;
--   SELECT currency, COUNT(*) AS row_count FROM shop_goods_sku_region GROUP BY currency;
-- 执行：人工审核后执行本文件；不要由应用启动过程自动执行。
-- 回滚：只能恢复字段结构，不能恢复原覆盖币种值：
--   ALTER TABLE shop_goods_sku_region
--     ADD COLUMN currency CHAR(3) NOT NULL DEFAULT '' COMMENT '币种；空表示继承商品区域币种' AFTER max_price;
-- ============================================================

DELETE FROM shop_goods_sku_region
WHERE price IS NULL
  AND suggested_price IS NULL
  AND min_price IS NULL
  AND max_price IS NULL;

ALTER TABLE shop_goods_sku_region
  DROP COLUMN currency;
