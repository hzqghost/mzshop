-- 041 运费模板改由商品区域销售价格选择（待人工审核执行）
-- 用途：运费模板归属从“商品×店铺”调整为“商品×销售区域”。
-- 影响：shop_goods_region 增加 shipping_template_id；旧 shop_goods_store.shipping_template_id 暂时保留但应用不再读写。
-- 兼容：无法可靠地把店铺模板自动映射到销售区域，本脚本不自动迁移；已有商品需在区域销售价格中人工选择模板。
-- 预览：
--   SELECT goods_id, store_id, shipping_template_id FROM shop_goods_store WHERE shipping_template_id <> 0;
--   SELECT goods_id, region_id FROM shop_goods_region ORDER BY goods_id, region_id;
-- 执行：审核并备份后执行本文件，再重启 mzshop-admin。
-- 回滚：删除新增索引和字段；旧店铺模板字段仍保留，可恢复旧版应用。

ALTER TABLE shop_goods_region
  ADD COLUMN shipping_template_id INT NOT NULL DEFAULT 0 COMMENT 'shipping_template.id，0表示未绑定' AFTER currency,
  ADD KEY idx_shop_goods_region_shipping_template (shipping_template_id);

-- 回滚（仅人工确认后执行）：
-- ALTER TABLE shop_goods_region DROP KEY idx_shop_goods_region_shipping_template, DROP COLUMN shipping_template_id;
