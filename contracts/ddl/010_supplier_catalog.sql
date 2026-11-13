-- ============================================================
-- 010 供应商档案、品牌字典、供应商产品目录（已获授权执行）
-- 用途：供应商产品目录模块的数据基础
--   1) supplier 供应商档案：把 shop_goods.supplier 字符串升级为结构化档案，
--      记录网站/联系人/币种与 Excel 列映射模板
--   2) brand 品牌字典：把 shop_goods.brand 字符串升级为结构化品牌
--   3) shop_goods 新增 brand_id / supplier_id（0=未设置）并从现有字符串列回填；
--      旧列 brand / supplier 暂保留（应用代码仍在用），待代码切换到 *_id 后由下一版 DDL 删除
--   4) supplier_catalog_item 供应商产品目录条目：品牌为公共字段（brand_id 结构化 +
--      brand_name 原文），异构属性走 attrs（供应商原文，溯源）+ mapped_attrs（映射 shop_attribute 后）
-- 影响表字段：新增 supplier、brand、supplier_catalog_item 三表；
--   shop_goods 仅新增 brand_id、supplier_id 列和两个索引，不改动旧列，兼容现有代码
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，级联在应用层
-- 回滚：见文件末尾（会删除数据，确认后再执行）
-- ============================================================

-- 1. 供应商档案
CREATE TABLE supplier (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  name             VARCHAR(100) NOT NULL COMMENT '供应商名称',
  website          VARCHAR(255) NOT NULL DEFAULT '' COMMENT '官网/店铺地址',
  contact_name     VARCHAR(100) NOT NULL DEFAULT '' COMMENT '联系人',
  contact_phone    VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '联系电话',
  contact_email    VARCHAR(100) NOT NULL DEFAULT '' COMMENT '联系邮箱',
  default_currency VARCHAR(3)   NOT NULL DEFAULT '' COMMENT '默认币种 ISO 4217，如 USD/CNY，空为未设置',
  excel_mapping    JSON         NULL COMMENT 'Excel 列映射模板 {源列名: 目标字段/属性名}，导入时自动套用',
  remark           VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
  status           TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_supplier_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='供应商档案';

-- 2. 品牌字典
CREATE TABLE brand (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  name       VARCHAR(100) NOT NULL COMMENT '品牌名称',
  logo_url   VARCHAR(500) NOT NULL DEFAULT '' COMMENT '品牌 logo 地址',
  website    VARCHAR(255) NOT NULL DEFAULT '' COMMENT '品牌官网',
  remark     VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
  sort_order INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  status     TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_brand_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='品牌字典';

-- 3. shop_goods 品牌/供应商结构化（旧字符串列暂保留，应用切换后删除）
ALTER TABLE shop_goods
  ADD COLUMN brand_id INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '品牌 brand.id，0为未设置' AFTER brand,
  ADD COLUMN supplier_id INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '供应商 supplier.id，0为未设置' AFTER supplier,
  ADD KEY idx_goods_brand (brand_id),
  ADD KEY idx_goods_supplier (supplier_id);

-- 4. 从现有字符串列回填（同名建字典项；大小写不同按不区分大小写归并，IGNORE 防重复）
INSERT IGNORE INTO brand (name) SELECT DISTINCT TRIM(brand) FROM shop_goods WHERE TRIM(brand) <> '';
INSERT IGNORE INTO supplier (name) SELECT DISTINCT TRIM(supplier) FROM shop_goods WHERE TRIM(supplier) <> '';

UPDATE shop_goods g JOIN brand b ON b.name = TRIM(g.brand) SET g.brand_id = b.id WHERE TRIM(g.brand) <> '';
UPDATE shop_goods g JOIN supplier s ON s.name = TRIM(g.supplier) SET g.supplier_id = s.id WHERE TRIM(g.supplier) <> '';

-- 5. 供应商产品目录条目（选品池；与 shop_goods 分离，选品后生成商品并回填 goods_id）
CREATE TABLE supplier_catalog_item (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  supplier_id    INT UNSIGNED NOT NULL COMMENT '供应商 supplier.id',
  supplier_sku   VARCHAR(100) NOT NULL COMMENT '供应商货号/SKU',
  name           VARCHAR(300) NOT NULL COMMENT '产品名称',
  brand_id       INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '品牌 brand.id（公共属性），0为未知',
  brand_name     VARCHAR(100) NOT NULL DEFAULT '' COMMENT '供应商原始品牌名（字典外或未映射时的原文）',
  category_name  VARCHAR(200) NOT NULL DEFAULT '' COMMENT '供应商原始分类名',
  category_id    INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '映射 shop_category.id，0为未映射',
  price          DECIMAL(12,2) NULL COMMENT '报价，面议/未知为空',
  currency       VARCHAR(3)   NOT NULL DEFAULT '' COMMENT '币种 ISO 4217，如 USD/CNY',
  stock          INT UNSIGNED NULL COMMENT '库存数量，未知为空',
  moq            VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '最小起订量原文，如 100 pcs',
  main_image_url VARCHAR(500) NOT NULL DEFAULT '' COMMENT '产品主图地址',
  source_type    VARCHAR(20)  NOT NULL DEFAULT 'manual' COMMENT '来源 manual人工录入/excel导入/website采集',
  source_url     VARCHAR(500) NOT NULL DEFAULT '' COMMENT '来源网址（website 来源）',
  source_file    VARCHAR(255) NOT NULL DEFAULT '' COMMENT '来源 Excel 文件名（excel 来源）',
  source_row     INT UNSIGNED NULL COMMENT '来源 Excel 行号（excel 来源）',
  attrs          JSON         NULL COMMENT '供应商原始属性键值对（原文保留，溯源）',
  mapped_attrs   JSON         NULL COMMENT '映射到 shop_attribute 后的标准化属性值',
  description    TEXT         NULL COMMENT '产品描述原文',
  status         TINYINT      NOT NULL DEFAULT 0 COMMENT '0待核对 1已核对 2已选品 3已忽略',
  goods_id       INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '选品后生成的商品 shop_goods.id，0为未选品',
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_catalog_supplier_sku (supplier_id, supplier_sku),
  KEY idx_catalog_brand (brand_id),
  KEY idx_catalog_category (category_id),
  KEY idx_catalog_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='供应商产品目录条目';

-- ============================================================
-- 回滚（会删除数据，确认后再执行）：
-- DROP TABLE supplier_catalog_item
-- ALTER TABLE shop_goods DROP KEY idx_goods_supplier, DROP KEY idx_goods_brand, DROP COLUMN supplier_id, DROP COLUMN brand_id
-- DROP TABLE supplier, brand
-- ============================================================
