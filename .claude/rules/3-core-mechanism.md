# 核心业务机制

## 实盘策略：50/50 A/B 组合（v186 确立）

> **50% A（无 sf）+ 50% B（sf+0.08）合并为单一等效公式 `combined_mult = (dd_mult + min(sf, dd_mult)) / 2`。defense_ratio = 1.00，进攻层完全搁置。**

### 为什么是组合而不是单一策略

| | 纯A 无sf | 纯B sf+0.08 | **50/50 组合** |
|---|---|---|---|
| Sharpe | 1.017 | 1.205 | **1.113** |
| 年化 | 11.72% | 8.94% | **10.35%** |
| 最大回撤 | -13.91% | -7.45% | **-9.93%** |
| 2018 | -8.6% | -3.6% | **-6.2%** |

纯 B Sharpe 最高但牛市被 sf 拖累收益。纯 A 收益最高但回撤最大。50/50 取两者之长——低波动时享受 A 的满仓，高波动时获得 B 的保护。等效公式自带"牛熊自动切换权重"。

### 等效单策略

A 和 B 持有同一批 ETF，只是仓位乘数不同。组合总仓位等效乘数：

```
combined_mult = (dd_mult + final_mult) / 2
              = (dd_mult + min(sf, dd_mult)) / 2
```

- **低波动（sf >= dd_mult）**：combined_mult = dd_mult，跟 A 一样满仓
- **高波动（sf < dd_mult）**：combined_mult = (dd_mult + sf) / 2，居于 A/B 之间

> 不需要跑两个账户。一个策略改乘数公式即可复现。

### 资产池（5 只 ETF）

| 名称 | 代码 | 角色 |
|------|------|------|
| 沪深300 | 510300 | A 股大盘 beta |
| 创业板 | 159915 | A 股成长/中小盘 |
| 纳指 | 513100 | 海外科技 beta |
| 黄金 | 518880 | 通胀/避险对冲 |
| 国债ETF | 511010 | 债券防御收益 |

### 六步决策链（每交易日执行）

**Step 1 — 趋势过滤（`trend_strength.py`）**

对每只 ETF 计算 `trend_strength = 年化收益率 / 年化波动率`（窗口 40 天）。`trend_strength > 0` 的 ETF 标记为 "active"，进入等权池。趋势为负的 ETF 被剔除。

> 因此组合持有的 ETF 数量在 0~5 之间动态变化。全部为负时空仓。

**Step 2 — 等权分配（`signal_generator.py`）**

active ETF 等权分配：`weight_i = 1 / N_active`。

**Step 3 — EWMA 波动率缩放（`target_volatility.py`）**

计算 active ETF 池的 EWMA 协方差矩阵（λ=0.94, 窗口 252 天）→ 组合预测波动率 → `scaling_factor = 0.08 / predicted_vol`。若 `|predicted - 0.08| ≤ 0.012` 则 sf=1.0（等比容忍带 = beta×15%）。

> sf 仅缩仓不加仓（被 `final_multiplier = min(sf, dd_mult)` 截断）。防御层最终乘数 `combined_mult = (dd_mult + min(sf, dd_mult)) / 2`。

**Step 4 — 股债相关性熔断（`correlation_circuit_breaker.py`）**

计算股票篮子（沪深300+创业板+纳指等权）与国债ETF 的 60 日滚动 Pearson 相关系数，经 5 日 SMA 平滑。**平滑值 > 0 则触发熔断** → 全部资金转入逆回购（年化 2%，零权益仓位）。

> 这是最强防线。Ablation 测试：关闭熔断 ΔSharpe -0.85。

**Step 5 — 回撤硬止损（`drawdown_stop.py`）**

| 回撤幅度 | 级别 | 仓位乘数 |
|---------|------|---------|
| < 8% | normal | 1.0 |
| 8% ~ 12% | warning | 1.0 |
| 12% ~ 18% | halve | 0.5 |
| ≥ 18% | liquidate | 0.0 |

**Step 6 — 资金路由（`portfolio_manager.py`）**

- 熔断触发 → positions = {}，全部 repo
- 正常 → 防御池 = total × defense_ratio × combined_mult → 按 target_weights 分配
  - `combined_mult = (dd_mult + final_mult) / 2 = (dd_mult + min(sf, dd_mult)) / 2`
