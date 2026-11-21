-- 039 包装箱档案、包装组与厘米尺寸（待人工审核执行）
-- 用途：包装尺寸从商品/SKU 中抽离；更换箱型只需修改包装组当前箱；尺寸统一厘米并保留两位小数。
-- 影响：新增 shipping_package_box、shipping_package_group；商品、SKU、店铺增加包装组；删除 038 的毫米尺寸列。
-- 兼容：038 尺寸字段尚未投入业务录入；执行前仍须预览确认没有已填写数据。重量字段继续保留。
-- 预览：
--   SELECT id, goods_no, package_length_mm, package_width_mm, package_height_mm FROM shop_goods
--   WHERE package_length_mm IS NOT NULL OR package_width_mm IS NOT NULL OR package_height_mm IS NOT NULL;
--   SELECT id, sku_code, package_length_mm, package_width_mm, package_height_mm FROM shop_goods_sku
--   WHERE package_length_mm IS NOT NULL OR package_width_mm IS NOT NULL OR package_height_mm IS NOT NULL;
-- 执行：上述两条预览必须为空；审核并备份后执行本文件，再重启 mzshop-admin。
-- 回滚：先确认包装组引用和箱型数据可舍弃，再按末尾语句人工回滚；已删除的毫米尺寸不会自动恢复数据。

CREATE TABLE shipping_package_box (
  id               INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  name             VARCHAR(100)  NOT NULL COMMENT '箱型名称',
  length_cm        DECIMAL(10,2) NOT NULL COMMENT '外部长（厘米）',
  width_cm         DECIMAL(10,2) NOT NULL COMMENT '外部宽（厘米）',
  height_cm        DECIMAL(10,2) NOT NULL COMMENT '外部高（厘米）',
  empty_weight_g   INT UNSIGNED  NOT NULL DEFAULT 0 COMMENT '空箱重量（克）',
  status           TINYINT       NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  remark           VARCHAR(500)  NOT NULL DEFAULT '' COMMENT '备注',
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shipping_package_box_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='物流包装箱档案';

CREATE TABLE shipping_package_group (
  id               INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  name             VARCHAR(100)  NOT NULL COMMENT '包装组名称',
  current_box_id   INT           NOT NULL DEFAULT 0 COMMENT '当前 shipping_package_box.id',
  status           TINYINT       NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  remark           VARCHAR(500)  NOT NULL DEFAULT '' COMMENT '备注',
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shipping_package_group_name (name),
  KEY idx_shipping_package_group_box (current_box_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='物流包装组';

ALTER TABLE shop_goods
  ADD COLUMN shipping_package_group_id INT NOT NULL DEFAULT 0 COMMENT '默认包装组，0表示未设置' AFTER weight_g,
  ADD KEY idx_shop_goods_shipping_package_group (shipping_package_group_id),
  DROP COLUMN package_height_mm,
  DROP COLUMN package_width_mm,
  DROP COLUMN package_length_mm;

ALTER TABLE shop_goods_sku
  ADD COLUMN shipping_package_group_id INT NOT NULL DEFAULT 0 COMMENT '包装组，0表示继承商品/店铺' AFTER weight_g,
  ADD KEY idx_shop_goods_sku_shipping_package_group (shipping_package_group_id),
  DROP COLUMN package_height_mm,
  DROP COLUMN package_width_mm,
  DROP COLUMN package_length_mm;

ALTER TABLE store
  ADD COLUMN shipping_package_group_id INT NOT NULL DEFAULT 0 COMMENT '默认包装组，0表示未设置' AFTER remark,
  ADD KEY idx_store_shipping_package_group (shipping_package_group_id);

-- 回滚（仅人工确认后执行）：
-- ALTER TABLE store DROP KEY idx_store_shipping_package_group, DROP COLUMN shipping_package_group_id;
-- ALTER TABLE shop_goods_sku DROP KEY idx_shop_goods_sku_shipping_package_group, DROP COLUMN shipping_package_group_id,
--   ADD COLUMN package_length_mm INT UNSIGNED NULL, ADD COLUMN package_width_mm INT UNSIGNED NULL, ADD COLUMN package_height_mm INT UNSIGNED NULL;
-- ALTER TABLE shop_goods DROP KEY idx_shop_goods_shipping_package_group, DROP COLUMN shipping_package_group_id,
--   ADD COLUMN package_length_mm INT UNSIGNED NULL, ADD COLUMN package_width_mm INT UNSIGNED NULL, ADD COLUMN package_height_mm INT UNSIGNED NULL;
-- DROP TABLE IF EXISTS shipping_package_group;
-- DROP TABLE IF EXISTS shipping_package_box;
