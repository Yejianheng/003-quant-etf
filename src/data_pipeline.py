# [2026-10-15] 修复：三源复权口径统一为不复权（adjust="qfq"→""）。此前腾讯/东财取前复权、
#            新浪只能取不复权，三源比的是两个不同对象；平时"前复权 vs 前复权"通过后写入
#            不复权历史，即 2026-09-29 接缝事故的成因。复权改由 src/dividend_adjust.py
#            在「研究行情层」独立完成，原始行情层只存不复权。
# [2026-07-24] 修改：提取 _normalize_ohlcv 共享归一化，新增 fetch_etf_daily_em/sina 独立源（v214）
# [2026-06-23] 新增：fetch_etf_daily_tx 腾讯财经主源 + check_freshness 新鲜度门禁
# [2026-06-18] 新增：trim_isolated_dates — 剔除跨 ETF 不一致的孤立交易日
# [2026-06-16] 修改：fetch_etf_daily 新增新浪 fallback（东方财富不可达时自动切换）
# [2026-06-12] 新增：拆分/除权自动检测与修正（跌幅>50%触发，前复权）
# [2026-05-27] 新增：数据管线 — AKShare → Parquet
# [2026-05-27] 修改：save_to_parquet 自动创建目录（技术隐患 #3）
# [2026-05-27] 修改：fetch_etf_daily 加代理绕过 + 重试 + 异常分类

import os
import time
from datetime import date

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


def _to_sina_symbol(code: str) -> str:
    """ETF 代码转新浪格式（加 sh/sz 交易所前缀）。"""
    # 5xxxxx = 上海, 1xxxxx = 深圳, 0xxxxx = 深圳
    if code.startswith(("0", "1", "2")):
        return f"sz{code}"
    return f"sh{code}"


def _normalize_ohlcv(
    df: pd.DataFrame, code: str, source: str,
    start_date: str | None = None, end_date: str | None = None,
) -> pd.DataFrame:
    """归一化 OHLCV DataFrame 为统一格式（date index, cols: open/high/low/close/volume）。"""
    if df is None or df.empty:
        return pd.DataFrame()

    # 列名映射：em 源中文 → 英文
    if source == "em":
        df = df.rename(columns={
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
        })

    cols = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in cols if c in df.columns]
    df = df[available]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df.sort_index()

    # TX 源的 volume 是 amount（手），×100 = 股
    if source == "tx" and "volume" in df.columns:
        df["volume"] = df["volume"] * 100

    # 按请求日期范围截取
    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        df = df.loc[start:end]

    # 拆分/除权检测：单日跌幅 > 50%
    close = df["close"]
    daily_ret = close.pct_change()
    split_mask = daily_ret < -0.50
    if split_mask.any():
        for split_date in daily_ret[split_mask].index:
            pre = close.loc[:split_date].iloc[-2]
            post = close.loc[split_date]
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


