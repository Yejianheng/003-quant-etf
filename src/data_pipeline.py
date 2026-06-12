# [2026-06-12] 新增：拆分/除权自动检测与修正（跌幅>50%触发，前复权）
# [2026-05-27] 新增：数据管线 — AKShare → Parquet
# [2026-05-27] 修改：save_to_parquet 自动创建目录（技术隐患 #3）
# [2026-05-27] 修改：fetch_etf_daily 加代理绕过 + 重试 + 异常分类

import os
import time
import pandas as pd
import akshare as ak
from src.logging_config import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # 秒，指数退避: 2s → 4s → 8s


def _patch_requests_no_proxy():
    """Monkey-patch requests.Session 强制不走系统代理（VPN 残留 127.0.0.1:7890）。"""
    import requests
    _original_init = requests.Session.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        self.trust_env = False

    requests.Session.__init__ = _patched_init


_patch_requests_no_proxy()


def fetch_etf_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """从 AKShare 拉取单只 ETF 日线，返回 pandas DataFrame。code: ETF 代码，如 "510300"."""
    for attempt in range(_MAX_RETRIES):
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )
        except Exception as e:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"AKShare 调用失败 (code={code}, attempt={attempt + 1}/{_MAX_RETRIES}): "
                f"{type(e).__name__}: {e}"
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(delay)
            else:
                logger.error(
                    f"AKShare 重试 {_MAX_RETRIES} 次后仍失败 (code={code})，返回空 DataFrame。"
                    f"可能原因：网络不可达 / 东方财富限流 / VPN 干扰。"
                )
                return pd.DataFrame()
            continue

        # AKShare 调用成功
        if df is None or df.empty:
            logger.info(f"AKShare 返回空数据 (code={code}, {start_date}~{end_date})，"
                        f"可能是非交易日区间")
            return pd.DataFrame()

        # 中文列名 → 英文
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
        cols = ["date", "open", "high", "low", "close", "volume"]
        available = [c for c in cols if c in df.columns]
        df = df[available]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df = df.sort_index()

        # 拆分/除权检测：单日跌幅 > 50%，自动前复权修正
        close = df["close"]
        daily_ret = close.pct_change()
        split_mask = daily_ret < -0.50
        if split_mask.any():
            for split_date in daily_ret[split_mask].index:
                pre = close.loc[:split_date].iloc[-2]  # 拆前最后一天
                post = close.loc[split_date]            # 拆后第一天
                ratio = pre / post
                logger.warning(
                    f"检测到拆分 (code={code}, date={str(split_date)[:10]}): "
                    f"拆前 close={pre:.3f}, 拆后 close={post:.3f}, "
                    f"比例 1:{ratio:.2f}，自动前复权修正"
                )
                pre_mask = df.index < split_date
                for col in ["open", "high", "low", "close"]:
                    df.loc[pre_mask, col] = df.loc[pre_mask, col] / ratio

        return df

    return pd.DataFrame()


def save_to_parquet(df: pd.DataFrame, path: str) -> None:
    """写入 Parquet，保留 index。自动创建目标目录。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_parquet(path, index=True)


def load_from_parquet(path: str) -> pd.DataFrame:
    """从 Parquet 读取 DataFrame，含 index。"""
    return pd.read_parquet(path)
