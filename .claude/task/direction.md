# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：股债相关性熔断鲁棒性扫描

### 背景

熔断是系统最强防线（ablation ΔSharpe +0.85），但三个参数从未扫描：corr_window=60, corr_sma_window=5, corr_threshold=0.0。需回答：0.0 这个阈值脆弱吗？

### 步骤 1：smoothed_corr 历史分布

```python
from src.backtest_engine import run_backtest
from src.signal_generator import DEFAULT_PARAMS
import pandas as pd, numpy as np
import copy

names=['沪深300','创业板','纳指','黄金','国债ETF']
codes=['510300','159915','513100','518880','511010']
prices={n:pd.read_parquet(f'data/{c}.parquet') for n,c in zip(names,codes)}

# 跑一次全回测提取所有 smoothed_corr
r = run_backtest(prices, 1000000, params=copy.deepcopy(DEFAULT_PARAMS))
# 从 signal 中逐日提取... 需要修改 recorder 或从 backtest_engine 抓取

# 或者：独立计算全期 smoothed_corr 序列（不用回测）
from src.correlation_circuit_breaker import stock_basket_returns, rolling_correlation
# 对每只股票计算 log 收益 → 等权篮子 → 与国债做 60 日滚动相关 → 5日 SMA
```

输出：
- smoothed_corr 的均值、标准差、min/max
- 分位数：50%/75%/90%/95%/99%
- 突破各阈值的交易日数：>0.0, >0.05, >0.1, >0.15, >0.2, >0.3
- smoothed_corr 时序图数据（日期 + 值，存 CSV）

### 步骤 2：corr_threshold 敏感性扫描

Patch signal_generator DEFAULT_PARAMS 的 corr_threshold，扫描：
[-0.1, -0.05, 0.0, 0.05, 0.10, 0.15]

每档跑一次 `run_backtest()`，记录：Sharpe、年化、回撤、CB 触发天数、CB 触发占比。

输出对比表：

| threshold | 触发天数 | 触发% | Sharpe | 年化 | 回撤 |
|------|------|------|------|------|------|

### 步骤 3：corr_window 敏感性扫描

固定 corr_threshold=0.0, corr_sma_window=5，扫描：
corr_window = [20, 40, 60, 90, 120]

输出同上格式对比表。

### 步骤 4：corr_sma_window 敏感性扫描

固定 corr_threshold=0.0, corr_window=60，扫描：
corr_sma_window = [1, 3, 5, 10, 20]

输出同上格式对比表。

### 步骤 5：结论写入

将步骤 1-4 的结果写入 `attribution/system_audit.md`，替换 §5.4（未测敏感度）表格，新增 §5.5（熔断鲁棒性评估）。

### 验收

- [ ] smoothed_corr 全期分布统计完成
- [ ] 三维扫描结果（threshold/window/sma）
- [ ] `attribution/system_audit.md` 已更新
- [ ] 确认阈值 0.0 的鲁棒裕量

### 审核协议

步骤 2-4 中 corr_window/corr_sma_window/corr_threshold 在 `protected-contracts.json` 为受保护值，需走内容级保护：
1. 扫描脚本使用临时参数副本（不修改 DEFAULT_PARAMS），仅读取
2. 如最终需修改生产值，走完整 CLI validate + audit 流程
