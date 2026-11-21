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
| `POST /api/v1/ui-style/{kind}/save` | `kind`=menu\|grid\|form；body `{values:{...}}`；只能改自己的；menu 当前支持 `width`（120~480px，默认 150） |
| `POST /api/v1/ui-style/{kind}/reset` | 重置为默认 |

## 4. 自有商品目录（`/api/v1/shop/...`，全部需登录，响应 `{code,data,msg}`）
| 资源 | 接口 | 说明 |
|---|---|---|
| 分类 | `GET/POST /shop/categories`、`PUT/DELETE /shop/categories/{id}` | 多级，`parent_id=0` 顶级；`code` 为选填的品类编码（≤50，允许重复）；列表带 `full_name`（路径）；上级不能是自己/下级；有子分类或商品不能删；删除时从属性的 `category_ids` 里摘掉该分类，属性不再适用任何分类才一并删除 |
| 属性定义 | `GET/POST /shop/attributes`、`PUT/DELETE /shop/attributes/{id}` | `category_ids` 为适用分类 id 数组（可多选，空数组=通用）；同名属性仅在「名称 + 分类集合」完全相同时拒绝；`input_type`=text\|textarea\|select\|multiselect\|number（select/multiselect 须有 options）；`GET ?category_id=x` 返回「通用+该分类」且启用的（商品录入用） |
| 商品 | `GET/POST /shop/goods`、`GET/PUT/DELETE /shop/goods/{id}` | 列表含 `profit`、`margin_pct`、`sku_count`、`stock`；详情含 `attr_values`、`images`、`stores`，图片项为 `{id,url,sku_id,sort_order}`，`sku_id=null` 表示商品共用，否则为当前商品 SKU 专用；保存时 `images` 整体替换并兼容旧 URL 字符串，共用图片第一张写入商品主图，上架商品至少保留一张共用图片；店铺项的 `product_url` 为平台同步成功后回写的只读商品网址；属性值按当前分类的属性定义校验（必填、单选范围），未定义的丢弃 |
| 自动商品编码 | `POST /shop/goods-no/generate` | body `{category_id, brand_id}`；按“品牌段 + 品类段 + 4 位流水”生成并立即占号。品牌不参与时品牌段为 `TH`；相同最终前缀共享流水，返回 `{goods_no,prefix,sequence}`；缺编码或超过 9999 时拒绝 |
| SKU | `GET/POST /shop/goods/{id}/skus`、`PUT/DELETE .../skus/{sid}` | SKU 管理编码、规格、成本、库存和启用状态；`sku_code` 全局唯一；旧 `sale_price` 字段保留兼容但页面不再编辑；仍有专用图片时禁止删除，须先删除图片或改为商品共用 |
| 默认 SKU | `POST /shop/goods/{id}/skus/default` | 商品没有任何 SKU 时，用商品编码创建默认 SKU，规格名称留空，成本继承商品、库存为 0；已有 SKU 或编码冲突时拒绝 |
| SKU 区域价格 | `GET/POST /shop/goods/{id}/sku-region-prices`、`PUT/DELETE .../{row_id}` | `(sku_id,region_id)` 唯一；可覆盖 price/suggested/min/max，空字段继承商品区域基础价；币种始终取所属区域币种，SKU 必须属于当前商品 |
| 图片上传 | `POST /shop/upload`（multipart 字段 `file`） | jpg/png/gif/webp，≤5MB，校验扩展名与文件头；存 `admin/static/uploads/YYYYMM/`，返回 `{url}` |
价格口径：拿货价 `cost_price`、销售价 `sale_price`、运费 `shipping_fee` 同一本位币（币种待确认）；毛利 = 销售价 − 拿货价 − 运费，毛利率 = 毛利 / 销售价。

## 5.5 供应商产品目录（`/api/v1/supplier-catalog`，全部需登录，响应 `{code,data,msg}`）

「选品池」：供应商产品（Excel 导入或手工录入）先进目录条目，核对后可关联为自有商品（`goods_id`，选品动作暂未实现）。与 shop_goods 分离，互不影响。

