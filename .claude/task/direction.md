# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet                ✅ 已完成
Step 2  趋势强度      年化收益率 / 年化波动率            ✅ 已完成
Step 3  截面动量      20+60 日 z-score 合成排名          ✅ 已完成
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带            ✅ 已完成
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA            ✅ 已完成
Step 6  回撤硬止损    8/12/18 三层                        ← 当前
Step 7  信号生成器    编排 Step 2-6
Step 8  组合管理器    仓位计算 + 资金路由
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 6 — 回撤硬止损

### 背景

回撤硬止损是系统的最后一道防线（方向性讨论.md 决策链第五关）。当组合净值从历史峰值回撤超过阈值时，强制降仓或清仓，不对市场方向做任何判断——只认回撤数字。

```
回撤 = (当前净值 - 历史峰值) / 历史峰值

8%  告警   → 仓位不变（仅通知），position_multiplier = 1.0
12% 减半   → 仓位降至 50%，position_multiplier = 0.5
18% 清仓   → 清空所有风险资产，position_multiplier = 0.0
```

阈值单向递增：一旦触发高级别，不因回撤缩小而降级（例如从 18% 清仓跌回 10% 不会自动复仓——复仓由趋势强度信号决定，不在本模块职责内）。本模块只负责根据**当前**回撤给出仓位乘数。

### 任务

`src/drawdown_stop.py` — 两个函数：

```python
compute_drawdown(portfolio_values: pd.Series) -> pd.Series
"""
计算滚动回撤序列。
portfolio_values: 组合净值 Series，index=日期 DatetimeIndex，按时间升序。
返回: 回撤 Series（负小数，如 -0.12 表示回撤 12%），index 同输入。
公式: (value - running_max) / running_max
running_max 为到当日为止的历史最高净值（含当日）。
"""

drawdown_stop(drawdown: float) -> dict
"""
根据当前回撤返回止损信号。
drawdown: 当前回撤值（负小数，如 -0.12 表示回撤 12%）。
返回: {
    "level": str,              # "normal" | "warning" | "halve" | "liquidate"
    "position_multiplier": float,  # 1.0 | 1.0 | 0.5 | 0.0
}
阈值（取绝对值比较）：
  |d| < 0.08  → normal,   1.0
  0.08 ≤ |d| < 0.12 → warning,  1.0
  0.12 ≤ |d| < 0.18 → halve,    0.5
  |d| ≥ 0.18 → liquidate, 0.0
"""
```

### 测试（先写，必须红灯）

`tests/test_drawdown_stop.py` — 5 个场景：

1. **无回撤**：净值单调上涨 [100, 101, 102, 103, 104, 105]。验证最新 drawdown = 0.0，level="normal"，multiplier=1.0。

2. **各层触发**：构造从峰值 100 跌到不同价位的场景：
   - 跌到 93 → |d|=7% → normal
   - 跌到 90 → |d|=10% → warning
   - 跌到 86 → |d|=14% → halve
   - 跌到 80 → |d|=20% → liquidate
   逐一验证 level 和 multiplier。

3. **先新高后回撤**：净值先涨到 150（新高），再跌到 120。验证 drawdown = (120-150)/150 = -20%，触发 liquidate（不是基于初始 100 计算）。

4. **回撤恢复**：净值 100→50（回撤 50%）→ 触发 liquidate → 但之后反弹到 90。验证 drawdown 仍为 (90-100)/100 = -10%（running_max 仍是 100），不因反弹而"复仓"。

5. **compute_drawdown 序列**：构造固定序列 [100, 110, 95, 85]，验证返回的 drawdown Series 为 [0, 0, 95/110-1, 85/110-1]（前两个峰值日 drawdown=0）。

### 约束

- 不写信号生成器、组合管理器等后续模块代码
- `compute_drawdown` 使用 `expanding().max()` 或 `cummax()`
- 阈值比较取绝对值：`abs(drawdown)` 与 0.08/0.12/0.18 比较
- `drawdown_stop` 输入是标量 float（通常是 `compute_drawdown` 返回序列的最后一个值）

### 验收标准

- [ ] `python -m pytest tests/test_drawdown_stop.py -v` — 5/5 绿
- [ ] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py tests/test_target_volatility.py tests/test_correlation_circuit_breaker.py -v` — 旧测试不红
- [ ] `python -c "from src.drawdown_stop import compute_drawdown, drawdown_stop; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 6"。
> 顾问审核通过并 commit 后，更新本文 Step 7。
> 禁止跳过步骤，禁止一次完成多步。
