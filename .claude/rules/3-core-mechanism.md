# 核心业务机制

## 纯防御策略（当前唯一生效策略）

> **defense_ratio = 1.00，进攻层完全搁置。纯防御 ≠ 简单等权。**

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

计算 active ETF 池的 EWMA 协方差矩阵（λ=0.94, 窗口 252 天）→ 组合预测波动率 → `scaling_factor = 0.10 / predicted_vol`。若 `|predicted - 0.10| ≤ 0.015` 则 sf=1.0（容忍带）。

> sf 可 >1（放大仓位）也可 <1（缩仓）。后续 `final_multiplier = min(sf, drawdown_multiplier)` 取保守值。

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
- 正常 → 防御池 = total × defense_ratio × dd_multiplier → 按 target_weights 分配
- 进攻池（offense_pool）= total × (1 - defense_ratio) = 0（因 defense_ratio=1.00）→ 进 repo
- 剩余零钱 → repo

### 关键参数（8 个入 Hook 保护）

```
trend_window = 40        # 趋势计算窗口
ewma_lambda = 0.94       # EWMA 衰减因子 (RiskMetrics)
target_vol_beta = 0.10   # 防御层目标波动率
target_vol_alpha = 0.20  # 进攻层目标波动率（搁置中）
defense_ratio = 1.00     # 防御资金占比（1.00=纯防御）
corr_threshold = 0.0     # 股债相关性熔断阈值
drawdown [0.08, 0.12, 0.18]  # 回撤三级阈值
vol_tolerance = 0.015    # Vol Target 容忍带
```

### 策略特点总结

- **动态持仓**：不是固定 5 只等权。趋势过滤剔除弱势 ETF，可能持有 0-5 只。
- **仓位缩放**：波动率目标会放大或缩小总仓位。
- **极端避险**：股债同涨时全部清仓进逆回购。
- **硬回撤止损**：回撤 ≥ 18% 强制清仓。
- **进攻层零权重**：defense_ratio=1.00 意味着进攻层完全不参与。

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
