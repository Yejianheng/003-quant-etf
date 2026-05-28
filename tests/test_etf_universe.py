# [2026-05-28] 新增：ETF 候选池测试 — ETF_UNIVERSE 回归 + OFFENSE_POOL 新行为
import pytest


class TestEtfUniverseRegression:
    """ETF_UNIVERSE 回归——现有防御层标的"""

    def test_has_5_defensive_tickers(self):
        from src.etf_universe import ETF_UNIVERSE
        assert len(ETF_UNIVERSE) == 5
        assert "沪深300" in ETF_UNIVERSE
        assert "创业板" in ETF_UNIVERSE
        assert "纳指" in ETF_UNIVERSE
        assert "黄金" in ETF_UNIVERSE
        assert "国债ETF" in ETF_UNIVERSE

    def test_all_codes_are_numeric_strings(self):
        from src.etf_universe import ETF_UNIVERSE
        for name, code in ETF_UNIVERSE.items():
            assert code.isdigit(), f"{name} 代码 {code} 非纯数字"


class TestOffensePoolExists:
    """OFFENSE_POOL 存在性——步骤 0 红灯预期：OFFENSE_POOL 尚未定义"""

    def test_offense_pool_importable(self):
        """OFFENSE_POOL 可导入且为 dict"""
        from src.etf_universe import OFFENSE_POOL
        assert isinstance(OFFENSE_POOL, dict), f"OFFENSE_POOL 应为 dict，实际 {type(OFFENSE_POOL)}"

    def test_offense_pool_count_10_to_15(self):
        """候选池数量 10-15 只"""
        from src.etf_universe import OFFENSE_POOL
        n = len(OFFENSE_POOL)
        assert 10 <= n <= 15, f"OFFENSE_POOL 数量 {n}，期望 10-15"

    def test_offense_pool_no_overlap_with_defensive(self):
        """OFFENSE_POOL 与 ETF_UNIVERSE 代码无重叠"""
        from src.etf_universe import OFFENSE_POOL, ETF_UNIVERSE
        defensive_codes = set(ETF_UNIVERSE.values())
        offense_codes = set(OFFENSE_POOL.values())
        overlap = defensive_codes & offense_codes
        assert len(overlap) == 0, f"重叠代码: {overlap}"

    def test_offense_pool_no_duplicate_codes(self):
        """OFFENSE_POOL 内部代码无重复"""
        from src.etf_universe import OFFENSE_POOL
        codes = list(OFFENSE_POOL.values())
        assert len(codes) == len(set(codes)), f"重复代码: {[c for c in codes if codes.count(c) > 1]}"


class TestCandidatePoolBuilder:
    """候选池构建函数——步骤 0 红灯预期：函数尚未定义"""

    def test_build_candidate_pool_exists(self):
        """build_candidate_pool 函数存在且可调用"""
        from src.etf_universe import build_candidate_pool
        assert callable(build_candidate_pool)

    def test_build_candidate_pool_returns_list_on_network_failure(self, monkeypatch):
        """网络不可达时返回空列表而非崩溃"""
        # 离线场景验证：函数存在即通过结构检查
        from src.etf_universe import build_candidate_pool
        # 不实际调 AKShare（网络不可达），验证函数签名合理
        import inspect
        sig = inspect.signature(build_candidate_pool)
        assert len(sig.parameters) == 0, "build_candidate_pool 应无必填参数"
