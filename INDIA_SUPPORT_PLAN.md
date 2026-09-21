# INDIA_SUPPORT_PLAN.md — Indian NSE 支持方案（规划）

> 本文档仅做现状分析与最小改动规划，**不实现任何代码**。
> 依据：`src/core/market_profile.py`、`src/services/market_symbol_utils.py`、`src/services/stock_code_utils.py`、`data_provider/yfinance_fetcher.py`、`data_provider/base.py`、`src/core/trading_calendar.py`、`src/services/stock_list_parser.py`、`api/v1/endpoints/stocks.py`、`src/market_context.py`。
> 测试股票：`RELIANCE.NS / TCS.NS / INFY.NS / HDFCBANK.NS / ICICIBANK.NS / SBIN.NS / BHARTIARTL.NS / LT.NS / SUNPHARMA.NS / ITC.NS`。

---

## 1. 当前应用如何检测市场（现状）

市场检测分散在多处，各层各有判定逻辑，且依赖共享的「后缀白名单」：

- **`src/services/market_symbol_utils.py`** —— 唯一的后缀市场白名单真源。
  `_SUFFIX_MARKET_SPECS` 目前只有三个 market：`jp(.T, 4-5位数字)`、`kr(.KS/.KQ, 6位数字)`、`tw(.TW/.TWO, 4-6位数字)`。`get_suffix_market()` 对「带点符号」做 `base + suffix` 拆分，并要求 **base 为纯数字且位数命中 `digit_lengths`** 才返回 market；否则返回 `None`。
- **`src/services/stock_code_utils.py`** —— `_normalize_code_and_exchange()` 与 `resolve_daily_stock_identity()`。判定顺序：显式前缀/后缀（`SH/SZ/SS/BJ/HK`、`.T/.KS/.KQ/.TW/.TWO`）→ 后缀市场 → US 正则 `^[A-Z]{1,5}(?:\.(?:US|[A-Z]))?$` → 纯数字位数（6 位 A 股 / 5 位港股）。`_PRESERVE_SUFFIXES` 决定哪些后缀原样保留。最终产出 `DailyStockIdentity(market=...)`，不能识别则返回 `None`。
- **`src/core/trading_calendar.py`** —— `get_market_for_stock()` 返回 `cn/hk/us/jp/kr/tw` 或 `None`（未知，fail-open 当作开市）。`MARKET_EXCHANGE` / `MARKET_TIMEZONE` 是交易日历与「今日」时区的按市场配置。
- **`src/market_context.py`** —— `detect_market()` 仅服务 LLM prompt 的角色/口径文案（A 股/港股/美股/日股/韩股/台股），返回 `cn/hk/us/jp/kr/tw`，无 `in` 分支时默认回退 `cn`。`_MARKET_ROLES` / `_MARKET_GUIDELINES` 是逐市场文案。
- **`data_provider/base.py`** —— `normalize_stock_code()`（跨市场清洗，保留 JP/KR/TW 后缀但无 NS）、`_market_tag()`（返回 `cn/us/hk/jp/kr/tw`，无 in 时回退 `cn`）、`_DAILY_MARKET_FETCHER_SUPPORT`（按 market 路由各数据源，`YfinanceFetcher` 当前支持 `cn/hk/us/jp/kr/tw`）。
- **`api/v1/endpoints/stocks.py`** —— `_STOCK_CODE_RE` 正则白名单（与前端 `validateStockCode` 对齐），用于 API 校验，未含 NSE 形式。

**结论**：市场检测的「统一开关」实际是 `market_symbol_utils` 的后缀白名单 + `stock_code_utils` 的解析器；其余模块都在消费/复刻这一判定。

## 2. 为什么 RELIANCE.NS 变成 market=unknown

根因是 **`.NS` 后缀不在任何后缀白名单中，且其 base 是字母而非数字**：

- `get_suffix_market("RELIANCE.NS")`：
  1. `split_suffix_symbol` → `("RELIANCE", "NS")`
  2. `_SUFFIX_TO_SPEC.get("NS")` → `None`（只有 T/KS/KQ/TW/TWO）
  3. → 返回 `None`。
- `_normalize_code_and_exchange("RELIANCE.NS")`：
  1. 非纯数字，跳过位数分支；
  2. `.NS` 不在 `_SUFFIX_DIGIT_LENS`、也不在 `_PRESERVE_SUFFIXES`；
  3. base `RELIANCE` 8 个字母，超出 US 正则 `^[A-Z]{1,5}` 上限；
  4. → 返回 `(None, "")`。
