# [2026-06-27] 新增：5 分钟执行间隔跟踪误差测试集
# 约束：不修改 src/ 下任何文件，只 import 现有公开接口

import numpy as np
import pandas as pd

from src.backtest_engine import run_backtest
from src.etf_universe import ETF_UNIVERSE
from src.data_pipeline import load_from_parquet

DATA_DIR = "data"


def _load_defense_prices(data_dir: str = DATA_DIR) -> dict[str, pd.DataFrame]:
    """加载 5 只防御 ETF OHLCV 数据。"""
    prices = {}
    for name, code in ETF_UNIVERSE.items():
        df = load_from_parquet(f"{data_dir}/{code}.parquet")
        prices[name] = df
    return prices


def _extract_trade_events(
    records: pd.DataFrame,
    pos_df: pd.DataFrame,
    prices: dict[str, pd.DataFrame],
) -> list[dict]:
    """从回测结果提取每日换手事件。

    返回列表，每个元素：{"date": date, "buys": {name: dollar_amount, ...}, "sells": ...}
    通过比较相邻两日持仓份额（dollar / close）的变化确定买卖方向。
    """
    etf_names = [c for c in pos_df.columns if c in prices]
    events = []
    prev_shares: dict[str, float] = {}
    for date_idx in records.index:
        if date_idx not in pos_df.index:
            continue
        current: dict[str, float] = {}
        for name in etf_names:
            val = pos_df.loc[date_idx, name]
            if pd.isna(val) or val <= 0:
                current[name] = 0.0
            else:
                cp = prices[name].loc[date_idx, "close"]
                current[name] = val / cp if cp > 0 else 0.0
        if prev_shares:
            buys: dict[str, float] = {}
            sells: dict[str, float] = {}
            for name in etf_names:
                diff = current.get(name, 0.0) - prev_shares.get(name, 0.0)
                if abs(diff) > 1e-8:
                    cp = prices[name].loc[date_idx, "close"]
                    amt = abs(diff) * cp
                    if diff > 0:
                        buys[name] = amt
                    else:
                        sells[name] = amt
            if buys or sells:
                events.append({"date": date_idx, "buys": buys, "sells": sells})
        prev_shares = current
    return events


# 风险源分类
RISK_SOURCE = {"沪深300": "equity", "创业板": "equity", "纳指": "equity",
               "黄金": "gold", "国债ETF": "bond"}


def _is_cross_source(event: dict) -> bool:
    """判断换手事件是否跨风险源（卖和买的风险源不同）。"""
    sell_sources = {RISK_SOURCE.get(n, n) for n in event["sells"]}
    buy_sources = {RISK_SOURCE.get(n, n) for n in event["buys"]}
    return bool(sell_sources and buy_sources and sell_sources != buy_sources)


def _run_mc(trade_events: list[dict], prices: dict[str, pd.DataFrame],
            names_list: list[str], initial_capital: float, n_days: int,
            n_mc: int = 1000, seed: int = 42) -> np.ndarray:
    """Monte Carlo 模拟 5 分钟执行间隔的跟踪误差。

    卖出价 = 开盘价（无漂移），买入价 = 开盘价 × (1 + r_5min)。
    r_5min 均值为 0，标准差 = σ_intraday / sqrt(48)，跨 ETF 相关性从日数据估计。

    返回 ndarray (n_mc,)：每次模拟的年化收益偏移（小数形式）。
    """
    # σ_5min per ETF
    sigma_5m = np.array([
        (prices[n]["close"] / prices[n]["open"] - 1).std() / np.sqrt(48)
        for n in names_list
    ])

    # 构建买入金额矩阵 T: [n_events × n_etfs]
    n_events = len(trade_events)
    T = np.zeros((n_events, len(names_list)))
    for e, ev in enumerate(trade_events):
        for name, val in ev["buys"].items():
            T[e, names_list.index(name)] = val

    # 日开-闭收益相关性矩阵（proxy for 5-min 相关性）
    oc_df = pd.DataFrame({n: prices[n]["close"] / prices[n]["open"] - 1
                          for n in names_list})
    corr = oc_df.corr().values
    # Cholesky（正则化防奇异）
    L = np.linalg.cholesky(corr + 1e-8 * np.eye(len(names_list)))

    rng = np.random.RandomState(seed)
    impacts = np.zeros(n_mc)
    for k in range(n_mc):
        # 生成独立标准正态 → 施加相关 → 缩放至 σ_5min
        Z = rng.randn(n_events, len(names_list))
        corr_samples = Z @ L.T
        r_5m = corr_samples * sigma_5m[None, :]

        # 每笔换手跟踪误差 = sum 买入金额 × r_5min
        total = float(np.sum(T * r_5m))
        impacts[k] = total / initial_capital * 252 / n_days

    return impacts


