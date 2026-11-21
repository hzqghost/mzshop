-- ============================================================
-- 017 国家地区与区域（随本次需求执行；应用启动 create_all 也会建表）
-- 用途：国家地区树（全球 / 洲 / 国家），以及可重复勾选国家的区域
-- 影响：新增 sys_geo、sys_region、sys_region_country，不改动现有表
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，级联由应用层处理
-- 回滚：DROP TABLE IF EXISTS sys_region_country, sys_region, sys_geo;
-- 种子：表为空时由应用启动写入，本脚本不插数据
-- ============================================================

CREATE TABLE sys_geo (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  parent_id   INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '上级 sys_geo.id，0为顶级',
  code        VARCHAR(10)  NOT NULL COMMENT '编码，如 ALL、AFR、CN',
  name_zh     VARCHAR(50)  NOT NULL COMMENT '中文名',
  name_en     VARCHAR(80)  NOT NULL DEFAULT '' COMMENT '英文名',
  is_leaf     TINYINT      NOT NULL DEFAULT 1 COMMENT '1子节点（国家/地区） 0分组（全球/洲）',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sys_geo_code (code),
  KEY idx_sys_geo_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='国家地区';

CREATE TABLE sys_region (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  name        VARCHAR(100) NOT NULL COMMENT '区域名称',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sys_region_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='区域';

CREATE TABLE sys_region_country (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  region_id  INT UNSIGNED NOT NULL COMMENT 'sys_region.id',
  geo_id     INT UNSIGNED NOT NULL COMMENT 'sys_geo.id，须为子节点',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sys_region_country (region_id, geo_id),
  KEY idx_sys_region_country_geo (geo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='区域包含的国家';
