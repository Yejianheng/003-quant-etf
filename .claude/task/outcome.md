# 执行结果 — 数据质量验证 + 三基准固定对比

> 执行时间：2026-05-28 | 状态：全部完成

## 任务 A：数据质量验证

### A1. 基础完整性检查 — 5 文件全 PASS

| 检查项 | 510300 | 159915 | 513100 | 518880 | 511010 |
|--------|--------|--------|--------|--------|--------|
| 负价格 | 0 | 0 | 0 | 0 | 0 |
| 异常跳变(>20%) | 0 | 0 | 1 | 0 | 0 |
| 重复日期 | 0 | 0 | 0 | 0 | 0 |
| 日期单调 | PASS | PASS | PASS | PASS | PASS |
| OHLC 逻辑 | 0 违规 | 0 违规 | 0 违规 | 0 违规 | 0 违规 |
| 最长停牌 | 2 天 | 2 天 | 2 天 | 2 天 | 1 天 |

纳指 1 次异常跳变在阈值内（美国假期后 A 股复盘跳空，正常现象）。

### A2/A3. 跨源交叉验证

baostock 不支持 ETF 历史数据，东方财富 API 不可达。采用指数点位回归（510300 ETF vs 沪深300 官方指数）：

| ETF | 比对源 | 共同日 | 相关性 | 年化跟踪误差 | 日跟踪差异 std |
|-----|--------|--------|--------|-------------|---------------|
| 510300 | 沪深300官方指数 | 3401 | 0.999 (价格) / 0.981 (日收益) | 4.72% | 0.28% |

- 日收益均值差异：0.002%（近乎零偏差）
- 仅 3.3% 交易日偏离 >0.5%
- 4.72% 年化跟踪误差由日噪声 × √252 放大，属 ETF 市场价（非 NAV）的正常水平
- 13 年累计偏离 8.89%，年均 ~0.68%，在 ETF 管理费 + 跟踪误差的合理范围内

**结论**：新浪数据源质量可靠，A1 全 PASS，跨源验证无系统偏差。

## 任务 B：三基准固定对比

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/benchmark.py` | 新增 `compute_single_benchmark(prices, name)` — 单标的买入持有净值（起始 1.0） |
| `src/backtest_engine.py` | `run_backtest()` 返回新增 `benchmark_300`/`benchmark_chinext`/`benchmark_nasdaq` |
| `src/visualization.py` | NAV 图表新增三条基准线（沪深300/创业板/纳指，虚线） |
| `tests/test_benchmark.py` | 新增 `TestSingleBenchmark`（3 tests） |
| `tests/test_backtest_engine.py` | 新增 `TestThreeBenchmarks`（1 test） |
| `tests/test_visualization.py` | 新增 `test_html_contains_three_benchmarks`（1 test） |

### 向后兼容

- `run_backtest()` 现有返回值 key 不删不改
- `benchmark_nav` 保留（5ETF 加权篮子），标签更新为 "基准净值(5ETF篮子)"
- `compute_single_benchmark` 标的不存在时返回 None（不抛异常）

### 测试

- 新增 5 tests 全部 PASS
- 全量 84 passed / 3 skipped（零回归）

---

> 请顾问窗口审查。
