# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet                ✅ 已完成
Step 2  趋势强度      年化收益率 / 年化波动率            ✅ 已完成
Step 3  截面动量      20+60 日 z-score 合成排名          ✅ 已完成
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带            ✅ 已完成
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA            ✅ 已完成
Step 6  回撤硬止损    8/12/18 三层                        ✅ 已完成
Step 7  信号生成器    编排 Step 2-6                        ✅ 已完成
Step 8  组合管理器    仓位计算 + 资金路由                  ✅ 已完成
Step 9  Recorder      日志记录 + 基准计算                  ✅ 已完成
Step 10 回测主循环    日循环 + 参数扫描入口                ← 当前
```

## 当前步骤：Step 10 — 回测主循环

### 背景

回测主循环是系统的运行时引擎。每天推进一次：拉取当日数据 → 生成信号 → 分配仓位 → 计算当日收益 → 记录状态。循环结束后输出完整的回测报告。

```
初始资金 1,000,000
    │
    ▼  (每日循环)
┌─────────────────────────────────┐
│ 1. 截取当日可见数据 ([:today])  │
│ 2. generate_signal()            │
│ 3. allocate_capital()           │
│ 4. 计算当日组合收益              │
│ 5. record_daily()               │
└─────────────────────────────────┘
    │
    ▼
回测报告: NAV 曲线 + 基准对比 + 绩效指标
```

### 任务

`src/backtest_engine.py` — 两个函数：

```python
run_backtest(
    prices: dict[str, pd.DataFrame],
    initial_capital: float = 1_000_000,
    params: dict | None = None,
    min_days: int = 120,
) -> dict
"""
运行完整回测。

prices: {标的名: OHLCV DataFrame}，所有 DataFrame 需对齐到同一日期范围。
initial_capital: 初始资金。
params: 传给 generate_signal 的参数。
min_days: 最少需要的数据天数（trend_window + corr_window + sma_window 缓冲）。

返回: {
    "records_df": pd.DataFrame,      # get_records_df 输出
    "benchmark_nav": pd.Series,      # 基准净值
    "final_nav": float,              # 最终净值
    "final_benchmark_nav": float,    # 基准最终净值
    "total_return": float,           # 策略总收益率
    "benchmark_return": float,       # 基准总收益率
    "annual_return": float,          # 策略年化收益率
    "annual_volatility": float,      # 策略年化波动率
    "sharpe_ratio": float,           # 夏普比率
    "max_drawdown": float,           # 最大回撤（负小数）
    "calmar_ratio": float,           # 卡玛比率
}

日循环逻辑：
1. 确定日期范围：prices 中所有标的日期 index 的交集
2. 初始状态：nav = initial_capital, cash = initial_capital（全现金起步）
3. 建立持仓跟踪：positions = {}  # {name: shares}
4. for each t in range(min_days, len(dates)):
     today = dates[t]
     visible_prices = {name: df.loc[:today] for name, df in prices.items()}

     # 生成信号 + 分配资金
     signal = generate_signal(visible_prices, nav_series[:t+1], params)
     alloc = allocate_capital(signal, nav)

     # 执行调仓（简化：按目标金额直接调整，忽略滑点/手续费）
     target_positions = alloc["positions"]  # {name: dollar_amount}
     for name, target_dollar in target_positions.items():
         price = prices[name].loc[today, "close"]
         positions[name] = target_dollar / price  # 转为股数

     # 计算当日组合价值
     nav = sum(positions[name] * prices[name].loc[today, "close"]
               for name in positions)
     nav += alloc["repo_amount"]  # 逆回购现金（不产生日收益，简化处理）

     # 构建 nav_series（用于下次 signal 的 drawdown 计算）
     nav_series[t] = nav

     # 记录
     record_daily(recorder, str(today.date()), nav, signal, alloc["positions"])

5. 循环结束后计算绩效指标
6. 计算基准净值（同日期范围）
7. 返回结果
```

```python
parameter_scan(
    prices: dict[str, pd.DataFrame],
    param_grid: dict[str, list],
    initial_capital: float = 1_000_000,
) -> list[dict]
"""
参数扫描入口。
param_grid: {"trend_window": [40, 60, 80], "target_vol_beta": [0.08, 0.10, 0.12], ...}

对每个参数组合调用 run_backtest(prices, initial_capital, params=combo)，
返回按 Sharpe 降序排列的结果列表。

每个元素 = {**params_combo, **run_backtest 返回的绩效指标}。
"""
```

### 关键简化（本步明确接受）

- **滑点/手续费**：不模拟。在 Step 10 阶段先验证逻辑正确性，交易成本留到模拟实盘阶段（方向性讨论 阶段 6）再引入。
- **逆回购收益**：repo 现金不产生日收益（GC001 年化 ~2%，每日 ~0.005%，对回测影响可忽略）。
- **整数股数**：使用浮点股数。A 股 ETF 最小交易单位 100 份，取整留到模拟实盘阶段。
- **调仓执行**：每次调仓按当日收盘价直接成交，无延迟。

### 测试（先写，必须红灯）

`tests/test_backtest_engine.py` — 3 个场景：

1. **全绿场景回测**：构造 5 只防御标的全部单边上涨、股债负相关的 200 天合成数据。运行 run_backtest。验证 final_nav > 1.0，records_df 行数 = 200 - min_days，max_drawdown > -0.05（牛市无大幅回撤）。

2. **下跌市回撤止损**：构造先涨后暴跌的场景（峰值后回撤 25%）。验证回测过程中 drawdown_stop 至少触发过 "halve" 或 "liquidate"，max_drawdown 不超过某个可控范围。

3. **参数扫描**：构造 2×1 参数网格（如 trend_window=[60, 80]）。验证 parameter_scan 返回 2 条结果，各有不同参数，按 Sharpe 降序。

### 约束

- 回测引擎是最后的模块，它依赖 Step 1-9 全部模块，但不修改任何已有代码
- `nav_series` 从初始资金 1.0 开始逐日构建，用于 drawdown 计算
- `parameter_scan` 中每个参数组合独立运行，互不干扰
- 日期对齐使用 pandas index.intersection

### 验收标准

- [ ] `python -m pytest tests/test_backtest_engine.py -v` — 3/3 绿
- [ ] `python -m pytest tests/ -v` — 全部不红（AKShare 相关 skip 除外）
- [ ] `python -c "from src.backtest_engine import run_backtest, parameter_scan; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 10"。
> 至此 10 步回测开发计划全部完成。
