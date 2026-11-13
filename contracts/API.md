# API 契约

## 1. 通用
- 前缀 `/api/v1/<module>`；JSON；UTF-8；时间 `YYYY-MM-DD HH:MM:SS`（服务器本地时间）。
- 响应统一：`{"code": 0, "data": <any>, "msg": "ok"}`；`code=0` 成功，失败时 `code` 等于 HTTP 状态码，`data=null`，`msg` 为中文原因。
- 失败通过 `raise HTTPException(status, msg)`，由 `main.py` 统一转成上述格式。
- 状态码：400 参数错误 · 401 未登录 · 404 不存在 · 其余服务器异常 500。
- 鉴权：除登录外一律 `require_user`；暂无角色权限。
- 布尔字段对外用 `true/false`（库中 `SmallInteger 1/0`）。
- 在线文档：`/api/docs`。

## 2. REST 资源约定（DxGrid.restStore 依赖）
| 动作 | 方法与路径 | 说明 |
|---|---|---|
| 列表 | `GET /api/v1/<res>` | `data` 为数组（目前整表返回，数据量大后需分页，见 TODO） |
| 新增 | `POST /api/v1/<res>` | body 为字段对象；`data` 返回新记录 |
| 修改 | `PUT /api/v1/<res>/{id}` | 只传变更字段；`data` 返回更新后记录 |
| 删除 | `DELETE /api/v1/<res>/{id}` | `data=null` |

## 3. 现有接口
| 接口 | 说明 |
|---|---|
| `POST /login/do`（表单） | 登录，303 跳转；失败 `/login?error=credentials\|disabled` |
| `GET /logout` | 退出 |
| `GET/POST /api/v1/users`、`PUT/DELETE /api/v1/users/{id}` | 用户 CRUD；用户名创建后不可改；密码仅写入，编辑时留空不改；不返回 `password_hash` |
| `POST /api/v1/ui-style/{kind}/save` | `kind`=grid\|form；body `{values:{...}}`；只能改自己的 |
| `POST /api/v1/ui-style/{kind}/reset` | 重置为默认 |

