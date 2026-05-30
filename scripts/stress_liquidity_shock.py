# [2026-05-30] 新增：极端流动性冲击压力测试 — 模拟连续跌停，测试纯防御缩仓速度
"""
用 2015 股灾和 2020 新冠的断层下跌模式，构造连续 3-5 天接近跌停场景，
测试纯防御在极端日的缩仓速度、峰值风险暴露。
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFENSE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010",
}
OFFENSE_MAP = {
    "消费ETF": "159928", "医药ETF": "512010", "证券ETF": "512880",
    "有色ETF": "512400", "科技ETF": "515000", "军工ETF": "512660",
}


def build_gap_down_prices(
    base_prices: pd.DataFrame,
    n_shock_days: int = 5,
    daily_drop: float = 0.07,
    seed: int = 42,
) -> pd.DataFrame:
    """在基准价格末尾追加连续断层下跌日。

    base_prices: 冲击前的正常 OHLC 价格。
    n_shock_days: 断层下跌天数。
    daily_drop: 每日跌幅（如 0.07 = 7%）。
    返回拼接后的完整价格 DataFrame。
    """
    if daily_drop <= 0:
        raise ValueError(f"daily_drop 必须 > 0，实际 {daily_drop}")
    if daily_drop >= 1.0:
        raise ValueError(f"daily_drop 必须 < 1.0，实际 {daily_drop}")

    rng = np.random.RandomState(seed)
    last_close = base_prices["close"].iloc[-1]
    hlc = np.median(base_prices["high"] / base_prices["close"])
    llc = np.median(base_prices["low"] / base_prices["close"])
    olc = np.median(base_prices["open"] / base_prices["close"])

    last_date = base_prices.index[-1]
    shock_rows = []
    current_close = last_close

    for i in range(n_shock_days):
        # 每日跌幅含随机噪声，±2%
        actual_drop = daily_drop + rng.uniform(-0.02, 0.02)
        actual_drop = max(0.001, actual_drop)  # 防止负跌幅
        prev_close = current_close
        current_close = prev_close * (1 - actual_drop)
        shock_date = last_date + pd.Timedelta(days=i + 1)
        # 绕过周末
        while shock_date.weekday() >= 5:
            shock_date += pd.Timedelta(days=1)

        shock_rows.append({
            "open": prev_close * olc * (1 - actual_drop * 0.5),  # 开盘已低开
            "high": max(prev_close * olc * (1 - actual_drop * 0.3), current_close * hlc),
            "low": min(current_close * llc, prev_close * 0.85),
            "close": current_close,
        })

    result = pd.concat([base_prices, pd.DataFrame(shock_rows, index=pd.DatetimeIndex([
        base_prices.index[-1] + pd.Timedelta(days=i + 1)
        for i in range(n_shock_days)
    ]))])
    return result


def compute_exposure_timeline(
    prices: pd.DataFrame,
    positions: dict[str, float],
) -> pd.Series:
    """给定持仓和价格，计算每日风险暴露序列。"""
    exposure = pd.Series(0.0, index=prices.index)
    for name, shares in positions.items():
        if name in prices.columns or name == "asset":
            col = "close" if "close" in prices.columns else name
            if col in prices.columns:
                exposure += shares * prices[col]
            elif name in prices:
                # multi-column df with asset names
                pass
    return exposure


def count_whipsaws(records: pd.DataFrame) -> int:
    """统计 defense_active 字段切换次数。"""
    if "defense_active" not in records.columns or len(records) < 2:
        return 0
    active = records["defense_active"].values
    whips = 0
    for i in range(1, len(active)):
        if active[i] != active[i - 1]:
            whips += 1
    return whips


def main():
    print("=" * 80)
    print("极端场景压力测试 — 2b: 极端流动性冲击（连续断层下跌）")
    print("=" * 80)

    prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df

    # 用近期一段正常数据作为冲击前的基准
    template = prices.get("沪深300")
    if template is None:
        print("错误：缺少沪深300 价格数据")
        return

    # 取一段相对平稳的数据作为冲击前背景（约 250 天）
    base_period = template.iloc[-250:].copy()
    base_period.index = pd.bdate_range("2021-01-04", periods=len(base_period))

    print(f"\n基准期：{base_period.index[0].date()} ~ {base_period.index[-1].date()}（{len(base_period)} 天）")

    # 对每个 ETF 构造冲击后价格
    for scenario_name, n_shock, daily_drop in [
        ("2015股灾式", 5, 0.07),
        ("2020新冠式", 3, 0.05),
    ]:
        print(f"\n{'─' * 60}")
        print(f"  场景：{scenario_name}（连续 {n_shock} 天，日均跌 {daily_drop:.0%}）")
        print(f"{'─' * 60}")

        shock_prices = {}
        for name, df in prices.items():
            # 用该 ETF 的最后 250 天做基准
            base = df.iloc[-250:].copy()
            base.index = base_period.index[:len(base)]
            shock_prices[name] = build_gap_down_prices(
                base, n_shock_days=n_shock, daily_drop=daily_drop, seed=42
            )

        params = {
            "trend_window": 40,
            "ewma_lambda": 0.94,
            "target_vol_beta": 0.10,
            "defense_ratio": 1.0,
            "vol_scaling_enabled": True,
        }
        result = run_backtest(
            prices=shock_prices,
            initial_capital=1_000_000,
            params=params,
            min_days=120,
        )
        records = result["records_df"]

        # 冲击日分析
        shock_start_idx = len(records) - n_shock - 5  # 冲击前 5 天开始看
        if shock_start_idx < 0:
            shock_start_idx = 0

        shock_window = records.iloc[shock_start_idx:]
        print(f"\n{'日期':<14} {'风险暴露':>12} {'drawdown':>10} {'信号状态':>10}")
        print(f"{'─' * 50}")

        peak_exposure = 0
        peak_dd = 0
        for idx, row in shock_window.iterrows():
            exposure = row["exposure"]
            dd = row["drawdown"]
            level = row["drawdown_level"]
            peak_exposure = max(peak_exposure, exposure)
            peak_dd = min(peak_dd, dd)
            print(f"{str(idx.date()):<14} {exposure:>12,.0f} {dd:>10.2%} {str(level):>10}")

        # 冲击本身的每日明细
        print(f"\n冲击日逐日明细：")
        shock_only = records.iloc[-n_shock:]
        print(f"{'天数':<10} {'风险暴露':>12} {'drawdown':>10} {'信号状态':>10}")
        print(f"{'─' * 50}")
        for i, (idx, row) in enumerate(shock_only.iterrows(), 1):
            print(f"第{i}天{'':<6} {row['exposure']:>12,.0f} {row['drawdown']:>10.2%} {str(row['drawdown_level']):>10}")

        print(f"\n  峰值风险暴露：{peak_exposure:,.0f}")
        print(f"  峰值 drawdown：{peak_dd:.2%}")
        # 缩仓速度
        if len(shock_only) >= 2:
            first_exp = shock_only["exposure"].iloc[0]
            last_exp = shock_only["exposure"].iloc[-1]
            if first_exp > 0:
                reduction = (first_exp - last_exp) / first_exp
                print(f"  缩仓比例（首日→末日）：{reduction:.1%}")

        records.to_csv(
            os.path.join(OUTPUT_DIR, f"records_stress_liquidity_{scenario_name}.csv")
        )

    print(f"\n=== 2b 极端流动性冲击压力测试完成 ===")


if __name__ == "__main__":
    main()