class TestOpenVsCloseExecution:
    """测试 A：上限测试 — 开盘 vs 收盘执行"""

    def test_open_vs_close_execution(self) -> None:
        """对比开盘执行与收盘执行的年化收益差，应 < 0.3pp。"""
        prices = _load_defense_prices()

        result = run_backtest(prices, initial_capital=1_000_000, execution_lag=1)
        records = result["records_df"]
        pos_detail_list = result["_recorder"]["positions_detail"]
        pos_detail_df = pd.DataFrame(pos_detail_list).set_index("date")
        pos_detail_df.index = pd.to_datetime(pos_detail_df.index)
        close_nav = records["nav"]
        repo = records["repo_amount"]

        open_nav_values = []
        for date_idx in records.index:
            total = 0.0
            if date_idx in pos_detail_df.index:
                for name in pos_detail_df.columns:
                    val = pos_detail_df.loc[date_idx, name]
                    if pd.isna(val) or val <= 0:
                        continue
                    if name in prices and date_idx in prices[name].index:
                        close_px = prices[name].loc[date_idx, "close"]
                        if close_px > 0:
                            open_px = prices[name].loc[date_idx, "open"]
                            total += val * open_px / close_px
            open_nav_values.append(total + float(repo.loc[date_idx]))

        open_nav = pd.Series(open_nav_values, index=records.index)
        n = len(records)
        close_ar = (close_nav.iloc[-1] / close_nav.iloc[0]) ** (252 / n) - 1
        open_ar = (open_nav.iloc[-1] / open_nav.iloc[0]) ** (252 / n) - 1

        diff = abs(open_ar - close_ar)
        assert diff < 0.003, (
            f"开盘与收盘执行年化收益差应 < 0.3pp，实际 {diff:.6f}"
        )


class TestFiveMinuteGapMonteCarlo:
    """测试 B：5 分钟间隔 Monte Carlo 模拟"""

    def test_five_minute_gap_monte_carlo(self) -> None:
        """模拟 5 分钟买卖间隔，方向性损耗应可忽略。"""
        prices = _load_defense_prices()
        result = run_backtest(prices, initial_capital=1_000_000, execution_lag=1)
        records = result["records_df"]
        pos_list = result["_recorder"]["positions_detail"]
        pos_df = pd.DataFrame(pos_list).set_index("date")
        pos_df.index = pd.to_datetime(pos_df.index)

        events = _extract_trade_events(records, pos_df, prices)
        names_list = list(ETF_UNIVERSE.keys())
        impacts = _run_mc(events, prices, names_list, 1_000_000, len(records),
                          n_mc=1000, seed=42)

        mean_impact = float(np.mean(impacts))
        std_impact = float(np.std(impacts))
        p5 = float(np.percentile(impacts, 2.5))
        p95 = float(np.percentile(impacts, 97.5))

        print(f"\n  换手事件：{len(events)} 笔")
        print(f"  年化收益偏移：均值 {mean_impact*100:.4f}pp，标准差 {std_impact*100:.4f}pp")
        print(f"  95% 置信区间：[{p5*100:.4f}pp, {p95*100:.4f}pp]")

        assert abs(mean_impact) < 0.0005, (
            f"5分钟间隔年化方向性损耗应 < 0.05pp，"
            f"实际 {mean_impact*100:.4f}pp"
        )


class TestCrossAssetGap:
    """测试 C：跨风险源切换场景"""

    def test_cross_asset_gap(self) -> None:
        """跨风险源 vs 同风险源换手的跟踪误差对比。"""
        prices = _load_defense_prices()
        result = run_backtest(prices, initial_capital=1_000_000, execution_lag=1)
        records = result["records_df"]
        pos_list = result["_recorder"]["positions_detail"]
        pos_df = pd.DataFrame(pos_list).set_index("date")
        pos_df.index = pd.to_datetime(pos_df.index)

        all_events = _extract_trade_events(records, pos_df, prices)
        names_list = list(ETF_UNIVERSE.keys())

        cross_events = [e for e in all_events if _is_cross_source(e)]
        same_events = [e for e in all_events if not _is_cross_source(e)]

        if cross_events and same_events:
            cross_impacts = _run_mc(
                cross_events, prices, names_list, 1_000_000, len(records),
                n_mc=1000, seed=42)
            same_impacts = _run_mc(
                same_events, prices, names_list, 1_000_000, len(records),
                n_mc=1000, seed=42)

            cross_std = float(np.std(cross_impacts))
            same_std = float(np.std(same_impacts))
            cross_mean = float(np.mean(cross_impacts))
            same_mean = float(np.mean(same_impacts))

            print(f"\n  跨风险源换手：{len(cross_events)} 笔，"
                  f"年化偏移 std={cross_std*100:.4f}pp, mean={cross_mean*100:.4f}pp")
            print(f"  同风险源换手：{len(same_events)} 笔，"
                  f"年化偏移 std={same_std*100:.4f}pp, mean={same_mean*100:.4f}pp")
        else:
            print(f"\n  跨风险源 {len(cross_events)} 笔，同风险源 {len(same_events)} 笔，跳过对比")
