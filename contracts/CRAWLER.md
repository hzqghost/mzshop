# CRAWLER 契约 — 采集任务系统

> 状态：一期设计稿。表结构见 `ddl/001_crawl_tables.sql`（已于 2026-11-10 执行）。

## 1. 概念
- **任务 crawl_task**：用户录入的条件 = 平台 + 搜索关键字 + 页数 + 分类名列表 + 遍历属性名（如 Fragrance Name）。
- **执行 crawl_run**：任务每次运行一行。
- **采集单元 crawl_run_unit**：运行时展开为「分类 × 属性值」，**每个单元单独采集**（各自在该分类下、选中该属性值、翻 1..max_pages 页）。属性值来自搜索页左侧该属性的可选项，运行时读取，不手工录入。不设遍历属性时，每个分类一个单元。
- **商品 product**：`(platform, item_id)` 唯一；已存在则**新数据覆盖旧数据**（upsert，刷新 last_crawled_at，保留 first_crawled_at）。
- **评价 product_review**：`(product_id, review_key)` 唯一，重复评价忽略/更新。

- **快照 product_snapshot**：每次采集追加一行价格/浏览/销量等，用于趋势分析；`product` 仍只保留最新值。
- 评价分两类（`review_type`）：`product` 商品评价、`seller` 卖家反馈。

## 2. 商品字段分层
1. 参与搜索的条件：`category_name` 单独成列；遍历的左侧属性（含 Fragrance Name）存 `search_attrs` JSON（`{属性名: 属性值}`），与 `attributes` 分开。
2. eBay 公共属性单独成列：brand、item_condition、mpn、upc、country_of_origin、listing_type；价格/热度/卖家类列（price、view_count、sold_count 等）。
3. 其余 Item Specifics 进 `attributes` JSON。
4. 页面上取不到的值存 NULL（不要用 0 冒充），文本取不到存空串。

## 3. 平台扩展约定
- 每个平台一个采集器，放 `tool/crawler/<platform>/`，实现统一接口：`list_attr_values(task, category)`、`search(task, category, attr_value, page)`、`parse_item(...)`、`fetch_reviews(item)`，输出统一的商品字典（键名即 product 列名 + attributes）。
- 新平台复用 `product` 表（platform 区分）；平台特有公共属性是否单独成列须先确认，否则进 attributes。

## 4. 运行架构
- 采集器是**独立进程**（`tool/crawler`），admin 与它只通过数据库通信，互不调用。
- 手动执行：admin 点击「执行」→ 插入 `crawl_run`（status=pending，trigger_type=manual）→ 采集器轮询领取 pending 的 run，展开单元并执行，回写进度。
- 定时执行：任务 `schedule_enabled=1` 且有 `schedule_cron` 时，采集器按 `next_run_at` 自动创建 trigger_type=schedule 的 run；**默认不定时**。同一任务已有 pending/running 的 run 时不重复创建。
- 单元失败不影响其他单元；run 状态：全成功 success、部分失败 partial、全失败 failed。
- 领取 run 需加锁（如 `UPDATE ... WHERE status='pending'` 判断影响行数），避免多进程重复执行。

## 5. 抓取规则
- 限速：同一域名请求间隔有下限（默认 ≥2 秒，可配置），单进程串行。
- 使用Google Chrome  156.0.8078.80或接近版本的 User-Agent

## 6. 实现与运行（一期，2026-11-10）
采集器已落地于 `tool/crawler/`，独立进程，只通过数据库与 admin 通信（不互调）。

### 目录
```
tool/crawler/
  run.py            入口：--loop(默认持续) / --once(处理一次) / --run-id N(调试) / --no-schedule
  config.py         读 .env；Chrome156 UA、>=2s 限速、退避、MAX_PAGES=10、浏览器通道、可选代理
  db.py / models.py 独立 engine/Base；完整映射 6 表（含 admin 未映射的 product/review/snapshot）；不建表
  worker.py         原子领取 pending run → 展开单元 → 逐单元采集 → 回写进度/状态；单元间检查 cancelled
  scheduler.py      croniter 算 next_run_at；到期且无 active run 才建 schedule run（去重）
  storage.py        product upsert（保留 first_crawled_at、刷新 last_crawled_at）、snapshot 追加、review 去重
  ratelimit.py      每域最小间隔 + 指数退避
  base.py/registry.py  采集器统一接口与平台分发（懒加载）
  ebay/             browser.py(httpx 快路径+Playwright 兜底) / parse.py(JSON-LD 优先+CSS 兜底) / collector.py
```

### 运行
```
cd tool/crawler
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# 默认用已安装的 Chrome（channel=chrome），无需 playwright install；若留空通道则需 playwright install chromium
.venv/Scripts/python run.py            # 持续轮询领取 admin 点「执行」产生的 pending run
.venv/Scripts/python run.py --once     # 只处理一次
```
`.env` 见 `.env.example`（DB_* 必填，其余有默认值）。

### 采集器接口（base.py，与 §3 一致）
- `list_attr_values(task, category)`：运行时读搜索页左侧 `attr_name` 的 refine 选项；空 attr_name 返回 `['']`。
- `search(task, category, attr_value, page)`：返回商品 stub（item_id/product_url/title/price…）。
- `parse_item(stub, task, category, attr_value)`：抓详情→统一 product 字典；遍历属性入 `search_attrs`、其余 specifics 入 `attributes`；取不到数值 None、文本空串。
- `fetch_reviews(item)`：商品评价（复用刚抓的详情 HTML，避免重复请求）。

### 关键行为
- 分类/属性筛选优先复用 eBay 自己的 refine href（含 _sacat/aspect 参数）；解析不到时退回关键字搜索（局限见 TODO）。
- 取页 `min(task.max_pages, 10)`，与 admin `MAX_PAGES_LIMIT` 一致，防御性硬上限。
- 网络默认直连：httpx `trust_env=False`、Chrome `--no-proxy-server`，避开本机损坏的代理环境变量；需要代理时设 `CRAWLER_PROXY`。
- 遇 403/429/验证码：退避重试（次数上限）后抛 `BlockedError`，该单元标记 failed，不影响其它单元；不绕过、不破解、不做隐身规避。
- run 状态汇总：全成功 success、部分失败 partial、全失败 failed；取消则保留 cancelled、剩余单元 skipped。

