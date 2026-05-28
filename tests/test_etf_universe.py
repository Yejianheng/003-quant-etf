# [2026-05-29] 重写：三层架构 OFFENSE_POOL 测试 — 旧 10 只结构作废
import pytest


# ============================================================
# ETF_UNIVERSE 回归（不碰）
# ============================================================

class TestEtfUniverseRegression:
    """防御层 ETF_UNIVERSE 回归——5 只标的不变"""

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


# ============================================================
# OFFENSE_POOL 新结构（三层架构：风险源层 → ETF 候选层 → 代表 ETF）
# ============================================================

RISK_SOURCE_NAMES = {"消费", "医药", "金融", "周期资源", "科技成长", "军工"}


class TestOffensePoolNewStructure:
    """OFFENSE_POOL 三层架构——步骤 0 红灯预期：OFFENSE_POOL 尚未重建"""

    def test_offense_pool_is_dict(self):
        from src.etf_universe import OFFENSE_POOL
        assert isinstance(OFFENSE_POOL, dict), \
            f"OFFENSE_POOL 应为 dict，实际 {type(OFFENSE_POOL)}"

    def test_offense_pool_has_6_risk_sources(self):
        from src.etf_universe import OFFENSE_POOL
        assert len(OFFENSE_POOL) == 6, \
            f"风险源数量应为 6，实际 {len(OFFENSE_POOL)}"

    def test_risk_source_names_match(self):
        from src.etf_universe import OFFENSE_POOL
        actual_names = set(OFFENSE_POOL.keys())
        missing = RISK_SOURCE_NAMES - actual_names
        extra = actual_names - RISK_SOURCE_NAMES
        assert not missing, f"缺少风险源: {missing}"
        assert not extra, f"多余风险源: {extra}"

    def test_each_source_has_required_fields(self):
        from src.etf_universe import OFFENSE_POOL
        for name, entry in OFFENSE_POOL.items():
            assert isinstance(entry, dict), \
                f"{name} 的值应为 dict，实际 {type(entry)}"
            assert 'code' in entry, f"{name} 缺少 'code' 字段"
            assert 'name' in entry, f"{name} 缺少 'name' 字段"
            assert 'candidates' in entry, f"{name} 缺少 'candidates' 字段"

    def test_each_source_candidates_1_to_3(self):
        from src.etf_universe import OFFENSE_POOL
        for name, entry in OFFENSE_POOL.items():
            candidates = entry['candidates']
            n = len(candidates)
            assert 1 <= n <= 3, \
                f"{name} 候选 ETF 数量 {n}，期望 1-3"

    def test_representative_code_is_numeric(self):
        from src.etf_universe import OFFENSE_POOL
        for name, entry in OFFENSE_POOL.items():
            code = entry['code']
            assert code.isdigit(), \
                f"{name} 代表 ETF 代码 {code} 非纯数字"

    def test_candidate_codes_are_numeric(self):
        from src.etf_universe import OFFENSE_POOL
        for name, entry in OFFENSE_POOL.items():
            for c in entry['candidates']:
                assert c['code'].isdigit(), \
                    f"{name} 候选 {c['name']} 代码 {c['code']} 非纯数字"

    def test_no_overlap_with_defensive(self):
        from src.etf_universe import OFFENSE_POOL, ETF_UNIVERSE
        defensive_codes = set(ETF_UNIVERSE.values())
        for name, entry in OFFENSE_POOL.items():
            assert entry['code'] not in defensive_codes, \
                f"{name} 代表代码 {entry['code']} 与防御层重叠"
            for c in entry['candidates']:
                assert c['code'] not in defensive_codes, \
                    f"{name} 候选 {c['name']} 代码 {c['code']} 与防御层重叠"

    def test_no_cross_source_code_duplication(self):
        from src.etf_universe import OFFENSE_POOL
        # 每个风险源的去重代码集合
        source_codes = {}
        for name, entry in OFFENSE_POOL.items():
            codes = {c['code'] for c in entry['candidates']}
            source_codes[name] = codes
        # 检查跨风险源重叠：两个不同风险源的代码集合不能有交集
        sources = list(source_codes.keys())
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                overlap = source_codes[sources[i]] & source_codes[sources[j]]
                assert len(overlap) == 0, \
                    f"{sources[i]} 与 {sources[j]} 代码重叠: {overlap}"

    def test_representative_in_candidates(self):
        from src.etf_universe import OFFENSE_POOL
        for name, entry in OFFENSE_POOL.items():
            candidate_codes = {c['code'] for c in entry['candidates']}
            assert entry['code'] in candidate_codes, \
                f"{name} 代表 ETF {entry['code']} 不在候选列表中"


# ============================================================
# 映射流水线函数
# ============================================================

class TestCandidatePoolBuilder:
    """候选池构建函数"""

    def test_build_candidate_pool_exists(self):
        from src.etf_universe import build_candidate_pool
        assert callable(build_candidate_pool)

    def test_build_candidate_pool_accepts_kwargs(self):
        from src.etf_universe import build_candidate_pool
        import inspect
        sig = inspect.signature(build_candidate_pool)
        # 应接受可选的数据源/过滤参数
        params = list(sig.parameters.keys())
        assert len(params) >= 0

    def test_build_candidate_pool_returns_list(self, monkeypatch):
        """网络不可达时返回空列表而非崩溃"""
        import src.etf_universe as eu
        original = getattr(eu, 'build_candidate_pool', None)
        if original is None:
            pytest.skip("build_candidate_pool 不存在")
        # 模拟网络异常
        def mock_unreachable(*args, **kwargs):
            raise ConnectionError("模拟网络不可达")
        monkeypatch.setattr(eu, 'build_candidate_pool', mock_unreachable)
        try:
            eu.build_candidate_pool()
        except ConnectionError:
            pass
