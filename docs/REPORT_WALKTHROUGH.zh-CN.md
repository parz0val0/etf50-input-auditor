# 看一份实际生成的合成报告

[English](REPORT_WALKTHROUGH.md) · [简体中文](REPORT_WALKTHROUGH.zh-CN.md)

以下六条输入是虚构资料。这是程序实际输出，不是伪造截屏或市场结果。目前核心CLI/报告文字为中文。

## 本地复跑（公开可运行）

先按README安装，从仓库根目录运行，输出目录须新建：

```sh
.venv/bin/python scripts/reproduce_onboarding_case.py --output onboarding-demo
```

演示核对坏输入主检查退出1、修正后退出0，演示本身退出0。修正是明确的虚构早期观测/估计和买卖盘，不是改时间标签或把结算价重命名。见[八个字段改动](../examples/onboarding/output/comparison.md)。

## 查看前后变化

| 用途 | 修正前 | 修正后 |
|---|---|---|
| 历史IV输入记录 | 3相容、2待补证、1阻断 / 6 | 6相容 / 6 |
| 配对输入记录 | 4相容、2阻断 / 6 | 6相容 / 6 |
| 完整且条件相容的配对 | 2 / 3 | 3 / 3 |

记录与配对是不同分母。以上只表示已实现检查下声明相容，不是研究资格或准确率。

修正前JSON汇总摘录，未更改值：

```json
{
  "rows": 6,
  "historical_iv": {
    "conditional_input_consistent": 3,
    "needs_evidence": 2,
    "blocked": 1
  },
  "pair": {
    "conditional_input_consistent": 4,
    "blocked": 2
  },
  "conditional_pairs": 2
}
```

[修正前JSON](../examples/onboarding/output/before/report.json) · [修正后JSON](../examples/onboarding/output/after/report.json) · [修正前离线HTML](../examples/onboarding/output/before/report.html) · [修正后离线HTML](../examples/onboarding/output/after/report.html)

GitHub把HTML显示为源代码；下载仓库并在浏览器打开本地生成的报告，它不是托管应用。先看问题码、业务记录和对侧记录，再读建议。预期问题包括SPOT_ALIGNMENT_MISSING、Q_INPUT_MISSING、SETTLEMENT_NOT_INDEPENDENT。

## 没有检查问题，仍可能有未知事实

修正后evidence_truth_verified仍为false。虚构policy和引用未经认证，真实许可和每日母集也未核验。不证明IV、carry、市场预测、交易或效率提升。有缺证的真实记录继续未知，不要把虚构q=0或事件覆盖搬进自己的数据。

[检查边界](TOOL_BOUNDARIES.md) · [案例规格](ONBOARDING_CASE.md) · [完整流程](GETTING_STARTED.zh-CN.md)
