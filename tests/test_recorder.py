# [2026-05-29] 修改：rankings 格式适配时间序列动量 — 取消 score 字段
# [2026-05-27] 新增：Recorder 测试 — 3 场景

import pandas as pd
import pytest
from src.recorder import init_recorder, record_daily, get_records_df


def _make_signal(defense_active=None, offense_top=None, cb_triggered=False,
                 dd_level="normal", dd=-0.02, final_mult=1.0):
    return {
        "date": "2024-06-01",
        "defense": {
            "active": defense_active or ["沪深300", "创业板", "纳指", "黄金", "国债ETF"],
            "scaling_factor": 1.0,
            "predicted_vol": 0.10,
        },
        "offense": {
            "rankings": [{"name": n} for n in (offense_top or [])],
        },
        "circuit_breaker": {"triggered": cb_triggered},
        "drawdown_stop": {"level": dd_level, "drawdown": dd},
        "execution": {"final_multiplier": final_mult},
    }


def _make_positions(names=None):
    return {name: 100_000 for name in (names or ["沪深300", "国债ETF"])}


class TestInitAndRecord:
    """场景 1：初始化和记录 — init → record 3 天 → get_records_df"""

    def test_init_and_record_three_days(self):
        rec = init_recorder()
        signal = _make_signal()
        positions = _make_positions()

        record_daily(rec, "2024-01-02", 1_000_000, signal, positions)
        record_daily(rec, "2024-01-03", 1_001_000, signal, positions)
        record_daily(rec, "2024-01-04", 1_002_000, signal, positions)

        df = get_records_df(rec)
        assert len(df) == 3, f"应 3 行，实际 {len(df)}"
        for col in ["nav", "exposure", "repo_amount", "drawdown_level"]:
            assert col in df.columns, f"缺少列 {col}"
        assert isinstance(df.index, pd.DatetimeIndex), "index 应为 DatetimeIndex"


class TestFieldCorrectness:
    """场景 2：字段正确性 — record 一条验证 date/nav/positions"""

    def test_field_correctness(self):
        rec = init_recorder()
        signal = _make_signal(
            defense_active=["沪深300", "国债ETF"],
            offense_top=["半导体"],
        )
        positions = {"沪深300": 600_000, "国债ETF": 300_000, "半导体": 100_000}

        record_daily(rec, "2024-06-15", 1_000_000, signal, positions)

        df = get_records_df(rec)
        row = df.iloc[0]

        assert row["nav"] == 1_000_000
        assert str(df.index[0].date()) == "2024-06-15"
        assert row["exposure"] == pytest.approx(1_000_000, rel=1e-6)
        assert row["n_positions"] == 3
        assert row["position_names"] == "沪深300;国债ETF;半导体"
        assert row["defense_active"] == "沪深300;国债ETF"
        assert row["offense_top"] == "半导体"


class TestEmptyRecorder:
    """场景 3：空 recorder 转 DataFrame — 返回空 DataFrame 不报错"""

    def test_empty_recorder(self):
        rec = init_recorder()
        df = get_records_df(rec)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0, f"空 recorder 应返回空 DataFrame，实际 {len(df)} 行"


class TestPositionsDetail:
    """positions_detail 优先用于 exposure / repo_amount 计算"""

    def test_repo_amount_from_positions_detail(self):
        """positions_detail != positions 时，repo_amount 应基于 positions_detail"""
        rec = init_recorder()
        signal = _make_signal(defense_active=["沪深300", "创业板", "纳指", "黄金"])
        # positions 来自当日 signal（满仓）→ exposure=1,000,000
        positions = {"沪深300": 250_000, "创业板": 250_000, "纳指": 250_000, "黄金": 250_000}
        # positions_detail 来自昨日执行（0.92 乘数）→ exposure=920,000
        detail = {"沪深300": 230_000, "创业板": 230_000, "纳指": 230_000, "黄金": 230_000}
        record_daily(rec, "2024-06-15", 1_000_000, signal, positions, positions_detail=detail)
        df = get_records_df(rec)
        row = df.iloc[0]
        assert row["exposure"] == pytest.approx(920_000, rel=1e-6), (
            f"exposure 应基于 positions_detail=920,000，实际 {row['exposure']}"
        )
        assert row["repo_amount"] == pytest.approx(80_000, rel=1e-6), (
            f"repo_amount 应为 1,000,000-920,000=80,000，实际 {row['repo_amount']}"
        )
        assert row["n_positions"] == 4

    def test_no_positions_detail_falls_back_to_positions(self):
        """无 positions_detail 时，exposure 应 fallback 到 positions"""
        rec = init_recorder()
        signal = _make_signal(defense_active=["沪深300", "国债ETF"])
        positions = {"沪深300": 600_000, "国债ETF": 300_000}
        record_daily(rec, "2024-06-15", 1_000_000, signal, positions)
        df = get_records_df(rec)
        row = df.iloc[0]
        assert row["exposure"] == pytest.approx(900_000, rel=1e-6)
        assert row["repo_amount"] == pytest.approx(100_000, rel=1e-6)
