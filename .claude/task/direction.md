# 执行指令

> 2026-07-13 | 回测引擎修正：execution_lag=1 执行价从收盘改为开盘

## 背景

[backtest_engine.py:205](src/backtest_engine.py#L205) 写死用 `close` 做执行价。实盘流程是"T日收盘出信号 → T+1日开盘执行"，但回测用 T 日收盘价执行 T-1 的信号，导致：
- 07-13 回测：持仓 50%创业板（来自 07-09 过时信号）贯穿全天，吃满 -2.87% 跌幅后才在收盘"卖出"
- 07-13 实盘：开盘即按 07-10 信号卖出创业板，不承担当日跌幅
- 结果：策略 Δ% 显示 -1.22%，实盘约 -0.28%

**parquet 里 open 列数据完整，只是从未被回测引擎使用。**

## 步骤

### 步骤 1 — 修正 backtest_engine.py

**文件**：`src/backtest_engine.py`

**改动**：`execution_lag=1` 时，执行顺序调整为 **先执行 → 再估值 → 再信号**，执行价用 `open`。

具体改动点：

**1a. 执行价改用 open（约第 205 行附近）**

```python
# 当前（所有情况都用 close）
price = prices[name].loc[exec_day, "close"]

# 改为：execution_lag=1 时用 open
price_col = "open" if execution_lag == 1 else "close"
price = prices[name].loc[exec_day, price_col]
```

**1b. 调仓循环提前到估值之前（execution_lag=1 时）**

当前循环顺序：
```
repo 利息 → 估值(close) → 信号 → alloc → 执行(close)
```

改为：
```
repo 利息 → 执行(open) → 估值(close) → 信号 → alloc
```

注意：估值步骤仍然用 close（反映当日持仓在收盘时的真实价值），只是执行价改为 open。

**1c. 现金守恒用 prev_nav**

执行提前后，`repo_cash = nav - positions_value - commission` 里的 `nav` 尚未更新。改用上一日收盘 NAV：

```python
repo_cash = prev_nav - positions_value_at_open - total_commission
```

**1d. execution_lag=0 保持不变**

所有改动仅在 `execution_lag == 1` 分支生效。lag=0 的路径（当日收盘价成交，学术回测）不碰。

### 步骤 2 — 跑全量测试

```bash
cd "d:/AI项目/003-quant-etf"
python -m pytest tests/ -v
```

必须全绿。

### 步骤 3 — 重新生成 2026-01-01 起的全部图表数据

```bash
cd "d:/AI项目/003-quant-etf"
python scripts/nav_chart.py
```

这将重新跑回测、重新生成 `nav_2026.html`。

### 步骤 4 — 验证

检查 07-13 的策略 Δ%：
- 修正前：-1.22%（含过时的创业板暴露）
- 修正后：应接近 -0.28%（开盘已换为 100% 纳指，仅承担纳指当日跌幅 × combined_mult）

## 约束

- `execution_lag=0` 路径不改任何逻辑
- 估值步骤始终用 close（反映持仓市场价值）
- `backtest_engine.py` 在 `protected-files.json` 中（第12行），修改前必须走 validate → audit 流程
- 每步提交，不跨步