| 资源 | 接口 | 说明 |
|---|---|---|
| 供应商 | `GET/POST /suppliers`、`PUT/DELETE /suppliers/{id}` | `name` 唯一；`website` 需 http(s) 开头；`default_currency` 3 位英文代码；列表附 `item_count`、`document_count`、`has_mapping`（是否存过导入模板）；下有目录条目或文档的供应商不能删（400） |
| 供应商文档 | `GET/POST /documents`、`PUT/DELETE /documents/{id}` | 见 §5.5.2 |
| 品牌 | 见 §5.6 `/api/v1/brands` | 结构化品牌（`brand` 表），目录条目用 `brand_id` 关联 |
| 属性 | `GET /attributes` | 启用的商品属性 `[{name,input_type,unit}]`，导入列映射「属性：xxx」的候选 |
| 目录条目 | `GET /items`、`POST /items`、`GET/PUT/DELETE /items/{id}` | 字段见下；编辑页走 `GET/PUT /items/{id}` |

条目字段：`supplier_id`、`supplier_sku`（同供应商内唯一）、`name`、`brand_id`、`brand_name`（原文）、`category_name`（原文）、`category_id`（唯一名称匹配到的分类，否则 0）、`price`、`suggested_price`（建议售价）、`min_price`（最低售价）、`max_price`（最高售价）、`price_rule`（价格规则，多行文本，最长 2000）、`lead_time`（交期，最长 100）、`currency`、`stock`、`moq`、`main_image_url`、`source_url`、`description`、`remark`（资料，HTML，最长 200000 字符，可空，拒绝 script）、`source_type`(excel/manual)、`source_file`、`source_row`、`attrs`（供应商原始属性 JSON，未映射的列原样保留）、`mapped_attrs`（映射到属性定义的 JSON）、`status`（0 待核对 / 1 已核对 / 2 已选品 / 3 已忽略）、`goods_id`。三个售价和报价一样可空，0~9999999999.99、两位小数；最低售价不能高于最高售价，建议售价须落在已填写的最低/最高售价之间。PUT 可改 supplier_id/supplier_sku/name/brand_name/brand_id/category_name/category_id/price/suggested_price/min_price/max_price/price_rule/lead_time/currency/stock/moq/main_image_url/source_url/status/remark；`description`/`attrs`/`mapped_attrs` 以导入为准，不开放修改。

- `POST /uploads`（multipart 字段 `file`）：资料编辑器在**保存时**上传正文里仍引用的图片和文件，供应商文档页上传时也走这个接口。图片 jpg/png/gif/webp ≤8MB（校验文件头）；文件 pdf/doc/docx/xls/xlsx/ppt/pptx/txt/csv/zip ≤20MB。返回 `{url, name, kind, size}`，`kind` 为 `image` 或 `file`，`size` 为字节数。存 `admin/static/uploads/YYYYMM/`，文件名换成随机名。
- `POST /uploads/discard`：body `{"urls":[...]}`（最多 50 个）。保存失败时丢掉刚刚上传、且没有任何资料 / 商品图片 / 品牌 Logo / 供应商文档引用的文件。
- 更新或删除目录条目时，旧资料里有、新资料里没有的 `/static/uploads/年月/32位hex.扩展名`，若产品资料、目录主图、商品主图、商品描述、商品图片、品牌 Logo、供应商文档都不再引用，则删除磁盘文件。

- `GET /items`：不带 `take` 返回全部（数组，按 id 倒序）；带 `take` 走服务端分页 `{items,total}`（与 §6.3 同一套 listquery 白名单实现，`take` 上限 500）。白名单字段：`id supplier_id supplier_sku name brand_id brand_name category_name category_id price suggested_price min_price max_price price_rule lead_time currency stock moq source_type status goods_id updated_at`。
- `POST /items/batch-status`：body `{"ids":[1~500 个整数], "status": 0~3}`，返回 `{"updated": n}`，不存在的 id 忽略。
- 每条返回都带 `supplier_name`（关联显示用）。

