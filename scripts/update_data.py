# [2026-05-30] 新增：每日数据更新脚本 — 增量拉取 AKShare 数据追加到 parquet
"""
每日数据更新脚本：遍历防御层 ETF parquet → 拉取最新数据 → 合并去重 → 存回。

用法：python scripts/update_data.py
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_pipeline import fetch_etf_daily, load_from_parquet, save_to_parquet
from src.etf_universe import ETF_UNIVERSE


def update_single_etf(code: str, data_dir: str = "data", lookback_days: int = 10) -> bool:
    """
    更新单只 ETF 的 parquet 文件。返回 True 表示有新数据写入，False 表示跳过。
    - 文件不存在 → 跳过
    - AKShare 返回空 → 跳过
    """
    path = os.path.join(data_dir, f"{code}.parquet")
    if not os.path.exists(path):
        print(f"  [{code}] 跳过：parquet 文件不存在")
        return False

    existing = load_from_parquet(path)
    last_date = existing.index.max().date()
    start_date = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = date.today().strftime("%Y-%m-%d")

    if start_date >= end_date:
        print(f"  [{code}] 已是最新（{last_date}）")
        return False

    new_data = fetch_etf_daily(code, start_date, end_date)
    if new_data.empty:
        print(f"  [{code}] 无新数据（{start_date}~{end_date}）")
        return False

    combined = pd.concat([existing, new_data])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()
    save_to_parquet(combined, path)
    print(f"  [{code}] 新增 {len(new_data)} 行（{start_date}~{end_date}）")
    return True


def main(data_dir: str = "data", lookback_days: int = 10) -> None:
    """遍历全部防御层 ETF，增量更新。"""
    codes = list(ETF_UNIVERSE.values())
    updated_count = 0
    for code in codes:
        if update_single_etf(code, data_dir, lookback_days):
            updated_count += 1
    print(f"更新完成：{updated_count}/{len(codes)} 只 ETF 有新数据")


if __name__ == "__main__":
    main()
