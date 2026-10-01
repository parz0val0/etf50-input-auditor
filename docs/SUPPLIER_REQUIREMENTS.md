# Supplier requirements / 供应商资料要求

The supplier's original headers need not be English. Preserve the original file and its dictionary; normalize a copy. / 供应商原表不必使用英文列名；保留原件和字典，转换副本。

| Normalized field / 规范列 | Meaning / 含义 |
|---|---|
| date, code | Shanghai trading date YYYY-MM-DD; actual contract ID / 上海交易日、真实合约ID |
| underlying, cp | 510050; C or P / 标的及认购认沽 |
| strike, expiry | Current effective strike in yuan per ETF share; expiry YYYY-MM-DD / 当日有效执行价、到期日 |
| contract_unit, adjustment_flag | Shares per contract; original M/A flag / 每合约ETF份数、原调整标记 |
| price, price_type | Yuan per ETF share; confirmed close/mid/settle meaning / 每ETF份人民币、已证实价格含义 |

These ten headers only permit parsing; blank or bad values are still checked. One row per contract per Shanghai date, no arbitrary intraday duplicates. UTF-8 CSV including BOM; standard comma/quoting; 32MiB, 128 columns, 100000 rows, 4096 characters per cell. Excel is not read directly: export CSV, preserve IDs and dates as strings. / 十列只允许解析，不意味着研究合格。每上海交易日每合约一行；限制同上。Excel请导出CSV，防止ID丢零、日期变序号。

For historical-IV inputs, supply independent spot and spot_known_at; r/q annual continuous decimal, their known times and references; option price_known_at, source_reference, terms_reference. Current implementation requires spot no later than option and at most one second earlier. Never fill unknown r/q with zero, receipt time with business time, or realized dividends with past expectations. / 历史IV输入另需独立ETF价与业务时点、连续复利小数r/q及已知时点/依据、期权时点、来源和条款依据；当前匹配不得用未来ETF且滞后≤1秒。

For pair inputs, additionally supply bid/ask in yuan per share and bid_qty/ask_qty in contracts, unique same-term C/P and actual business timestamps. Declared mid must equal their mean; depth must be positive for pairing. Coverage-policy references and adjustment-event completeness are separate evidence. Static M/10000 only; preserve adjusted units rather than forcing them to10000. / 配对另需买卖一价量、唯一同条款双侧和实际业务时点；中点需相容、配对深度须正；事件覆盖声明独立，调整合约不得改成标准合约过关。

High-quality research additionally needs effective-dated independent master/universe, source/export versions, observed price formation rules, licensed research and public aggregation rights, rate conventions/publication and historical dividend information, a frozen independent evaluation design. The tool does not authenticate these facts. / 高质量研究另需有效期主表/挂牌母集、源版本/导出日志、价格形成规则、研究及公开汇总权限、利率和历史分红信息、冻结独立评价；工具不认证事实。

Preflight suggests common aliases; a close or settle header is deliberately not auto-selected as price. A mapping JSON explicitly selects columns only, not values/units. Chinese C/P values and slash dates require separately reviewed conversion. Mixed offsets are listed, never silently removed. Unknown columns are reported; unsupported meaning remains unknown. / 预检只建议常见别名，不自动挑收盘或结算价；映射只改列名，中文C/P、斜杠日期需另行审阅转换。混合时区保留，未知不猜。

Reports contain a five-row price/ID preview and are private by default. Mapping, source and normalized hashes support repeat imports; confirm each new source hash. Keep supplier files in user-data and results in audit-output; neither is published. / 报告含五行价格/ID预览，默认私有；重复导入可复用映射，但每个新源仍需确认哈希。
