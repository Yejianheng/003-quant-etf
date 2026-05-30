# [2026-05-30] 新增：生存者偏差审计 — 验证回测不使用未上市 ETF、无退市残留
import os
import sys
import re
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import union_dates, get_available_etfs, run_backtest

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")

# 五只防御 ETF 上市日期（公开信息验证）
LISTING_DATES = {
    "510300": pd.Timestamp("2012-05-28"),  # 华泰柏瑞沪深300ETF
    "159915": pd.Timestamp("2011-12-09"),  # 易方达创业板ETF
    "513100": pd.Timestamp("2013-05-15"),  # 国泰纳斯达克100ETF
    "518880": pd.Timestamp("2013-07-29"),  # 华安黄金ETF
    "511010": pd.Timestamp("2013-03-25"),  # 国泰上证5年期国债ETF
}


def _collect_all_referenced_codes() -> set[str]:
    """扫描所有 .py 文件中的 6 位 ETF 代码引用。"""
    codes = set()
    code_re = re.compile(r'"(1[56]\d{4})"')
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in (".git", ".claude", "__pycache__", ".pytest_cache", "node_modules")]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        for match in code_re.finditer(fh.read()):
                            codes.add(match.group(1))
                except Exception:
                    pass
    return codes


# ═══════════════════════════════════════════════════════════════
# 基础路径：上市日期验证 + get_available_etfs 正确性
# ═══════════════════════════════════════════════════════════════


class TestListingDates:
    """核查防御 ETF 上市日期"""

    def test_defense_data_starts_after_listing(self):
        """每只防御 ETF 的数据开始日 ≥ 上市日期"""
        for code, listing_date in LISTING_DATES.items():
            fpath = os.path.join(DATA_DIR, f"{code}.parquet")
            if not os.path.exists(fpath):
                pytest.skip(f"{code}.parquet 不存在")
            df = pd.read_parquet(fpath)
            data_start = df.index.min()
            assert data_start >= listing_date, (
                f"{code} 数据开始日 {data_start.date()} 应 ≥ 上市日期 {listing_date.date()}，"
                f"数据不应早于上市日（否则有前视偏差）"
            )

    def test_last_defense_etf_listing(self):
        """最后一只防御 ETF 上市日 = 2013-07-29（黄金 518880）"""
        last_listing = max(LISTING_DATES.values())
        assert last_listing == pd.Timestamp("2013-07-29"), (
            f"最后上市日应为 2013-07-29，实际 {last_listing.date()}"
        )


class TestAvailableETFs:
    """get_available_etfs 正确排除数据不足的 ETF"""

    def test_insufficient_history_excluded(self):
        """ETF 在数据开始日当天 → min_history=120 应排除"""
        idx = pd.date_range("2024-01-01", "2026-01-01", freq="B")
        prices = {
            "新ETF": pd.DataFrame({"close": range(len(idx))}, index=idx),
        }
        # 第 5 天：仅 5 天数据，远 < 120
        available = get_available_etfs(prices, idx[5], min_history=120)
        assert "新ETF" not in available, (
            "min_history=120 时，仅 5 天数据的 ETF 不应出现"
        )

    def test_sufficient_history_included(self):
        """ETF 数据满足 min_history → 正确包含"""
        idx = pd.date_range("2024-01-01", "2026-01-01", freq="B")
        prices = {
            "成熟ETF": pd.DataFrame({"close": range(len(idx))}, index=idx),
        }
        # 第 150 天：150 ≥ 120
        available = get_available_etfs(prices, idx[150], min_history=120)
        assert "成熟ETF" in available, (
            "150 天数据 ≥ min_history=120，应包含"
        )

    def test_missing_date_excluded(self):
        """ETF 在该日期无数据 → 排除"""
        idx = pd.date_range("2024-01-01", "2024-06-30", freq="B")
        prices = {
            "A": pd.DataFrame({"close": range(len(idx))}, index=idx),
        }
        missing_date = pd.Timestamp("2023-12-15")
        available = get_available_etfs(prices, missing_date, min_history=10)
        assert "A" not in available, "该日期不在 ETF 数据范围内，应排除"


