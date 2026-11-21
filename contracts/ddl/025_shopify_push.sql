-- ============================================================
-- 025 Shopify 主动推送基础结构（已于 2026-11-18 经授权执行）
-- 用途：
--   1. 为现有 store 保存 Shopify 店铺域名、价格区域、内容语言、默认库存地点和发布渠道；
--   2. 保存 mzShop 商品/SKU 与 Shopify Product/Variant/InventoryItem 的稳定映射；
--   3. 以持久化任务驱动商品、价格、库存主动推送，并保留失败告警和重试信息。
-- 范围：仅 mzShop -> Shopify；本期不含 Webhook、订单、客户和反向覆盖。
-- 敏感信息：Client ID / Client Secret 只放 admin/.env，本脚本不保存密钥或访问令牌。
-- 影响：新增 4 张表，不修改现有表；不建外键，删除和级联由应用层处理。
-- 兼容性：MySQL 8；InnoDB；utf8mb4 / utf8mb4_unicode_ci。
--
-- 预览：
--   SELECT id, platform_id, code, name, website FROM store ORDER BY id;
--   SELECT id, code, name FROM platform WHERE LOWER(code) = 'shopify' OR LOWER(name_en) = 'shopify';
--   SELECT id, code, name FROM sys_region ORDER BY sort_order, id;
--   SELECT code, name, status FROM shop_language ORDER BY sort_order, id;
--
-- 执行：人工审核后在测试库执行本文件；执行后再启动包含对应 ORM 模型的 admin。
-- 回滚前预览：
--   SELECT status, COUNT(*) FROM shopify_sync_task GROUP BY status;
--   SELECT COUNT(*) AS product_maps FROM shopify_product_map;
--   SELECT COUNT(*) AS variant_maps FROM shopify_variant_map;
-- 回滚（会丢失全部 Shopify 映射与同步记录）：
--   DROP TABLE IF EXISTS shopify_sync_task, shopify_variant_map, shopify_product_map, shopify_store_config;
-- ============================================================

CREATE TABLE shopify_store_config (
  id                    INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id              INT UNSIGNED NOT NULL COMMENT 'store.id',
  shop_domain           VARCHAR(255) NOT NULL COMMENT 'Shopify 固定域名，格式为 xxx.myshopify.com',
  shop_gid              VARCHAR(100) NOT NULL DEFAULT '' COMMENT 'Shopify Shop GID，连接测试后回填',
  region_id             INT UNSIGNED NOT NULL COMMENT 'sys_region.id，推送价格取该区域',
  language_code         VARCHAR(20)  NOT NULL DEFAULT '' COMMENT 'shop_language.code，空表示默认语言',
  default_location_gid  VARCHAR(100) NOT NULL DEFAULT '' COMMENT '默认 Shopify Location GID，推送库存必填',
  publication_gid       VARCHAR(100) NOT NULL DEFAULT '' COMMENT 'Shopify Publication GID，发布商品时使用',
  currency              CHAR(3)      NOT NULL DEFAULT '' COMMENT '店铺币种，大写 ISO 4217；连接测试后校验',
  sync_enabled          TINYINT      NOT NULL DEFAULT 1 COMMENT '1允许同步 0暂停同步',
  connection_status     VARCHAR(20)  NOT NULL DEFAULT 'unchecked' COMMENT '连接状态：unchecked/ok/error',
  last_connected_at     DATETIME     NULL COMMENT '最近连接成功时间',
  last_error            TEXT         NULL COMMENT '最近连接错误，不得包含密钥或访问令牌',
  created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_store_config_store (store_id),
  UNIQUE KEY uq_shopify_store_config_domain (shop_domain),
  KEY idx_shopify_store_config_region (region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 店铺配置';

CREATE TABLE shopify_product_map (
  id                 INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id           INT UNSIGNED NOT NULL COMMENT 'store.id',
  goods_id           INT UNSIGNED NOT NULL COMMENT 'shop_goods.id',
  product_gid        VARCHAR(100) NOT NULL COMMENT 'Shopify Product GID',
  source_hash        CHAR(64)     NOT NULL DEFAULT '' COMMENT '最近成功推送的 mzShop 商品内容 SHA-256',
  sync_status        VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT '同步状态：pending/syncing/success/error/warning',
  last_synced_at     DATETIME     NULL COMMENT '最近同步成功时间',
  remote_updated_at  DATETIME     NULL COMMENT '同步后读取到的 Shopify 更新时间',
  last_error         TEXT         NULL COMMENT '最近同步错误或远端改动告警',
  created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_product_map_goods_store (goods_id, store_id),
  UNIQUE KEY uq_shopify_product_map_product_store (product_gid, store_id),
  KEY idx_shopify_product_map_store_status (store_id, sync_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 商品映射';

CREATE TABLE shopify_variant_map (
  id                  INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id            INT UNSIGNED NOT NULL COMMENT 'store.id',
  goods_id            INT UNSIGNED NOT NULL COMMENT 'shop_goods.id，便于应用层级联清理',
  sku_id              INT UNSIGNED NOT NULL COMMENT 'shop_goods_sku.id',
  variant_gid         VARCHAR(100) NOT NULL COMMENT 'Shopify ProductVariant GID',
  inventory_item_gid  VARCHAR(100) NOT NULL DEFAULT '' COMMENT 'Shopify InventoryItem GID',
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_variant_map_sku_store (sku_id, store_id),
  UNIQUE KEY uq_shopify_variant_map_variant_store (variant_gid, store_id),
  KEY idx_shopify_variant_map_goods_store (goods_id, store_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify SKU 映射';

CREATE TABLE shopify_sync_task (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id          INT UNSIGNED NOT NULL COMMENT 'store.id',
  goods_id          INT UNSIGNED NOT NULL COMMENT 'shop_goods.id',
  action            VARCHAR(30)  NOT NULL DEFAULT 'upsert_product' COMMENT '动作：upsert_product/archive_product/sync_inventory',
  status            VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT '状态：pending/running/success/failed/cancelled',
  retry_count       INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已重试次数',
  max_retries       INT UNSIGNED NOT NULL DEFAULT 3 COMMENT '最大重试次数',
  next_retry_at     DATETIME     NULL COMMENT '下次允许重试时间',
  locked_at         DATETIME     NULL COMMENT '任务领取时间',
  started_at        DATETIME     NULL COMMENT '开始处理时间',
  finished_at       DATETIME     NULL COMMENT '处理完成时间',
  request_id        VARCHAR(100) NOT NULL DEFAULT '' COMMENT '最近一次 Shopify 请求追踪标识',
  error_message     TEXT         NULL COMMENT '失败原因，不得包含密钥、令牌或完整请求头',
  created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_shopify_sync_task_claim (status, next_retry_at, id),
  KEY idx_shopify_sync_task_goods_store (goods_id, store_id, id),
  KEY idx_shopify_sync_task_store_created (store_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify 主动同步任务';
