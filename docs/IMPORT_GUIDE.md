# 把外部导出映射为可检查的CSV

本工具不识别所有供应商格式，也不会从代码解析执行价。以下族都是本项目构造，仅验证说明与检查接口；不代表真实供应商或真实用户已经导入成功。

## 路径一：只有日行情

先导出10列：date、code、underlying、cp、strike、expiry、contract_unit、adjustment_flag、price、price_type。模板：[最小合成日行情](../examples/admission/synthetic_minimal_daily.csv)。日期ISO，CP为C/P，执行价/单位来自有效主表，price_type明确来自数据字典。现有单位未知时不要猜10000：填写空值以保留阻断。

公开可运行（先安装README中的CLI）：`.venv/bin/etf50-audit examples/admission/synthetic_minimal_daily.csv --output audit-output/minimal`。预期退出1，缺失证据完整保留；无需先编造25列“合格输入”。输出能告诉你还缺什么，不能恢复原导出没有的时点/BBO。

## 路径二：列名不同的外部导出族

[构造的中文列CSV](../examples/admission/synthetic_vendor_export.csv)和[构造的数据字典](../examples/admission/synthetic_vendor_dictionary.json)故意使用另一组列名，直接导入应退出2、提示必要列缺失。公开可运行：`.venv/bin/etf50-audit examples/admission/synthetic_vendor_export.csv --output audit-output/vendor-raw`。错误输入不创建目录。

| 构造导出字段 | 目标字段/转换 |
| --- | --- |
| 交易日期、到期日 | date、expiry；明确YYYY/MM/DD转换为YYYY-MM-DD |
| 合约编码、标的代码 | code、underlying；字符串保留前导零 |
| 认购认沽 | cp；认购→C、认沽→P |
| 行权价格 | strike；真实生效执行价，不用初始执行价或代码尾部 |
| 合约单位、调整标记 | contract_unit、adjustment_flag；按原值保留调整单位/A |
| 收盘价 | price；由该构造字典明示语义填price_type=close，不替换成settle或mid |

映射后的10列应与最小模板相同，仍待补证。列名映射、日期格式和CP编码是三类明确规范化操作；映射成本由使用者承担，本轮没有加入通用映射模块。真实导出字段若语义不明先问数据持有人，不能照表猜。Excel日期序号、时区、复权/单位等不在此自动转换范围。

## 路径三：有证据的同步报价

再按[完整契约](ADMISSION_SCHEMA.md)提供主表/源版本引用、带时区的业务时间、独立现货时间、时点已知r/q及方法、BBO和数量。完整合成模板见[声明条件相容CSV](../examples/admission/synthetic_consistent.csv)及[合成配置](../examples/admission/synthetic_policy.json)。这些示例值只能用于演示。

需要用户数据的命令模板：`etf50-audit user-data/INPUT.csv --policy user-data/POLICY.json --output audit-output/NEW_NAME`。无可证明同步时继续保留待补证/阻断，不能只扩大lag、把缺失q改0、回填未来时间、重写M/10000或扩大覆盖区间。非空引用仍可能不真实，工具不会联网核实。

日行情族、另一列名族、正常报价族、负价格/NaN/异步/调整/对侧/未知覆盖在开发回归中检查。真实导入效率是否提高尚待独立模拟；目前能自动重复检查已映射字段与整对关系，仍不能省掉供应商映射和外部证据核验。

## rc5预检

新增独立etf50-preflight入口，先建议并审阅映射，再提供源哈希和明确映射生成副本；见双语README及[供应商要求](SUPPLIER_REQUIREMENTS.md)。不自动转换语义、单位或未知时点。