- `resolve_daily_stock_identity("RELIANCE.NS")`：`normalized_code is None` → 直接返回 `None`（market 未知）。
- `trading_calendar.get_market_for_stock("RELIANCE.NS")`：非 us/hk，`get_suffix_market` 为 `None`，非 6 位数字 → 返回 `None`。

> 补充：`market_context.detect_market("RELIANCE.NS")` 因 8 字母不匹配 US 正则且无后缀市场，会**误回退为 `cn`**；而 identity/日历层的 `get_suffix_market`/`resolve_daily_stock_identity` 则是 `None`（unknown）。即「unknown」主要出现在解析与交易日历层。

## 3. NSE 符号在内部应如何表示

建议沿用现有「后缀式 Yahoo 市场」约定，保持一致：

- **market 编码**：`in`（印度 NSE）。如后续也支持孟买 BSE，可用 `in` 覆盖 `.NS` 与 `.BO` 两个后缀，或单独用 `inbse`；本计划仅按 NSE 的最小范围处理 `.NS`。
- **规范形式**：大写 Yahoo 形式 `RELIANCE.NS`（`_normalize_suffix_market_symbol` 语义），后缀 `.NS` 保留。
- **与 JP/KR/TW 的关键差异**：现有 `SuffixMarketSpec.digit_lengths` 要求 base 为**纯数字**。NSE 的 base 是**字母 ticker**（`RELIANCE`、`HDFCBANK`、`LT`），因此现有「数字位数校验」模型无法直接套用，需要新增/放宽一个「字母 base 后缀市场」的判定分支（见 §4）。
- `DailyStockIdentity` 里 `market="in"`，`normalized_code` / `refill_code` / `code_candidates` 均保留 `.NS` 形式；`suffix_base_lookup_allowed` 对 `in` 保持与 JP/KR 相同或更严格（建议保守，不放开裸码模糊查找，避免与 US/A 股数字撞码）。

## 4. 市场检测的最小改动

集中在「后缀白名单 + 解析器 + 各消费点」：

- **`src/services/market_symbol_utils.py`**：
  - 新增 `SuffixMarketSpec("in", ("NS",), ...)`。因 NSE base 是字母，需为 `in` 放宽 `digit_lengths` 校验（如 base 允许 `^[A-Z]{2,}$`），或在 `get_suffix_market`/`normalize_suffix_market_symbol` 中为 `in` 单独走字母 base 判定。
  - 相应更新 `_MARKET_TO_SPEC` / `_SUFFIX_TO_SPEC` / `market_suffixes("in")`。
- **`src/services/stock_code_utils.py`**：
  - `_SUFFIX_DIGIT_LENS` 增加 `".NS"`；`_PRESERVE_SUFFIXES` 增加 `".NS"`。
  - `_normalize_code_and_exchange` / `resolve_daily_stock_identity`：在 US 正则分支**之前**先识别 `in` 后缀（含字母 base），避免把 `LT.NS`（2 字母，命中 US 正则 `^[A-Z]{1,5}(\.[A-Z]{1,2})?$`）误判为美股；在 market 归并处增加 `in` 分支与 `refill_code`。
  - `suffix_base_lookup_allowed` 明确 `in` 的策略。
- **`src/core/trading_calendar.py`**：`get_market_for_stock` 返回 `in`；`MARKET_EXCHANGE`/`MARKET_TIMEZONE`/`_CLOSING_AUCTION_WINDOW_MINUTES` 增加 `in`（见 §7）。
- **`src/market_context.py`**：`detect_market` 在 US 正则前识别 `.NS` 后缀 → `in`；`_MARKET_ROLES` / `_MARKET_GUIDELINES` 增加 `in`（中英文案，表述印度卢比、NSE 交易规则、T+0 等，不套用 A 股概念）。
- **`data_provider/base.py`**：`normalize_stock_code` 增加 `.NS` 保留分支；`_market_tag` 增加 `in`（置于 US 判定前）；`_DAILY_MARKET_FETCHER_SUPPORT` 的 `YfinanceFetcher` 支持集合加入 `"in"`。
- **`src/core/market_profile.py`**：新增 `IN_PROFILE`（region=`in`，mood_index_code 用 NSE 基准如 `^NSEI` 或 `NSEI`，news_queries / prompt 为印度市场文案，`has_market_stats`/`has_sector_rankings` 默认 False）；`get_profile("in")` 返回该 profile（注意 `get_profile` 目前未命中会回退 CN，需显式加分支）。

