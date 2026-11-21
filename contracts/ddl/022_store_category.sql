-- ============================================================
-- 022 店铺绑定商品分类（随本次需求执行；应用启动 create_all 也会建表）
-- 用途：店铺管理「绑定分类」多选，一个店铺可绑多个 shop_category
-- 影响：新增 store_category，不改动现有表
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，级联由应用层处理
-- 回滚：DROP TABLE IF EXISTS store_category;
-- ============================================================

CREATE TABLE store_category (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id     INT UNSIGNED NOT NULL COMMENT 'store.id',
  category_id  INT UNSIGNED NOT NULL COMMENT 'shop_category.id',
  PRIMARY KEY (id),
  UNIQUE KEY uq_store_category (store_id, category_id),
  KEY idx_store_category_cat (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='店铺绑定的商品分类';