### 5.5.1 Excel 导入
- `POST /import/preview`（multipart：`file`、`supplier_id`、`has_header` 0/1）→ `{file_name, columns:[{key,name,sample}], rows:前 20 行, total_rows, suggest:{列key→目标}, has_template}`。列 key=表头文本（重名加「 (n)」，无表头用「列N」）；`suggest` 顺序：该供应商保存过的模板 → 表头关键字（中英）→ 属性名（先完全相等、再包含，按长度降序）。
- `POST /import/run`（multipart：`file`、`supplier_id`、`has_header`、`mapping`（JSON 字符串，列 key→标准字段或 `attr:属性名`）、`duplicate_mode` skip/overwrite、`save_mapping` 0/1）→ `{total, imported, updated, skipped, errors:[{row,msg}], error_count}`。
- 校验：`supplier_sku` 与 `name` 必须各映射一列、同一目标不能映射多列；`attr:` 目标必须是启用的属性名；映射的列必须在文件里。行级错误（货号/名称为空、超长、价格/币种/库存格式错）跳过该行并记 Excel 行号，最多报 100 条（报满即停止处理后续行）。
- 限制：≤10MB、.xlsx/.xlsm、≤5000 数据行、≤100 列，空行跳过。
- 清洗口径：价格、建议售价、最低售价、最高售价去逗号/空格/货币符号，「面议/电议/待定」等视为无价，0~9999999999.99 保留 2 位小数；最低售价不能高于最高售价，建议售价须落在已填写的区间内；价格规则最长 2000（多行文本，导入超长截断）、交期最长 100（导入超长截断）；币种缺省取供应商 `default_currency`；库存非数字视为空。
- 品牌自动建档：`brand_name` 有值即按名称取 `brand` 表，没有就新建（并发下靠 SAVEPOINT 回退取现成的）；分类只按**唯一名称**（不区分大小写）匹配 shop_category，不唯一或没有则 `category_id=0` 保留原文。
- 重复口径：同 `(supplier_id, supplier_sku)`；`skip` 跳过（同文件内重复也跳过），`overwrite` 覆盖更新（**保留 `status` 与 `goods_id`**）。
- 模板记忆：`save_mapping=1` 时把 mapping 存进 `supplier.excel_mapping`，下次 preview 自动套用（`has_template=true`）。

### 5.5.2 供应商文档
按供应商归档营业执照、资质、合同等文件。`GET /documents` 返回全部（按 id 倒序），每条带 `supplier_name`。

字段：`supplier_id`（必须是已有供应商）、`title`（最长 200）、`doc_type`（`license` 营业执照 / `qualification` 资质证书 / `contract` 合同协议 / `pricelist` 价目表 / `catalog` 产品资料 / `other` 其他）、`file_url`（必须是本系统 `POST /uploads` 返回的地址，且文件还在磁盘上）、`file_name`（原始文件名，最长 180）、`remark`（最长 500）。`file_size` 由服务端按磁盘文件计算，客户端传入的大小不采用。

更换 `file_url` 或删除文档时，旧文件若没有被资料、商品图片、品牌 Logo 或其他文档引用，则从磁盘删除。取消弹窗未保存的上传走 `POST /uploads/discard`。

## 5.6 品牌管理（`/api/v1/brands`，全部需登录，响应 `{code,data,msg}`）

商品库结构化品牌（`brand` 表），被 `shop_goods.brand_id` 与 `supplier_catalog_item.brand_id` 引用；Excel 导入遇到新品牌名会自动建档（见 §5.5.1）。品牌名称的默认语言存在 `brand.name`，其他语言译文存 `shop_translation`（`entity_type=brand`，字段 `name`），列表 / 增改接口带 `i18n: {语言: {name: 值}}`。

