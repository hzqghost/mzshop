-- ============================================================
-- 001 采集任务系统建表（待人工审核，未执行）
-- 用途：采集任务、执行记录、展开的采集单元、商品、商品评价
-- 影响：仅新增 6 张表，不改动现有表
-- 兼容性：MySQL 8；utf8mb4 / utf8mb4_unicode_ci / InnoDB
-- 注意：执行前先备份并在测试环境验证
-- 回滚：见文件末尾（会删除数据，确认后再执行）
-- ============================================================

-- 1. 采集任务（用户在后台录入的条件）
CREATE TABLE crawl_task (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  platform        VARCHAR(20)  NOT NULL DEFAULT 'ebay' COMMENT '平台标识，如 ebay',
  name            VARCHAR(100) NOT NULL COMMENT '任务名称',
  keyword         VARCHAR(200) NOT NULL COMMENT '搜索关键字，如 perfume',
  max_pages       SMALLINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '每个采集单元最多采集的搜索结果页数',
  category_names  JSON         NOT NULL COMMENT '需遍历的分类名数组，如 ["Women''s Fragrances","Men''s Fragrances"]',
  attr_name       VARCHAR(100) NOT NULL DEFAULT '' COMMENT '需遍历的左侧筛选属性名，如 Fragrance Name；空表示不按属性遍历',
  status          TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  schedule_enabled TINYINT     NOT NULL DEFAULT 0 COMMENT '是否定时执行 1是 0否（默认否，仅手动点击执行）',
  schedule_cron   VARCHAR(100) NOT NULL DEFAULT '' COMMENT '定时表达式（5段 cron，如 0 3 * * *）；schedule_enabled=1 时必填',
  next_run_at     DATETIME     NULL COMMENT '下次定时执行时间，由采集器根据 schedule_cron 计算',
  last_run_at    DATETIME     NULL COMMENT '最近一次开始执行时间',
  created_by      INT          NOT NULL DEFAULT 0 COMMENT '创建人 sys_user.id，0为超级管理员',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_task_platform_status (platform, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集任务';

-- 2. 采集执行记录（任务每执行一次一行）
CREATE TABLE crawl_run (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  task_id       INT UNSIGNED NOT NULL COMMENT '所属任务 crawl_task.id',
  trigger_type  VARCHAR(20)  NOT NULL DEFAULT 'manual' COMMENT '触发方式 manual手动点击 schedule定时',
  status       VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending待执行 running执行中 success成功 partial部分失败 failed失败 cancelled已取消',
  total_units   INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '展开的采集单元总数',
  done_units    INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已完成单元数',
  item_count    INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '本次采集到的商品条数（含覆盖更新）',
  error_msg     VARCHAR(500) NOT NULL DEFAULT '' COMMENT '失败原因摘要',
  started_at    DATETIME     NULL COMMENT '开始时间',
  finished_at   DATETIME     NULL COMMENT '结束时间',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_run_task (task_id, id),
  KEY idx_run_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集执行记录';

-- 3. 采集单元（分类 × 属性值 展开后，每个单元单独采集，可断点重试）
CREATE TABLE crawl_run_unit (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  run_id        INT UNSIGNED NOT NULL COMMENT '所属执行记录 crawl_run.id',
  category_name VARCHAR(200) NOT NULL COMMENT '分类名',
  attr_value    VARCHAR(200) NOT NULL DEFAULT '' COMMENT '属性值，如具体的 Fragrance Name；不按属性遍历时为空',
  status        VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending待执行 running执行中 success成功 failed失败 skipped跳过',
  pages_done    SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已采集页数',
  item_count    INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已采集商品条数',
  error_msg     VARCHAR(500) NOT NULL DEFAULT '' COMMENT '失败原因',
  started_at    DATETIME     NULL COMMENT '开始时间',
  finished_at   DATETIME     NULL COMMENT '结束时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_unit_run_cond (run_id, category_name, attr_value),
  KEY idx_unit_status (run_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集单元';

-- 4. 商品（平台+商品编号唯一；重复采集时新数据覆盖旧数据）
CREATE TABLE product (
  id                  INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  platform            VARCHAR(20)  NOT NULL DEFAULT 'ebay' COMMENT '平台标识',
  item_id             VARCHAR(40)  NOT NULL COMMENT '平台商品编号（eBay Item Number）',
  task_id             INT UNSIGNED NULL COMMENT '最近一次采集到它的任务 crawl_task.id',
  run_id              INT UNSIGNED NULL COMMENT '最近一次采集到它的执行记录 crawl_run.id',
  title               VARCHAR(500) NOT NULL DEFAULT '' COMMENT '商品标题',
  product_url         VARCHAR(500) NOT NULL DEFAULT '' COMMENT '商品详情页链接',
  image_url           VARCHAR(500) NOT NULL DEFAULT '' COMMENT '主图链接',
  -- 参与搜索的条件
  category_name       VARCHAR(200) NOT NULL DEFAULT '' COMMENT '搜索时所属分类名',
  search_attrs        JSON         NULL COMMENT '参与搜索遍历的左侧属性键值，如 {"Fragrance Name":"Chanel No 5"}；与 attributes 分开',
  -- eBay 公共属性
  brand               VARCHAR(100) NOT NULL DEFAULT '' COMMENT '品牌',
  item_condition      VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '成色，如 New、Pre-owned',
  mpn                 VARCHAR(100) NOT NULL DEFAULT '' COMMENT '制造商零件号',
  upc                 VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '通用商品条码',
  country_of_origin   VARCHAR(100) NOT NULL DEFAULT '' COMMENT '制造国家/地区',
  listing_type        VARCHAR(30)  NOT NULL DEFAULT '' COMMENT '销售方式，如 Buy It Now、Auction',
  -- 价格与热度
  price               DECIMAL(12,2) NULL COMMENT '当前价格',
  currency            CHAR(3)      NOT NULL DEFAULT '' COMMENT '价格币种，如 USD',
  shipping_price      DECIMAL(12,2) NULL COMMENT '运费，免运费为 0，未知为空',
  original_price      DECIMAL(12,2) NULL COMMENT '划线原价',
  view_count          INT UNSIGNED NULL COMMENT '浏览量（页面未显示为空）',
  watcher_count       INT UNSIGNED NULL COMMENT '关注人数',
  sold_count          INT UNSIGNED NULL COMMENT '已售数量（页面未显示为空）',
  available_qty       INT UNSIGNED NULL COMMENT '剩余库存',
  review_count        INT UNSIGNED NULL COMMENT '评价数量',
  review_avg          DECIMAL(3,2) NULL COMMENT '平均评分',
  -- 卖家
  seller_name         VARCHAR(100) NOT NULL DEFAULT '' COMMENT '卖家名称',
  seller_feedback_pct DECIMAL(5,2) NULL COMMENT '卖家好评率(%)',
  seller_feedback_cnt INT UNSIGNED NULL COMMENT '卖家评价总数',
  item_location       VARCHAR(100) NOT NULL DEFAULT '' COMMENT '商品所在地',
  -- 其他
  attributes          JSON         NULL COMMENT '其他商品属性（Item Specifics 中未单独成列的键值对）',
  first_crawled_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次采集时间',
  last_crawled_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近采集时间（覆盖更新时刷新）',
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_product_platform_item (platform, item_id),
  KEY idx_product_task (task_id),
  KEY idx_product_category (category_name),
  KEY idx_product_brand (brand),
  KEY idx_product_crawled (last_crawled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品';

-- 5. 商品评价
CREATE TABLE product_review (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  product_id     INT UNSIGNED NOT NULL COMMENT '所属商品 product.id',
  review_type    VARCHAR(20)  NOT NULL DEFAULT 'product' COMMENT '评价类型 product商品评价 seller卖家反馈',
  review_key     VARCHAR(64)  NOT NULL COMMENT '评价唯一标识：平台评价ID；无ID时取 评价人+日期+内容 的哈希，用于去重',
  reviewer_name  VARCHAR(100) NOT NULL DEFAULT '' COMMENT '评价人',
  rating         TINYINT UNSIGNED NULL COMMENT '评分 1-5',
  title          VARCHAR(300) NOT NULL DEFAULT '' COMMENT '评价标题',
  content        TEXT         NULL COMMENT '评价内容',
  reviewed_at    DATE         NULL COMMENT '评价日期',
  helpful_count  INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '认为有帮助的人数',
  is_verified    TINYINT      NOT NULL DEFAULT 0 COMMENT '是否已验证购买 1是 0否',
  crawled_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '采集时间',
  PRIMARY KEY (id),
  UNIQUE KEY uq_review_product_key (product_id, review_type, review_key),
  KEY idx_review_date (reviewed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品评价（含商品评价与卖家反馈）';

-- 6. 商品价格/热度快照（每次采集追加一行，product 表本身仍是覆盖更新）
CREATE TABLE product_snapshot (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  product_id     INT UNSIGNED NOT NULL COMMENT '所属商品 product.id',
  run_id         INT UNSIGNED NULL COMMENT '产生快照的执行记录 crawl_run.id',
  price          DECIMAL(12,2) NULL COMMENT '当时价格',
  currency       CHAR(3)      NOT NULL DEFAULT '' COMMENT '币种',
  shipping_price DECIMAL(12,2) NULL COMMENT '当时运费',
  view_count     INT UNSIGNED NULL COMMENT '当时浏览量',
  watcher_count  INT UNSIGNED NULL COMMENT '当时关注人数',
  sold_count     INT UNSIGNED NULL COMMENT '当时已售数量',
  available_qty  INT UNSIGNED NULL COMMENT '当时剩余库存',
  review_count   INT UNSIGNED NULL COMMENT '当时评价数量',
  review_avg     DECIMAL(3,2) NULL COMMENT '当时平均评分',
  crawled_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '采集时间',
  PRIMARY KEY (id),
  KEY idx_snapshot_product_time (product_id, crawled_at),
  KEY idx_snapshot_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品价格热度快照';

-- ============================================================
-- 回滚（会删除数据，确认后再执行）
-- DROP TABLE product_snapshot;
-- DROP TABLE product_review;
-- DROP TABLE product;
-- DROP TABLE crawl_run_unit;
-- DROP TABLE crawl_run;
-- DROP TABLE crawl_task;
-- ============================================================
