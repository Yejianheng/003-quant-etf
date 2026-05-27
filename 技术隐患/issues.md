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

## #2 无日志/可观测性机制 ~~已解决~~

| 项 | 内容 |
|------|------|
| **重要性** | 中 |
| **位置** | 全局 |
| **现象** | 项目无统一日志模块。数据拉取成功/失败、API 调用耗时、异常堆栈均无记录 |
| **后果** | Step 3+ 模块增多后，排查问题只能靠 print 或断点。回测跑 10 年数据中途挂掉，无法定位 |
| **解决** | Step 2 已创建 `src/logging_config.py` — `get_logger(name)` 统一 logger，格式 `时间 \| 级别 \| 名称 \| 消息`，输出到 stdout + `logs/app.log`。后续模块通过 `logger = get_logger(__name__)` 引用。 |

## #3 `save_to_parquet` 不创建目录

| 项 | 内容 |
|------|------|
| **重要性** | 低 |
| **位置** | `src/data_pipeline.py:43-45` |
| **现象** | `df.to_parquet(path)` 在目标目录不存在时直接抛 FileNotFoundError |
| **后果** | 当前 `data/.gitkeep` 保证了目录存在。但若目录被误删或 CI 环境未初始化，保存会挂 |
| **计划解决** | Step 7（信号生成器开始写 data/ 时），`save_to_parquet` 内部加 `os.makedirs(os.path.dirname(path), exist_ok=True)` |

## #4 AKShare `fund_etf_hist_em` 返回空 DataFrame

| 项 | 内容 |
|------|------|
| **重要性** | 高 |
| **发现时间** | 2026-05-27 Step 2 执行时 |
| **位置** | `src/data_pipeline.py:10-17` `fetch_etf_daily` → 调 `ak.fund_etf_hist_em()` |
| **现象** | 调用 `fetch_etf_daily("510300", "2024-01-01", "2024-01-31")` 返回空 DataFrame。Step 1 提交时该测试通过（commit `501cdde`），当前同一代码失败。 |
| **排查** | 1. 确认参数格式无误（与 Step 1 测试完全一致） 2. 尝试换日期范围（2024-01-01 ~ 2024-06-30）同样返回空 3. Step 1 测试 `test_fetch_returns_dataframe_with_required_columns` 同样失败（原是绿变红）→ 排除代码变更引入 |
| **根因推断** | AKShare 东方财富 ETF 历史接口可能限流、后端 API 地址变更、或临时网络不可达。`fund_etf_hist_em` 依赖东方财富公开接口，历史上发生过类似断连。 |
| **影响面** | - Step 1 安全线测试：1/3 红 - Step 2 真实数据测试：已加 skip 空数据保护，暂不影响绿灯 - **未来所有依赖真实数据的测试均受影响** |
| **计划解决** | Step 2 合入后立即排查。方案：① 抓包确认东方财富接口是否可达 ② 升级 AKShare 版本尝试 ③ `fetch_etf_daily` 加超时/重试 + 异常详情日志（配合 #2 日志模块）④ 测试用 mock 数据替代，减少对 AKShare 实时依赖 |
| **临时措施** | Step 2 测试场景 4（真实数据往返）加入 `pytest.skip`，AKShare 空数据时跳过而非报错。 |
