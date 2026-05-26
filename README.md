# 003-quant-etf

ETF 多资产动量轮动量化系统。AI 辅助纪律执行和标的筛选，不追求全自动交易。

## 策略概要

**双引擎结构**：防御层（70% 资金，多资产趋势跟踪 + 目标波动率控制）+ 进攻层（30% 资金，行业截面动量排名）。

完整策略规格见 [方向性讨论.md](方向性讨论.md)。

## 技术栈

Python 3.10+ / AKShare / pandas / numpy / scipy / pytest

## 版本

### v1-20260527：项目初始化

- Git 仓库初始化
- 基础文件骨架：`src/config.py`（配置入口）、`tests/test_config.py`（3/3 绿）
- 依赖清单：akshare / pandas / numpy / scipy / dashscope / pytest
- 架构防火墙三层 Hook 就位（pre_bash + pre_edit_file + post-edit-audit）
- 策略方向性讨论完成，架构冻结（方向性讨论.md）
- 三角色模型分配：顾问 DeepSeek V4 Pro / 执行 DeepSeek Chat / 审计 Qwen3-Max

### 版本说明

每个 Release 对应一个可运行的功能增量。README 随版本更新，记录每个版本的核心变更。
