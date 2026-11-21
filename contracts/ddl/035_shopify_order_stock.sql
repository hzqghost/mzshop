-- ============================================================
-- 035 Shopify 订单镜像、退款退货与 Webhook 幂等（待人工审核执行）
-- 用途：
--   1. 镜像 Shopify 订单及普通/组合组件行，不在 mzShop 创建或改价；
--   2. 冻结组合版本、组件、金额、折扣、税费和成本快照；
--   3. 记录退款与极简退货入库确认；
--   4. 以 Webhook ID 去重，支撑“已支付占用、发货扣减、取消释放、退货入库”。
-- 影响：新增 shop_order、shop_order_line、shop_refund、shop_refund_line、
--      shop_return、shop_return_line、shopify_webhook_event 共 7 张表。
-- 兼容性：MySQL 8；无外键；订单不保存客户姓名、电话、地址或完整 Webhook 原文。
-- 依赖：应先执行并配置 034；store、SKU、组合版本、库存地点均由应用层校验。
-- 金额口径：同时保存店铺币种与顾客结算币种；退款使用原订单行快照，不按现价重算。
--
-- 预览：
--   SELECT id, code, name FROM store ORDER BY id;
--   SELECT id, store_id, stock_location_id, default_location_gid FROM shopify_store_config ORDER BY id;
--
-- 执行：人工备份并审核后执行；配置公网可信 HTTPS 和 Webhook 后方可正式接单。
-- 回滚前预览：
--   SELECT status, COUNT(*) FROM shopify_webhook_event GROUP BY status;
--   SELECT COUNT(*) FROM shop_order;
--   SELECT COUNT(*) FROM shop_refund;
--   SELECT COUNT(*) FROM shop_return;
-- 回滚（会丢失订单镜像、退款退货和 Webhook 幂等记录；先停止 Webhook）：
--   DROP TABLE IF EXISTS shopify_webhook_event, shop_return_line, shop_return,
--                        shop_refund_line, shop_refund, shop_order_line, shop_order;
-- 注意：回滚不会反向恢复 stock_balance；如已有库存流水，须按业务记录人工核对。
-- ============================================================

