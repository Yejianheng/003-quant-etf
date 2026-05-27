# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet                ✅ 已完成
Step 2  趋势强度      年化收益率 / 年化波动率            ✅ 已完成
Step 3  截面动量      20+60 日 z-score 合成排名          ✅ 已完成
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带            ← 当前
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA
Step 6  回撤硬止损    8/12/18 三层
Step 7  信号生成器    编排 Step 2-6
Step 8  组合管理器    仓位计算 + 资金路由
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 4 — 目标波动率

### 背景

目标波动率框架回答"买多少"——不是按名义权重分配资金，而是按风险预算缩放仓位（方向性讨论.md 决策链第三关）。

```
缩放系数 = 目标波动率 / 预测波动率

预测波动率 = sqrt(w^T Σ w)
Σ = EWMA 协方差矩阵（λ=0.94，半衰期 ≈ 11 个交易日）

容忍带：|预测波动率 - 目标波动率| ≤ 1.5% → 不操作（缩放系数 = 1.0）
```

两层独立管理（Beta 70% / Alpha 30%），互不穿透。本模块只负责计算协方差和缩放系数，不负责资金分配（那是 Step 8 组合管理器的职责）。

### 任务

`src/target_volatility.py` — 三个函数：

```python
ewma_covariance(prices: pd.DataFrame, lambda_: float = 0.94, window: int = 252) -> pd.DataFrame
"""
EWMA 加权的年化协方差矩阵。
prices: 多资产收盘价 DataFrame（index=日期，columns=资产）。
lambda_: 衰减因子，默认 0.94。
window: 用于计算协方差的历史窗口（交易日数），默认 252。
返回: 年化协方差矩阵 DataFrame，行列均为资产名。

计算步骤：
1. 取最近 window 个交易日的日对数收益率（ln(P_t/P_{t-1})，skipna）
2. 对每对资产 i, j，EWMA 协方差：
   cov[i,j] = Σ_t( w_t × (r_i[t] - r̄_i) × (r_j[t] - r̄_j) ) / Σ_t(w_t)
   其中 w_t = (1-λ) × λ^(T-t)，最新观测权重最大，r̄ 为 EWMA 加权均值
3. 年化：× 252
"""

portfolio_volatility(weights: np.ndarray, cov_matrix: pd.DataFrame) -> float
"""
组合预测波动率 = sqrt(w^T Σ w)。
weights: 权重数组（顺序对应 cov_matrix 的列）。
cov_matrix: 年化协方差矩阵。
返回: 年化波动率标量（如 0.10 表示 10%）。
"""

scaling_factor(target_vol: float, predicted_vol: float, tolerance: float = 0.015) -> float
"""
计算仓位缩放系数，含容忍带。
|predicted_vol - target_vol| ≤ tolerance → 返回 1.0（不操作）
否则 → 返回 target_vol / predicted_vol。
predicted_vol ≤ 0 → 返回 1.0（异常保护）。
"""
```

### 测试（先写，必须红灯）

`tests/test_target_volatility.py` — 5 个场景：

1. **EWMA 近期权重更大**：构造 252 天数据，前 200 天剧烈波动 + 后 52 天零波动。验证 EWMA 协方差接近 0（近期低波主导，λ=0.94 遗忘快），而等权协方差显著 > 0（验证 EWMA 的遗忘特性生效）。

2. **完美正相关**：构造 2 只 ETF 完全相同的价格序列。验证协方差矩阵的 σ_12 / (σ_1 × σ_2) ≈ 1.0（相关系数 ≈ 1）。

3. **组合波动率计算**：3 资产、给定权重 [0.5, 0.3, 0.2]、已知协方差矩阵。验证 `portfolio_volatility` 返回值与手动 `sqrt(w^T Σ w)` 一致（误差 < 1e-10）。

4. **容忍带内不操作**：target=0.10, predicted=0.108（偏离 0.8% < 1.5%）。验证 scaling_factor 返回 1.0。

5. **容忍带外缩放**：target=0.10, predicted=0.15（偏离 5% > 1.5%）。验证 scaling_factor 返回 0.10/0.15 ≈ 0.6667。

### 约束

- 不写相关性熔断、回撤止损等后续模块代码
- 日收益率使用对数收益率（与 Step 2/3 一致）
- EWMA 公式使用标准指数衰减：最新观测权重最大，`w_t ∝ λ^(T-t)`
- 年化因子 252（交易日）
- `ewma_covariance` 内部自行计算日收益率，输入是 prices 不是 returns

### 验收标准

- [ ] `python -m pytest tests/test_target_volatility.py -v` — 5/5 绿
- [ ] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py -v` — 旧测试不红
- [ ] `python -c "from src.target_volatility import ewma_covariance, scaling_factor; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 4"。
> 顾问审核通过并 commit 后，更新本文 Step 5。
> 禁止跳过步骤，禁止一次完成多步。
