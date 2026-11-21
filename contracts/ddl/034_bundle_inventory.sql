-- ============================================================
-- 034 固定组合与单地点库存基础结构（待人工审核执行）
-- 用途：
--   1. 区分普通 SKU 与独立组合父 SKU；
--   2. 保存固定组合的不可变版本和组件明细；
--   3. 以库存地点、余额和流水维护 mzShop 主库存；
--   4. 保存各 Shopify 店铺当前已同步的组合版本。
-- 影响：
--   修改 shop_goods_sku、shopify_store_config；
--   新增 shop_bundle_revision、shop_bundle_component、stock_location、
--        stock_balance、stock_ledger、shopify_bundle_map 共 6 张表。
-- 兼容性：MySQL 8；无外键；级联和“一个父 SKU 只能有一个已发布版本”由应用层保证。
-- 库存口径：可售 = on_hand - reserved - unavailable - safety_stock；组合父 SKU 不建库存余额。
-- 数据迁移：现有 SKU 全部回填为 normal；不自动创建库存地点或迁移 shop_goods_sku.stock，
--           避免未经人工确认把旧汇总库存归入错误地点。
--
-- 预览：
--   SELECT COUNT(*) AS sku_count, SUM(stock) AS legacy_stock FROM shop_goods_sku;
--   SELECT id, store_id, default_location_gid FROM shopify_store_config ORDER BY id;
--   SELECT id, sku_code, stock FROM shop_goods_sku WHERE stock <> 0 ORDER BY id;
--
-- 执行：人工备份并审核后执行；随后在后台创建默认库存地点，并人工确认旧 stock 的初始化方式。
-- 回滚前预览：
--   SELECT COUNT(*) FROM shop_bundle_revision;
--   SELECT COUNT(*) FROM stock_balance;
--   SELECT COUNT(*) FROM stock_ledger;
-- 回滚（会丢失组合版本、地点库存及流水）：
--   DROP TABLE IF EXISTS shopify_bundle_map, stock_ledger, stock_balance, stock_location,
--                        shop_bundle_component, shop_bundle_revision;
--   ALTER TABLE shopify_store_config DROP COLUMN stock_location_id;
--   ALTER TABLE shop_goods_sku DROP COLUMN sku_type;
-- 注意：回滚不会改动旧 shop_goods_sku.stock；执行和回滚均须由人工完成。
-- ============================================================

ALTER TABLE shop_goods_sku
  ADD COLUMN sku_type VARCHAR(20) NULL COMMENT 'SKU类型：normal普通 bundle组合父SKU' AFTER spec_name;

UPDATE shop_goods_sku SET sku_type = 'normal' WHERE sku_type IS NULL OR sku_type = '';

ALTER TABLE shop_goods_sku
  MODIFY COLUMN sku_type VARCHAR(20) NOT NULL DEFAULT 'normal' COMMENT 'SKU类型：normal普通 bundle组合父SKU';

ALTER TABLE shopify_store_config
  ADD COLUMN stock_location_id INT UNSIGNED NULL COMMENT 'stock_location.id，本店铺库存对应的本地地点' AFTER default_location_gid;

UPDATE shopify_store_config SET stock_location_id = 0 WHERE stock_location_id IS NULL;

ALTER TABLE shopify_store_config
  MODIFY COLUMN stock_location_id INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'stock_location.id，0表示尚未绑定本地库存地点',
  ADD KEY idx_shopify_store_config_stock_location (stock_location_id);

