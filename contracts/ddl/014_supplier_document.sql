-- ============================================================
-- 014 供应商文档（人工审核后执行；应用启动 create_all 也会建这张空表）
-- 用途：产品池「供应商文档」按供应商归档营业执照、资质、合同、价目表等资料
-- 影响表字段：新增 supplier_document；不改已有表
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB；不建外键，删除供应商前由应用检查
-- 回滚：DROP TABLE supplier_document;
-- ============================================================

CREATE TABLE supplier_document (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  supplier_id INT UNSIGNED NOT NULL COMMENT '供应商 supplier.id',
  title       VARCHAR(200) NOT NULL COMMENT '文档标题',
  doc_type    VARCHAR(30)  NOT NULL DEFAULT 'other' COMMENT 'license营业执照 qualification资质证书 contract合同协议 pricelist价目表 catalog产品资料 other其他',
  file_url    VARCHAR(500) NOT NULL COMMENT '本系统上传地址 /static/uploads/年月/随机名',
  file_name   VARCHAR(180) NOT NULL DEFAULT '' COMMENT '原始文件名',
  file_size   INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '文件字节数',
  remark      VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_supplier_document_supplier (supplier_id),
  KEY idx_supplier_document_type (doc_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='供应商文档';
