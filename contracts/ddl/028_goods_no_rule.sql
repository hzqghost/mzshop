-- 用途：支持“品牌编码 + 品类编码 + 4 位流水”的自动商品编码规则。
-- 影响：shop_category 新增 code；brand 新增 brand_type、include_in_goods_no；新增 shop_goods_no_sequence。
-- 兼容性：历史分类编码保持 NULL；历史品牌默认为第三方品牌且参与商品编码；现有商品编码不修改。
-- 预览：
--   SELECT id, parent_id, name FROM shop_category ORDER BY id;
--   SELECT id, code, name FROM brand ORDER BY id;
--   SELECT goods_no FROM shop_goods ORDER BY id;
-- 执行：备份后在低峰期执行下列 ALTER / CREATE；完成后先维护分类编码和品牌配置，再使用自动生成。
-- 回滚前预览：SELECT * FROM shop_goods_no_sequence ORDER BY prefix;
-- 回滚：
--   DROP TABLE IF EXISTS shop_goods_no_sequence;
--   ALTER TABLE brand DROP COLUMN include_in_goods_no, DROP COLUMN brand_type;
--   ALTER TABLE shop_category DROP COLUMN code;
-- 注意事项：生成按钮点击即占用流水，未保存商品也不会回收；相同最终前缀共享 0001~9999。

ALTER TABLE shop_category
  ADD COLUMN code VARCHAR(50) NULL COMMENT '商品编码中的品类段，允许重复' AFTER parent_id;

ALTER TABLE brand
  ADD COLUMN brand_type VARCHAR(20) NOT NULL DEFAULT 'third_party' COMMENT '品牌类型：own自有品牌 third_party第三方品牌' AFTER name,
  ADD COLUMN include_in_goods_no SMALLINT NOT NULL DEFAULT 1 COMMENT '是否参与商品编码：1参与 0使用TH' AFTER brand_type;

CREATE TABLE shop_goods_no_sequence (
  prefix       VARCHAR(60) NOT NULL COMMENT '品牌段与品类段拼接后的最终前缀',
  current_seq  INT NOT NULL COMMENT '当前已占用的四位流水号',
  updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (prefix)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品编码流水';
