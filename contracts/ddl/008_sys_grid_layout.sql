-- ============================================================
-- 008 表格布局（已获授权执行，已执行）
-- 用途：后台各表格设置菜单里的「保存布局 / 恢复布局」——把列宽、顺序、显隐、固定、排序、每页条数和编辑模式按用户、按表格保存到服务端，换浏览器也能恢复
-- 影响：仅新增 1 张表，不改动现有表
-- 约定：user_id 对应 sys_user.id，0 为内置超级管理员；grid_key 一般是页面路径，如 /goods；同一用户同一表格只有一份布局（覆盖保存）
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键
-- 回滚：见文件末尾
-- ============================================================

CREATE TABLE sys_grid_layout (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id    INT UNSIGNED NOT NULL COMMENT '所属用户 sys_user.id，0为内置超级管理员',
  grid_key   VARCHAR(100) NOT NULL COMMENT '表格标识，一般为页面路径，如 /goods',
  layout     JSON         NOT NULL COMMENT '布局内容：{state: DevExtreme 表格状态（列宽/顺序/显隐/固定/排序/每页条数）, editMode: 编辑模式}',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_grid_layout_user_grid (user_id, grid_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='表格布局';

-- ============================================================
-- 回滚（会删除所有已保存的布局）：
-- DROP TABLE sys_grid_layout;
-- ============================================================
