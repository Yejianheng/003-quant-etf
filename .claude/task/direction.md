# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 执行纪律（强制）

**每步完成 → 验证通过 → 提交 → 再进行下一步。** 禁止批量执行后统一提交。

---

## 当前任务：修复 4.6 无趋势市场压力测试

### 背景

上次 `scripts/stress_no_trend.py` 的合成数据有缺陷：block bootstrap 对多资产统一采样，股债生成出强正相关 → 熔断 100% 触发 → 策略全程 repo → NAV 零变动 → 实际未测到趋势过滤在横盘中的表现。

### 修复要求

合成数据必须满足：

1. **股债负相关**：股票篮子（沪深300/创业板/纳指）共享一个随机源，债券（国债ETF）用独立或反向随机源
2. **黄金独立**：黄金用独立随机路径
3. **零均值**：所有路径累计收益 ≈ 0
4. **保留波动率特征**：每只 ETF 用各自历史数据的波动率参数生成

### 步骤 1：修复合成数据生成

修改 `scripts/stress_no_trend.py`：

```python
# 股票篮子：共享一个 log_return 序列（block bootstrap）
stock_returns = bootstrap(log_returns_沪深300, seed=42)

# 债券：独立 bootstrap — 确保与股票低/负相关
bond_returns = bootstrap(log_returns_国债ETF, seed=99)

# 黄金：独立路径
gold_returns = bootstrap(log_returns_黄金, seed=77)
```

使用不同 seed 确保三组收益率相关性接近真实历史水平。

**验证**：合成数据生成后，检查股债相关性：
```python
stock_stock_corr = np.corrcoef(synth_沪深300_returns, synth_创业板_returns)  # 应 > 0.5
stock_bond_corr = np.corrcoef(synth_沪深300_returns, synth_国债_returns)     # 应 < 0.2
```
不满足则调整 seed 重试。

### 步骤 2：重跑纯防御回测

| 场景 | 时长 | 预期 |
|------|------|------|
| 横盘 A（低波动）| 2 年 | 趋势过滤反复进场 → whipsaw 磨损 |
| 横盘 B（中波动）| 2 年 | whipsaw 更频繁 |
| 横盘 C（高波动）| 2 年 | 熔断可能触发，但不应全程触发 |

对比有/无趋势过滤在横盘区间内的净值路径。

### 步骤 3：量化失血速度

| 指标 | 值 |
|------|-----|
| 2 年横盘总磨损 | |
| 年化失血率 | |
| Whipsaw 次数 | |
| 最大回撤 | |
| 熔断触发天数占比 | ← 关键：不能是 100% |

### 验收标准

- 熔断触发占比 < 80%（不能全程 repo）
- 明确量化横盘环境下年化磨损率
- 全量测试零回归

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
