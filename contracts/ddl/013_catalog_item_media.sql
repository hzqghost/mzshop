-- ============================================================
-- 013 供应商产品目录条目增加图片列表、附件列表（人工审核后执行）
-- 用途：产品编辑页用上传维护图片和附件，不再手填图片链接；
--       main_image_url 仍保留，保存时写成图片列表的第一张，列表缩略图不用改
-- 影响表字段：supplier_catalog_item 新增 images、attachments（可空 JSON，历史行为空）
-- 兼容性：MySQL 8；在线加列，不改已有列
-- 回滚：ALTER TABLE supplier_catalog_item DROP COLUMN images, DROP COLUMN attachments;
-- ============================================================

ALTER TABLE supplier_catalog_item
  ADD COLUMN images JSON NULL COMMENT '图片列表 [{url,name}]' AFTER main_image_url,
  ADD COLUMN attachments JSON NULL COMMENT '附件列表 [{url,name}]' AFTER images;
