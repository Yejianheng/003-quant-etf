# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：数据质量验证 + 三基准固定对比

### 背景

数据源从东方财富被动切换到新浪（`fund_etf_hist_sina`），新浪源数据质量从未验证。如果 OHLCV 有系统偏差，前面全部回测结论不可靠。数据验证是第一优先级。

三基准固定对比是上轮已定事项，改动量小，作为第二项。

---

## 任务 A：新浪数据质量验证（优先）

### A1. 基础完整性检查

对 5 个 parquet 文件逐一检查：

| 检查项 | 方法 | 通过标准 |
|--------|------|---------|
| 无负价格 | `(df['close'] <= 0).any()` | 全 False |
| 无异常跳变 | 日收益率绝对值 > 20% 的次数 | ≤ 5 次/文件（停牌复牌可接受） |
| 无重复日期 | `df.index.duplicated().sum()` | 0 |
| 日期单调递增 | `df.index.is_monotonic_increasing` | True |
| OHLC 逻辑一致 | `low <= close <= high` 和 `low <= open <= high` | 违反率 < 0.1% |
| 停牌处理 | 连续相同 close 的最大天数 | ≤ 5 天（国庆/春节最长 7 天） |

输出检查结果表。

### A2. 跨源交叉验证

尝试至少一种第二数据源，比对关键数值差异。

**方案优先级**：

1. **东方财富**（同源比对最理想）：
   ```python
   import src.data_pipeline  # monkey-patch
   import akshare as ak
   # 仅拉 2024 年数据做比对样本（减少限流风险）
   df_em = ak.fund_etf_hist_em(symbol='510300', start_date='20240101', end_date='20241231', adjust='qfq')
   ```
   如果东方财富仍不可达 → 进入方案 2

2. **baostock**（免费免注册，推荐备选）：
   ```bash
   pip install baostock
   ```
   ```python
   import baostock as bs
   bs.login()
   rs = bs.query_history_k_data_plus('sh.510300', 'date,open,high,low,close,volume', start_date='2024-01-01', end_date='2024-12-31', frequency='d', adjustflag='2')
   ```
   比对 2024 年 close 价格与新浪源的差异。

3. **指数点位回归**（兜底方案）：
   用 `ak.stock_zh_index_daily(symbol='sh000300')` 取沪深300 官方指数点位，计算 510300 ETF 净值与指数的跟踪偏离度。年化跟踪误差应 < 2%。

### A3. 比对输出

对比对成功的 ETF，输出：

| ETF | 比对源 | 日期数 | close 相关性 | 最大单日差异 | 年均差异 |
|-----|--------|--------|-------------|-------------|---------|
| 510300 | baostock/东方财富 | X | 0.99X | X.XX% | X.XX% |

---

## 任务 B：三基准固定对比

修改 `benchmark.py` + `backtest_engine.py`，使 `run_backtest()` 返回中固定包含三条买入持有基准：

- `benchmark_300`：沪深300 买入持有净值 Series
- `benchmark_chinext`：创业板买入持有净值 Series  
- `benchmark_nasdaq`：纳指买入持有净值 Series

现有 `benchmark_nav`（5ETF 加权篮子）保留不改名。

### 修改文件

**`src/benchmark.py`**：
- 新增 `compute_single_benchmark(prices, name)` 函数——对单个标的做买入持有净值计算，返回 Series（起始值 1.0）

**`src/backtest_engine.py`**：
- `run_backtest()` 返回 dict 新增三个 key：
  - `"benchmark_300"`: `compute_single_benchmark(prices, "沪深300")`（如不存在则 None）
  - `"benchmark_chinext"`: 同上创业板
  - `"benchmark_nasdaq"`: 同上纳指

**`src/visualization.py`**（如存在）：
- 如有基准线绘制逻辑，增加三条新基准线

**`tests/test_benchmark.py`**：
- 新增 `test_single_benchmark`：验证单标的买入持有净值计算

### 约束

- 只修改 `benchmark.py`、`backtest_engine.py`、`visualization.py`、`test_benchmark.py`
- 向后兼容：`run_backtest` 现有返回 key 不删不改
- 不触碰保护区

---

## 验收标准

- [ ] A1：5 文件全部通过基础完整性检查（输出检查表）
- [ ] A2：至少一种跨源比对完成（东方财富 / baostock / 指数回归）
- [ ] A3：比对结果 close 相关性 > 0.99，最大年度偏差 < 2%
- [ ] B：`run_backtest(prices)` 返回含 `benchmark_300`/`benchmark_chinext`/`benchmark_nasdaq`
- [ ] `python -m pytest tests/ -v` — 全量通过（新增测试也绿）

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
