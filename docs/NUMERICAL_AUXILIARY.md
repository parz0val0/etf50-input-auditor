# 辅助数值诊断

核心用途是研究输入检查。原项目的BS/CRR/MC、IV、Heston等作为辅助保留，不把定价计算器当差异化核心。原历史协议、数据及负结果留在本地；本候选不含行情或未许可历史聚合。

公开可运行（先按README创建.venv并安装项目）：

```sh
.venv/bin/python scripts/numerical_budget_study.py --output numerical-demo.json
.venv/bin/python -m pip install '.[test,web]'
.venv/bin/python -m pytest -q
```

新输出文件不可已存在。预算演示为固定合成GBM、固定种子与510次计时；经验误差预算不是市场精度或总体置信保证，计时不是跨硬件稳定排名。新手案例可直接使用标准库Python，不需这些可选依赖。
