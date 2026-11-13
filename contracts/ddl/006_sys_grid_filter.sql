-- ============================================================
-- 006 表格过滤器模板（已获授权执行）
-- 用途：后台各表格的「过滤器模板」——把过滤器（DevExtreme filterValue）按用户、按表格保存成命名模板，之后一键选用
-- 影响：仅新增 1 张表，不改动现有表
-- 约定：user_id 对应 sys_user.id，0 为内置超级管理员；grid_key 一般是页面路径，如 /goods；同一用户同一表格下模板名唯一
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键
-- 回滚：见文件末尾
-- ============================================================

CREATE TABLE sys_grid_filter (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id       INT UNSIGNED NOT NULL COMMENT '所属用户 sys_user.id，0为内置超级管理员',
  grid_key      VARCHAR(100) NOT NULL COMMENT '表格标识，一般为页面路径，如 /goods',
  name          VARCHAR(50)  NOT NULL COMMENT '模板名称',
  filter_value  JSON         NOT NULL COMMENT '过滤器内容（DevExtreme filterValue 表达式）',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_grid_filter_user_grid_name (user_id, grid_key, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='表格过滤器模板';

-- ============================================================
-- 回滚（会删除所有已保存的模板）：
-- DROP TABLE sys_grid_filter;
-- ============================================================
