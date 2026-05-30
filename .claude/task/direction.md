# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 执行纪律（强制）

**每步完成 → 验证通过 → 提交 → 再进行下一步。** 禁止批量执行后统一提交。

---

## 当前任务：修复 T+1 现金泄漏 + 重跑 Look-Ahead Bias

### 背景

上次 look-ahead bias 验证（Sharpe 1.23 → 0.02）不可信。`src/backtest_engine.py` 的 T+1 实现存在现金泄漏 bug：

```python
# line 162 — 当前（错误）
repo_cash = exec_alloc["repo_amount"]
```

**泄漏机制**：

```
T 日：NAV = 1M → alloc = {positions: 600K, repo: 0} → 存入 pending_alloc
T+1 日：持仓涨了 → NAV = 1.05M
       exec_alloc = T 日 alloc = {positions: 600K, repo: 0}
       → positions 只买 600K 股票 + repo_cash = 0
       → 净值 600K，但 NAV 是 1.05M，50K 市值涨幅凭空消失
```

每天泄漏当天市值变动量，12 年累积把策略漏穿。这不是真实的 look-ahead bias，是实现错误。

### 步骤 1：修复现金泄漏

修改 `src/backtest_engine.py` line 162 附近，将 `repo_cash` 从执行 alloc 取值改为**残差计算**：

```python
# 改后：现金 = NAV - 持仓市值（保证现金守恒）
positions = {}
if exec_alloc is not None:
    for name, target_dollar in exec_alloc["positions"].items():
        ...
        positions[name] = target_dollar / price
# repo_cash 总是残差，不依赖 alloc 来源
positions_value = sum(
    positions.get(name, 0.0) * prices[name].loc[exec_day, "close"]
    for name in positions
    if name in prices and exec_day in prices[name].index
)
repo_cash = nav - positions_value
```

注意 `nav` 是当天已更新的净值（line 111），`exec_day` 的收盘价用于计算持仓市值。

同时修复 `pending_alloc` 初始化为 None 的问题：首日直接执行（不延迟），避免空仓期。

### 步骤 2：重跑 Look-Ahead Bias

修改 `scripts/check_lookahead_bias.py`（如需要更新参数），重跑全量 2014-2026 对比：

| 指标 | 原版（T 日成交） | 修正版（T+1 成交） | 差异 |
|------|---------------|-------------------|------|
| 总收益 | | | |
| Sharpe | | | |
| 最大回撤 | | | |

**预期**：纯防御 ΔSharpe < 0.05（MA40 对一日延迟不敏感）。

### 步骤 3：决策

- ΔSharpe < 0.05 → 记录结论，引擎保持 T+0 默认，不改
- ΔSharpe ≥ 0.05 → 分析差异来源，待顾问决策

### 验收标准

- 现金泄漏修复后，T+0 和 T+1 的净值曲线走势一致（差异 < 几个百分点）
- 全量测试零回归
- 明确量化真实的 look-ahead bias 量级

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
