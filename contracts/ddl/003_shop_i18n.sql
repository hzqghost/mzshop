-- ============================================================
-- 003 商品内容多语言（已获授权执行）
-- 用途：商品数据（分类名、属性名/可选值、商品名/描述/属性值、规格名）的多语言版本；与后台界面语言无关
-- 约定：shop_* 基础表里的文字就是「默认语言」的内容；其他语言的译文存 shop_translation，缺译时读取方回退到默认语言
-- 影响：仅新增 2 张表，并写入 2 条语言种子（zh-CN 默认、en），不改动现有表
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，级联在应用层
-- 回滚：见文件末尾（会删除数据，确认后再执行）
-- ============================================================

-- 1. 商品内容语言（is_default=1 只能有一条，其内容存放在 shop_* 基础表里）
CREATE TABLE shop_language (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  code        VARCHAR(20)  NOT NULL COMMENT '语言代码，如 zh-CN、en、ja',
  name        VARCHAR(50)  NOT NULL COMMENT '语言名称，如 简体中文、English',
  is_default  TINYINT      NOT NULL DEFAULT 0 COMMENT '是否默认语言 1是 0否；基础表里的内容即默认语言',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
  status      TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_language_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品内容语言';

-- 2. 商品内容译文（非默认语言；一个实体的一个字段在一种语言下一行）
CREATE TABLE shop_translation (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  entity_type  VARCHAR(20)  NOT NULL COMMENT '实体类型 category分类 attribute属性 goods商品 sku规格',
  entity_id    INT UNSIGNED NOT NULL COMMENT '实体ID，对应 entity_type 所指表的主键',
  lang_code    VARCHAR(20)  NOT NULL COMMENT '语言代码 shop_language.code',
  field_name   VARCHAR(50)  NOT NULL COMMENT '被翻译的字段，如 name、description、options、attr_values、spec_name',
  content      TEXT         NOT NULL COMMENT '译文；options / attr_values 为 JSON 文本',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_translation (entity_type, entity_id, lang_code, field_name),
  KEY idx_translation_lang (lang_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品内容译文';

-- 3. 语言种子（可在后台「商品语言」里增删改）
INSERT INTO shop_language (code, name, is_default, sort_order, status) VALUES
  ('zh-CN', '简体中文', 1, 0, 1),
  ('en', 'English', 0, 10, 1);

-- ============================================================
-- 回滚（会删除数据）：
-- DROP TABLE shop_translation, shop_language;
-- ============================================================
