# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。
> 2026-06-18 | 收工轮 — 补全报表 + 最终结论

## 当前状态

- 代码层完整，23/23 全绿
- 数据 21 年（2005-2026），外部数据源已穷尽
- 策略 Sharpe 0.86（TLT），结论方向已明确
- **待补**：逐年表不完整、A/B 对照区间不一致

## 本轮目标

不改代码，只补数据。最终产出完整 outcome。

---

## 步骤 1：补全逐年表现表

**不改 `scripts/backtest_us.py`，直接写一个一次性脚本来提取逐年数据：**

```bash
python -c "
import sys; sys.path.insert(0, '.')
import pandas as pd
from scripts.backtest_us import fetch_us_data, run_us_backtest, US_TICKERS

# 拉取数据（用缓存或重拉）
prices = fetch_us_data(US_TICKERS, start='2005-01-01', end='2026-06-18')
result = run_us_backtest(prices, 'TLT')
records = result['records_df']
records['date'] = pd.to_datetime(records['date'])
records['year'] = records['date'].dt.year

# 计算策略逐年收益
yearly = records.groupby('year').agg(
    nav_start=('nav', 'first'),
    nav_end=('nav', 'last'),
    cb_pct=('circuit_breaker_triggered', 'mean'),
).reset_index()
yearly['策略'] = yearly['nav_end'] / yearly['nav_start'] - 1

# 计算 SPY 基准逐年收益
spy_close = prices['SPY']['close']
spy_yearly = spy_close.resample('YE').agg(['first', 'last']).dropna()
spy_yearly['SPY'] = spy_yearly['last'] / spy_yearly['first'] - 1

# 合并输出
merged = yearly.merge(spy_yearly[['SPY']], left_on='year', right_index=True, how='left')
for _, row in merged.iterrows():
    y = int(row['year'])
    s = row['策略']
    sp = row.get('SPY', float('nan'))
    ytd = ' YTD' if y == 2026 else ''
    print(f\"| {y}{ytd} | {s:+.1%} | {sp:+.1%} | |\")
"
```

输出每年一行（2005-2026 共 22 行），填充到 outcome 逐年表中。

---

## 步骤 2：同区间 A 股对照

当前 A/B 对照区间不一致（A 股 2012-2026 vs 美股 2005-2026）。需要一份**同区间**对比。

用上轮已有的 A 股数据（`data/` 目录 parquet），跑一次同区间（2005-2026 交集）的 A 股回测：

```python
# 加载 A 股数据，截取与美股回测相同的日期区间
# 跑 run_backtest(prices, execution_lag=1, params={"repo_rate": 0.02})
# 输出对比表
```

对照表格式：

| 指标 | A股版 | 美股版 | Δ |
|------|:--:|:--:|:--:|
| 区间 | 2005-2026 | 2005-2026 | 同区间 |
| 年化 | ? | 7.03% | |
| 波动率 | ? | 8.17% | |
| Sharpe | ? | 0.86 | |
| 最大回撤 | ? | -17.02% | |

如果同区间数据不可用（A 股 parquet 不全），则直接引用 system_audit.md 的 A 股数据并注明区间差异。

---

## 步骤 3：写 outcome.md（最终版）

必须包含以下全部内容：

### 3a. 数据覆盖

（引用上轮，无需重列）

### 3b. 久期对比

（引用上轮）

### 3c. 美股全期对照表

（引用上轮）

### 3d. 逐年表现（**完整 22 行，不可省略**）

| 年份 | 策略 | SPY | 60/40 | 备注 |
|------|:--:|:--:|:--:|------|
| 2005 | | | | |
| 2006 | | | | |
| 2007 | | | | |
| 2008 | | | | 🔴 金融危机 |
| 2009 | | | | |
| 2010 | | | | |
| 2011 | | | | |
| 2012 | | | | |
| 2013 | | | | |
| 2014 | | | | |
| 2015 | | | | |
| 2016 | | | | |
| 2017 | | | | |
| 2018 | | | | |
| 2019 | | | | |
| 2020 | | | | 🔴 COVID |
| 2021 | | | | |
| 2022 | | | | 🔴 加息 |
| 2023 | | | | |
| 2024 | | | | |
| 2025 | | | | |
| 2026 | | | | YTD |

### 3e. 2008 专项

（引用上轮）

### 3f. 2022 专项（新增）

| | 策略 | SPY | 60/40 |
|------|:--:|:--:|:--:|
| 年化 | | | |
| 最大回撤 | | | |
| 熔断天数 | | — | — |

### 3g. A 股 vs 美股同区间对照

### 3h. 最终结论

明确回答以下问题：
1. 策略逻辑是否跨市场成立？（是/否，证据）
2. A 股 vs 美股核心差异？（TLT vs SHY 最优久期、熔断频率、回撤水平）
3. 数据限制对结论的影响有多大？
4. 生产建议（是否可实盘、需补什么）
