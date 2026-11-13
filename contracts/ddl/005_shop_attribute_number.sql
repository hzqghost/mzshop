-- ============================================================
-- 005 商品属性增加「数字」类型（已获授权执行）
-- 用途：数字属性（如 容量 30 ml）需要小数位数和单位；单位可多语言，其它语言的单位存 shop_translation（field_name='unit'）
-- 影响表字段：shop_attribute
--   新增 decimal_places（小数位数，0=整数）、unit（单位，默认语言）
--   input_type 只改 Comment（增加 number 取值），类型/NULL/默认值不变
-- 兼容性：新增列均有默认值，历史数据不受影响；表很小，在线 DDL 无锁表风险
-- 回滚：见文件末尾
-- ============================================================

ALTER TABLE shop_attribute
  MODIFY COLUMN input_type VARCHAR(20) NOT NULL DEFAULT 'text' COMMENT '录入方式 text文本 select单选 number数字',
  ADD COLUMN decimal_places TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '数字属性的小数位数，0表示整数；仅 input_type=number 使用' AFTER options,
  ADD COLUMN unit VARCHAR(30) NOT NULL DEFAULT '' COMMENT '数字属性的单位（默认语言），如 ml；其它语言的单位存 shop_translation' AFTER decimal_places;

-- ============================================================
-- 回滚（会丢失已配置的小数位数和单位）：
-- ALTER TABLE shop_attribute DROP COLUMN unit, DROP COLUMN decimal_places,
--   MODIFY COLUMN input_type VARCHAR(20) NOT NULL DEFAULT 'text' COMMENT '录入方式 text文本 select单选';
-- DELETE FROM shop_translation WHERE entity_type='attribute' AND field_name='unit';
-- ============================================================
