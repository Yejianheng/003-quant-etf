# [2026-05-29] 新增：震荡市 Whipsaw 专项分析

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")

WHIPSAW_WINDOW = 20  # 交易日内先入后出视为 whipsaw
DEFENSE_ETFS = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]

SHAKE_PERIODS = {
    "2016震荡": ("2016-02-01", "2016-12-31"),
    "2021H2震荡": ("2021-07-01", "2021-12-31"),
}


def parse_defense_etfs(s) -> list:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return []
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return []
    return [x.strip() for x in s.split(";") if x.strip()]


def detect_etf_flips(defense_series: pd.Series, etf_name: str) -> pd.DataFrame:
    mask = defense_series.apply(
        lambda s: etf_name in parse_defense_etfs(s)
    )
    changed = mask != mask.shift(1)
    changed.iloc[0] = False  # 首日不算翻转
    flip_idx = changed[changed].index

    events = []
    for dt in flip_idx:
        is_active = mask.loc[dt]
        events.append({
            "date": dt,
            "etf": etf_name,
            "event": "entry" if is_active else "exit",
        })
    return pd.DataFrame(events)


def classify_whipsaws(flips: pd.DataFrame, window: int = WHIPSAW_WINDOW) -> list:
    if len(flips) < 2:
        return []

    pairs = []
    i = 0
    while i < len(flips) - 1:
        a = flips.iloc[i]
        b = flips.iloc[i + 1]
        if a["event"] == "entry" and b["event"] == "exit":
            delta = (b["date"] - a["date"]).days
            if delta <= window:
                pairs.append({
                    "etf": a["etf"],
                    "entry_date": a["date"],
                    "exit_date": b["date"],
                    "hold_days": delta,
                    "type": "whipsaw",
                })
                i += 2
                continue
        i += 1

    return pairs


def build_whipsaw_detail(records: pd.DataFrame, nav: pd.Series,
                         start: str, end: str, window: int = WHIPSAW_WINDOW) -> pd.DataFrame:
    mask = (records.index >= pd.Timestamp(start)) & (records.index <= pd.Timestamp(end))
    rec_slice = records.loc[mask].copy()
    nav_slice = nav.loc[nav.index.isin(rec_slice.index)]

    if len(rec_slice) == 0:
        return pd.DataFrame()

    da_col = rec_slice["defense_active"].fillna("").astype(str)
    all_rows = []

    for etf in DEFENSE_ETFS:
        flips = detect_etf_flips(da_col, etf)
        pairs = classify_whipsaws(flips, window)

        for p in pairs:
            entry_dt = p["entry_date"]
            exit_dt = p["exit_date"]

            entry_nav = nav_slice.loc[entry_dt] if entry_dt in nav_slice.index else np.nan
            exit_nav = nav_slice.loc[exit_dt] if exit_dt in nav_slice.index else np.nan

            ret = None
            if not np.isnan(entry_nav) and not np.isnan(exit_nav) and entry_nav > 0:
                ret = exit_nav / entry_nav - 1

            # 恢复后重新进入该 ETF 的最短间隔
            all_rows.append({
                "regime": f"{start[:7]}→{end[:7]}",
                "etf": etf,
                "entry_date": entry_dt.strftime("%Y-%m-%d"),
                "exit_date": exit_dt.strftime("%Y-%m-%d"),
                "hold_days": p["hold_days"],
                "entry_nav": round(entry_nav, 2) if not np.isnan(entry_nav) else np.nan,
                "exit_nav": round(exit_nav, 2) if not np.isnan(exit_nav) else np.nan,
                "segment_return": round(ret, 6) if ret is not None else np.nan,
                "is_loss": (ret < 0) if ret is not None else False,
            })

    df = pd.DataFrame(all_rows)
    if len(df) > 0:
        df = df.sort_values(["regime", "etf", "entry_date"])
    return df


def compute_cumulative_wear(whipsaw_df: pd.DataFrame) -> dict:
    if len(whipsaw_df) == 0:
        return {
            "total_whipsaws": 0,
            "loss_count": 0,
            "cum_loss": 0.0,
            "avg_loss": 0.0,
            "worst_loss": 0.0,
        }

    loss_mask = whipsaw_df["is_loss"] == True
    losses = whipsaw_df.loc[loss_mask, "segment_return"].dropna()

    return {
        "total_whipsaws": len(whipsaw_df),
        "loss_count": loss_mask.sum(),
        "cum_loss": float(losses.sum()) if len(losses) > 0 else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) > 0 else 0.0,
        "worst_loss": float(losses.min()) if len(losses) > 0 else 0.0,
    }


def main():
    print("=" * 70)
    print("震荡市 Whipsaw 专项分析")
    print("=" * 70)

    nav_path = os.path.join(OUTPUT_DIR, "nav_纯防御.csv")
    rec_path = os.path.join(OUTPUT_DIR, "records_纯防御.csv")
    nav = pd.read_csv(nav_path, index_col=0, parse_dates=True).iloc[:, 0]
    records = pd.read_csv(rec_path, index_col=0, parse_dates=True)

    all_details = []
    print(f"\n{'ETF':<10} {'Regime':<18} {'Whipsaw':>8} {'亏损次':>8} "
          f"{'累计磨损':>10} {'最差单次':>10}")

    for regime_label, (start, end) in SHAKE_PERIODS.items():
        detail = build_whipsaw_detail(records, nav, start, end)
        all_details.append(detail)

        # 按 ETF 汇总
        for etf in DEFENSE_ETFS:
            etf_detail = detail[detail["etf"] == etf] if len(detail) > 0 else pd.DataFrame()
            wear = compute_cumulative_wear(etf_detail)
            if wear["total_whipsaws"] > 0:
                print(f"{etf:<10} {regime_label:<18} {wear['total_whipsaws']:>8d} "
                      f"{wear['loss_count']:>8d} {wear['cum_loss']:>9.3%} "
                      f"{wear['worst_loss']:>9.3%}")

        # 汇总该 regime
        regime_wear = compute_cumulative_wear(detail)
        print(f"{'[合计]':<10} {regime_label:<18} {regime_wear['total_whipsaws']:>8d} "
              f"{regime_wear['loss_count']:>8d} {regime_wear['cum_loss']:>9.3%} "
              f"{regime_wear['worst_loss']:>9.3%}")
        print()

    combined = pd.concat(all_details, ignore_index=True) if all_details else pd.DataFrame()
    out_path = os.path.join(OUTPUT_DIR, "regime_whipsaw_detail.csv")
    combined.to_csv(out_path, index=False)
    print(f"明细 → {out_path} ({len(combined)} 条 whipsaw 记录)")

    # 累计磨损分析
    print("\n=== 累计磨损分析 ===")
    for regime_label, (start, _) in SHAKE_PERIODS.items():
        r_detail = combined[combined["regime"].str.startswith(start[:7])]
        losses = r_detail[r_detail["is_loss"] == True]
        if len(losses) > 0:
            cum = losses["segment_return"].sum()
            n_loss = len(losses)
            print(f"  {regime_label}: {n_loss} 次亏损 whipsaw, 累计磨损 {cum:.3%}, "
                  f"单次平均 {losses['segment_return'].mean():.3%}")
        else:
            print(f"  {regime_label}: 无亏损 whipsaw")

    print("\n=== 步骤 2 完成 ===")
    return combined


if __name__ == "__main__":
    main()
