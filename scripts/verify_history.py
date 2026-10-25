# [2026-10-25] 新增：历史行情抽检门禁 — data/raw 收盘价与新浪逐日比对
"""历史行情抽检门禁。

背景：数据管线只校验「当日最新收盘」，历史行入库后不再复核，
盘中快照等错误会永久沉淀（2026-10-25 发现 2026-06-11 / 06-16 / 07-03
共 5 个交易日的腾讯错误价）。本脚本按交易日抽检最近 N 天，任一不一致即失败。

用法：
    python scripts/verify_history.py [--days 250] [--data-dir data]

退出码：0 = 全部一致；1 = 存在不一致 / 缺数据 / 第二源拉取失败
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import akshare as ak  # noqa: E402

DEFAULT_CODES = ["510300", "159915", "513100", "518880", "511010"]
TOLERANCE = 1e-9


def _sina_symbol(code: str) -> str:
    """ETF 代码 → 新浪 symbol（沪深前缀）。"""
    return ("sz" if code.startswith(("0", "1", "2")) else "sh") + code


def fetch_sina_close(code: str) -> pd.Series:
    """拉取新浪全历史收盘价，index=交易日。失败抛异常，由调用方记为问题。"""
    df = ak.fund_etf_hist_sina(symbol=_sina_symbol(code))
    if df is None or df.empty:
        raise RuntimeError("新浪返回空数据")
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float).sort_index()


def verify(data_dir: str = "data", days: int = 250, codes: list[str] | None = None,
           fetch_fn=None) -> list[str]:
    """抽检最近 days 个交易日，返回问题列表（空列表 = 通过）。

    比对规则：两源收盘价必须精确相等（无容差），与数据管线 v214 一致。
    fetch_fn 默认在调用时解析，便于测试注入桩函数。
    """
    codes = codes or DEFAULT_CODES
    if fetch_fn is None:
        fetch_fn = fetch_sina_close
    problems: list[str] = []
    for code in codes:
        path = os.path.join(data_dir, "raw", f"{code}.parquet")
        if not os.path.exists(path):
            problems.append(f"{code}: raw parquet 缺失")
            continue

        raw = pd.read_parquet(path)
        raw.index = pd.to_datetime(raw.index)
        if len(raw) == 0 or "close" not in raw.columns:
            problems.append(f"{code}: raw 数据为空或无 close 列")
            continue

        try:
            sina = fetch_fn(code)
        except Exception as exc:
            problems.append(f"{code}: 第二源拉取失败 {type(exc).__name__}: {exc}")
            continue

        merged = pd.DataFrame({"raw": raw["close"].tail(days), "sina": sina}).dropna()
        if len(merged) == 0:
            problems.append(f"{code}: 两源无重叠交易日")
            continue

        bad = merged[(merged["raw"] - merged["sina"]).abs() > TOLERANCE]
        for dt, row in bad.iterrows():
            problems.append(
                f"{code} {dt.date()} raw={row['raw']:.4f} sina={row['sina']:.4f}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    """命令行入口：返回 0/1 退出码。"""
    parser = argparse.ArgumentParser(description="历史行情抽检（data/raw vs 新浪）")
    parser.add_argument("--days", type=int, default=250, help="抽检最近 N 个交易日")
    parser.add_argument("--data-dir", default="data", help="数据目录")
    args = parser.parse_args(argv)

    problems = verify(args.data_dir, days=args.days)
    if problems:
        print(f"[抽检失败] {len(problems)} 处问题：")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"[抽检通过] 最近 {args.days} 个交易日，{len(DEFAULT_CODES)} 只 ETF 与新浪逐日一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