CREATE TABLE shop_bundle_revision (
  id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  parent_sku_id        INT UNSIGNED    NOT NULL COMMENT '组合父SKU，shop_goods_sku.id',
  version_no           INT UNSIGNED    NOT NULL COMMENT '父SKU内递增版本号',
  status               VARCHAR(20)     NOT NULL DEFAULT 'draft' COMMENT '状态：draft草稿 published已发布 disabled已停用',
  replaced_revision_id BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '替换的旧版本id，0表示无',
  remark               VARCHAR(500)    NOT NULL DEFAULT '' COMMENT '版本说明或组件替换原因',
  published_at         DATETIME        NULL COMMENT '发布时间',
  created_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_bundle_revision_parent_version (parent_sku_id, version_no),
  KEY idx_shop_bundle_revision_parent_status (parent_sku_id, status, id),
  KEY idx_shop_bundle_revision_replaced (replaced_revision_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='固定组合版本';

CREATE TABLE shop_bundle_component (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  revision_id      BIGINT UNSIGNED NOT NULL COMMENT 'shop_bundle_revision.id',
  component_sku_id INT UNSIGNED    NOT NULL COMMENT '普通组件SKU，shop_goods_sku.id',
  quantity         INT UNSIGNED    NOT NULL COMMENT '每套所需数量，必须大于0',
  sort_order       INT             NOT NULL DEFAULT 0 COMMENT '显示顺序，越小越靠前',
  created_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_bundle_component_revision_sku (revision_id, component_sku_id),
  KEY idx_shop_bundle_component_sku (component_sku_id, revision_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='固定组合版本组件';

CREATE TABLE stock_location (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  code       VARCHAR(50)  NOT NULL COMMENT '库存地点编码',
  name       VARCHAR(100) NOT NULL COMMENT '库存地点名称',
  status     TINYINT      NOT NULL DEFAULT 1 COMMENT '状态：1启用 0停用',
  remark     VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_stock_location_code (code),
  UNIQUE KEY uq_stock_location_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='库存地点';

CREATE TABLE stock_balance (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  sku_id       INT UNSIGNED    NOT NULL COMMENT '普通SKU，shop_goods_sku.id',
  location_id  INT UNSIGNED    NOT NULL COMMENT 'stock_location.id',
  on_hand      INT             NOT NULL DEFAULT 0 COMMENT '在库数量',
  reserved     INT             NOT NULL DEFAULT 0 COMMENT '已支付订单占用数量',
  unavailable  INT             NOT NULL DEFAULT 0 COMMENT '损坏、质检中等不可售数量',
  safety_stock INT             NOT NULL DEFAULT 0 COMMENT '安全库存，默认0',
  created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_stock_balance_sku_location (sku_id, location_id),
  KEY idx_stock_balance_location (location_id, sku_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU地点库存余额';

CREATE TABLE stock_ledger (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  sku_id            INT UNSIGNED    NOT NULL COMMENT '普通SKU，shop_goods_sku.id',
  location_id       INT UNSIGNED    NOT NULL COMMENT 'stock_location.id',
  event_type        VARCHAR(30)     NOT NULL COMMENT '类型：initial/manual/reserve/release/ship/return_sellable/return_unavailable/sync_correct',
  delta_on_hand     INT             NOT NULL DEFAULT 0 COMMENT '在库变化量',
  delta_reserved    INT             NOT NULL DEFAULT 0 COMMENT '占用变化量',
  delta_unavailable INT             NOT NULL DEFAULT 0 COMMENT '不可售变化量',
  after_on_hand     INT             NOT NULL COMMENT '变化后在库数量',
  after_reserved    INT             NOT NULL COMMENT '变化后占用数量',
  after_unavailable INT             NOT NULL COMMENT '变化后不可售数量',
  reference_type    VARCHAR(30)     NOT NULL DEFAULT '' COMMENT '来源类型：order/order_line/return/manual等',
  reference_id      BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '来源记录id，0表示无',
  idempotency_key   VARCHAR(160)    NOT NULL COMMENT '业务幂等键，同一库存动作只能出现一次',
  remark            VARCHAR(500)    NOT NULL DEFAULT '' COMMENT '中文说明',
  created_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_stock_ledger_idempotency (idempotency_key),
  KEY idx_stock_ledger_sku_location_created (sku_id, location_id, created_at),
  KEY idx_stock_ledger_reference (reference_type, reference_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='库存流水';

CREATE TABLE shopify_bundle_map (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id           INT UNSIGNED    NOT NULL COMMENT 'store.id',
  parent_sku_id      INT UNSIGNED    NOT NULL COMMENT '组合父SKU，shop_goods_sku.id',
  revision_id        BIGINT UNSIGNED NOT NULL COMMENT '最近成功同步的shop_bundle_revision.id',
  source_hash        CHAR(64)        NOT NULL DEFAULT '' COMMENT '最近成功同步的组合定义SHA-256',
  sync_status        VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '同步状态：pending/syncing/success/error',
  last_synced_at     DATETIME        NULL COMMENT '最近同步成功时间',
  last_error         TEXT            NULL COMMENT '最近错误，不得包含密钥或访问令牌',
  created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_bundle_map_sku_store (parent_sku_id, store_id),
  KEY idx_shopify_bundle_map_revision (revision_id),
  KEY idx_shopify_bundle_map_store_status (store_id, sync_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify组合版本同步映射';
