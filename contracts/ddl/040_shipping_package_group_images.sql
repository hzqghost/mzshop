-- 040 包装组多图（待人工审核执行）
-- 用途：一个包装组可保存多张包装实物参考图。
-- 影响：新增 shipping_package_group_image；不改变包装组与当前包装箱的一对一选择。
-- 预览：SELECT COUNT(*) AS group_count FROM shipping_package_group;
-- 执行：审核并备份后执行本文件，再重启 mzshop-admin。
-- 回滚：确认图片关联数据可舍弃后执行 DROP TABLE shipping_package_group_image；上传文件不会自动删除。

CREATE TABLE shipping_package_group_image (
  id          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  group_id    INT          NOT NULL COMMENT 'shipping_package_group.id',
  url         VARCHAR(500) NOT NULL COMMENT '图片地址',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_shipping_package_group_image_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='物流包装组图片';

-- 回滚（仅人工确认后执行）：
-- DROP TABLE shipping_package_group_image;
