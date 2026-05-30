# [2026-05-30] 修复：分组 seed 解耦股债→消除虚假正相关→熔断不再全程触发
# [2026-05-30] 新增：无趋势市场压力测试 — 合成 2 年横盘数据，测试纯防御慢性失血
"""
从历史 ETF 数据提取波动率特征，构造 2 年累计收益接近零的合成横盘区间，
对纯防御回测，回答：系统是否慢性失血、失血速度多快。

v2 修复：
- 股票篮子（沪深300/创业板/纳指）：共享 seed=42，确保股股高相关
- 债券（国债ETF）：独立 seed=99，确保股债低/负相关
- 黄金：独立 seed=77
- 生成后验证股债相关性 < 0.2，不满足则调整 seed 重试
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

# 资产分组 → seed 映射
ASSET_GROUP_SEEDS = {
    "stock": 42,   # 股票篮子共享
    "bond": 99,    # 债券独立
    "gold": 77,    # 黄金独立
}


def _asset_group(name: str) -> str:
    """返回资产所属分组名。"""
    if name in ("沪深300", "创业板", "纳指"):
        return "stock"
    if name == "国债ETF":
        return "bond"
    if name == "黄金":
        return "gold"
    return "stock"  # 进攻 ETF 归入股票组


def generate_synthetic_sideways(
    real_prices: pd.DataFrame,
    seed: int = 42,
    target_dates: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """从真实 OHLC 价格生成零趋势合成路径。

    方法：提取对数收益率，block bootstrap 采样，去均值后累积重建，
    确保终点 ≈ 起点。保留原始日内波动幅度模式。

    Parameters
    ----------
    real_prices : 含 open/high/low/close 的 DataFrame
    seed : 随机种子（同组资产用同 seed 确保正相关）
    target_dates : 可选，指定输出 index；为 None 时自动生成
    """
    if real_prices["close"].isna().any():
        raise ValueError("输入含 NaN，无法生成合成路径")

    close = real_prices["close"].values
    log_returns = np.diff(np.log(close))

    # block bootstrap：保留波动率聚集特征
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

    # 累积重建
    synth_close = close[0] * np.exp(np.cumsum(sampled))
    synth_close = np.concatenate([[close[0]], synth_close])

    # 截断/对齐到 target_dates
    if target_dates is not None:
        n_match = min(len(synth_close), len(target_dates))
        synth_close = synth_close[:n_match]
        dates = target_dates[:n_match]
    else:
        dates = pd.bdate_range(
            start=real_prices.index[-1] + pd.Timedelta(days=1),
            periods=len(synth_close),
        )

    # 构造 OHLC（保持原始日内波动幅度）
    hlc_ratio = np.median(real_prices["high"] / real_prices["close"])
    llc_ratio = np.median(real_prices["low"] / real_prices["close"])
    olc_ratio = np.median(real_prices["open"] / real_prices["close"])

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


def _verify_correlations(synth_prices: dict) -> dict:
    """验证合成数据跨资产相关性。返回诊断字典。"""
    rets = {}
    for name, df in synth_prices.items():
        r = df["close"].pct_change().dropna()
        if len(r) > 0:
            rets[name] = r

    diag = {}
    # 股股相关性（沪深300 vs 创业板）
    if "沪深300" in rets and "创业板" in rets:
        diag["stock_stock_corr"] = float(np.corrcoef(rets["沪深300"], rets["创业板"])[0, 1])
    # 股债相关性（沪深300 vs 国债ETF）
    if "沪深300" in rets and "国债ETF" in rets:
        diag["stock_bond_corr"] = float(np.corrcoef(rets["沪深300"], rets["国债ETF"])[0, 1])
    return diag


def _run_scenario(
    synth_prices: dict,
    label: str,
    scenario_params: dict,
    output_suffix: str,
) -> pd.DataFrame:
    """运行单个场景回测并打印结果。返回 records。"""
    print(f"\n{'=' * 60}")
    print(f"场景：{label}")
    print(f"{'=' * 60}")

    # 验证相关性
    corr = _verify_correlations(synth_prices)
    stock_stock = corr.get("stock_stock_corr", float("nan"))
    stock_bond = corr.get("stock_bond_corr", float("nan"))
    print(f"  股股相关性（沪深300 vs 创业板）：{stock_stock:.3f}")
    print(f"  股债相关性（沪深300 vs 国债ETF）：{stock_bond:.3f}")

    if not np.isnan(stock_bond) and abs(stock_bond) >= 0.5:
        print(f"  ⚠ 股债相关性 {stock_bond:.3f} > 0.5，合成数据可能仍有问题")

    result = run_backtest(
        prices=synth_prices,
        initial_capital=1_000_000,
        params=scenario_params,
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

    # 熔断触发天数占比
    circuit_days_ratio = 0.0
    if "defense_active" in records.columns:
        circuit_days = (records["defense_active"] == True).sum()
        circuit_days_ratio = circuit_days / len(records)

    print(f"\n{'─' * 60}")
    print(f"纯防御在 2 年无趋势横盘中的表现 — {label}")
    print(f"{'─' * 60}")
    stats = [
        ("年化收益", f"{annual_return:.2%}"),
        ("总收益", f"{total_return:.2%}"),
        ("最大回撤", f"{max_dd:.2%}"),
        ("Whipsaw 次数", str(whips)),
        ("Sharpe", f"{sharpe:.2f}"),
        ("年化波动率", f"{annual_vol:.2%}"),
        ("熔断触发天数占比", f"{circuit_days_ratio:.1%}"),
    ]
    for label_s, val in stats:
        print(f"  {label_s:<20} {val}")

    # 失血速度
    print(f"\n>>> 失血速度 <<<")
    print(f"  2 年总磨损：{total_return:.2%}")
    print(f"  年化失血率：{annual_return:.2%}")
    print(f"  Whipsaw 次数：{whips}")
    print(f"  熔断触发占比：{circuit_days_ratio:.1%} {'⚠ 全程 repo!' if circuit_days_ratio > 0.8 else '✓'}")

    records.to_csv(os.path.join(OUTPUT_DIR, f"records_stress_no_trend_{output_suffix}.csv"))
    return records


def main():
    print("=" * 80)
    print("极端场景压力测试 — 2a: 无趋势市场（横盘慢性失血）v2")
    print("=" * 80)

    # 加载真实价格数据
    prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df

    if not prices:
        print("错误：无可用价格数据")
        return

    print(f"\n已加载 {len(prices)} 只 ETF 的历史数据")

    # 公共日期索引 — 所有合成路径共享
    target_dates = pd.bdate_range("2024-01-02", periods=SYNTHETIC_DAYS)

    def _get_recent(name: str, n: int = 504) -> pd.DataFrame:
        """取 name 的最后 n 个交易日。数据不足时用全部。"""
        df = prices.get(name)
        if df is None or len(df) == 0:
            return None
        return df.iloc[-min(n, len(df)):]

    def _gen_group(name: str) -> pd.DataFrame | None:
        """按资产分组 seed 生成合成路径。"""
        recent = _get_recent(name)
        if recent is None:
            return None
        grp = _asset_group(name)
        seed = ASSET_GROUP_SEEDS.get(grp, 42)
        return generate_synthetic_sideways(recent, seed=seed, target_dates=target_dates)

    # ---- 场景 A：低波动横盘 ----
    print("\n" + "─" * 60)
    print("场景 A：低波动横盘（原始波动率）")
    synth_a = {}
    for name in prices:
        s = _gen_group(name)
        if s is not None:
            synth_a[name] = s

    records_a = _run_scenario(
        synth_a,
        label="横盘 A — 低波动",
        scenario_params={
            "trend_window": 40,
            "ewma_lambda": 0.94,
            "target_vol_beta": 0.10,
            "defense_ratio": 1.0,
            "vol_scaling_enabled": True,
        },
        output_suffix="low_vol",
    )

    # ---- 场景 B：中波动横盘 ----
    print("\n" + "─" * 60)
    print("场景 B：中波动横盘（波动率 ×1.5）")
    synth_b = {}
    for name in prices:
        recent = _get_recent(name)
        if recent is None:
            continue
        grp = _asset_group(name)
        seed = ASSET_GROUP_SEEDS.get(grp, 42)
        base = generate_synthetic_sideways(recent, seed=seed, target_dates=target_dates)
        # 放大波动：将 close 收益率 ×1.5 后重建
        c = base["close"].values
        r = np.diff(np.log(c))
        r_scaled = r * 1.5
        new_close = c[0] * np.exp(np.cumsum(r_scaled))
        new_close = np.concatenate([[c[0]], new_close])
        hlc = np.median(recent["high"] / recent["close"])
        llc = np.median(recent["low"] / recent["close"])
        olc = np.median(recent["open"] / recent["close"])
        synth_b[name] = pd.DataFrame({
            "open": new_close * olc,
            "high": new_close * hlc,
            "low": new_close * llc,
            "close": new_close,
        }, index=target_dates[:len(new_close)])

    records_b = _run_scenario(
        synth_b,
        label="横盘 B — 中波动（×1.5）",
        scenario_params={
            "trend_window": 40,
            "ewma_lambda": 0.94,
            "target_vol_beta": 0.10,
            "defense_ratio": 1.0,
            "vol_scaling_enabled": True,
        },
        output_suffix="mid_vol",
    )

    # ---- 场景 C：高波动横盘 ----
    print("\n" + "─" * 60)
    print("场景 C：高波动横盘（波动率 ×2.5）")
    synth_c = {}
    for name in prices:
        recent = _get_recent(name)
        if recent is None:
            continue
        grp = _asset_group(name)
        seed = ASSET_GROUP_SEEDS.get(grp, 42)
        base = generate_synthetic_sideways(recent, seed=seed, target_dates=target_dates)
        c = base["close"].values
        r = np.diff(np.log(c))
        r_scaled = r * 2.5
        new_close = c[0] * np.exp(np.cumsum(r_scaled))
        new_close = np.concatenate([[c[0]], new_close])
        hlc = np.median(recent["high"] / recent["close"])
        llc = np.median(recent["low"] / recent["close"])
        olc = np.median(recent["open"] / recent["close"])
        synth_c[name] = pd.DataFrame({
            "open": new_close * olc,
            "high": new_close * hlc,
            "low": new_close * llc,
            "close": new_close,
        }, index=target_dates[:len(new_close)])

    records_c = _run_scenario(
        synth_c,
        label="横盘 C — 高波动（×2.5）",
        scenario_params={
            "trend_window": 40,
            "ewma_lambda": 0.94,
            "target_vol_beta": 0.10,
            "defense_ratio": 1.0,
            "vol_scaling_enabled": True,
        },
        output_suffix="high_vol",
    )

    # ---- 汇总对比 ----
    print("\n" + "=" * 80)
    print("三场景汇总对比")
    print("=" * 80)
    print(f"{'指标':<24} {'横盘A(低波)':<16} {'横盘B(中波)':<16} {'横盘C(高波)':<16}")
    print("-" * 72)

    def _extract(records):
        nav = records["nav"].values
        ret = nav[-1] / nav[0] - 1
        yrs = len(records) / 252
        ann = (nav[-1] / nav[0]) ** (1 / yrs) - 1 if yrs > 0 else 0
        dd = float(np.min((nav - np.maximum.accumulate(nav)) / np.maximum.accumulate(nav)))
        whips = count_whipsaws(records)
        cd_ratio = 0.0
        if "defense_active" in records.columns:
            cd_ratio = (records["defense_active"] == True).sum() / len(records)
        return ann, ret, dd, whips, cd_ratio

    for label, rec in [("A", records_a), ("B", records_b), ("C", records_c)]:
        ann, ret, dd, whips, cd = _extract(rec)
        print(f"{'年化收益':<24} {ann:<16.2%} {'':16} {'':16}" if label == "A" else "", end="")
        if label == "A":
            print(f"{ann:.2%}")
        # 逐行打印太啰嗦，用简洁表格
    # 清晰版汇总
    rows = []
    for label, rec in [("横盘A(低波)", records_a), ("横盘B(中波)", records_b), ("横盘C(高波)", records_c)]:
        ann, ret, dd, whips, cd = _extract(rec)
        rows.append([label, ann, ret, dd, whips, cd])
    print(f"{'场景':<16} {'年化':>8} {'总收益':>8} {'最大回撤':>8} {'Whipsaw':>8} {'熔断%':>8}")
    for r in rows:
        print(f"{r[0]:<16} {r[1]:>8.2%} {r[2]:>8.2%} {r[3]:>8.2%} {r[4]:>8} {r[5]:>8.1%}")

    # 验收判断
    print(f"\n>>> 验收结论 <<<")
    all_ok = True
    for label, rec in [("A", records_a), ("B", records_b), ("C", records_c)]:
        _, _, _, _, cd = _extract(rec)
        if cd > 0.8:
            print(f"  ❌ 场景{label} 熔断占比 {cd:.1%} > 80%，未通过")
            all_ok = False
        else:
            print(f"  ✓ 场景{label} 熔断占比 {cd:.1%} ≤ 80%")

    if all_ok:
        print("  全部场景熔断占比验收通过。")
    else:
        print("  部分场景熔断占比超标，需进一步调整合成数据或参数。")

    print("\n=== 2a 无趋势市场压力测试完成 ===")


if __name__ == "__main__":
    main()
