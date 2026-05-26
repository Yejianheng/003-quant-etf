# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务

项目初始化：搭建 003-quant-etf 基础文件骨架，初始化 git 仓库，准备好回测开发环境。不涉及任何业务逻辑代码。

## 涉及文件

### 新建文件

- `.gitignore` — Python 项目标准忽略规则（__pycache__/、.venv/、.env、*.pyc、.pytest_cache/）
- `.env.example` — 环境变量模板，含 `DASHSCOPE_API_KEY=` 和 `AKSHARE_DATA_DIR=./data`
- `requirements.txt` — 依赖清单：`akshare>=1.14.0`、`pandas>=2.0.0`、`numpy>=1.24.0`、`scipy>=1.10.0`（协方差矩阵）、`dashscope>=1.20.0`（审计模型），版本号不锁死
- `src/__init__.py` — 空文件
- `src/config.py` — 配置入口，读取环境变量。内容：
  ```python
  """
  模块归属：业务层 / 配置入口
  职责：读取环境变量，提供全局配置常量
  用法：from src.config import DASHSCOPE_API_KEY, DATA_DIR
  """
  import os

  DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
  DATA_DIR = os.getenv("AKSHARE_DATA_DIR", "./data")
  ```
- `tests/__init__.py` — 空文件
- `tests/test_config.py` — 验证 config.py 正确读取环境变量。测试场景：
  - 环境变量已设置 → DASHSCOPE_API_KEY 非空
  - 环境变量未设置 → 返回空字符串
  - DATA_DIR 默认值为 "./data"
- `prompts/` 目录 — 创建空目录，放 `.gitkeep`
- `data/` 目录 — 创建空目录，放 `.gitkeep`
- `项目日志/` 目录 — 已存在，无需操作

### 修改文件

- `.claude/next-session.md` — 更新为：
  - 当前阶段：回测开发
  - 已决策：方向性讨论.md 架构冻结，所有参数和决策见该文件
  - 待处理：搭建回测引擎、实现趋势强度计算、实现截面动量计算、实现目标波动率模块、实现完整回测管线
  - 最后状态：2026-05-26 方向性讨论完成，架构冻结，准备进入回测开发阶段

- `protected-files.json` — 新增保护区条目：
  - `protected_files` 新增：`src/config.py`
  - 说明：config.py 是配置唯一入口，禁止绕过直接硬编码 API Key

## 约束

- 不写任何业务逻辑代码（趋势强度、动量计算、回测引擎等均为下一步）
- 不新增功能，纯基础设施搭建
- 保护区文件（protected-files.json）修改需走 audit 流程

## 验收标准

- [ ] `git status` — 显示新文件已 staged，工作区干净
- [ ] `python -c "from src.config import DASHSCOPE_API_KEY, DATA_DIR; print('OK')"` — 输出 OK
- [ ] `python -m pytest tests/test_config.py -v` — 全部通过
- [ ] `ls src/ tests/ prompts/ data/ 项目日志/` — 五个目录均存在
- [ ] `ls requirements.txt .env.example .gitignore` — 三个文件均存在

---

> 执行完成后，写 outcome.md 并提示人开顾问窗口审查。
> 涉及保护区文件时，执行者必须跑 CLI validate → CLI audit，结果写入 outcome.md。
