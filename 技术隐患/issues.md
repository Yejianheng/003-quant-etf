# 待解决隐患

> 按重要性降序。解决时间关联回测开发步骤（Step 1-10）。

## #1 异常静默吞没 — `fetch_etf_daily` ~~已解决~~

| 项 | 内容 |
|------|------|
| **重要性** | 高 |
| **位置** | `src/data_pipeline.py:31-54` |
| **解决** | 2026-05-27：① 3 次指数退避重试（2s/4s/8s）② `requests.Session.trust_env=False` monkey-patch 绕过 VPN 残留代理 ③ 异常日志含错误类型 + 排查建议 ④ 空数据返回带 info 日志区分网络错误 vs 非交易日 |
| **附加** | `pre_bash.js` 新增分时限流层（滑动窗口 60s/3→60s 冷却/6→120s 冷却，东方财富最低间隔 5s，会话预算 300 次） |

## #2 无日志/可观测性机制 ~~已解决~~

| 项 | 内容 |
|------|------|
| **重要性** | 中 |
| **解决** | Step 2 已创建 `src/logging_config.py` — `get_logger(name)` 统一 logger，格式 `时间 | 级别 | 名称 | 消息`，输出到 stdout + `logs/app.log`。`data_pipeline.py` 已接入。 |

## #3 `save_to_parquet` 不创建目录

| 项 | 内容 |
|------|------|
| **重要性** | 低 |
| **位置** | `src/data_pipeline.py:43-45` |
| **计划解决** | Step 7（信号生成器开始写 data/ 时），`save_to_parquet` 内部加 `os.makedirs(os.path.dirname(path), exist_ok=True)` |

## #4 AKShare `fund_etf_hist_em` 返回空 DataFrame ~~已解决~~

| 项 | 内容 |
|------|------|
| **重要性** | 高 |
| **发现时间** | 2026-05-27 Step 2 执行时 |
| **根因** | ① VPN 客户端（Clash）设置 Windows 系统代理 `127.0.0.1:7890`，关闭 VPN 后代理开关关闭但注册表残留 ② `requests` 库通过 `get_environ_proxies()` 读取残留代理，无需环境变量即可走代理 ③ 东方财富对 `/api/qt/stock/kline/get` 路径有严格反爬 + 限流（~1-2 次/分钟后断连） |
| **解决** | `data_pipeline.py` 模块加载时 monkey-patch `requests.Session.__init__` 设 `trust_env=False`，绕过 Windows 注册表代理。`pre_bash.js` 加分时限流防止触发东方财富反爬。测试层加 `pytest.skip` 容错。 |
