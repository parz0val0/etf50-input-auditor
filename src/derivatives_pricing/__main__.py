"""Run a synthetic, reproducible pricing example."""

from . import BSInputs, greeks, parity_gap, price


def main() -> None:
    inputs = BSInputs(S=100, K=100, T=1, r=0.05, sigma=0.2, q=0.03)
    call = price(inputs, "call")
    put = price(inputs, "put")
    print("合成输入示例（非市场数据）")
    print(f"参数: {inputs}")
    print(f"认购价格: {call:.10f}")
    print(f"认沽价格: {put:.10f}")
    for option_type in ("call", "put"):
        sensitivities = greeks(inputs, option_type)
        print(f"{option_type} Greeks: {sensitivities}")
    print(f"认购认沽平价残差: {parity_gap(call, put, inputs):.3e}")


if __name__ == "__main__":
    main()
