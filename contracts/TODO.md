# 已知偏差与待办（开工前先看）

## 与契约的偏差
1. **建表方式**：`main.py` 用 `create_all` 启动即建表，违背 DB.md「DDL 人工审核执行」。建议改为：模型变更输出 DDL 脚本人工执行，去掉 create_all（或仅在开发库启用）。
2. **Comment 缺失**：`sys_user` 的 id/created_at/updated_at、`sys_ui_style` 全部字段缺中文 Comment，违背 DB.md 第 5 条。补注释须走「只改 Comment」的 DDL。
3. **超级管理员口令硬编码**在 `admin/app/config.py`（明文），应改为 .env 配置（存哈希更好）；`SECRET_KEY` 也须是强随机值。
4. `requirements.txt` / `.env.example` 带 UTF-8 BOM，注意工具兼容。

## 待开发
- 电商业务域建模：平台/店铺、商品(SPU/SKU)、订单、订单明细、客户、库存、售后、广告/费用等——**需先与业务方确认范围和字段**，再出 DDL。
- `tool/crawler`：采集工具**一期已实现**（独立进程，Playwright+httpx，eBay 采集器；运行/接口见 CRAWLER.md §6）。剩余局限见下「采集器一期局限」。
- 数据分析：报表/看板（指标口径待定，图表库待定，DevExtreme 自带图表可用）。
- 角色与权限；操作日志；用户列表分页；Alembic 迁移（表增多后）。

## 采集器一期局限（2026-11-10）
1. **eBay 选择器未在真实页面校准**：开发机出口 IP 被 eBay 返回 403（httpx 与 Chrome 均如此），无法在此抓真实页校准。解析以 JSON-LD 优先 + 多组 CSS 兜底写成，需在有浏览器/住宅网络的环境跑一次真实任务，按实际 DOM 微调 `ebay/parse.py` 选择器。
2. **分类名→筛选**：任务存的是分类名，采集器从搜索页左侧 Category facet 解析其筛选 href（含 _sacat）；解析不到时退回关键字搜索（不精确按分类过滤）。属性值同理复用 refine href，兜底用 `&属性名=值` 参数。
3. **评价**：一期只解析详情页内的商品评价（JSON-LD review / CSS），`review_type=seller` 卖家反馈尚未实现（需另抓卖家反馈页）。
4. **反爬**：遇 403/429/验证码只退避重试后标记单元失败，不绕过/不破解；若长期受阻，需在有正常浏览器环境处运行，或设 `CRAWLER_PROXY`、`CRAWLER_HEADLESS=0`。
5. **崩溃恢复**：领取后若进程崩溃，run 会停在 running（不会被自动重新领取）；单元支持复用（重置 run 为 pending 可断点续跑），但 running 僵死 run 需人工重置。
6. **环境代理**：本机代理环境变量损坏（`HTTP_PROXY禁用`、`NO_PROXY` 含 `[::1]`），采集器默认直连并忽略系统代理；如需代理走 `CRAWLER_PROXY`。

## 商品管理
- 「商品管理」菜单 = 自有商品目录（shop_* 表，见 API.md §5）；采集的 `product` 表放在「数据采集 → 采集商品」，两者互不关联。
- 待办：币种；SKU 多规格维度（颜色/尺码组合生成）；图片存储（现存本地 static/uploads，删除商品不清理文件；上线需对象存储或备份）；库存流水；批量导入导出；分类 `status` 目前不影响商品录入；商品与采集商品的关联（如从采集商品一键入库）待确认。
- 页面：/goods（列表+SKU 子表）、/goodsEdit（商品详情，内容标签页）、/goodsCategories（树）、/goodsAttributes、/goodsLanguages；共用 `static/js/lib/shop.js`。
- 多语言待办：批量导入导出译文、机器翻译辅助、翻译完成度展示（哪些商品缺哪种语言）、品牌/供应商是否需要多语言、价格是否按语言/地区区分（币种）——待确认。
- 多语言：列表页每多一种启用语言就多一列，语言多了表格会很宽，届时需要「按语言开关列」；商品文本属性的译文只存「属性值」，若属性名改名需同步处理（译文按属性名取键）。