## 5. yfinance 数据抓取的最小改动

- **`data_provider/yfinance_fetcher.py` `_convert_stock_code`**：当前未知后缀会一路落到「默认深市 `.SZ`」，导致 `RELIANCE.NS` 被转成 `RELIANCE.SZ`（错误）。需在 `_is_jp_kr_suffix_stock` / `_is_tw_suffix_stock` 同一位置新增 `_is_in_suffix_stock`，命中 `.NS` 时**原样透传**给 Yahoo（`.NS` 本就是 Yahoo 的 NSE 后缀）。
- **`get_realtime_quote`** 的入参门槛（约第 819 行 `if not (is_us or _is_hk or _is_jp_kr or _is_tw)`）：必须把 NSE 加入放行集合，否则 `.NS` 直接 `return None`。返回的 `UnifiedRealtimeQuote.market` 在 `get_suffix_market(symbol)` 命中后会正确变为 `in`，`currency` 由 `ticker_info.currency` 得到 `INR`。
- **`get_main_indices`**：如需印度大盘复盘，新增 `region=="in"` 委托方法（`_get_in_main_indices`），复用 `_fetch_yf_ticker_data`（如 `^NSEI` / `^BSESN`）。
- **`data_provider/base.py` `_DAILY_MARKET_FETCHER_SUPPORT`**：`YfinanceFetcher` 支持集合加 `"in"`，否则日线路由会跳过该数据源。

## 6. INR / 货币处理

- 实时行情侧：`UnifiedRealtimeQuote.currency` 已由 yfinance 的 `ticker_info["currency"]` 直接填充（返回 `INR`），本层无需新逻辑。
- 需补的缺口：**日线 `STANDARD_COLUMNS`（`base.py`）只有 `amount`，不含货币字段**，`amount` 由「成交量 × close」估算，含义与 INR 无关。报告 / 通知 / WebUI 中若用市场符号拼接货币（如 `CNY`/`USD`/`HKD`），需要按 `market=in` 提供 `INR` 的映射与显示。
- 建议：增加一个「market → 默认货币」映射（`in → INR`），供报告、行情卡片、通知模板统一取用；不要硬编码到分析 prompt。本计划不修改 `.env`。

## 7. 交易日历 / 时区要求

- **时区**：`MARKET_TIMEZONE["in"] = "Asia/Kolkata"`（IST，UTC+5:30）。
- **交易日历**：`MARKET_EXCHANGE["in"]` 使用 exchange-calendars 的印度市场代码（NSE 通常为 `XNSE`；实施时需核实该版本 exchange-calendars 提供的印度日历键名，若不可用则保持 fail-open）。
- **收盘拍卖窗口**：`_CLOSING_AUCTION_WINDOW_MINUTES["in"]` 建议 `5`（NSE 15:25–15:30 收盘集合竞价，需实施时确认），不设置时 `get(market,0)` 退化为普通收盘。
- `get_market_for_stock`、`get_effective_trading_date`、`infer_market_phase`、`get_open_markets_today` 均以 `MARKET_EXCHANGE` / `MARKET_TIMEZONE` 为驱动，补上 `in` 后自动覆盖。

## 8. 股票名称解析

- `yfinance_fetcher.get_realtime_quote` 已用 `ticker.info.shortName/longName` 经 `is_meaningful_stock_name` 判断后取名称，失败时回退 `STOCK_NAME_MAP`（`src/data/stock_mapping.py`）。
- 对 NSE，名称解析应：优先用 yfinance 返回的官方名称；`STOCK_NAME_MAP` 需增加以 `.NS` 为 key 的中文/英文名称条目（例如 `RELIANCE.NS`、`TCS.NS`…），供无网络或 yfinance 失败时兜底。
- `stock_index_loader` / `stocks.index.json`（`src/data/stock_index_loader.py`、`apps/dsa-web/public/stocks.index.json`）若用于名称/代码解析，需评估是否补充 NSE 条目；本计划按最小范围默认不强制，除非名称查询依赖它。

## 9. WebUI 校验

