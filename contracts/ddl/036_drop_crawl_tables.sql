-- 036 删除已停用的数据采集模块表
-- 用途：彻底移除采集任务、执行记录、采集商品、评价和快照数据。
-- 影响：永久删除 6 张采集表及其全部数据；不影响 shop_* 自有商品、供应商目录和 Shopify 数据。
-- 预览：执行下方 information_schema 查询，确认 6 张目标表及行数后再执行 DROP TABLE。
-- 执行：人工备份确认后，按本文件顺序执行 DROP TABLE；应用代码不会自动执行本脚本。
-- 回滚：表结构可重新执行 001_crawl_tables.sql 恢复，已删除数据只能从执行前备份恢复。

SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
    'crawl_task', 'crawl_run', 'crawl_run_unit',
    'product', 'product_review', 'product_snapshot'
  )
ORDER BY table_name;

DROP TABLE IF EXISTS product_snapshot;
DROP TABLE IF EXISTS product_review;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS crawl_run_unit;
DROP TABLE IF EXISTS crawl_run;
DROP TABLE IF EXISTS crawl_task;
