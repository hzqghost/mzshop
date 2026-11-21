-- ============================================================
-- 021 销售平台与店铺（随本次需求执行；应用启动 create_all 也会建表）
-- 用途：店铺菜单下的平台管理、店铺管理
--   platform 销售平台：编码、中英文名称、网址、市场、特性、备注、是否独立站
--   store 店铺：归属平台；独立站不在本表保存，读取时取所属平台
-- 影响：新增 platform、store，不改动现有表
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，删除由应用层校验
-- 回滚：DROP TABLE IF EXISTS store, platform;
-- ============================================================

CREATE TABLE platform (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  code            VARCHAR(50)  NOT NULL COMMENT '编码',
  name            VARCHAR(100) NOT NULL COMMENT '平台名称',
  name_en         VARCHAR(100) NOT NULL DEFAULT '' COMMENT '平台名称（英文）',
  website         VARCHAR(255) NOT NULL DEFAULT '' COMMENT '网址',
  market          VARCHAR(100) NOT NULL DEFAULT '' COMMENT '市场',
  feature         VARCHAR(500) NOT NULL DEFAULT '' COMMENT '特性',
  remark          VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
  is_independent  TINYINT      NOT NULL DEFAULT 0 COMMENT '1独立站 0否',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_platform_code (code),
  UNIQUE KEY uq_platform_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售平台';

CREATE TABLE store (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  platform_id  INT UNSIGNED NOT NULL COMMENT 'platform.id',
  code         VARCHAR(50)  NOT NULL COMMENT '编码',
  name         VARCHAR(100) NOT NULL COMMENT '店铺名称',
  name_en      VARCHAR(100) NOT NULL DEFAULT '' COMMENT '店铺名称（英文）',
  website      VARCHAR(255) NOT NULL DEFAULT '' COMMENT '网址',
  feature      VARCHAR(500) NOT NULL DEFAULT '' COMMENT '特性',
  remark       VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_store_platform_code (platform_id, code),
  UNIQUE KEY uq_store_platform_name (platform_id, name),
  KEY idx_store_platform (platform_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='店铺';