| 接口 | 说明 |
|---|---|
| `GET /brands` | 全部品牌，按 `sort_order, id` 升序；每个含 `id code name brand_type include_in_goods_no logo_url website remark sort_order status(bool) item_count goods_count created_at updated_at i18n`（`brand_type` 为 own/third_party；`include_in_goods_no` 为布尔值） |
| `POST /brands` | 新建；`name` 必填 ≤100 且唯一，`code` 选填 ≤50 且唯一；`brand_type` 为 own/third_party（默认 third_party），`include_in_goods_no` 默认 true；其余校验和 i18n 同原规则 |
| `PUT /brands/{id}` | 修改，校验同新建（按传了的字段）；改名时同步更新引用它的 `shop_goods.brand` 冗余名称；可带 `i18n` |
| `DELETE /brands/{id}` | 被目录条目或商品引用时 400「该品牌已被 N 个目录条目 / M 个商品 使用，不能删除」；译文一并删除 |
| `POST /brands/move` | 拖动排序：`{"id", "target_id", "after": bool}`，把 id 移到 target_id 之前/之后，全部品牌 `sort_order` 按新顺序重排（10、20、30…） |

商品表单的品牌字段为 `brand_id`（下拉取 `/brands` 的启用品牌，空值 = 0 未设置）；保存时后端把品牌名冗余写入 `shop_goods.brand`，列表仍可按品牌名筛选，也可按 `brand_id` 筛选。

## 5.7 国家地区与区域（全部需登录，响应 `{code,data,msg}`）

国家地区是树：全球 → 洲 → 国家。区域勾选的是树上的节点，一个国家可以被多个区域勾选。只勾「全球」或只勾某个洲时，只保存该节点，不展开成国家 id，范围由后续业务解释。

| 接口 | 说明 |
|---|---|
| `GET /api/v1/geo` | 全部节点，按 `sort_order, code, id`。字段 `id parent_id code name_zh name_en is_leaf(bool) sort_order created_at updated_at` |
| `POST /api/v1/geo` | 新建。`code` 必填、1~10 位、存大写且全局唯一；`name_zh` ≤50、`name_en` ≤80 必填；`parent_id` 0 为顶级；`is_leaf` 缺省 true；还有下级时不能标为子节点。上级若是子节点，保存时改为分组 |
| `PUT /api/v1/geo/{id}` | 修改，校验同新建。上级不能是自己或自己的下级 |
| `DELETE /api/v1/geo/{id}` | 还有下级，或已被区域勾选时 400 |
| `GET /api/v1/regions` | 全部区域，按 `sort_order, id`。`countries` 为已保存的节点（全球、洲或国家，按树顺序），每项含 `is_leaf`；`country_ids` 为对应 id。列表最多展示前 15 个中文名 |
| `POST /api/v1/regions` | 新建。`name` 必填 ≤100 且唯一；`sort_order` 0~999999；`country_ids` 为节点 id 数组，缺省空。只含全球或洲、且其下没有单独勾选的国家时，不展开成国家 id。上级和它下面的国家同时出现时，丢掉上级 |
| `PUT /api/v1/regions/{id}` | 修改。未传 `country_ids` 时不改已选范围；传了则按上面的规则整体覆盖 |
| `DELETE /api/v1/regions/{id}` | 删除区域及其勾选关系，不删除国家 |
| `POST /api/v1/regions/move` | 拖动排序。body `{id, target_id, after}`，把 id 移到 target_id 之前（after=false）或之后（after=true），全部区域 `sort_order` 重排为 10、20、30…。id 与 target_id 相同返回「参数不合法」，不存在返回 404 |

## 5.8 平台与店铺（全部需登录，响应 `{code,data,msg}`）

菜单「店铺」位于「产品池」之后，子项为「平台管理」「店铺管理」。店铺不保存「独立站」，接口里的 `is_independent` 取所属平台，传入的值会被忽略。

商品详情的 `stores` 项只管理店铺及是否允许上架，不再选择运费模板。`region_prices` 每项可选 `shipping_template_id`。运费模板及重量、包装资料均不参与商品上架、店铺允许上架、SKU 保存或 Shopify 推送校验；缺少资料只在运费试算或订单运费计算时返回明确错误。

