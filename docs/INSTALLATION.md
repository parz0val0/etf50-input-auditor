# 安装与版本自检

核心检查只使用标准库，但从源码安装会用构建工具；两者不能混为一谈。Python最低3.9，rc4曾在干净macOS/Python3.9联网隔离构建实跑；rc5安装证据见交付记录。Windows及其他版本尚未实测。

## 常规安装（公开可运行，需允许访问PyPI）

从候选解压目录运行；不要在冻结目录内生成文件：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/etf50-audit --version
.venv/bin/python -c "from importlib.metadata import version; print(version('derivatives-pricing'))"
```

两项自检均应显示0.4.0rc6。仅pip退出0不足以证明安装了本项目：若出现UNKNOWN-0.0.0、没有CLI或版本不符，停止使用，核对解释器和构建后端。

## 离线前提（需预先准备本地文件）

没有构建工具缓存时，不应机械加`--no-index --no-build-isolation`凑安装。项目要求setuptools>=61；关闭隔离意味着必须自己保证合格后端及wheel工具。首次代理模拟的失败发生在额外离线参数和旧后端条件下，不能推广为标准pip隔离流程失败或Python3.9运行不兼容。

最直接的离线方式是预先取得并核对附送候选wheel及SHA。命令模板（需用户本地已取得该wheel，不是源码目录自带文件）：`python3 -m pip install --no-index --no-deps /PATH/TO/derivatives_pricing-0.4.0rc6-py3-none-any.whl`。核心没有第三方运行依赖；数值/测试可选依赖需另行准备。随后用`etf50-audit --version`与发行包版本自检。已验证wheel的文件名和哈希在交付记录中，不自行使用未知或旧wheel。

仅看案例无需安装：公开可运行`python3 scripts/reproduce_onboarding_case.py --output onboarding-demo`。工具发现坏输入的退出1是正常检查结果，不能与安装错误或输入格式错误的退出2混淆。
