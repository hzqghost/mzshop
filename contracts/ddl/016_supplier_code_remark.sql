-- ============================================================
-- 016 供应商档案增加编码，备注改为 HTML（随本次需求执行）
-- 用途：供应商增加编码；备注用 HTML 编辑器，原 VARCHAR(500) 装不下
-- 影响表字段：supplier 新增 code（可空，空编码不占唯一）；remark 改为可空 MEDIUMTEXT
-- 兼容性：MySQL 8；在线加列、改列类型，已有备注原文保留
-- 回滚：ALTER TABLE supplier DROP INDEX uq_supplier_code, DROP COLUMN code,
--         MODIFY COLUMN remark VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注';
-- ============================================================

ALTER TABLE supplier
  ADD COLUMN code VARCHAR(50) NULL COMMENT '供应商编码' AFTER id,
  ADD UNIQUE KEY uq_supplier_code (code),
  MODIFY COLUMN remark MEDIUMTEXT NULL COMMENT '备注（HTML）';
