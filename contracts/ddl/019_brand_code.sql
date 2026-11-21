-- ============================================================
-- 019 品牌字典增加编码（随本次需求执行）
-- 用途：品牌增加编码，列表第一列展示；空编码不占唯一
-- 影响表字段：brand 新增 code
-- 兼容性：MySQL 8；在线加列；已有品牌编码为空
-- 回滚：ALTER TABLE brand DROP INDEX uq_brand_code, DROP COLUMN code;
-- ============================================================

ALTER TABLE brand
  ADD COLUMN code VARCHAR(50) NULL COMMENT '品牌编码' AFTER id,
  ADD UNIQUE KEY uq_brand_code (code);
