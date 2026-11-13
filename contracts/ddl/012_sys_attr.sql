-- ============================================================
-- 012 系统通用属性（属性类型 + 属性值）
-- 用途：系统级字典。属性类型定义标识码、是否树型、是否用编码、扩展字段；
--       属性值按类型存放。币种（currency）是预置类型，默认人民币 / 美元 / 欧元。
--       供应商默认币种、目录条目币种保存的是这里的编码（CNY / USD / EUR）。
-- 影响：新增 sys_attr_type、sys_attr_value；不改已有表结构。
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，引用在应用层校验。
-- 回滚：见文件末尾（会删除通用属性数据，确认后再执行）。
-- ============================================================

CREATE TABLE IF NOT EXISTS sys_attr_type (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  code        VARCHAR(30)  NOT NULL COMMENT '类型标识码，如 currency',
  cn_name     VARCHAR(50)  NOT NULL COMMENT '中文名称',
  en_name     VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '英文名称',
  is_tree     TINYINT      NOT NULL DEFAULT 0 COMMENT '1树型 0平铺',
  use_code    TINYINT      NOT NULL DEFAULT 0 COMMENT '1启用编码',
  ext_schema  JSON         NULL COMMENT '扩展字段 schema：[{group,caption,items:[{type,caption,field}]}]',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sys_attr_type_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统通用属性类型';

CREATE TABLE IF NOT EXISTS sys_attr_value (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  type_id     INT UNSIGNED NOT NULL COMMENT 'sys_attr_type.id',
  parent_id   INT UNSIGNED NULL COMMENT '上级属性值，仅树型使用',
  cn_name     VARCHAR(100) NOT NULL COMMENT '中文名称',
  en_name     VARCHAR(100) NOT NULL DEFAULT '' COMMENT '英文名称',
  code        VARCHAR(50)  NULL COMMENT '编码；不用编码时为 NULL',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  ext_values  JSON         NULL COMMENT '扩展字段值',
  status      TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sys_attr_value_code (type_id, code),
  KEY idx_sys_attr_value_type (type_id),
  KEY idx_sys_attr_value_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统通用属性值';

-- 预置币种。类型已存在时不再插入；某个编码已存在时不覆盖。
INSERT INTO sys_attr_type (code, cn_name, en_name, is_tree, use_code, ext_schema, sort_order)
SELECT 'currency', '币种', 'Currency', 0, 1,
       CAST('[{"group":"finance","caption":"财务属性","items":[{"type":"number","caption":"对人民币汇率","field":"cny_rate","required":0,"min":0}]}]' AS JSON),
       1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM sys_attr_type WHERE code = 'currency');

INSERT INTO sys_attr_value (type_id, cn_name, en_name, code, sort_order, ext_values, status)
SELECT t.id, '人民币', 'Chinese Yuan', 'CNY', 1, CAST('{"cny_rate":1}' AS JSON), 1
FROM sys_attr_type t
WHERE t.code = 'currency'
  AND NOT EXISTS (SELECT 1 FROM sys_attr_value v WHERE v.type_id = t.id AND v.code = 'CNY');

INSERT INTO sys_attr_value (type_id, cn_name, en_name, code, sort_order, status)
SELECT t.id, '美元', 'US Dollar', 'USD', 2, 1
FROM sys_attr_type t
WHERE t.code = 'currency'
  AND NOT EXISTS (SELECT 1 FROM sys_attr_value v WHERE v.type_id = t.id AND v.code = 'USD');

INSERT INTO sys_attr_value (type_id, cn_name, en_name, code, sort_order, status)
SELECT t.id, '欧元', 'Euro', 'EUR', 3, 1
FROM sys_attr_type t
WHERE t.code = 'currency'
  AND NOT EXISTS (SELECT 1 FROM sys_attr_value v WHERE v.type_id = t.id AND v.code = 'EUR');

-- 回滚：
-- DROP TABLE IF EXISTS sys_attr_value;
-- DROP TABLE IF EXISTS sys_attr_type;
