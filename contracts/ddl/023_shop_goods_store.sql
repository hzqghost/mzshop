-- ============================================================
-- 023 商品的店铺上架许可（随本次需求执行；应用启动 create_all 也会建表）
-- 用途：商品详情「店铺」：记录当前商品可以上架 / 不可以上架的店铺。
--       没有相关记录时，商品的上下架不生效。
-- 影响：新增 shop_goods_store，不改动现有表
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键
-- 回滚：DROP TABLE IF EXISTS shop_goods_store;
-- ============================================================

CREATE TABLE shop_goods_store (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  goods_id    INT UNSIGNED NOT NULL COMMENT 'shop_goods.id',
  store_id    INT UNSIGNED NOT NULL COMMENT 'store.id',
  allowed     TINYINT      NOT NULL DEFAULT 1 COMMENT '1可以上架 0不可以上架',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_goods_store (goods_id, store_id),
  KEY idx_shop_goods_store_store (store_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品的店铺上架许可';
