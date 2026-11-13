-- ============================================================
-- 002 自有商品目录建表（已获授权执行）
-- 用途：商品分类、分类属性定义、商品(SPU)、商品图片、商品规格(SKU)
-- 影响：仅新增 5 张 shop_ 前缀表，不改动现有表；与采集的 product 表无关
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，级联由应用层处理
-- 回滚：见文件末尾（会删除数据，确认后再执行）
-- 价格口径：拿货价(cost_price)、销售价(sale_price)、运费(shipping_fee) 均为同一本位币，币种待业务确认后再加字段
-- ============================================================

-- 1. 商品分类（多级，parent_id=0 为顶级）
CREATE TABLE shop_category (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  parent_id   INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '上级分类 shop_category.id，0为顶级',
  name        VARCHAR(100) NOT NULL COMMENT '分类名称',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  status      TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_category_parent_name (parent_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品分类';

-- 2. 商品属性定义（category_id=0 为所有分类通用；否则仅该分类下的商品使用）
CREATE TABLE shop_attribute (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  category_id  INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '适用分类 shop_category.id，0为通用',
  name         VARCHAR(100) NOT NULL COMMENT '属性名称，如 材质、颜色',
  input_type   VARCHAR(20)  NOT NULL DEFAULT 'text' COMMENT '录入方式 text文本 select单选',
  options      JSON         NULL COMMENT '可选值数组，仅 input_type=select 使用，如 ["棉","麻"]',
  is_required  TINYINT      NOT NULL DEFAULT 0 COMMENT '商品是否必填 1是 0否',
  sort_order   INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  status       TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_attribute_category_name (category_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品属性定义';

-- 3. 商品（SPU）
CREATE TABLE shop_goods (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  goods_no        VARCHAR(64)  NOT NULL COMMENT '商品编码（自定义，唯一）',
  name            VARCHAR(200) NOT NULL COMMENT '商品名称',
  category_id     INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '所属分类 shop_category.id，0为未分类',
  brand           VARCHAR(100) NOT NULL DEFAULT '' COMMENT '品牌',
  supplier        VARCHAR(100) NOT NULL DEFAULT '' COMMENT '供应商/货源',
  source_url      VARCHAR(500) NOT NULL DEFAULT '' COMMENT '货源链接',
  main_image_url  VARCHAR(500) NOT NULL DEFAULT '' COMMENT '主图地址（冗余 shop_goods_image 的第一张，列表用）',
  cost_price      DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '拿货价',
  sale_price      DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '销售价',
  shipping_fee    DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '运费',
  weight_g        INT UNSIGNED NULL COMMENT '重量（克），未知为空',
  attr_values     JSON         NULL COMMENT '属性值键值对，键为 shop_attribute.name，如 {"材质":"棉"}',
  description     TEXT         NULL COMMENT '商品描述',
  status          TINYINT      NOT NULL DEFAULT 0 COMMENT '1上架 0下架（新建默认下架）',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_goods_no (goods_no),
  KEY idx_goods_category (category_id),
  KEY idx_goods_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品（SPU）';

-- 4. 商品图片（按 sort_order 排，第一张为主图）
CREATE TABLE shop_goods_image (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  goods_id    INT UNSIGNED NOT NULL COMMENT '所属商品 shop_goods.id',
  url         VARCHAR(500) NOT NULL COMMENT '图片地址',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_goods_image_goods (goods_id, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品图片';

-- 5. 商品规格（SKU，可售最小单元；价格不填时按商品价格）
CREATE TABLE shop_goods_sku (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  goods_id    INT UNSIGNED NOT NULL COMMENT '所属商品 shop_goods.id',
  sku_code    VARCHAR(64)  NOT NULL COMMENT 'SKU编码（唯一）',
  spec_name   VARCHAR(200) NOT NULL DEFAULT '' COMMENT '规格描述，如 红色/XL',
  cost_price  DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '拿货价',
  sale_price  DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '销售价',
  stock       INT          NOT NULL DEFAULT 0 COMMENT '库存数量',
  status      TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sku_code (sku_code),
  KEY idx_sku_goods (goods_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品规格（SKU）';

-- ============================================================
-- 回滚（会删除数据）：
-- DROP TABLE shop_goods_sku, shop_goods_image, shop_goods, shop_attribute, shop_category;
-- ============================================================
