# [2026-05-26] 新增：配置入口，读取环境变量
"""
模块归属：业务层 / 配置入口
职责：读取环境变量，提供全局配置常量
用法：from src.config import DASHSCOPE_API_KEY, DATA_DIR
"""
import os

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DATA_DIR = os.getenv("AKSHARE_DATA_DIR", "./data")