| 接口 | 说明 |
|---|---|
| `GET /api/v1/platforms` | 全部平台，按 `code, id`。字段 `id code name name_en website market feature remark is_independent(bool) store_count created_at updated_at` |
| `POST /api/v1/platforms` | 新建。`code` 必填 ≤50 且唯一，`name` 必填 ≤100 且唯一；`name_en` ≤100，`website` ≤255（有值时须 http(s) 开头），`market` ≤100，`feature`、`remark` ≤500；`is_independent` 缺省否 |
| `PUT /api/v1/platforms/{id}` | 修改，校验同新建（按传了的字段） |
| `DELETE /api/v1/platforms/{id}` | 其下还有店铺时 400「该平台下还有 N 个店铺，不能删除」 |
| `GET /api/v1/stores` | 全部店铺，按平台编码、店铺编码。另含 `platform_name`、`shipping_package_group_id`；`is_independent` 为所属平台的值；分类摘要字段同下 |
| `POST /api/v1/stores` | 新建。`platform_id` 必须是已有平台；`code`、`name` 必填，在同一平台下各自唯一；`shipping_package_group_id` 可为 0 或已有包装组。不写独立站。绑定分类走单独接口 |
| `PUT /api/v1/stores/{id}` | 修改，校验同新建。未传的字段保持原值。不改绑定分类 |
| `DELETE /api/v1/stores/{id}` | 删除店铺及其分类绑定 |
| `GET /api/v1/stores/{id}/categories` | 已绑定的 `category_ids` |
| `PUT /api/v1/stores/{id}/categories` | 整体覆盖绑定。body `{category_ids:[...]}`，须是已有 `shop_category.id`，重复项会去掉；空数组表示全部解绑 |

重复时 400：「平台编码已存在」「平台名称已存在」「该平台下店铺编码已存在」「该平台下店铺名称已存在」。不存在时 404。

## 5.9 销售运费模板（`/api/v1/shipping-templates`，全部需登录）

| 接口 | 说明 |
|---|---|
| `GET /api/v1/shipping-templates` | 模板及区域规则列表 |
| `GET /api/v1/shipping-templates/{id}` | 模板详情 |
| `POST /api/v1/shipping-templates` | 新建模板并整体保存 `rules`，至少一条规则 |
| `PUT /api/v1/shipping-templates/{id}` | 修改；传 `rules` 时整体覆盖规则 |
| `DELETE /api/v1/shipping-templates/{id}` | 已被商品区域销售价格使用时拒绝删除 |
| `POST /api/v1/shipping-templates/{id}/calculate` | 按 `region_id subtotal weight_g package_length_cm package_width_cm package_height_cm` 试算；尺寸精确到 0.01 cm；返回实际、体积、计费重量及运费 |
| `POST /api/v1/shipping-templates/calculate-order` | body 为 `store_id region_id lines[{sku_id,quantity,unit_price}]`；先校验商品允许在店铺销售，再从商品对应 `region_id` 的区域销售价格取模板；相同模板合并、不同模板分别计算后相加 |

计费方式为 `fixed`、`weight` 或 `chargeable`。`chargeable` 的体积重克数为 `ceil(长cm × 宽cm × 高cm ÷ volume_divisor × 1000)`；每件实际运输重量为商品重量加空箱重量，再与体积重取大后按数量汇总。重量费用公式为“首重费用 + 向上取整的续重单位数 × 续重费用”；随后应用分组满额免邮、最低运费、最高运费。同一订单中同模板商品合并成组，不同模板分别计算后相加。

包装组按 SKU → 商品 → 店铺继承，组内 `current_box_id` 决定当前箱型；更换采购箱只改包装组。使用 `chargeable` 模板计算运费时，SKU 必须有有效重量并能解析到启用包装组和包装箱；资料不足只导致该次运费计算失败，不影响上架或 Shopify 推送。

## 5.10 包装管理（`/api/v1/shipping-packages`，全部需登录）

