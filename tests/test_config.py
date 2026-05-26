# [2026-05-26] 新增：config.py 配置读取测试
import os
import pytest
from src.config import DASHSCOPE_API_KEY, DATA_DIR


class TestConfig:
    """验证 config.py 正确读取环境变量"""

    def test_dashscope_api_key_set(self, monkeypatch):
        """环境变量已设置 → DASHSCOPE_API_KEY 非空"""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-key-123")
        # 需要重新导入以获取 monkeypatched 环境变量
        import importlib
        import src.config
        importlib.reload(src.config)
        assert src.config.DASHSCOPE_API_KEY == "sk-test-key-123"

    def test_dashscope_api_key_unset(self, monkeypatch):
        """环境变量未设置 → 返回空字符串"""
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        import importlib
        import src.config
        importlib.reload(src.config)
        assert src.config.DASHSCOPE_API_KEY == ""

    def test_data_dir_default(self, monkeypatch):
        """DATA_DIR 默认值为 './data'"""
        monkeypatch.delenv("AKSHARE_DATA_DIR", raising=False)
        import importlib
        import src.config
        importlib.reload(src.config)
        assert src.config.DATA_DIR == "./data"
