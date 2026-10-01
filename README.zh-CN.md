# 50ETF研究输入检查小工具

[English](README.md) | [简体中文](README.zh-CN.md)

面向已经拿到510050期权CSV、准备做历史IV或同期限call-put研究的人。**0.4.0rc6**新增保守的供应商CSV预检，识别建模前的输入矛盾、证据缺失和静态条款不适用。这是普通Python软件，运行不需要AI服务、账号、API密钥或网络；安装可能下载构建后端。它不定价、不认证数据，也没有完成原历史实证。

## 安装和版本验证（公开可运行）

Python3.9+，在macOS/Linux的仓库根目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/etf50-audit --version
.venv/bin/etf50-preflight --help
```

核心运行无第三方依赖，Windows路径尚未实测。参见[安装说明](docs/INSTALLATION.md)。

## 完整合成演示（公开可运行）

使用尚不存在的输出目录。正常、故障和修正都是完全合成资料，不是市场证据：

```sh
.venv/bin/etf50-audit examples/admission/synthetic_consistent.csv --policy examples/admission/synthetic_policy.json --output audit-output/normal
.venv/bin/etf50-audit examples/admission/synthetic_failures.csv --policy examples/admission/synthetic_failure_policy.json --output audit-output/failures
.venv/bin/python scripts/reproduce_onboarding_case.py --output onboarding-demo
```

第一条预期退出0；第二条退出1并生成报告，是预期发现问题；第三条核对修正前后案例后退出0。三个根因是未来ETF、尚未已知的q、结算价当市场价格；修正使用明确的虚构早期观测、估计和BBO。打开`onboarding-demo/comparison.md`及其中HTML链接。修正后仅声明条件相容，证据仍为虚构。见[案例详情](docs/ONBOARDING_CASE.md)。

## 供应商CSV：先预检，审阅后确认转换

[供应商资料要求](docs/SUPPLIER_REQUIREMENTS.md)区分十个基础解析列、历史IV/配对追加证据及高质量研究资料。UTF-8 CSV允许BOM，每上海交易日每合约一行，列名唯一；Excel请先导出。不能为方便猜测单位、时区、来源或价格含义。[完整字段契约](docs/ADMISSION_SCHEMA.md)。

公开可运行的合成日数据预检：

```sh
.venv/bin/etf50-preflight examples/admission/synthetic_minimal_daily.csv --output audit-output/preflight
```

基础映射无歧义预期退出0，但JSON仍列用途证据缺项，**不代表准入通过**。输出建议、歧义、类型/日期/时间提醒、未知列及最多五行预览。预检退出0表示检查没有结构/映射提醒；1表示需审阅或后续准入有问题；2表示输入输出无效。主检查的退出含义另见下文。

用户资料模板（需要自己的合法本地文件，不是公开演示）：

```sh
.venv/bin/etf50-preflight user-data/vendor.csv --output audit-output/review
.venv/bin/etf50-preflight user-data/vendor.csv --mapping user-data/confirmed-mapping.json --expected-source-sha256 SOURCE_SHA256_FROM_REVIEW --policy user-data/policy.json --output audit-output/converted
```

审阅建议及原字典，写如`{"date":"交易日期","code":"合约代码"}`的JSON并补齐必要列。显式选price不代表语义已核验。别名冲突需明确一对一选择；缺必要列有报告但不生成规范CSV。确认映射只改列名、保留值，不翻译C/P、日期、单位或伪造证据。每次转换须确认当前源哈希，复用映射也记录哈希。转换调用**同一个主检查器**，可提供自己的policy；读嵌入准入结果。无policy不能证明事件覆盖。源文件不改，不覆盖既有输出目录。

预览含原ID/价格，应保持私有。原件放被忽略的`user-data/`，输出放`audit-output/`；分享前人工检查，gitignore不是安全保证。

公开可运行的中文列/BOM确认演示：生成合成供应商CSV，记录显式映射和源哈希，并验证调用同一主检查器：

```sh
.venv/bin/python scripts/reproduce_preflight_case.py --output audit-output/preflight-demo
```

预期退出0；虚构证据没有被认证。

## 状态及边界

主检查退出0=所实现条件相容，1=报告发现问题，2=格式/输入输出错误。`blocked`=已实现检查的硬矛盾；`needs_evidence`=缺失或不可用证据；`conditional_input_consistent`=所实现条件下声明相容。历史IV与配对分开，对侧问题传播到整对。部分已知不可用输入仍归待补证，不能理解为加引用就可修好值。

仅支持静态M/10000；拒绝调整、跨事件及未核验事件日条款。用户声明事件覆盖不等于认证。不认证来源/许可或每日母集，不估计IV/carry，不证明市场有效性，不提供金融建议或交易。未知保持未知。HTML转义/结构有测试，浏览器视觉尚未验证。[检查边界](docs/TOOL_BOUNDARIES.md)。

[首次模拟评价](docs/SIMULATED_USER_EVALUATION.md)没有证明正确率提升或真人提效；后续模拟回归验证机制，不是独立效能证据。可复用数值工具包与输入检查是交付，原历史实证尚未完成。[数值辅助](docs/NUMERICAL_AUXILIARY.md) · [相关项目](docs/RELATED_WORK.md) · [发布清单](docs/RELEASE_CHECKLIST.md)。

## 许可

[MIT](LICENSE)，Copyright (c) 2026 JasonChen。软件许可不覆盖供应商数据或第三方材料，须保留相应归因。当前为本地审查候选，独立审查通过后再发布仓库。
