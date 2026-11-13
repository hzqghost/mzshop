-- ============================================================
-- 009 商品属性的适用分类改为多选（已获授权执行）
-- 用途：一个属性可同时适用于多个分类（如「产地」同时挂在香水、化妆品下）
-- 影响表字段：shop_attribute
--   新增 category_ids JSON：适用分类 shop_category.id 数组；空数组 = 所有分类通用
--   原 category_id（单分类，0=通用）数据迁移为 [category_id]（0 迁移为空数组）后删除
--   删除唯一键 uq_attribute_category_name：多分类下无法再用单列唯一约束
--   同名检查改由后端在保存时按「名称 + 分类集合」判断（JSON 列无法直接建唯一索引）
-- 兼容性：属性表很小，在线 DDL 无明显锁表风险；迁移期间旧代码无法读写 category_id，前后端须同版本发布
-- 回滚：见文件末尾（多分类属性只能回填第一个分类）
-- ============================================================

ALTER TABLE shop_attribute
  ADD COLUMN category_ids JSON NULL COMMENT '适用分类 shop_category.id 数组，空数组为所有分类通用（含下级继承）' AFTER category_id;

UPDATE shop_attribute
  SET category_ids = IF(category_id = 0, JSON_ARRAY(), JSON_ARRAY(category_id));

ALTER TABLE shop_attribute
  DROP INDEX uq_attribute_category_name,
  DROP COLUMN category_id;

-- ============================================================
-- 回滚（会丢失多分类信息，只保留第一个分类）：
-- ALTER TABLE shop_attribute
--   ADD COLUMN category_id INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '适用分类 shop_category.id，0为通用' AFTER id;
-- UPDATE shop_attribute SET category_id = IFNULL(CAST(JSON_EXTRACT(category_ids, '$[0]') AS UNSIGNED), 0);
-- ALTER TABLE shop_attribute
--   ADD UNIQUE KEY uq_attribute_category_name (category_id, name),
--   DROP COLUMN category_ids;
-- ============================================================