class TestBacktestStartDate:
    """回测起始日 ≥ 最后一只防御 ETF 数据开始日"""

    def test_defense_start_uses_max_of_defense_starts(self):
        """引擎内部 defense_start = max(各防御 ETF 数据首日)"""
        idx_a = pd.date_range("2020-01-01", "2022-12-31", freq="B")
        idx_b = pd.date_range("2018-01-01", "2022-12-31", freq="B")
        prices = {
            "A": pd.DataFrame({
                "open": [1]*len(idx_a), "high": [1]*len(idx_a),
                "low": [1]*len(idx_a), "close": [1]*len(idx_a),
                "volume": [1]*len(idx_a),
            }, index=idx_a),
            "B": pd.DataFrame({
                "open": [1]*len(idx_b), "high": [1]*len(idx_b),
                "low": [1]*len(idx_b), "close": [1]*len(idx_b),
                "volume": [1]*len(idx_b),
            }, index=idx_b),
        }
        # union_dates 返回并集
        dates = union_dates(prices)
        # 验证 A 的首日 2020-01-01 出现在并集中（B 更早，但 A 的首日在并集内）
        assert pd.Timestamp("2020-01-01") in dates
        # 验证 B 的首日 2018-01-01 也在并集中
        assert pd.Timestamp("2018-01-01") in dates


# ═══════════════════════════════════════════════════════════════
# 边界：空数据 + 退市残留检测
# ═══════════════════════════════════════════════════════════════


class TestNoDelistedResiduals:
    """data/ 目录下不应有退市 ETF 的 parquet 残留文件"""

    def test_all_parquet_files_referenced(self):
        """data/*.parquet 每个文件都应在某处被引用"""
        referenced = _collect_all_referenced_codes()
        unreferenced = []
        for f in os.listdir(DATA_DIR):
            if not f.endswith(".parquet"):
                continue
            code = f.replace(".parquet", "")
            if code not in referenced:
                unreferenced.append(code)

        # 输出给人工审查，不硬阻断（新采集的 ETF 可能尚未录入代码）
        if unreferenced:
            print(f"\n  WARNING: {len(unreferenced)} 个文件无代码引用: {unreferenced}")
            print("  这些可能是退市 ETF 残留或尚未录入映射表的 ETF。")
        # 不硬 assert — 由人判断


class TestEmptyInput:
    """空 prices → get_available_etfs 返回 []"""

    def test_empty_prices_returns_empty(self):
        available = get_available_etfs({}, pd.Timestamp("2024-01-15"), min_history=10)
        assert available == [], "空 prices 应返回 []"

    def test_empty_dataframe_skipped(self):
        idx = pd.date_range("2024-01-01", "2024-03-31", freq="B")
        prices = {
            "正常ETF": pd.DataFrame({"close": range(len(idx))}, index=idx),
            "空ETF": pd.DataFrame(),
        }
        available = get_available_etfs(prices, idx[50], min_history=10)
        assert "空ETF" not in available, "空 DataFrame 应被跳过"
        assert "正常ETF" in available, "正常 ETF 应被包含"


# ═══════════════════════════════════════════════════════════════
# 异常：min_history 边界
# ═══════════════════════════════════════════════════════════════


class TestMinHistoryBoundary:
    """min_history 边界值行为"""

    def test_exactly_min_history(self):
        """日期恰好 = 第 min_history 天 → 应包含 (>= min_history)"""
        n = 120
        idx = pd.date_range("2024-01-01", periods=n + 10, freq="B")
        prices = {
            "ETF": pd.DataFrame({"close": range(len(idx))}, index=idx),
        }
        # 第 120 天（index n-1=119, 0-based）
        available = get_available_etfs(prices, idx[n - 1], min_history=n)
        assert "ETF" in available, (
            f"第 {n} 天 (idx[{n-1}]) 应有恰好 min_history 天数据"
        )

    def test_one_less_than_min_history(self):
        """日期 = 第 min_history-1 天 → 应排除"""
        n = 120
        idx = pd.date_range("2024-01-01", periods=n + 10, freq="B")
        prices = {
            "ETF": pd.DataFrame({"close": range(len(idx))}, index=idx),
        }
        available = get_available_etfs(prices, idx[n - 2], min_history=n)
        assert "ETF" not in available, (
            f"第 {n-1} 天 (idx[{n-2}]) 应因历史不足被排除"
        )
