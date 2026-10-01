# CSV与配置契约 v1

UTF-8（可带BOM），逗号分隔，标准CSV引用规则。32MiB、128列、100000业务行、单字段4096字符上限。列名唯一、非空且无首尾空格；坏编码、列数错配、重复列、空文件会失败。未知额外列保留列名，但不读取其语义，不复制其值进报告。默认不转换Excel公式、不执行用户代码、不访问证据URL。

## 必要列

| 字段 | 规则 |
| --- | --- |
| date / expiry | ISO YYYY-MM-DD；expiry严格晚于date；date按上海交易日期理解 |
| code | 非空合约ID；日期+ID唯一；报告用业务记录号定位 |
| underlying | 本版本仅510050 |
| cp | C或P，大小写严格 |
| strike | 正有限数，当前生效真实执行价，元/ETF份额；不解析代码尾部 |
| contract_unit | 正整数；静态实现要求10000 |
| adjustment_flag | M；A等调整合约保持原值并阻断，不能改成M逃避检查 |
| price | 非负有限数、元/ETF份额；零价格历史IV输入阻断 |
| price_type | close / mid / settle；settle不可作为独立市场IV/配对验证价格 |

## 证据与问题所需列

| 字段 | 所用于检查 |
| --- | --- |
| terms_reference | 有效主表来源/版本引用，要求非空；本工具不证明master有效区间真实性 |
| source_reference | 原始来源/导出版本引用，要求非空；本工具不验证许可 |
| price_known_at | **价格业务时间**，带明确UTC偏移ISO时戳（或Z）；转换上海+08:00后日期须与date一致。接收时间不能替代业务时间 |
| spot / spot_known_at | 历史IV输入需正独立ETF观测，时戳不晚于期权且滞后≤1秒 |
| r / q | 年化连续复利数值（.02表示2%）；允许负数但须有限；不默认0 |
| r_known_at / q_known_at | 信息已知时间，带时区，不晚于价格业务时间 |
| r_reference / q_reference | 曲线/预测方法/版本的非空引用；实现分红不等于此前已知q |
| bid / ask / bid_qty / ask_qty | 配对需0≤bid≤ask，数量正整数（合约张数）；mid等于两边均值，绝对容差1e-9元 |

真实用户提交值的真实性不能仅靠格式验证。时戳只检查声明的时序，无法证明历史同步；代码不计算IV/远期，输出条件状态不能当全研究资格。

## 配置JSON

[完整合成配置](../examples/admission/synthetic_policy.json)可运行，仅用于虚构场景。

- schema_version固定1；data_kind为synthetic或user_market。
- rights_reference是使用权/来源证据引用，必须非空；不是自动授权。
- coverage严格含start/end/complete/evidence_reference。日期区间有序、complete须true；只是用户对事件清单完整性的声明。区间必须包住观察日至到期，不能凭软件把区间延长。
- events必须显式存在，元素含唯一date和非空evidence_reference；日期须在coverage内。空列表仅在该区间真实无事件并有证据时才可用于行情。
- max_pair_lag_seconds默认1，可声明0至5；容差只是必要条件，不证明经济同步。
- 未识别键、重复JSON键或无效配置会失败。无policy则覆盖证据保持缺失，不自动使用任何硬编码年份的认证规则。

整对按date/expiry/strike/unit/flag/underlying分组，只接受一个C和一个P；同条款多ID视为歧义，不自动选。配对必须为mid及容差内带时戳BBO；本工具只检查整对准入，不做跨执行价carry估计，也不要求曲面最小深度。

## 输出契约

report.json包括schema_version、tool_version、checker_sha256、input_sha256（原文件字节）、policy_sha256（原配置字节）、完整configuration、evidence_level、scope、limits、summary及records。每条issue包含code/severity/scope/message/repair。records从1计数，分别输出historical_iv和pair状态；配置声明synthetic则synthetic_declared，否则user_declared_unverified。

内容可由JSON直接追溯到输入与代码。没有随机或网络结果；同输入/配置/检查器版本JSON确定一致。程序/输入失败退出2；正常生成且有阻断或待补证退出1；所有记录的两个问题条件一致退出0。警告仍需人工审阅。分享前检查configuration及列名中的私人信息。

rc2：唯一整对先计算双方自身资格，再对称传播对侧pair阻断/缺证；每侧含peer_record，传播问题含peer_issue_codes。历史IV按行独立。重复/多ID歧义整组配对阻断；缺侧待补证，不虚构peer。超大整数及过深配置返回INPUT_ERROR退出2，不生成目录。

rc4：mid均值核验不依赖深度是否合格；bid/ask有效有序时即检查声明价格。bid/ask缺失或无效则历史IV出现MID_PRICE_UNVERIFIABLE，不隐含已核实mid。--version可在无需输入文件时检查CLI版本。
