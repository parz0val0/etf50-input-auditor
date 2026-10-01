# 三个问题的合成前后对比

全部数据和证据是人为构造。修正后仅条件相容，实际证据真实性仍未由工具验证。

| 业务记录 | 历史IV前→后 | 配对前→后 | 原问题代码 |
| --- | --- | --- | --- |
| 1 | conditional_input_consistent → conditional_input_consistent | conditional_input_consistent → conditional_input_consistent |  |
| 2 | needs_evidence → conditional_input_consistent | conditional_input_consistent → conditional_input_consistent | SPOT_ALIGNMENT_MISSING |
| 3 | needs_evidence → conditional_input_consistent | conditional_input_consistent → conditional_input_consistent | Q_INPUT_MISSING |
| 4 | conditional_input_consistent → conditional_input_consistent | conditional_input_consistent → conditional_input_consistent |  |
| 5 | conditional_input_consistent → conditional_input_consistent | blocked → conditional_input_consistent | PAIR_NOT_SYNCHRONOUS_MID, PAIR_PEER_BLOCKED |
| 6 | blocked → conditional_input_consistent | blocked → conditional_input_consistent | SETTLEMENT_NOT_INDEPENDENT, PAIR_NOT_SYNCHRONOUS_MID, PAIR_PEER_EVIDENCE_MISSING |

三个根因在记录2、3、6；其余配对提示是根因造成的派生问题，不是额外三份独立证据。

[修正前HTML](before/report.html) · [修正后HTML](after/report.html) · [字段修改与哈希](comparison.json)

每次输出目录须新建。不能把本案例的补证值或虚构覆盖配置用于行情。