`GET/POST /boxes`、`PUT/DELETE /boxes/{id}` 维护包装箱；被包装组引用时不可删除。`GET/POST /groups`、`PUT/DELETE /groups/{id}` 维护包装组；组必须选择启用包装箱，被商品、SKU 或店铺引用时不可删除。包装组读写字段 `images:[{id?,url,sort_order?}]`，最多 20 张，仅接受本系统 `/static/uploads/` 图片地址；保存时整体覆盖图片顺序。

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

商品列表可额外传 `store_ids=1,2`，返回至少绑定其中一个店铺的商品；该参数与 Grid 的 `filter` 条件同时生效。
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

## 8. Shopify 主动推送（`/api/v1/shopify`）

| 接口 | 说明 |
|---|---|
| `GET /stores/{store_id}` | 读取 Shopify 店铺配置，以及可选的区域和启用语言；非 Shopify 平台店铺返回 400 |
| `PUT /stores/{store_id}` | 保存 `shop_domain region_id language_code default_location_gid stock_location_id publication_gid currency sync_enabled`；Shopify Location 必须绑定 mzShop 库存地点；域名必须为 `*.myshopify.com` |
| `POST /stores/{store_id}/test` | body 可带 `shop_domain`；使用 Client Credentials 测试连接，返回 Shop、Location、Publication、已授权与缺失权限；不返回 Token |
| `POST /stores/{store_id}/webhooks/register` | 注册订单、支付、取消、履约、退款 Webhook；要求 `SHOPIFY_WEBHOOK_BASE_URL` 为公网可信 HTTPS，重复主题和 URI 跳过 |
| `POST /goods/{goods_id}/enqueue` | 把该商品所有允许上架、已启用且连接正常的 Shopify 店铺加入推送队列；可带 `store_ids` 限定店铺 |
| `POST /goods/batch-enqueue` | body `{ids:[商品ID], store_ids?:[店铺ID]}`；批量加入推送队列，同一商品/店铺已有活动任务时跳过 |
| `GET /goods/{goods_id}/status` | 返回该商品在各 Shopify 店铺的 Product GID、同步状态、最后成功时间和错误/告警 |
| `GET /tasks?take&skip&sort&filter` | 同步任务服务端分页列表 `{items,total}`；支持任务、商品、店铺、状态、动作、时间、Request ID、错误字段的白名单筛选/排序 |
| `POST /tasks/{task_id}/retry` | 失败或已取消任务重新置为 pending，清除本轮执行信息；同商品/店铺已有活动任务时拒绝 |
| `POST /tasks/batch-retry` | body `{ids:[任务ID]}`（1~500）；只重试 failed/cancelled，同商品/店铺已有活动任务或其它状态计入 skipped；返回 `{updated,skipped}` |
| `DELETE /tasks/{task_id}` | 删除单条历史任务；pending/running 禁止删除。同步任务页的“删除选中行”逐条调用该接口 |
| `POST /taxonomy/import` | 从 Shopify 官方 product-taxonomy 最新稳定 release 下载 `zh-CN`、`en` 分类并增量更新；官方已移除的历史分类标记为失效，不物理删除 |
| `GET /taxonomy?take&skip&sort&filter` | Shopify 标准分类服务端分页列表 `{items,total}`；字段白名单为分类 ID、中英文名称/完整路径、层级、末级、有效、版本、更新时间 |
| `GET /taxonomy/options?q&take` | 分类绑定搜索候选；按中文/英文完整路径或分类 ID 模糊搜索，只返回当前有效分类 |
| `GET /taxonomy/attributes?take&skip&sort&filter` | Shopify 官方属性服务端分页；返回中英文名称、handle、说明、版本、状态和有效属性值数量 |
| `GET /taxonomy/attributes/{attribute_id}/values?take&skip&sort&filter` | 指定官方属性的属性值服务端分页；返回中英文名称、handle、TaxonomyValue GID、版本和状态 |
| `GET /category-maps` | 返回全部 mzShop 分类及其直接绑定的 Shopify 标准分类；未直接绑定的行也会返回 |
| `PUT /category-maps/{category_id}` | body `{taxonomy_category_id}`；新增或更换该 mzShop 分类的直接绑定 |
| `DELETE /category-maps/{category_id}` | 解除该 mzShop 分类的直接绑定 |
| `GET /category-attributes?category_id=` | 读取 mzShop 分类最终继承的 Shopify 标准分类及全部适用官方属性，附本地属性和值映射状态 |
| `GET /category-attributes/{relation_id}/mapping?category_id=` | 属性映射编辑数据：适用的 mzShop 属性、官方预定义值及现有映射 |
| `PUT /category-attributes/{relation_id}/mapping` | body `{category_id,local_attribute_id,value_map}`；保存属性及固定选项到 TaxonomyValue 的映射 |
| `DELETE /category-attributes/{relation_id}/mapping?category_id=` | 解除指定分类下的属性映射 |

