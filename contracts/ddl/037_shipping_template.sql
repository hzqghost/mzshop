-- 037 销售运费模板、SKU 重量与商品店铺模板绑定（待人工审核执行）
-- 用途：按配送区域配置固定/重量运费；商品在每个店铺绑定一个模板；SKU 重量为空时继承商品重量。
-- 影响：新增 shipping_template、shipping_template_rule；shop_goods_sku 和 shop_goods_store 各新增一列。
-- 兼容：历史商品店铺绑定的 shipping_template_id 默认为 0，不自动下架；再次保存、上架或推送时必须补模板。
-- 预览：
--   SELECT COUNT(*) AS store_links FROM shop_goods_store;
--   SELECT COUNT(*) AS sku_without_weight FROM shop_goods_sku WHERE status=1;
-- 执行：审核并备份后执行本文件；执行后重启 mzshop-admin。
-- 回滚：先确认新字段和新表数据不再使用，再按文件末尾的逆序语句人工回滚。

CREATE TABLE shipping_template (
  id                 INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  name               VARCHAR(100)  NOT NULL COMMENT '模板名称',
  currency           VARCHAR(3)    NOT NULL COMMENT '币种',
  calc_type          VARCHAR(20)   NOT NULL COMMENT '计费方式：fixed固定运费 weight按重量',
  free_threshold     DECIMAL(12,2) NULL COMMENT '分组商品金额满此值免邮',
  min_fee            DECIMAL(12,2) NULL COMMENT '最低运费',
  max_fee            DECIMAL(12,2) NULL COMMENT '最高运费',
  no_match_action    VARCHAR(20)   NOT NULL DEFAULT 'reject' COMMENT '区域未匹配处理：reject禁止配送 default使用默认规则',
  status             TINYINT       NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  remark             VARCHAR(500)  NOT NULL DEFAULT '' COMMENT '备注',
  created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shipping_template_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售运费模板';

CREATE TABLE shipping_template_rule (
  id                    INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  template_id           INT           NOT NULL COMMENT 'shipping_template.id',
  region_id             INT           NOT NULL DEFAULT 0 COMMENT 'sys_region.id，0表示默认规则',
  priority              INT           NOT NULL DEFAULT 100 COMMENT '匹配优先级，越小越优先',
  fixed_fee             DECIMAL(12,2) NULL COMMENT '固定运费',
  first_weight_g        INT UNSIGNED  NULL COMMENT '首重克数',
  first_fee             DECIMAL(12,2) NULL COMMENT '首重费用',
  additional_weight_g   INT UNSIGNED  NULL COMMENT '续重单位克数',
  additional_fee        DECIMAL(12,2) NULL COMMENT '每个续重单位费用',
  arrival_days_min      INT UNSIGNED  NULL COMMENT '最快到达天数',
  arrival_days_max      INT UNSIGNED  NULL COMMENT '最慢到达天数',
  created_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shipping_rule_template_region (template_id, region_id),
  KEY idx_shipping_rule_region (region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售运费模板区域规则';

ALTER TABLE shop_goods_sku
  ADD COLUMN weight_g INT UNSIGNED NULL COMMENT 'SKU重量（克），空值继承商品重量' AFTER sku_type;

ALTER TABLE shop_goods_store
  ADD COLUMN shipping_template_id INT NOT NULL DEFAULT 0 COMMENT 'shipping_template.id，0表示未绑定' AFTER store_id,
  ADD KEY idx_shop_goods_store_shipping_template (shipping_template_id);

-- 回滚（仅人工确认后执行）：
-- ALTER TABLE shop_goods_store DROP KEY idx_shop_goods_store_shipping_template, DROP COLUMN shipping_template_id;
-- ALTER TABLE shop_goods_sku DROP COLUMN weight_g;
-- DROP TABLE IF EXISTS shipping_template_rule;
-- DROP TABLE IF EXISTS shipping_template;
