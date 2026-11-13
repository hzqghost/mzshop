-- 007 属性录入方式增加 textarea 多行文本、multiselect 多选
-- 目的：商品属性支持「多行文本」「多选」。
-- 影响：shop_attribute 只改 input_type / options 两列的 COMMENT；类型、NULL、默认值不变，不改数据，不锁表重建。
--       多选的商品属性值存进 shop_goods.attr_values（JSON），值是可选值数组，无需改表。
-- 回滚：把 COMMENT 改回 005 里的写法即可（已有 textarea / multiselect 属性需先改回 text / select）。
ALTER TABLE shop_attribute
  MODIFY COLUMN input_type VARCHAR(20) NOT NULL DEFAULT 'text' COMMENT '录入方式 text文本 textarea多行文本 select单选 multiselect多选 number数字',
  MODIFY COLUMN options JSON NULL COMMENT '可选值数组，仅 input_type=select/multiselect 使用，如 ["棉","麻"]';
