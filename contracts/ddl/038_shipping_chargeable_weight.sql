-- 038 按计费重量与商品/SKU 包装尺寸（待人工审核执行）
-- 用途：国际运费支持实际重量与体积重量取较大值；SKU 尺寸为空时继承商品默认包装尺寸。
-- 影响：shipping_template、shop_goods、shop_goods_sku 新增字段；不修改历史模板和商品数据。
-- 兼容：历史 weight 模板保持不变；新增 chargeable 模板必须配置体积系数，默认 5000。
-- 预览：
--   SELECT id, name, calc_type FROM shipping_template ORDER BY id;
--   SELECT COUNT(*) AS goods_count FROM shop_goods;
--   SELECT COUNT(*) AS sku_count FROM shop_goods_sku;
-- 执行：审核并备份后执行本文件；执行后重启 mzshop-admin。
-- 回滚：确认没有 chargeable 模板且新增尺寸不再使用后，按文件末尾语句人工回滚。

ALTER TABLE shipping_template
  ADD COLUMN volume_divisor INT UNSIGNED NOT NULL DEFAULT 5000 COMMENT '体积重系数，仅按计费重量使用' AFTER calc_type;

ALTER TABLE shop_goods
  ADD COLUMN package_length_mm INT UNSIGNED NULL COMMENT '默认包装长度（毫米）' AFTER weight_g,
  ADD COLUMN package_width_mm  INT UNSIGNED NULL COMMENT '默认包装宽度（毫米）' AFTER package_length_mm,
  ADD COLUMN package_height_mm INT UNSIGNED NULL COMMENT '默认包装高度（毫米）' AFTER package_width_mm;

ALTER TABLE shop_goods_sku
  ADD COLUMN package_length_mm INT UNSIGNED NULL COMMENT 'SKU包装长度（毫米），空值继承商品' AFTER weight_g,
  ADD COLUMN package_width_mm  INT UNSIGNED NULL COMMENT 'SKU包装宽度（毫米），空值继承商品' AFTER package_length_mm,
  ADD COLUMN package_height_mm INT UNSIGNED NULL COMMENT 'SKU包装高度（毫米），空值继承商品' AFTER package_width_mm;

-- 回滚（仅人工确认后执行）：
-- ALTER TABLE shop_goods_sku DROP COLUMN package_height_mm, DROP COLUMN package_width_mm, DROP COLUMN package_length_mm;
-- ALTER TABLE shop_goods DROP COLUMN package_height_mm, DROP COLUMN package_width_mm, DROP COLUMN package_length_mm;
-- ALTER TABLE shipping_template DROP COLUMN volume_divisor;
