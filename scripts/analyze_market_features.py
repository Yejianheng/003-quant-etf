# [2026-05-29] 新增：步骤2 — 市场环境特征提取，对跑赢/跑输时段做特征画像

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")
DATA_DIR = os.path.join(BASE, "data")


def load_hs300_prices() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, "510300.parquet")
    return pd.read_parquet(path)


def load_offense_prices() -> dict[str, pd.DataFrame]:
    codes = {
        "512690": "消费ETF", "159992": "医药ETF", "512880": "证券ETF",
        "512400": "有色ETF", "512480": "科技ETF", "512660": "军工ETF",
    }
    prices = {}
    for code, name in codes.items():
        path = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(path):
            prices[name] = pd.read_parquet(path)
    return prices


def load_records() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "records_纯进攻.csv")
    return pd.read_csv(path, index_col=0, parse_dates=True)


def load_regimes() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "offense_vs_defense_regimes.csv")
    return pd.read_csv(path)


def compute_trend_direction(prices: pd.DataFrame, window: int = 60) -> pd.Series:
    ma = prices["close"].rolling(window).mean()
    trend = (prices["close"] - ma) / ma
    return trend.rename("trend_direction")


def compute_market_volatility(prices: pd.DataFrame, window: int = 60) -> pd.Series:
    returns = prices["close"].pct_change()
    vol = returns.rolling(window).std() * np.sqrt(252)
    return vol.rename("market_volatility")


def extract_offense_counts(records: pd.DataFrame) -> pd.Series:
    def parse_count(val):
        if pd.isna(val) or str(val).strip() == "":
            return 0
        return len(str(val).split(";"))
    return records["offense_top"].apply(parse_count).rename("offense_count")


def extract_defense_counts(records: pd.DataFrame) -> pd.Series:
    def parse_count(val):
        if pd.isna(val) or str(val).strip() == "":
            return 0
        return len(str(val).split(";"))
    return records["defense_active"].apply(parse_count).rename("defense_count")


def compute_correlation_matrix(offense_prices: dict[str, pd.DataFrame]) -> pd.Series:
    daily_returns = {}
    for name, df in offense_prices.items():
        daily_returns[name] = df["close"].pct_change()
    returns_df = pd.DataFrame(daily_returns).dropna()

    rolling_corr = returns_df.rolling(60).corr().dropna()
    dates = rolling_corr.index.get_level_values(0).unique()
    avg_corr = pd.Series(np.nan, index=dates, name="avg_correlation")
    for d in dates:
        try:
            mat = rolling_corr.loc[d]
            n = len(mat)
            if n > 1:
                upper = mat.values[np.triu_indices(n, k=1)]
                avg_corr.loc[d] = np.nanmean(upper)
        except Exception:
            pass
    return avg_corr.dropna()


def aggregate_regime_features(
    regimes: list[dict],
    feature_map: dict[str, pd.Series],
) -> list[dict]:
    rows = []
    for r in regimes:
        start, end = r["start"], r["end"]
        row = {
            "start": str(start)[:10],
            "end": str(end)[:10],
            "regime": r["regime"],
            "mean_excess": r["mean_excess"],
        }
        for name, series in feature_map.items():
            window = series.loc[start:end]
            if len(window) > 0:
                row[f"{name}_mean"] = float(window.mean())
        rows.append(row)
    return rows


def compute_feature_table(
    regimes_df: pd.DataFrame,
    hs300: pd.DataFrame,
    records: pd.DataFrame,
    offense_prices: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    trend = compute_trend_direction(hs300)
    vol = compute_market_volatility(hs300)
    offense_cnt = extract_offense_counts(records)
    defense_cnt = extract_defense_counts(records)
    avg_corr = compute_correlation_matrix(offense_prices)

    feature_map = {
        "trend": trend,
        "volatility": vol,
        "offense_count": offense_cnt,
        "defense_count": defense_cnt,
        "avg_correlation": avg_corr,
    }

    regimes = []
    for _, row in regimes_df.iterrows():
        regimes.append({
            "start": pd.Timestamp(row["开始"]),
            "end": pd.Timestamp(row["结束"]),
            "regime": "outperform" if row["类型"] == "进攻跑赢" else "underperform",
            "mean_excess": row["均值超额"],
        })

    rows = aggregate_regime_features(regimes, feature_map)
    return pd.DataFrame(rows)


def main():
    print("=== Step 2: Market Regime Feature Extraction ===\n")

    print("[1/4] Loading data...")
    hs300 = load_hs300_prices()
    records = load_records()
    offense_prices = load_offense_prices()
    regimes_df = load_regimes()
    print(f"  HS300: {len(hs300)} days, Records: {len(records)} days, "
          f"Offense ETFs: {len(offense_prices)}, Regimes: {len(regimes_df)}")

    print("\n[2/4] Computing features...")
    ft = compute_feature_table(regimes_df, hs300, records, offense_prices)

    print("\n[3/4] Outperform vs Underperform summary:")
    out = ft[ft["regime"] == "outperform"]
    under = ft[ft["regime"] == "underperform"]

    print(f"\n  {'Feature':<22} {'Outperform':>12} {'Underperform':>12} {'Diff':>12}")
    print("  " + "-" * 60)
    feat_cols = [c for c in ft.columns if c.endswith("_mean")]
    for col in feat_cols:
        name = col.replace("_mean", "")
        o_mean = out[col].mean() if len(out) > 0 else 0
        u_mean = under[col].mean() if len(under) > 0 else 0
        diff_val = o_mean - u_mean
        print(f"  {name:<22} {o_mean:>12.4f} {u_mean:>12.4f} {diff_val:>+12.4f}")

    ft_path = os.path.join(OUTPUT_DIR, "regime_features.csv")
    ft.to_csv(ft_path, index=False)
    print(f"\n  Feature table saved to {ft_path}")

    print("\n[4/4] Per-regime details:")
    print(f"\n  {'Start':>12} {'End':>12} {'Regime':>8} {'Excess':>8} "
          f"{'Trend':>8} {'Vol':>8} {'OffCnt':>6} {'DefCnt':>6} {'Corr':>8}")
    print("  " + "-" * 85)
    for _, r in ft.iterrows():
        regime_label = "WIN" if r["regime"] == "outperform" else "LOSE"
        print(f"  {r['start']:>12} {r['end']:>12} {regime_label:>8} {r['mean_excess']:>7.1%} "
              f"{r['trend_mean']:>7.3f} {r['volatility_mean']:>7.3f} "
              f"{r['offense_count_mean']:>5.1f} {r['defense_count_mean']:>5.1f} "
              f"{r['avg_correlation_mean']:>7.3f}")

    print("\n=== Step 2 Complete ===")


if __name__ == "__main__":
    main()
