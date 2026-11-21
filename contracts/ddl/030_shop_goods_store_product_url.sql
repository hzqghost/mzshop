-- 用途：保存每个商品在各店铺中的商品详情网址，由平台同步成功后自动回写。
-- 影响：shop_goods_store 新增 product_url；历史记录默认空字符串，不修改现有绑定关系。
-- 预览：
--   SELECT id, goods_id, store_id, allowed FROM shop_goods_store ORDER BY id;
-- 执行：人工审核后在测试库执行下列 ALTER；执行完成后再重启 admin 与 Shopify worker。
-- 回滚前预览：
--   SELECT id, goods_id, store_id, product_url FROM shop_goods_store WHERE product_url <> '' ORDER BY id;
-- 回滚：ALTER TABLE shop_goods_store DROP COLUMN product_url;
-- 注意：回滚会丢失已经回写的店铺商品网址，但不影响 Shopify 商品映射及商品本身。

ALTER TABLE shop_goods_store
  ADD COLUMN product_url VARCHAR(500) NOT NULL DEFAULT '' COMMENT '该商品在店铺中的商品网址' AFTER allowed;
