# [2026-06-18] 新增：四张表入口脚本测试
import pytest


class TestFourTables:
    def test_entry_point_imports(self):
        """four_tables 入口可导入"""
        import scripts.four_tables  # noqa: F401