CREATE TABLE shop_order (
  id                       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id                 INT UNSIGNED    NOT NULL COMMENT 'store.id',
  external_order_gid       VARCHAR(100)    NOT NULL COMMENT 'Shopify Order GID',
  order_no                 VARCHAR(80)     NOT NULL COMMENT 'Shopify订单显示编号',
  financial_status         VARCHAR(30)     NOT NULL DEFAULT '' COMMENT '支付状态，按Shopify原值保存',
  fulfillment_status       VARCHAR(30)     NOT NULL DEFAULT '' COMMENT '履约状态，按Shopify原值保存',
  cancel_status            VARCHAR(20)     NOT NULL DEFAULT 'active' COMMENT '取消状态：active/cancelled',
  shop_currency            CHAR(3)         NOT NULL COMMENT '店铺币种',
  presentment_currency     CHAR(3)         NOT NULL COMMENT '顾客结算币种',
  total_price              DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种订单总额',
  presentment_total_price  DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '顾客结算币种订单总额',
  total_discount           DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种折扣合计',
  total_tax                DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种税费合计',
  processed_at             DATETIME        NULL COMMENT 'Shopify订单处理时间',
  cancelled_at             DATETIME        NULL COMMENT '取消时间',
  last_external_updated_at DATETIME        NULL COMMENT 'Shopify最近更新时间',
  created_at               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_order_store_external (store_id, external_order_gid),
  KEY idx_shop_order_store_no (store_id, order_no),
  KEY idx_shop_order_status (financial_status, fulfillment_status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify订单镜像';

CREATE TABLE shop_order_line (
  id                            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  order_id                      BIGINT UNSIGNED NOT NULL COMMENT 'shop_order.id',
  external_line_gid             VARCHAR(100)    NULL COMMENT 'Shopify LineItem GID；本地合成父行为空',
  external_group_gid            VARCHAR(100)    NOT NULL DEFAULT '' COMMENT 'Shopify组合分组GID',
  parent_line_id                BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '组合父行id，0表示顶层',
  line_type                     VARCHAR(20)     NOT NULL COMMENT '类型：normal普通 bundle_parent组合父行 bundle_component组件行',
  goods_id                      INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT 'shop_goods.id，删除后仍保留快照',
  sku_id                        INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT 'shop_goods_sku.id，删除后仍保留快照',
  bundle_revision_id            BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'shop_bundle_revision.id，非组合为0',
  sku_code                      VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '下单时SKU编码快照',
  title                         VARCHAR(300)    NOT NULL COMMENT '下单时商品标题快照',
  spec_name                     VARCHAR(200)    NOT NULL DEFAULT '' COMMENT '下单时规格快照',
  quantity                      INT UNSIGNED    NOT NULL COMMENT '订购数量',
  reserved_quantity             INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '当前已占用库存数量',
  fulfilled_quantity            INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '已发货数量',
  cancelled_quantity            INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '已取消数量',
  refunded_quantity             INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '已退款数量',
  returned_sellable_quantity    INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '已确认可售退货数量',
  returned_unavailable_quantity INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '已确认不可售退货数量',
  unit_original_price           DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种原单价快照',
  allocated_subtotal            DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种分摊成交小计',
  allocated_discount            DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种分摊折扣',
  allocated_tax                 DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种分摊税费',
  presentment_subtotal          DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '顾客结算币种分摊成交小计',
  presentment_discount          DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '顾客结算币种分摊折扣',
  presentment_tax               DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '顾客结算币种分摊税费',
  unit_cost                     DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '下单时组件单位成本快照',
  created_at                    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at                    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_order_line_external (order_id, external_line_gid),
  KEY idx_shop_order_line_order_parent (order_id, parent_line_id, id),
  KEY idx_shop_order_line_sku (sku_id, order_id),
  KEY idx_shop_order_line_group (order_id, external_group_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单行及组合组件快照';

CREATE TABLE shop_refund (
  id                       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  order_id                 BIGINT UNSIGNED NOT NULL COMMENT 'shop_order.id',
  store_id                 INT UNSIGNED    NOT NULL COMMENT 'store.id，便于按外部GID去重',
  external_refund_gid      VARCHAR(100)    NOT NULL COMMENT 'Shopify Refund GID',
  amount                   DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种退款总额',
  presentment_amount       DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '顾客结算币种退款总额',
  shipping_amount          DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种退运费',
  tax_amount               DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种退税合计',
  processed_at             DATETIME        NULL COMMENT 'Shopify退款处理时间',
  created_at               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_refund_store_external (store_id, external_refund_gid),
  KEY idx_shop_refund_order (order_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify退款镜像';

CREATE TABLE shop_refund_line (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  refund_id          BIGINT UNSIGNED NOT NULL COMMENT 'shop_refund.id',
  order_line_id      BIGINT UNSIGNED NOT NULL COMMENT 'shop_order_line.id',
  quantity           INT UNSIGNED    NOT NULL COMMENT '退款数量',
  subtotal           DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种退款小计',
  tax                DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '店铺币种退税',
  presentment_total  DECIMAL(12,2)   NOT NULL DEFAULT 0 COMMENT '顾客结算币种退款含税金额',
  restock_type       VARCHAR(30)     NOT NULL DEFAULT '' COMMENT 'Shopify补库存类型原值；不直接等同本地入库',
  created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_refund_line_refund_order_line (refund_id, order_line_id),
  KEY idx_shop_refund_line_order_line (order_line_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify退款行';

CREATE TABLE shop_return (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  order_id            BIGINT UNSIGNED NOT NULL COMMENT 'shop_order.id',
  store_id            INT UNSIGNED    NOT NULL COMMENT 'store.id',
  external_return_gid VARCHAR(100)    NULL COMMENT 'Shopify Return GID；人工登记可为空',
  status              VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '状态：pending待收货 received已确认 cancelled已取消',
  received_at         DATETIME        NULL COMMENT '实物收货确认时间',
  remark              VARCHAR(500)    NOT NULL DEFAULT '' COMMENT '退货及质检备注',
  created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_return_store_external (store_id, external_return_gid),
  KEY idx_shop_return_order_status (order_id, status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='退货及入库确认';

CREATE TABLE shop_return_line (
  id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  return_id            BIGINT UNSIGNED NOT NULL COMMENT 'shop_return.id',
  order_line_id        BIGINT UNSIGNED NOT NULL COMMENT 'shop_order_line.id，只允许普通或组合组件行',
  quantity             INT UNSIGNED    NOT NULL COMMENT '退回数量',
  sellable_quantity    INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '质检后可售数量',
  unavailable_quantity INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '质检后不可售数量',
  reason               VARCHAR(200)    NOT NULL DEFAULT '' COMMENT '退货原因',
  created_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shop_return_line_return_order_line (return_id, order_line_id),
  KEY idx_shop_return_line_order_line (order_line_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='退货组件及质检结果';

CREATE TABLE shopify_webhook_event (
  id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  store_id             INT UNSIGNED    NOT NULL COMMENT 'store.id',
  webhook_id           VARCHAR(100)    NOT NULL COMMENT 'Shopify Webhook ID，用于幂等去重',
  topic                VARCHAR(80)     NOT NULL COMMENT 'Webhook主题',
  external_resource_id VARCHAR(100)    NOT NULL DEFAULT '' COMMENT '订单、退款或履约等外部资源GID',
  payload_sha256       CHAR(64)        NOT NULL COMMENT '原始请求体SHA-256；不保存含客户资料的完整原文',
  status               VARCHAR(20)     NOT NULL DEFAULT 'processed' COMMENT '处理状态：processed/ignored/failed',
  error_message        TEXT            NULL COMMENT '失败原因，不得包含客户资料、密钥或令牌',
  received_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '接收时间',
  processed_at         DATETIME        NULL COMMENT '处理完成时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_shopify_webhook_event_store_webhook (store_id, webhook_id),
  KEY idx_shopify_webhook_event_status_received (status, received_at),
  KEY idx_shopify_webhook_event_resource (store_id, external_resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Shopify Webhook幂等记录';