def fetch_etf_daily_tx(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """从腾讯财经（AKShare stock_zh_a_hist_tx）拉取单只 ETF 日线。
    腾讯数据作为主源，返回与 fetch_etf_daily 一致的 DataFrame（cols: open/high/low/close/volume, date index）。
    code: ETF 代码，如 "510300"。限流：调用方需保证 3s 间隔。
    """
    # 5xxxxx = 上海, 1xxxxx/0xxxxx = 深圳
    if code.startswith(("0", "1", "2")):
        tx_symbol = f"sz{code}"
    else:
        tx_symbol = f"sh{code}"

    try:
        df = ak.stock_zh_a_hist_tx(
            symbol=tx_symbol,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="",  # 2026-10-15：三源统一不复权，复权在研究行情层做（见 dividend_adjust.py）
        )
    except Exception as e:
        logger.warning(f"腾讯财经调用失败 (code={code}): {type(e).__name__}: {e}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # 列映射：腾讯列名 → 统一列名。amount 为成交量（手），×100 转换为股
    df = df.rename(columns={
        "date": "date", "open": "open", "high": "high",
        "low": "low", "close": "close", "amount": "volume",
    })

    cols = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in cols if c in df.columns]
    df = df[available]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df.sort_index()

    # amount（手）×100 → volume（股）
    df["volume"] = df["volume"] * 100

    # 截取日期范围
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    df = df.loc[start_ts:end_ts]

    # 拆分/除权检测：同 fetch_etf_daily
    close = df["close"]
    daily_ret = close.pct_change()
    split_mask = daily_ret < -0.50
    if split_mask.any():
        for split_date in daily_ret[split_mask].index:
            pre = close.loc[:split_date].iloc[-2]
            post = close.loc[split_date]
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


def fetch_etf_daily_em(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """东方财富独立拉取（3 次重试，不含新浪 fallback）。失败返回空 DataFrame。"""
    for attempt in range(_MAX_RETRIES):
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="",  # 2026-10-15：三源统一不复权，复权在研究行情层做（见 dividend_adjust.py）
            )
            if df is None or df.empty:
                return pd.DataFrame()
            return _normalize_ohlcv(df, code, "em")
        except Exception as e:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"东方财富调用失败 (code={code}, attempt={attempt + 1}/{_MAX_RETRIES}): "
                f"{type(e).__name__}: {e}"
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(delay)
            continue
    return pd.DataFrame()


def fetch_etf_daily_sina(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """新浪独立拉取。失败返回空 DataFrame。"""
    try:
        sina_symbol = _to_sina_symbol(code)
        df = ak.fund_etf_hist_sina(symbol=sina_symbol)
        if df is None or df.empty:
            return pd.DataFrame()
        return _normalize_ohlcv(df, code, "sina", start_date, end_date)
    except Exception as e:
        logger.warning(f"新浪调用失败 (code={code}): {type(e).__name__}: {e}")
        return pd.DataFrame()


def fetch_etf_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """[deprecated] 从 AKShare 拉取单只 ETF 日线（EM 3 次重试 → Sina fallback）。
    改用 fetch_etf_daily_tx / fetch_etf_daily_em / fetch_etf_daily_sina。"""
    df = None
    source = None  # "em" | "sina"

    # 主源：东方财富（3 次重试 + 指数退避）
    for attempt in range(_MAX_RETRIES):
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="",  # 2026-10-15：三源统一不复权，复权在研究行情层做（见 dividend_adjust.py）
            )
        except Exception as e:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"AKShare 东方财富调用失败 (code={code}, attempt={attempt + 1}/{_MAX_RETRIES}): "
                f"{type(e).__name__}: {e}"
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(delay)
                continue
            # 最后一次重试也失败 → 切新浪
            logger.warning(f"东方财富不可达，切换新浪源 (code={code})")
            try:
                sina_symbol = _to_sina_symbol(code)
                df = ak.fund_etf_hist_sina(symbol=sina_symbol)
                if df is not None and not df.empty:
                    source = "sina"
            except Exception as e2:
                logger.error(f"新浪源也失败 (code={code}): {type(e2).__name__}: {e2}")
            if source is None:
                logger.error(
                    f"所有数据源均不可达 (code={code})，返回空 DataFrame。"
                    f"可能原因：网络不可达 / 东方财富限流 / 新浪不可达。"
                )
                return pd.DataFrame()
            break  # Sina 成功，跳出循环进入数据归一化

        # 东方财富 try 成功
        if df is None or df.empty:
            logger.info(f"AKShare 返回空数据 (code={code}, {start_date}~{end_date})，"
                        f"可能是非交易日区间")
            return pd.DataFrame()
        source = "em"
        break

    # === 数据归一化（两种源共用处理逻辑） ===
    if source == "em":
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

    # Sina 返回全量数据，按请求日期范围截取
    if source == "sina":
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        df = df.loc[start:end]

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


def save_to_parquet(df: pd.DataFrame, path: str) -> None:
    """写入 Parquet，保留 index。自动创建目标目录。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_parquet(path, index=True)


def load_from_parquet(path: str) -> pd.DataFrame:
    """从 Parquet 读取 DataFrame，含 index。"""
    return pd.read_parquet(path)


# ---- 三层数据布局（2026-10-15 新增）------------------------------------------
# 业界标准：原始行情 / 除权因子 / 研究行情 三层分离，复权数据不覆盖原始数据。
#   data/raw/{code}.parquet       原始行情（不复权，三源可比对，管线唯一写入目标）
#   data/dividends/{code}.parquet 除权因子（除息日 + 每股分红）
#   data/{code}.parquet           研究行情（分红再投，由前两层派生，策略消费此层）
# 之所以保持 data/{code}.parquet 作为研究行情路径，是为了让既有 40+ 处
# pd.read_parquet("data/xxx.parquet") 无需改动即可拿到正确口径。

RAW_DIR_NAME = "raw"
DIVIDEND_DIR_NAME = "dividends"


def raw_data_path(code: str, data_dir: str = "data") -> str:
    """原始行情（不复权）parquet 路径。"""
    return os.path.join(data_dir, RAW_DIR_NAME, f"{code}.parquet")


def dividend_data_path(code: str, data_dir: str = "data") -> str:
    """除权因子 parquet 路径。"""
    return os.path.join(data_dir, DIVIDEND_DIR_NAME, f"{code}.parquet")


def load_dividends(code: str, data_dir: str = "data") -> pd.DataFrame:
    """读取某只 ETF 的除息表。文件不存在 → 返回空表（视为无分红）。"""
    path = dividend_data_path(code, data_dir)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["dividend"])
    return load_from_parquet(path)


def rebuild_adjusted(code: str, data_dir: str = "data") -> bool:
    """由「原始行情 + 除权因子」重算并写入研究行情层 data/{code}.parquet。

    返回 True 表示已写入；原始行情缺失时返回 False 且不写。
    """
    from src.dividend_adjust import adjust_prices_for_dividends

    raw_path = raw_data_path(code, data_dir)
    if not os.path.exists(raw_path):
        return False

    raw = load_from_parquet(raw_path)
    adjusted = adjust_prices_for_dividends(raw, load_dividends(code, data_dir))
    save_to_parquet(adjusted, os.path.join(data_dir, f"{code}.parquet"))
    return True


def trim_isolated_dates(etf_codes: list[str], data_dir: str = "data") -> int:
    """剔除跨 ETF 不一致的孤立交易日（某只 ETF 有、另一只没有的日期）。

    加载所有 parquet → 取日期交集 → 每只 ETF 只保留交集内的行 → 写回。
    返回剔除的总行数。
    """
    import os as _os

    # 加载全部
    dfs = {}
    for code in etf_codes:
        path = _os.path.join(data_dir, f"{code}.parquet")
        if not _os.path.exists(path):
            continue
        dfs[code] = load_from_parquet(path)

    if len(dfs) < 2:
        return 0

    # 取日期交集
    common_dates = set(dfs[list(dfs.keys())[0]].index)
    for df in dfs.values():
        common_dates = common_dates.intersection(set(df.index))
    common_dates = sorted(common_dates)

    # 剔除孤立日期 + 写回
    total_removed = 0
    for code, df in dfs.items():
        before = len(df)
        trimmed = df.loc[common_dates]
        removed = before - len(trimmed)
        if removed > 0:
            path = _os.path.join(data_dir, f"{code}.parquet")
            save_to_parquet(trimmed, path)
            logger.info(f"  [{code}] 剔除 {removed} 行孤立日期，保留 {len(trimmed)} 行")
        total_removed += removed

    if total_removed > 0:
        logger.info(f"trim_isolated_dates: 共剔除 {total_removed} 行，交集 {len(common_dates)} 天")
    return total_removed


def check_freshness(etf_codes: list[str], data_dir: str = "data", max_age_days: int = 3) -> list[str]:
    """检查所有 ETF parquet 最新日期是否在容忍期内。
    返回超出容忍期的 ETF 代码列表（空列表 = 全部新鲜）。
    max_age_days: 允许的最大日历天数差距（默认 3，覆盖周末+节假日）。
    """
    today = date.today()
    stale = []
    for code in etf_codes:
        path = os.path.join(data_dir, f"{code}.parquet")
        if not os.path.exists(path):
            stale.append(code)
            continue
        df = load_from_parquet(path)
        if df.empty:
            stale.append(code)
            continue
        last_date = df.index.max().date()
        age = (today - last_date).days
        if age > max_age_days:
            stale.append(code)
    return stale
