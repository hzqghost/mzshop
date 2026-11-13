-- ============================================================
-- 011 供应商产品目录条目增加大备注（人工审核后执行）
-- 用途：产品编辑页用 HTML 编辑器维护资料，与导入的 description 原文分开
-- 影响表字段：supplier_catalog_item 新增 remark（可空 MEDIUMTEXT，历史行为空）
-- 兼容性：MySQL 8；在线加列，不改已有列；TEXT 类字段不能设 DEFAULT，故可空
-- 回滚：ALTER TABLE supplier_catalog_item DROP COLUMN remark;
-- ============================================================

ALTER TABLE supplier_catalog_item
  ADD COLUMN remark MEDIUMTEXT NULL COMMENT '资料（HTML）' AFTER description;
