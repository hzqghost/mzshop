-- ============================================================
-- 015 供应商产品目录条目增加售价与交期（随本次需求执行）
-- 用途：产品基本信息记录建议售价、最低售价、最高售价、价格规则、交期
-- 影响表字段：supplier_catalog_item 新增 5 列（价格可空，文本有默认空串，历史行不受影响）
-- 兼容性：MySQL 8；在线加列，不改已有列
-- 回滚：ALTER TABLE supplier_catalog_item
--         DROP COLUMN suggested_price, DROP COLUMN min_price, DROP COLUMN max_price,
--         DROP COLUMN price_rule, DROP COLUMN lead_time;
-- ============================================================

ALTER TABLE supplier_catalog_item
  ADD COLUMN suggested_price DECIMAL(12,2) NULL COMMENT '建议售价' AFTER price,
  ADD COLUMN min_price DECIMAL(12,2) NULL COMMENT '最低售价' AFTER suggested_price,
  ADD COLUMN max_price DECIMAL(12,2) NULL COMMENT '最高售价' AFTER min_price,
  ADD COLUMN price_rule TEXT NOT NULL COMMENT '价格规则，多行文本' AFTER max_price,
  ADD COLUMN lead_time VARCHAR(100) NOT NULL DEFAULT '' COMMENT '交期' AFTER price_rule;
