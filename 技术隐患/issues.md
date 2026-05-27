# 待解决隐患

> 按重要性降序。解决时间关联回测开发步骤（Step 1-10）。

## #1 异常静默吞没 — `fetch_etf_daily`

| 项 | 内容 |
|------|------|
| **重要性** | 高 |
| **位置** | `src/data_pipeline.py:16-17` |
| **现象** | `except Exception: return pd.DataFrame()` 捕获所有异常（网络故障、API 变更、参数错误），全部静默转为空 DataFrame |
| **后果** | 回测引擎拿到空数据 → 认为"该时段无行情" → 跳过交易 → 回测结果悄无声息地错误 |
| **计划解决** | Step 2 开始前，建立统一的异常分类规范（网络错误重试 / 数据为空正常返回 / 未知错误上报），然后收窄此处 exception 范围 |

## #2 无日志/可观测性机制

| 项 | 内容 |
|------|------|
| **重要性** | 中 |
| **位置** | 全局 |
| **现象** | 项目无统一日志模块。数据拉取成功/失败、API 调用耗时、异常堆栈均无记录 |
| **后果** | Step 3+ 模块增多后，排查问题只能靠 print 或断点。回测跑 10 年数据中途挂掉，无法定位 |
| **计划解决** | Step 2 建一个最小的 `src/logging_config.py`（标准库 logging，输出到 stdout + 文件），后续每个模块引用统一 logger |

## #3 `save_to_parquet` 不创建目录

| 项 | 内容 |
|------|------|
| **重要性** | 低 |
| **位置** | `src/data_pipeline.py:43-45` |
| **现象** | `df.to_parquet(path)` 在目标目录不存在时直接抛 FileNotFoundError |
| **后果** | 当前 `data/.gitkeep` 保证了目录存在。但若目录被误删或 CI 环境未初始化，保存会挂 |
| **计划解决** | Step 7（信号生成器开始写 data/ 时），`save_to_parquet` 内部加 `os.makedirs(os.path.dirname(path), exist_ok=True)` |
