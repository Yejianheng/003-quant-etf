# 执行结果 — P0/P1 补测（新增测试方案）

> 执行时间: 2026-05-30 | 状态: 全部完成 | 验收: 待顾问审查

---

## 步骤 1：Golden Dataset（P0-1）

**产出**：
| 文件 | 行数 | 说明 |
|------|------|------|
| `output/golden_nav.csv` | 2175 | NAV 日序列 |
| `output/golden_signals.csv` | 2175 | 12 列信号日序列 |
| `output/golden_positions.csv` | 2175 | 5 列持仓市值日序列 |
| `output/golden_trades.csv` | 4978 | 交易记录 |

固定数据：防御 5 ETF，截止 2022-12-31，参数 `trend_window=40, ewma_lambda=0.94, target_vol_beta=0.10, corr_threshold=0.0, defense_ratio=1.0`。

**引擎改动**：
- `recorder.py`：`record_daily` 新增 `positions_detail` 可选参数
- `backtest_engine.py`：返回 `_recorder`，传递持仓明细

**测试**：7 条全绿（NAV 逐行一致 / signals 集合一致 / positions 1 元容差 / trades 计数一致 / 确定性验证 / 参数敏感性 / 边界）

---

## 步骤 2：生存者偏差审计（P0-3）

**上市日期校正**（方向性讨论中 3 只有误）：

| ETF | 原记录 | 实际上市日 | 数据开始日 | 判定 |
|-----|--------|-----------|-----------|------|
| 510300 沪深300 | 2012-05-28 ✓ | 2012-05-28 | 2012-05-28 | OK |
| 159915 创业板 | 2011-09-22 ✗ | 2011-12-09 | 2011-12-09 | 原为成立日 |
| 513100 纳指 | 2013-05-15 ✓ | 2013-05-15 | 2013-07-31 | OK |
| 518880 黄金 | 2013-06-24 ✗ | 2013-07-29 | 2013-07-29 | 原为发行日 |
| 511010 国债ETF | 2013-06-18 ✗ | 2013-03-25 | 2013-04-09 | 原记录错误 |

**验证**：
- 五只 ETF 数据开始日均 ≥ 实际上市日（无前视偏差）
- `get_available_etfs` min_history 正确排除数据不足的 ETF
- data/ 下 28 个 parquet 文件均可追溯到代码引用（无退市残留）

**测试**：11 条全绿

---

## 步骤 3：熔断阈值敏感性扫描（P1-8）

**结果**：

| 阈值 | Sharpe | 年化 | 最大回撤 | liquidate 天数 | 恢复天数 |
|------|--------|------|---------|---------------|---------|
| 0.15 | 1.23 | 14.0% | -13.4% | 0 | 0 |
| 0.18 | 1.23 | 14.0% | -13.4% | 0 | 0 |
| 0.20 | 1.23 | 14.0% | -13.4% | 0 | 0 |
| 0.25 | 1.23 | 14.0% | -13.4% | 0 | 0 |

**关键发现**：四阈值结果完全一致。2014-2026 全周期内最大回撤 -13.4%，halve@12% 已有效控制回撤至 <15%，所有 liquidate 阈值均未触发。

**判定**：
- 0.18 在合理区间 [PASS]
- 策略对阈值不敏感（回撤极差 0%）[PASS]

**测试**：6 条引擎测试 + 4 条脚本测试，全绿

---

## 全量回归

300 passed, 0 new failures, 3 skipped（预存 `test_loads_summary` 1 failed 与本次无关）

## 改动文件

| 文件 | 操作 | 步骤 |
|------|------|------|
| `src/recorder.py` | 修改 | 步骤1 |
| `src/backtest_engine.py` | 修改 | 步骤1 |
| `scripts/generate_golden_dataset.py` | 新增 | 步骤1 |
| `tests/test_generate_golden_dataset.py` | 新增 | 步骤1 |
| `output/golden_nav.csv` | 新增 | 步骤1 |
| `output/golden_signals.csv` | 新增 | 步骤1 |
| `output/golden_positions.csv` | 新增 | 步骤1 |
| `output/golden_trades.csv` | 新增 | 步骤1 |
| `tests/test_survivorship_bias.py` | 新增 | 步骤2 |
| `tests/test_threshold_sensitivity.py` | 新增 | 步骤3 |
| `tests/test_scan_dd_threshold.py` | 新增 | 步骤3 |
| `scripts/scan_dd_threshold.py` | 新增 | 步骤3 |
| `output/threshold_sensitivity.csv` | 新增 | 步骤3 |

## 提交记录

| 提交 | 内容 |
|------|------|
| `v1-20260530-135` | 步骤1：Golden Dataset — 4 基准文件 + 引擎改动 + 7 测试 |
| `v1-20260530-136` | 步骤2：生存者偏差审计 — 上市日期校正 + 11 测试 |
| `v1-20260530-137` | 步骤3：熔断阈值敏感性扫描 — 四阈值对比 + 10 测试 |

---

> 请顾问窗口审查。
