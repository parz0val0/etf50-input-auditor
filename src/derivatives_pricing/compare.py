"""Reproduce a synthetic convergence and timing comparison."""

import argparse
import platform
import sys
from pathlib import Path
from time import perf_counter_ns

from . import BSInputs, binomial_price, monte_carlo_price, price

INPUTS = BSInputs(S=100, K=100, T=1, r=0.05, sigma=0.2, q=0.03)
SEED = 20260928
TREE_STEPS = (50, 100, 200, 400, 800)
MC_PATHS = (2000, 8000, 32000, 128000)


def _timed(function):
    start = perf_counter_ns()
    value = function()
    elapsed_ms = (perf_counter_ns() - start) / 1_000_000
    return value, elapsed_ms


def build_report() -> str:
    """Return Markdown; numeric prices are seeded, timings describe this run."""
    lines = [
        "# 阶段 2：合成输入数值收敛比较",
        "",
        f"输入：`{INPUTS}`；蒙特卡洛种子：`{SEED}`。所有价格单位均与 S、K 相同。",
        "",
        "环境：Python " + platform.python_version() + "；" + platform.platform()
        + "；实现：" + platform.python_implementation() + "。",
        "",
        "计时：`time.perf_counter_ns()`，每个方法、期权类型及样本量单次顺序调用；"
        "毫秒数包含该次函数的参数检查、建树或随机数生成，不含表格格式化及 Black–Scholes 基准计算。"
        "未预热或重复取均值，运行时间受机器负载影响。",
        "",
        "树为 CRR 欧式定价；蒙特卡洛模拟同一风险中性几何布朗运动的终值，"
        "采用反向变量配对，95% 区间是按独立配对均值计算的正态近似区间。",
        "",
    ]
    for option_type, name in (("call", "认购"), ("put", "认沽")):
        benchmark = price(INPUTS, option_type)
        lines.extend([
            f"## {name}", "",
            f"Black–Scholes 基准：`{benchmark:.10f}`。误差 = 数值价格 − 基准价格。", "",
            "| 方法 | 步数/路径数 | 价格 | 误差 | 95% 置信区间 | 运行时间 (ms) |",
            "| --- | ---: | ---: | ---: | --- | ---: |",
        ])
        for steps in TREE_STEPS:
            value, elapsed = _timed(lambda: binomial_price(INPUTS, option_type, steps))
            lines.append(f"| 二叉树 | {steps} | {value:.10f} | {value - benchmark:+.10f} | — | {elapsed:.3f} |")
        for paths in MC_PATHS:
            result, elapsed = _timed(
                lambda: monte_carlo_price(INPUTS, option_type, paths, SEED)
            )
            lines.append(
                f"| 蒙特卡洛 | {paths} | {result.price:.10f} | "
                f"{result.price - benchmark:+.10f} | "
                f"[{result.ci_lower:.10f}, {result.ci_upper:.10f}] | {elapsed:.3f} |"
            )
        lines.append("")
    lines.extend([
        "同一偶数步数序列中，树的离散化误差随步数增加而缩小。蒙特卡洛的单次绝对误差"
        "不要求逐项递减；区间宽度随独立配对数增加而缩小，区间具有近似覆盖率而非确定保证。",
        "",
        "上述差异是相同模型假设下的**数值误差**。本比较没有市场价格或替代模型，"
        "因此不能测量**模型误差**，也不能得出市场定价结论。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write Markdown to this path instead of stdout")
    args = parser.parse_args()
    report = build_report()
    if args.output is None:
        sys.stdout.write(report)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"已写入 {args.output}")


if __name__ == "__main__":
    main()