连接测试所需 scopes：`write_products write_inventory read_locations read_publications read_orders read_metaobjects write_metaobjects read_metaobject_definitions write_metaobject_definitions`。任务处理和字段映射见 `SHOPIFY.md`。
批量加入队列时，商品没有启用 SKU、没有可上架 Shopify 店铺、店铺未配置或连接状态不正常均返回明确的 400 错误，不创建空任务。
商品推送时从商品所属 mzShop 分类开始逐级向上寻找最近的有效绑定，并把对应 `TaxonomyCategory` GID 写入 `ProductSetInput.category`；整条祖先链均未绑定时不传该字段。

## 11. 固定组合与库存（`/api/v1/bundles`、`/api/v1/inventory`）

| 接口 | 契约 |
|---|---|
| `GET /bundles?parent_sku_id=` | 组合版本及父/组件 SKU 基本信息；状态 draft/published/disabled；附父 SKU 各区域有效售价与各启用库存地点的实时组合可用量 |
| `GET /bundles/parent-options`、`component-options` | 父 SKU 与普通组件 SKU 搜索候选；父 SKU 候选标记并优先显示独立商品，组件候选排除组合 SKU |
| `POST /bundles` | 新建草稿并把父 SKU 标记为 bundle；body `{parent_sku_id,remark,components:[{component_sku_id,quantity}]}` |
| `PUT /bundles/{id}` | 只允许修改草稿，组件集合整体替换 |
| `POST /bundles/{id}/publish` | 在 mzShop 本地启用草稿配方（不是发布 Shopify）；旧 published 改为 disabled，新版本记录 replaced_revision_id |
| `DELETE /bundles/{id}` | 只允许删除草稿；父 SKU 无其它版本时恢复 normal |
| `GET/POST /inventory/locations` | 库存地点列表、新建地点；编码和名称分别唯一 |
| `PUT/DELETE /inventory/locations/{id}` | 修改、删除库存地点；已绑定店铺或存在库存余额/流水时禁止删除 |
| `GET /inventory/balances?take&skip&sort&filter` | 库存余额服务端分页；每行返回所属 `goods_id`，SKU 编码可链接到商品详情；可售=`max(在库-占用-不可售-安全库存,0)` |
| `POST /inventory/adjust` | 普通 SKU 人工盘点式调整在库、不可售和安全库存；写唯一流水并加入最新库存同步任务 |
| `GET /inventory/ledger?take=` | 最近库存流水，最多 500 条 |
| `GET /inventory/bundle-available/{parent_sku_id}?location_id=` | 按已发布版本计算组合可售量 |

## 12. Shopify 订单与退货（`/api/v1/orders`）

| 接口 | 契约 |
|---|---|
| `POST /api/v1/shopify/webhooks` | 无后台 Session；校验 Shopify HMAC，以店铺和 Webhook ID 去重，整单重读并差量更新库存 |
| `GET /orders?take&skip&sort&filter` | 订单镜像服务端分页，不返回客户资料 |
| `GET /orders/{id}` | 订单父组合/组件行、履约、退款和退货数量及金额快照 |
| `POST /orders/{id}/returns` | 极简退货入库；body `{remark,lines:[{order_line_id,sellable_quantity,unavailable_quantity,reason}]}`；父组合行不可入库 |
