"""
步骤 6：联合回测 + 三基准对比（强制输出）
使用真实 ETF 数据，跑三种配置，输出同期三基准对比表。
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")

# 防御层映射
DEFENSE_MAP = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

# 进攻层：6 只代表 ETF（风险源 → 代表 ETF）
OFFENSE_MAP = {
    "消费": "512690",
    "医药": "159992",
    "金融": "512880",
    "周期资源": "512400",
    "科技成长": "512480",
    "军工": "512660",
}


def load_prices(code: str) -> pd.DataFrame | None:
    """加载单只 ETF 数据。"""
    fpath = os.path.join(DATA_DIR, f"{code}.parquet")
    if not os.path.exists(fpath):
        return None
    df = pd.read_parquet(fpath)
    # 确保有 OHLCV 列
    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in df.columns:
            return None
    return df


def build_prices_dict(asset_map: dict[str, str]) -> dict[str, pd.DataFrame]:
    """加载数据 → {名称: OHLCV DataFrame}。"""
    prices = {}
    for name, code in asset_map.items():
        df = load_prices(code)
        if df is not None:
            prices[name] = df
        else:
            print(f"  缺少数据: {code} {name}")
    return prices


def compute_metrics(nav_series: pd.Series) -> dict:
    """计算绩效指标。"""
    if len(nav_series) < 2:
        return {}
    returns = nav_series.pct_change().dropna()
    annual_factor = 252
    total_return = (nav_series.iloc[-1] / nav_series.iloc[0]) - 1
    years = len(nav_series) / annual_factor
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    annual_vol = returns.std() * np.sqrt(annual_factor)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0

    # 最大回撤
    peak = nav_series.expanding().max()
    drawdown = (nav_series - peak) / peak
    max_dd = drawdown.min()

    return {
        "总收益": f"{total_return:.1%}",
        "年化": f"{annual_return:.1%}",
        "波动率": f"{annual_vol:.1%}",
        "Sharpe": f"{sharpe:.2f}",
        "最大回撤": f"{max_dd:.1%}",
    }


def compute_benchmark_nav(bench_name: str, dates: pd.DatetimeIndex, base_nav: float) -> pd.Series | None:
    """计算基准净值序列。"""
    bench_codes = {"沪深300": "510300", "创业板": "159915", "纳指": "513100"}
    code = bench_codes.get(bench_name)
    if not code:
        return None
    df = load_prices(code)
    if df is None:
        return None
    close = df["close"]
    common = dates.intersection(close.index)
    if len(common) < 2:
        return None
    close = close.loc[common].sort_index()
    nav = base_nav * close / close.iloc[0]
    return nav


def print_comparison_table(results: list[dict]):
    """打印同期三基准对比表。"""
    headers = ["指标", "策略", "沪深300", "创业板", "纳指"]
    col_widths = [10, 12, 12, 12, 12]
    sep = "+" + "+".join("-" * w for w in col_widths) + "+"

    for config in results:
        print(f"\n--- {config['label']} ---")
        print(sep)
        print("|" + "|".join(h.center(w) for h, w in zip(headers, col_widths)) + "|")
        print(sep)
        metrics = ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]
        for m in metrics:
            strategy_val = config["strategy"].get(m, "-")
            hs300_val = config["benchmarks"]["沪深300"].get(m, "-")
            cyb_val = config["benchmarks"]["创业板"].get(m, "-")
            ndx_val = config["benchmarks"]["纳指"].get(m, "-")
            row = [m, strategy_val, hs300_val, cyb_val, ndx_val]
            print("|" + "|".join(v.center(w) for v, w in zip(row, col_widths)) + "|")
        print(sep)


def main():
    print("=== 步骤 6：联合回测 + 三基准对比 ===\n")

    # 加载防御层数据
    print("[1/3] 加载防御层数据...")
    defense_prices = build_prices_dict(DEFENSE_MAP)
    for name, df in defense_prices.items():
        print(f"  {name}: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")

    # 加载进攻层数据
    print("\n[2/3] 加载进攻层数据...")
    offense_prices = build_prices_dict(OFFENSE_MAP)
    for name, df in offense_prices.items():
        print(f"  {name}: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")

    # 找共同日期范围
    all_dfs = list(defense_prices.values()) + list(offense_prices.values())
    date_sets = [set(df.index) for df in all_dfs]
    common_dates = sorted(set.intersection(*date_sets))
    print(f"\n共同交易日: {len(common_dates)} 天")
    print(f"回测区间: {common_dates[0].date()} ~ {common_dates[-1].date()}")
    years = len(common_dates) / 252
    print(f"约 {years:.1f} 年")

    # 对齐数据到共同日期
    for name in defense_prices:
        defense_prices[name] = defense_prices[name].loc[common_dates]
    for name in offense_prices:
        offense_prices[name] = offense_prices[name].loc[common_dates]

    # 三基准计算用数据
    bench_prices = {
        "沪深300": load_prices("510300"),
        "创业板": load_prices("159915"),
        "纳指": load_prices("513100"),
    }
    dates_idx = pd.DatetimeIndex(common_dates)

    # 三种配置
    configs = [
        ("纯防御", None, None),
        ("防御+进攻 K=3", 3, None),
        ("防御+进攻 K=2", 2, None),
    ]

    results = []
    print("\n[3/3] 运行回测...")

    for label, offense_k, _ in configs:
        print(f"\n{'='*60}")
        print(f"  配置: {label}")
        print(f"{'='*60}")

        if offense_k is None:
            # 纯防御：只用防御层数据
            prices = dict(defense_prices)
            params = {"offense_top_k": 3}
        else:
            # 防御 + 进攻
            prices = dict(defense_prices)
            prices.update(offense_prices)
            params = {"offense_top_k": offense_k}

        try:
            result = run_backtest(
                prices=prices,
                initial_capital=1_000_000,
                params=params,
                min_days=120,
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        # 策略指标
        records = result["records_df"]
        nav = records["nav"] if "nav" in records.columns else None
        if nav is None or len(nav) < 2:
            print("  无有效净值数据")
            continue

        strategy_metrics = compute_metrics(nav)
        print(f"  策略: 年化={strategy_metrics['年化']}, Sharpe={strategy_metrics['Sharpe']}, "
              f"最大回撤={strategy_metrics['最大回撤']}")

        # 三个基准
        bench_metrics = {}
        for bname in ["沪深300", "创业板", "纳指"]:
            bdf = bench_prices[bname]
            if bdf is not None:
                common = dates_idx.intersection(bdf.index)
                bclose = bdf.loc[common, "close"].sort_index()
                if len(bclose) > 1:
                    bnav = 1_000_000 * bclose / bclose.iloc[0]
                    bench_metrics[bname] = compute_metrics(bnav)
                    print(f"  {bname}: 年化={bench_metrics[bname]['年化']}, "
                          f"Sharpe={bench_metrics[bname]['Sharpe']}, "
                          f"最大回撤={bench_metrics[bname]['最大回撤']}")
                else:
                    bench_metrics[bname] = {}
            else:
                bench_metrics[bname] = {}

        results.append({
            "label": label,
            "strategy": strategy_metrics,
            "benchmarks": bench_metrics,
        })

    # 输出对比表
    if results:
        print("\n" + "=" * 60)
        print("  同期三基准对比表")
        print("=" * 60)
        print_comparison_table(results)
    else:
        print("\n无有效回测结果。")


if __name__ == "__main__":
    main()
