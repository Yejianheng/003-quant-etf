# [2026-05-27] 新增：数据管线 — AKShare → Parquet

import pandas as pd
import akshare as ak


def fetch_etf_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """从 AKShare 拉取单只 ETF 日线，返回 pandas DataFrame。code: ETF 代码，如 "510300"."""
    try:
        df = ak.fund_etf_hist_em(
            symbol=code,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # akshare 返回的日期列名是中文
    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        }
    )
    # 只保留需要的列
    cols = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in cols if c in df.columns]
    df = df[available]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df.sort_index()
    return df


def save_to_parquet(df: pd.DataFrame, path: str) -> None:
    """写入 Parquet，保留 index。"""
    df.to_parquet(path, index=True)


def load_from_parquet(path: str) -> pd.DataFrame:
    """从 Parquet 读取 DataFrame，含 index。"""
    return pd.read_parquet(path)