- 后端 `api/v1/endpoints/stocks.py` 的 `_STOCK_CODE_RE` 是 API 入参校验白名单，目前未含 NSE 形式 → 需增加 `.NS` 模式（字母 base，例如 `[A-Z]{2,}\.NS`，且放行前于 US ticker 分支以避免歧义）。
- 前端 `apps/dsa-web` 的 `validateStockCode` 需与后端 `_STOCK_CODE_RE` 同步新增 NSE 校验；`_watchlist_match_key` / `normalize_stock_code` 需保证 `.NS` 稳定去重。
- 需同步确认 WebUI 的行情卡片、货币显示、市场标签渲染对 `market=in` 与 `INR` 的兼容性（不在本计划实现范围，列为交付验证项）。

## 10. 针对 10 只 NSE 股票所需测试

测试目标：`RELIANCE.NS / TCS.NS / INFY.NS / HDFCBANK.NS / ICICIBANK.NS / SBIN.NS / BHARTIARTL.NS / LT.NS / SUNPHARMA.NS / ITC.NS`。

- **市场检测**：`get_suffix_market`、`resolve_daily_stock_identity`、`trading_calendar.get_market_for_stock`、`market_context.detect_market` 对这 10 只均返回 `in`（重点：`LT.NS` 2 字母、`HDFCBANK.NS` 8 字母、`BHARTIARTL.NS` 10 字母等边界）。
- **代码规范化**：`normalize_stock_code` / `_normalize_code_and_exchange` / `canonical_stock_code` 对 `.NS` 原样保留、大小写归一。
- **yfinance 转换**：`_convert_stock_code` 对 `RELIANCE.NS` 等原样透传（返回 `RELIANCE.NS`，不是 `RELIANCE.SZ`）；`get_realtime_quote` 放行 `.NS` 且返回 `market=in`、`currency=INR`。
- **API 校验**：`_STOCK_CODE_RE` 接受全部 10 只 NSE 代码（含 `LT.NS`），拒绝非法形式。
- **交易日历**：`is_market_open("in", date)`、`get_market_now("in")`、`get_effective_trading_date("in")` 走 IST 时区与印度日历（离线 mock 固定断言，避免在线依赖）。
- **名称解析**：`STOCK_NAME_MAP` / yfinance 名称兜底对这 10 只返回非空名称。
- **Prompt 市场语境**：`get_market_role` / `get_market_guidelines` 对 `.NS` 返回印度市场文案而非 A 股文案。

## 11. 哪些现有市场可能受影响

- **US（最高风险）**：NSE 的字母 base 会与 US ticker 分支冲突。`LT.NS`、`TCS.NS`、`INFY.NS`（base ≤5 字母）会命中 US 正则 `^[A-Z]{1,5}(\.[A-Z]{1,2})?$`，必须在 US 判定**之前**识别 `.NS`，否则被误判为美股。所有相关模块（`stock_code_utils`、`market_context.detect_market`、`base._market_tag`）都要保证 `in` 判定优先于 US。
- **cn（低风险但存在误回退）**：`market_context.detect_market` 与 `base._market_tag` 无 `in` 分支时默认回退 `cn`，会导致 `.NS` 被当成 A 股；补 `in` 分支即可消除。
- **jp / kr / tw（共享后缀机制）**：`market_symbol_utils` 是三者共用的后缀表，新增 `in` 时不改变既有 `T/KS/KQ/TW/TWO` 的判定，但要确保新后缀与它们互不冲突（`NS`/`BO` 与现有后缀无重合）。
- **hk（低风险）**：`.NS` 与 `.HK`/`HK` 前缀无冲突，但需在 `normalize_stock_code` 中把 `.NS` 加入保留分支，避免被 `.HK` 前缀/后缀分支误吞。
- **A 股 6 位数字分支**：不受影响，因为 NSE base 非纯数字；但仍建议在 `_classify_bare_code` / 数字位数分支显式排除 `in`，以防未来出现数字型 NSE/证券。

---

## 交付注意事项（后续实现时）

- 按 `AGENTS.md`：改动后端时至少跑 `python -m py_compile`，影响 API/报告/通知/数据源路由/日历的路径需说明覆盖情况；新增配置项同步 `.env.example` 与文档；用户可见能力变化同步 `docs/CHANGELOG.md`。
- 本计划仅做方案，未修改任何源码，未修改 `.env`，未翻译任何既有中文文本。