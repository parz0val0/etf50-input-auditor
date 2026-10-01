# 相关工具与本项目差异

2026-10-01直接阅读原仓库页面/README或指定测试源码。没有运行这些仓库，也没有审查其全部代码；表内能力来自可定位材料，不能证明它们缺少本项目某功能。没有复制第三方代码。

| 项目与材料 | 已见能力 | 对本项目定位的影响 |
| --- | --- | --- |
| [vollib/py_vollib](https://github.com/vollib/py_vollib) | Black/BS/BSM定价、IV与解析/数值Greeks | 本项目不能以BS/IV计算器作为原创核心 |
| [QuantLib Heston测试](https://github.com/lballabio/QuantLib/blob/master/test-suite/hestonmodel.cpp) | 多参数/方法参考与数值一致性测试 | 多精度、参考价与数值审计已有成熟先例 |
| [fourier-option-pricer](https://github.com/nl2992/fourier-option-pricer) | 论文复现、冻结参考、断言门槛、CSV基准和验证状态 | 通用可复现/证据分级理念与本项目接近，不能声称首创 |
| [heston-model-calibration](https://github.com/drmshoaib/heston-model-calibration) | 合成曲面、多起点校准、残差、敏感性、积分收敛及可辨识性限制 | 数值诊断只是辅助价值 |
| [vol-surface README](https://github.com/wzx11223344/vol-surface/blob/main/README.md) | README声明AkShare50ETF/300ETF、SVI、无套利及可视化；未实测 | 50ETF工具与曲面已有项目，不宣称没有重复 |

本候选具体尝试：将50ETF静态/调整条款的拒绝规则、时点/来源准入、同侧整对检查及研究结论限制串成低依赖、离线CSV→行级JSON/HTML的流程。差异可以从合成正常/故障样例、哈希绑定和测试复核，而不是市场新颖性排名。模块仍是原型，未认证真实历史覆盖，未证明相较上述项目的精度或效率优势。
