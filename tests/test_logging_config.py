# [2026-05-27] 新增：日志模块测试 — 1 场景

import logging

from src.logging_config import get_logger


class TestGetLogger:
    """场景 1：logger 正常输出 — 返回 Logger 实例，level=INFO，有 StreamHandler"""

    def test_get_logger_returns_logger_with_info_level(self):
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger), f"应返回 Logger 实例，得到 {type(logger)}"
        assert logger.level == logging.INFO, f"默认级别应为 INFO，得到 {logger.level}"

    def test_get_logger_has_stream_handler(self):
        logger = get_logger("test")
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types, f"应有 StreamHandler，现有 handlers: {handler_types}"

    def test_get_logger_name_matches(self):
        logger = get_logger("test")
        assert logger.name == "test", f"logger name 应为 'test'，得到 '{logger.name}'"
