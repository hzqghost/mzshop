-- ============================================================
-- 033 商品图片支持绑定规格 SKU
-- 用途：区分商品共用图片与某个 SKU 的专用图片
-- 影响：shop_goods_image 新增可空 sku_id，并增加商品/SKU/排序联合索引；现有图片全部保持为商品共用图片
-- 预览：SELECT COUNT(*) AS image_count FROM shop_goods_image;
-- 执行：人工确认后在 pdc_shop 库执行本文件
-- 回滚：见文件末尾；回滚只移除 SKU 绑定能力，不删除图片记录
-- 兼容性：MySQL 8；不建外键，SKU 删除约束由应用层处理
-- ============================================================

ALTER TABLE shop_goods_image
  ADD COLUMN sku_id INT UNSIGNED NULL COMMENT '专用 SKU shop_goods_sku.id，NULL 表示商品共用图片' AFTER goods_id,
  ADD KEY idx_goods_image_sku (goods_id, sku_id, sort_order);

-- ============================================================
-- 回滚：
-- ALTER TABLE shop_goods_image DROP KEY idx_goods_image_sku, DROP COLUMN sku_id;
-- ============================================================
