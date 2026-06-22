# [2026-06-22] 新增：数据校验脚本 — 新鲜度/行数/空值三类检查
"""
数据校验脚本：检查 parquet 数据新鲜度、行数一致性、空值。
用法：python scripts/verify_data.py
"""
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.etf_universe import ETF_UNIVERSE
from src.data_pipeline import load_from_parquet


def verify_data(data_dir: str = "data") -> list[str]:
    """校验 data_dir 下所有防御 ETF parquet，返回告警字符串列表（空列表=全部通过）。"""
    warnings: list[str] = []
    today = date.today()

    loaded: dict[str, pd.DataFrame] = {}
    rows: dict[str, int] = {}

    for name, code in ETF_UNIVERSE.items():
        path = os.path.join(data_dir, f"{code}.parquet")
        if not os.path.exists(path):
            warnings.append(f"[缺失] {name}({code}): parquet 文件不存在")
            continue

        df = load_from_parquet(path)
        loaded[name] = df
        rows[name] = len(df)
        latest = df.index.max().date()

        # 新鲜度：最新日期距今天超过 2 个交易日
        trading_days_behind = len(pd.bdate_range(latest + pd.Timedelta(days=1), today))
        if trading_days_behind > 2:
            warnings.append(
                f"[新鲜度] {name}({code}): 最新 {latest}，"
                f"落后 {trading_days_behind} 个交易日"
            )

        # 空值：close 列
        nan_count = int(df["close"].isna().sum())
        if nan_count > 0:
            warnings.append(f"[空值] {name}({code}): close 列 {nan_count} 个 NaN")

    # 行数一致性：各 ETF 行数极差
    if len(rows) > 1:
        counts = list(rows.values())
        if max(counts) - min(counts) > 3:
            details = "; ".join(f"{n}={r}" for n, r in rows.items())
            warnings.append(f"[行数] ETF 行数差异过大: {details}")

    return warnings


def main() -> None:
    warnings = verify_data()
    if warnings:
        print(f"[校验] {len(warnings)} 条告警：")
        for m in warnings:
            print(f"  {m}")
        sys.exit(1)
    print("[校验] 全部通过")


if __name__ == "__main__":
    main()
