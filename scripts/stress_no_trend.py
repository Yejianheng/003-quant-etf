# [2026-05-30] 新增：无趋势市场压力测试 — 合成 2 年横盘数据，测试纯防御慢性失血
"""
从历史 ETF 数据提取波动率特征，构造 2 年累计收益接近零的合成横盘区间，
对纯防御回测，回答：系统是否慢性失血、失血速度多快。
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

SYNTHETIC_YEARS = 2
SYNTHETIC_DAYS = SYNTHETIC_YEARS * 252


def generate_synthetic_sideways(
    real_prices: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """从真实 OHLC 价格生成零趋势合成路径。

    方法：提取对数收益率，去均值后累积重建，确保终点 ≈ 起点。
    保留原始日内波动幅度模式（high/low vs close 比例）。
    """
    if real_prices["close"].isna().any():
        raise ValueError("输入含 NaN，无法生成合成路径")

    close = real_prices["close"].values
    log_returns = np.diff(np.log(close))

    # 自助采样（block bootstrap）：保留波动率聚集特征
    rng = np.random.RandomState(seed)
    n_orig = len(log_returns)
    block_size = 5
    n_needed = len(real_prices) - 1  # 需要 n-1 个收益率

    sampled = []
    while len(sampled) < n_needed:
        start = rng.randint(0, max(n_orig - block_size, 1))
        sampled.extend(log_returns[start : start + block_size])
    sampled = np.array(sampled[:n_needed])

    # 附加小噪声使路径不完全复现
    noise_scale = np.std(log_returns) * 0.3
    sampled += rng.randn(len(sampled)) * noise_scale

    # 强制去均值 → 累计收益 ≈ 0
    sampled -= sampled.mean()

    # 累积重建（起始价 + 累积收益率）
    synth_close = close[0] * np.exp(np.cumsum(sampled))
    synth_close = np.concatenate([[close[0]], synth_close])

    # 构造 OHLC（保持原始日内波动幅度）
    n_total = len(synth_close)
    hlc_ratio = np.median(real_prices["high"] / real_prices["close"])
    llc_ratio = np.median(real_prices["low"] / real_prices["close"])
    olc_ratio = np.median(real_prices["open"] / real_prices["close"])

    dates = pd.bdate_range(
        start=real_prices.index[-1] + pd.Timedelta(days=1),
        periods=n_total,
    )
    df = pd.DataFrame({
        "open": synth_close * olc_ratio,
        "high": synth_close * hlc_ratio,
        "low": synth_close * llc_ratio,
        "close": synth_close,
    }, index=dates)
    return df


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
    print("极端场景压力测试 — 2a: 无趋势市场（横盘慢性失血）")
    print("=" * 80)

    prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df

    # 用沪深 300 作为波动率模板
    template = prices.get("沪深300")
    if template is None:
        print("错误：缺少沪深300 价格数据")
        return

    print(f"\n沪深300 作为波动率模板：{len(template)} 个交易日")

    # 用最后 2 年作为波动率参考
    recent = template.iloc[-504:]
    synth = generate_synthetic_sideways(recent, seed=42)

    # 构造完整合成价格字典：防御 ETF 用同一个合成价格（模拟系统性横盘），进攻 ETF 也相同
    synth_prices = {}
    for name in prices:
        synth_prices[name] = synth.copy()

    print(f"合成横盘区间：{synth.index[0].date()} ~ {synth.index[-1].date()}（{len(synth)} 天）")
    print(f"合成沪深300 累计收益：{synth['close'].iloc[-1] / synth['close'].iloc[0] - 1:.2%}")

    # 纯防御回测
    params = {
        "trend_window": 40,
        "ewma_lambda": 0.94,
        "target_vol_beta": 0.10,
        "defense_ratio": 1.0,
        "vol_scaling_enabled": True,
    }
    print("\n运行纯防御回测...")
    result = run_backtest(
        prices=synth_prices,
        initial_capital=1_000_000,
        params=params,
        min_days=120,
    )
    records = result["records_df"]

    nav = records["nav"].values
    total_return = nav[-1] / nav[0] - 1
    years = len(records) / 252
    annual_return = (nav[-1] / nav[0]) ** (1 / years) - 1 if years > 0 else 0
    daily_returns = np.diff(nav) / nav[:-1]
    annual_vol = float(np.std(daily_returns, ddof=1) * np.sqrt(252))
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    running_max = np.maximum.accumulate(nav)
    drawdowns = (nav - running_max) / running_max
    max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0
    whips = count_whipsaws(records)

    print(f"\n{'─' * 60}")
    print("纯防御在 2 年无趋势横盘中的表现")
    print(f"{'─' * 60}")
    stats = [
        ("年化收益", f"{annual_return:.2%}"),
        ("总收益", f"{total_return:.2%}"),
        ("最大回撤", f"{max_dd:.2%}"),
        ("Whipsaw 次数", str(whips)),
        ("Sharpe", f"{sharpe:.2f}"),
        ("年化波动率", f"{annual_vol:.2%}"),
    ]
    for label, val in stats:
        print(f"  {label:<16} {val}")

    # 结论
    print(f"\n>>> 无趋势横盘结论 <<<")
    if max_dd > -0.05 and sharpe > 0:
        print("  系统在横盘中基本不慢性失血，防御机制有效分辨无趋势环境。")
    elif max_dd > -0.10:
        print("  系统存在轻度慢性失血（年化 {:.1%}），波动主要来自 whipsaw 交易。".format(annual_return))
    else:
        print("  系统在横盘中慢性失血严重，需要关注趋势过滤机制是否过度敏感。")

    records.to_csv(os.path.join(OUTPUT_DIR, "records_stress_no_trend.csv"))
    print(f"\nrecords → {OUTPUT_DIR}/records_stress_no_trend.csv")
    print("=== 2a 无趋势市场压力测试完成 ===")


if __name__ == "__main__":
    main()