## 4. 采集任务接口（`/api/v1/crawl-tasks`，均需登录）
| 接口 | 说明 |
|---|---|
| `GET/POST ""`、`PUT/DELETE /{id}` | 任务 CRUD。字段：name、platform(ebay)、keyword、max_pages(1~10，硬上限）、category_names(数组，去空去重)、attr_name、status、schedule_enabled、schedule_cron(5段，启用定时时必填)。列表附带 last_run_status。删除会连带删除其执行记录与单元，已采集商品保留；有待执行/执行中记录时拒绝 |
| `POST /{id}/run` | 点击「执行」：插入 status=pending、trigger_type=manual 的 crawl_run，交给采集器领取；任务停用或已有 pending/running 记录时 400 |
| `GET /{id}/runs` | 该任务最近 200 条执行记录 |
| `POST /runs/{run_id}/cancel` | 取消 pending/running 记录（置 cancelled）；采集器须在单元之间检查该状态并停止 |

## 4. 商品管理（`/api/v1/products`，不区分平台）
| 接口 | 说明 |
|---|---|
| `GET /api/v1/products` | 商品列表（整表返回，不含 attributes/search_attrs；数据量大后需改服务端分页） |
| `GET /api/v1/products/{id}` | 详情，含 `search_attrs`、`attributes` |
| `PUT /api/v1/products/{id}` | 仅允许修正 title/brand/category_name/item_condition/mpn/upc/country_of_origin；其余字段以采集为准，不开放 |
| `DELETE /api/v1/products/{id}` | 删除商品并一并删除其评价、快照（应用层级联，无外键） |
| `GET /api/v1/products/{id}/reviews` | 评价 / 卖家反馈 |
| `GET /api/v1/products/{id}/snapshots` | 价格热度快照（采集时间倒序） |
商品由采集器写入，admin 不提供新增。

## 5. 自有商品目录（`/api/v1/shop/...`，与采集无关；全部需登录，响应 `{code,data,msg}`）
| 资源 | 接口 | 说明 |
|---|---|---|
| 分类 | `GET/POST /shop/categories`、`PUT/DELETE /shop/categories/{id}` | 多级，`parent_id=0` 顶级；列表带 `full_name`（路径）；上级不能是自己/下级；有子分类或商品不能删；删除时从属性的 `category_ids` 里摘掉该分类，属性不再适用任何分类才一并删除 |
| 属性定义 | `GET/POST /shop/attributes`、`PUT/DELETE /shop/attributes/{id}` | `category_ids` 为适用分类 id 数组（可多选，空数组=通用）；同名属性仅在「名称 + 分类集合」完全相同时拒绝；`input_type`=text\|textarea\|select\|multiselect\|number（select/multiselect 须有 options）；`GET ?category_id=x` 返回「通用+该分类」且启用的（商品录入用） |
| 商品 | `GET/POST /shop/goods`、`GET/PUT/DELETE /shop/goods/{id}` | 列表含 `profit`、`margin_pct`、`sku_count`、`stock`；详情含 `attr_values`、`images`；保存时 `images`（地址数组，首张为主图）整体替换；属性值按当前分类的属性定义校验（必填、单选范围），未定义的丢弃 |
| SKU | `GET/POST /shop/goods/{id}/skus`、`PUT/DELETE .../skus/{sid}` | 价格不填默认取商品价；`sku_code` 全局唯一 |
| 图片上传 | `POST /shop/upload`（multipart 字段 `file`） | jpg/png/gif/webp，≤5MB，校验扩展名与文件头；存 `admin/static/uploads/YYYYMM/`，返回 `{url}` |
价格口径：拿货价 `cost_price`、销售价 `sale_price`、运费 `shipping_fee` 同一本位币（币种待确认）；毛利 = 销售价 − 拿货价 − 运费，毛利率 = 毛利 / 销售价。

## 5.5 供应商产品目录（`/api/v1/supplier-catalog`，全部需登录，响应 `{code,data,msg}`）

「选品池」：供应商产品（Excel 导入或手工录入）先进目录条目，核对后可关联为自有商品（`goods_id`，选品动作暂未实现）。与 shop_goods 分离，互不影响；与采集库无关。

| 资源 | 接口 | 说明 |
|---|---|---|
| 供应商 | `GET/POST /suppliers`、`PUT/DELETE /suppliers/{id}` | `name` 唯一；`website` 需 http(s) 开头；`default_currency` 3 位英文代码；列表附 `item_count`、`has_mapping`（是否存过导入模板）；下有目录条目的供应商不能删（400） |
| 品牌 | 见 §5.6 `/api/v1/brands` | 结构化品牌（`brand` 表），目录条目用 `brand_id` 关联 |
| 属性 | `GET /attributes` | 启用的商品属性 `[{name,input_type,unit}]`，导入列映射「属性：xxx」的候选 |
| 目录条目 | `GET /items`、`POST /items`、`GET/PUT/DELETE /items/{id}` | 字段见下；编辑页走 `GET/PUT /items/{id}` |

条目字段：`supplier_id`、`supplier_sku`（同供应商内唯一）、`name`、`brand_id`、`brand_name`（原文）、`category_name`（原文）、`category_id`（唯一名称匹配到的分类，否则 0）、`price`、`currency`、`stock`、`moq`、`main_image_url`、`source_url`、`description`、`remark`（资料，HTML，最长 200000 字符，可空，拒绝 script）、`source_type`(excel/manual)、`source_file`、`source_row`、`attrs`（供应商原始属性 JSON，未映射的列原样保留）、`mapped_attrs`（映射到属性定义的 JSON）、`status`（0 待核对 / 1 已核对 / 2 已选品 / 3 已忽略）、`goods_id`。PUT 可改 supplier_id/supplier_sku/name/brand_name/brand_id/category_name/category_id/price/currency/stock/moq/main_image_url/source_url/status/remark；`description`/`attrs`/`mapped_attrs` 以导入为准，不开放修改。

- `POST /uploads`（multipart 字段 `file`）：资料编辑器在**保存时**上传正文里仍引用的图片和文件。图片 jpg/png/gif/webp ≤8MB（校验文件头）；文件 pdf/doc/docx/xls/xlsx/ppt/pptx/txt/csv/zip ≤20MB。返回 `{url, name, kind}`，`kind` 为 `image` 或 `file`。存 `admin/static/uploads/YYYYMM/`，文件名换成随机名。
- `POST /uploads/discard`：body `{"urls":[...]}`（最多 50 个）。保存失败时丢掉刚刚上传、且没有任何资料 / 商品图片 / 品牌 Logo 引用的文件。
- 更新或删除目录条目时，旧资料里有、新资料里没有的 `/static/uploads/年月/32位hex.扩展名`，若产品资料、目录主图、商品主图、商品描述、商品图片、品牌 Logo 都不再引用，则删除磁盘文件。

- `GET /items`：不带 `take` 返回全部（数组，按 id 倒序）；带 `take` 走服务端分页 `{items,total}`（与 §6.3 同一套 listquery 白名单实现，`take` 上限 500）。白名单字段：`id supplier_id supplier_sku name brand_id brand_name category_name category_id price currency stock moq source_type status goods_id updated_at`。
- `POST /items/batch-status`：body `{"ids":[1~500 个整数], "status": 0~3}`，返回 `{"updated": n}`，不存在的 id 忽略。
- 每条返回都带 `supplier_name`（关联显示用）。

### 5.5.1 Excel 导入
- `POST /import/preview`（multipart：`file`、`supplier_id`、`has_header` 0/1）→ `{file_name, columns:[{key,name,sample}], rows:前 20 行, total_rows, suggest:{列key→目标}, has_template}`。列 key=表头文本（重名加「 (n)」，无表头用「列N」）；`suggest` 顺序：该供应商保存过的模板 → 表头关键字（中英）→ 属性名（先完全相等、再包含，按长度降序）。
- `POST /import/run`（multipart：`file`、`supplier_id`、`has_header`、`mapping`（JSON 字符串，列 key→标准字段或 `attr:属性名`）、`duplicate_mode` skip/overwrite、`save_mapping` 0/1）→ `{total, imported, updated, skipped, errors:[{row,msg}], error_count}`。
- 校验：`supplier_sku` 与 `name` 必须各映射一列、同一目标不能映射多列；`attr:` 目标必须是启用的属性名；映射的列必须在文件里。行级错误（货号/名称为空、超长、价格/币种/库存格式错）跳过该行并记 Excel 行号，最多报 100 条（报满即停止处理后续行）。
- 限制：≤10MB、.xlsx/.xlsm、≤5000 数据行、≤100 列，空行跳过。
- 清洗口径：价格去逗号/空格/货币符号，「面议/电议/待定」等视为无价，0~9999999999.99 保留 2 位小数；币种缺省取供应商 `default_currency`；库存非数字视为空。
- 品牌自动建档：`brand_name` 有值即按名称取 `brand` 表，没有就新建（并发下靠 SAVEPOINT 回退取现成的）；分类只按**唯一名称**（不区分大小写）匹配 shop_category，不唯一或没有则 `category_id=0` 保留原文。
- 重复口径：同 `(supplier_id, supplier_sku)`；`skip` 跳过（同文件内重复也跳过），`overwrite` 覆盖更新（**保留 `status` 与 `goods_id`**）。
- 模板记忆：`save_mapping=1` 时把 mapping 存进 `supplier.excel_mapping`，下次 preview 自动套用（`has_template=true`）。

## 5.6 品牌管理（`/api/v1/brands`，全部需登录，响应 `{code,data,msg}`）

商品库结构化品牌（`brand` 表），被 `shop_goods.brand_id` 与 `supplier_catalog_item.brand_id` 引用；Excel 导入遇到新品牌名会自动建档（见 §5.5.1）。品牌名称的默认语言存在 `brand.name`，其他语言译文存 `shop_translation`（`entity_type=brand`，字段 `name`），列表 / 增改接口带 `i18n: {语言: {name: 值}}`。

| 接口 | 说明 |
|---|---|
| `GET /brands` | 全部品牌，按 `sort_order, id` 升序；每个含 `id name logo_url website remark sort_order status(bool) item_count goods_count created_at updated_at i18n`（`item_count`/`goods_count` 为目录条目 / 商品引用数，只读） |
| `POST /brands` | 新建；`name` 必填 ≤100 且唯一（400「品牌名称已存在」），`logo_url` ≤500、`website` ≤255（需 http(s) 开头）、`remark` ≤500、`sort_order` 0~999999、`status` 缺省启用；可带 `i18n` 随品牌同一事务保存 |
| `PUT /brands/{id}` | 修改，校验同新建（按传了的字段）；改名时同步更新引用它的 `shop_goods.brand` 冗余名称；可带 `i18n` |
| `DELETE /brands/{id}` | 被目录条目或商品引用时 400「该品牌已被 N 个目录条目 / M 个商品 使用，不能删除」；译文一并删除 |
| `POST /brands/move` | 拖动排序：`{"id", "target_id", "after": bool}`，把 id 移到 target_id 之前/之后，全部品牌 `sort_order` 按新顺序重排（10、20、30…） |

商品表单的品牌字段为 `brand_id`（下拉取 `/brands` 的启用品牌，空值 = 0 未设置）；保存时后端把品牌名冗余写入 `shop_goods.brand`，列表仍可按品牌名筛选，也可按 `brand_id` 筛选。

## 6. 商品内容多语言（与后台界面语言无关）
约定：`shop_*` 基础表里的文字就是**默认语言**的内容；其他语言的译文存 `shop_translation`，**缺译时读取方回退到默认语言**。默认语言有且仅有一个（种子：zh-CN 默认、en），默认语言不能删除/禁用，已有译文的语言不能改成默认。
| 接口 | 说明 |
|---|---|
| `GET/POST /shop/languages`、`PUT/DELETE /shop/languages/{id}` | 语言管理；`code` 如 en、ja、zh-TW，创建后不可改；删除语言会删除其全部译文 |
| `GET /shop/i18n/{type}/{id}` | 取某对象的翻译信息：`fields`（可翻译字段）、`defaults`（默认语言原文）、`languages`（非默认语言）、`translations`（已有译文） |
| `PUT /shop/i18n/{type}/{id}` | body `{"translations": {"en": {"name": "..."}}}`；传了的语言×字段整体覆盖，空值=删除该译文，没传的不动 |
| `GET /shop/goods/{id}/localized?lang=en` | 供前台/下游取商品某语言版本（名称、描述、品牌、分类、属性、规格）；`fallback` 列出回退到默认语言的字段 |
可翻译字段（`type`）：`category`(name)、`attribute`(name、options 需与默认语言数量一致按序对应)、`goods`(name、description、attr_values 按默认语言的属性名取键)、`sku`(spec_name)、`brand`(name)。供应商、编码、价格等不翻译。删除对象时译文一并删除。

### 6.1 列表与表单里直接显示/编辑译文（启用的非默认语言，目前为 en）
- 分类、属性、商品、SKU、品牌的列表和增改接口的输出都带 `i18n: {语言: {字段: 值}}`，缺译为空值：分类/属性/品牌 `name`；商品列表 `name`，商品详情 `name`/`description`/`attr_values`；SKU `spec_name`。
- 新增/修改接口的 body 可带同结构的 `i18n`，与主体**同一事务**保存：任一校验失败整体回滚，不会只存一半；未启用的语言被忽略；空值删除该译文。
- 前端：`shop.js` 的 `Shop.ready`（语言加载完成）、`Shop.langColumns / withLang / langItems`（表格语言列、表单项），新增语言后列表页自动多出对应列，无需改页面。
- 属性「可选值」的译文、其他语言之外的批量维护仍走 `PUT /shop/i18n/...`（属性列表的「翻译」按钮）。

### 6.2 属性多语言的完整口径
- **属性名称**：`i18n.<语言>.name`，列表/表单直接编辑。
- **单选属性的可选值**：`options` 与 `i18n.<语言>.options` 按序号一一对应（数量必须一致，否则 400）；后台用「每个选项一行、默认语言 + 各语言各一列」的编辑器维护，删行/加行两边同步。只改可选值、没带新译文时，旧译文因序号错位会被清掉。
- **文本属性录入的内容**：商品 `i18n.<语言>.attr_values`（键为默认语言的属性名），在商品编辑页每个文本属性下按语言各一个输入框；单选属性的商品值不用再填译文，读取时按选项序号取可选值译文（`/goods/{id}/localized` 已处理）。

### 6.3 商品列表的服务端分页 / 筛选 / 排序
`GET /api/v1/shop/goods?take=20&skip=0&sort=<JSON>&filter=<JSON>`
- 不带 `take`：返回全部（数组，兼容旧调用）；带 `take`：返回 `{items, total}`，`take` 上限 500。
- `sort`：`[{"selector":"sale_price","desc":true}, ...]`；`filter`：DevExtreme 格式，`["字段","操作符",值]`、嵌套 `and`/`or` 分组、`["!", 条件]`；操作符 `= <> > >= < <= contains notcontains startswith endswith in/anyof`（`in`/`anyof` 值为 1~1000 个数组，表格「查看已选」在服务端分页列表上用；前端统一发 `anyof`）。
- 可筛选/排序字段（白名单，其它返回 400）：`id goods_no name category_id brand supplier cost_price sale_price shipping_fee profit margin_pct sku_count stock status weight_g updated_at`，以及启用语言的 `i18n.<语言>.name`。`profit`、`margin_pct`、`sku_count`、`stock` 是计算列，按 SQL 表达式过滤；数值列用 `contains` 时按文本比；`contains` 的 `% _` 已转义，当普通字符。
- 通用实现在 `app/listquery.py`（`build_filter / build_sort / clamp_page`），新的大表列表照此接入，字段一律走白名单。

### 6.4 分类与属性的规则（商品分类树）
- **属性继承**：属性的「适用分类」可多选，任一选中分类对其所有下级分类生效（选「香水」，女士/男士/中性香水都适用）；适用分类为空数组为全部通用。同名属性在多级都定义时，离商品分类最近的一级生效；同一属性命中的多个分类取最近的层级。`GET /shop/attributes?category_id=x` 返回 x 适用的全部启用属性（通用 + 本级 + 所有上级，已去重、按 sort_order 排）；商品保存时的必填/选项校验、`/goods/{id}/localized` 都按这个口径。实现见 `app/catalog.py`。
- **商品只能挂末级分类**：创建商品或更换分类时，选了有子分类的分类返回 400；已有商品的分类不能再新增子分类（需先把商品移走）。老商品所在分类后来长出子级，不影响它保存其它字段。「未分类」(0) 仍允许。
- 英文版商品里，单选属性的值按可选值译文显示，文本属性的值按商品的 `attr_values` 译文显示，缺译回退默认值。

### 6.5 数字类型属性（`input_type = number`）
- 属性定义新增 `decimal_places`（小数位数 0~6，**0 表示整数，前端按整型处理**）和 `unit`（单位，默认语言，≤30 字符）。单位可多语言：其它语言的单位随属性的 `i18n.<语言>.unit` 提交/返回，存 `shop_translation`（field_name=`unit`）。非数字属性的这两项恒为默认值（0 / 空）。
- 商品里的值存在 `attr_values`，**统一存成固定小数位的文本**：0 位小数存 `"30"`，1 位存 `"30.5"`。保存时校验：必须是数字、小数位数不能超过属性定义（否则 400，如“最多 1 位小数”“需为整数”）、绝对值 < 1e12；不限正负。数字值不翻译，只有单位翻译。
- `GET /shop/goods/{id}/localized`：属性项带 `unit`（按语言取单位，缺译回退默认单位；非数字属性为空串），如 `{"name":"Volume","value":"30","unit":"ml"}`。
- 改小数位数不会回改已存的值；已存的值在下次保存该商品时按新位数重新校验。

## 7. 表格过滤器模板（`/api/v1/grid-filters`，只能看到和改自己的）
| 接口 | 说明 |
|---|---|
| `GET /grid-filters?grid_key=/goods` | 当前用户在该表格下的模板 `[{id, name, filter_value}]` |
| `POST /grid-filters` | body `{grid_key, name, filter_value}`；同名覆盖更新；`filter_value` 是 DevExtreme 过滤表达式（非空数组，≤20000 字符）；每表格最多 50 个 |
| `DELETE /grid-filters/{id}` | 删除自己的模板；别人的返回 404 |

## 7.5 表格布局（`/api/v1/grid-layouts`，每用户每表格一份，只能看到和改自己的）
| 接口 | 说明 |
|---|---|
| `GET /grid-layouts?grid_key=/goods` | 当前用户在该表格下的布局 `{"layout": {...}}`；没存过返回 `data: null` |
| `POST /grid-layouts` | body `{grid_key, layout}` 覆盖保存；`layout = {state: DevExtreme 表格状态（非空对象，≤200000 字符）, editMode: 编辑模式或 null}` |

### 6.6 商品批量上架 / 下架
`POST /api/v1/shop/goods/batch-status`，body `{"ids": [1,2,3], "status": true|false}`（true=上架，false=下架）；ids 为 1~500 个整数，其它返回 400；返回 `{"updated": 实际更新条数}`，不存在的 id 直接忽略。

## 6.7 属性：多行文本 / 多选 / 拖动排序
- `input_type` 取值：`text` 文本、`textarea` 多行文本、`select` 单选、`multiselect` 多选、`number` 数字。`select` / `multiselect` 必须有可选值（`options`，各语言译文 `i18n.<语言>.options` 按序号对应）。
- 商品 `attr_values`：多选属性的值是**可选值数组**（保存时按可选值顺序去重存储，值必须在可选值内，必填则至少选一项）；多行文本最长 2000 字符（文本 200）；其译文（`i18n.<语言>.attr_values`）单项最长 2000。
- `GET /goods/{id}/localized?lang=`：多选属性的 `value` 是译文数组（按可选值序号取译文，缺译回退默认值）。
- `POST /attributes/move`：body `{id, target_id, after}`，把 `id` 移到 `target_id` 之前（`after=false`）或之后（`after=true`），并把全部属性的 `sort_order` 按新顺序重排为 10、20、30…；`id` 与 `target_id` 相同返回「参数不合法」，不存在返回 404。