- 进攻池（offense_pool）= total × (1 - defense_ratio) = 0（因 defense_ratio=1.00）→ 进 repo
- 剩余零钱 → repo

### 关键参数（8 个入 Hook 保护）

```
trend_window = 40        # 趋势计算窗口
ewma_lambda = 0.94       # EWMA 衰减因子 (RiskMetrics)
target_vol_beta = 0.08   # 防御层目标波动率（v184 边际换率最优）
target_vol_alpha = 0.20  # 进攻层目标波动率（搁置中）
defense_ratio = 1.00     # 防御资金占比（1.00=纯防御）
corr_threshold = 0.0     # 股债相关性熔断阈值
drawdown [0.08, 0.12, 0.18]  # 回撤三级阈值
vol_tolerance = 0.012    # Vol Target 容忍带（= beta×15%，等比缩放）
```

### 策略特点总结

- **A/B 组合**：等效公式 `(dd_mult + min(sf, dd_mult)) / 2`，低波动满仓(A端主导)、高波动折中(B端保护)，牛熊自动切换权重
- **动态持仓**：不是固定 5 只等权。趋势过滤剔除弱势 ETF，可能持有 0-5 只。
- **仓位缩放**：波动率 > 8% 时 B 端缩仓，A 端满仓，组合居于中间
- **极端避险**：股债同涨时全部清仓进逆回购。
- **硬回撤止损**：回撤 ≥ 18% 强制清仓。
- **进攻层零权重**：defense_ratio=1.00 意味着进攻层完全不参与。
- **理论地板**：~ -2.0 Sharpe（涨跌停 + T+1 + 18% 止损 + sf 半保护锁死尾部）

### 进攻层状态

已搁置。截面动量在 A 股行业 ETF 上不成立（Sharpe -0.15~0.23），时间序列动量改善至 0.69 但仍跑输纯防御 1.23。混合和条件性激活均跑输纯防御。当前防御/进攻比例硬编码为 100/0。

### 关键文件

| 文件 | 职责 |
|------|------|
| `src/signal_generator.py` | 六步编排，信号生成总入口 |
| `src/trend_strength.py` | Step 1: 趋势强度 + 确认 |
| `src/target_volatility.py` | Step 3: EWMA 协方差 + 波动率缩放 |
| `src/correlation_circuit_breaker.py` | Step 4: 股债相关性熔断 |
| `src/drawdown_stop.py` | Step 5: 回撤硬止损 |
| `src/portfolio_manager.py` | Step 6: 资金路由 |
| `src/backtest_engine.py` | 日循环回测引擎 + 参数扫描 |
| `src/etf_universe.py` | ETF 代码映射 |
| `src/data_pipeline.py` | 数据管线（东方财富 + 新浪 fallback） |

### 执行延迟（execution_lag）— 新窗口必须了解

回测引擎支持两种执行模式：

| 参数 | 含义 | 现实可行性 | Sharpe | 总收益 | 回撤 |
|------|------|-----------|--------|--------|------|
| `execution_lag=0` | 当日收盘价算信号 → 当日收盘价成交 | **物理不可能**（同一瞬间既计算又成交） | ~1.19 | ~358% | -13.4% |
| `execution_lag=1` | T-1 日收盘价算信号 → T 日收盘价成交 | **现实可行**（盘后跑信号，次日执行） | ~1.02 | ~275% | -13.9% |

**ΔSharpe ≈ 0.17**：差值来自信号含当日收盘价带来的 1 日先知优势（趋势突破当日即可成交，延迟一日错过首日收益）。

**T+1 组合策略 Sharpe 1.108 仍远超三基准**（沪深300/创业板/纳指），策略未失效。T+0 的 1.19 是理论上限。

**当前默认**：`run_backtest()` 默认 `execution_lag=0`。`nav_chart.py` 和 `check_position.py` 使用 `execution_lag=1`。图表为 T+1 真实可执行数据。

**历史**：早期 Look-Ahead Bias 验证时 T+1 数据因现金泄漏 bug（repo_cash 取值错误）被压至 Sharpe 0.02。修复后 T+1 恢复至 1.02（commit `17aea9e` → `f88bcd6`）。此后未切换默认值，保持 T+0。
