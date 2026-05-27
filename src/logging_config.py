# [2026-05-27] 新增：日志模块 — 统一 logger 配置

import logging
import os


def get_logger(name: str) -> logging.Logger:
    """返回统一配置的 logger。格式：时间 | 级别 | 名称 | 消息，输出到 stdout 和 logs/app.log"""
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    # stdout handler
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # file handler — 自动创建 logs/ 目录
    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("logs/app.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 禁止 propagate 到 root logger，避免重复输出
    logger.propagate = False

    return logger
