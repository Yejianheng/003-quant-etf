# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet                ✅ 已完成
Step 2  趋势强度      年化收益率 / 年化波动率            ✅ 已完成
Step 3  截面动量      20+60 日 z-score 合成排名          ✅ 已完成
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带            ✅ 已完成
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA            ← 当前
Step 6  回撤硬止损    8/12/18 三层
Step 7  信号生成器    编排 Step 2-6
Step 8  组合管理器    仓位计算 + 资金路由
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 5 — 相关性熔断

### 背景

相关性熔断回答"钱去哪"（方向性讨论.md 决策链第四关）。防御层的核心价值是资产间低相关——当股债相关性转正，分散化的基础消失，资金应撤离风险资产进入逆回购。

```
股票篮子日收益率 = (沪深300 + 创业板 + 纳指) / 3  ← 等权合成
股票篮子 vs 国债 ETF，60 日滚动 Pearson 相关性
    ↓
5 日 SMA 平滑（防单日噪声触发）
    ↓
平滑后相关性 > 0 → 熔断触发 → 释放资金直进逆回购
平滑后相关性 ≤ 0 → 正常 → 资金留在防御层
```

### 任务

`src/correlation_circuit_breaker.py` — 三个函数：

```python
stock_basket_returns(stock_prices: dict[str, pd.Series]) -> pd.Series
"""
计算股票篮子等权日收益率。
stock_prices: {"沪深300": Series, "创业板": Series, "纳指": Series}，
  每个 Series index=日期 DatetimeIndex，values=close 价格。
返回: 日对数收益率 Series（等权平均），index=日期。
步骤：
1. 每只 ETF 独立计算日对数收益率 ln(P_t/P_{t-1})
2. 按日期横向等权平均（skipna，某 ETF 某日缺数据不拖垮整体）
3. dropna 后返回
"""

rolling_correlation(series_a: pd.Series, series_b: pd.Series, window: int = 60) -> pd.Series
"""
滚动 Pearson 相关系数。
series_a, series_b: 两个等长日收益率 Series，index 对齐。
window: 滚动窗口（交易日数）。
返回: 滚动相关系数 Series，index=日期，长度 < window 的位置为 NaN。
使用 pandas .rolling(window).corr()。
"""

correlation_circuit_breaker(
    stock_prices: dict[str, pd.Series],
    bond_prices: pd.Series,
    corr_window: int = 60,
    sma_window: int = 5,
    threshold: float = 0.0,
) -> dict
"""
相关性熔断判断。
返回: {
    "triggered": bool,          # 是否触发熔断
    "smoothed_corr": float,     # 最新平滑相关性
    "raw_corr": float,          # 最新原始 60 日相关性（调试用）
}
步骤：
1. stock_basket_returns(stock_prices) → 股票篮子日收益率
2. bond 日对数收益率
3. rolling_correlation(股票篮子, 债券, corr_window) → 滚动相关性
4. 对滚动相关性做 sma_window 日 SMA 平滑 → 取最后一个值为 smoothed_corr
5. smoothed_corr > threshold → triggered=True
数据不足（如 < corr_window + sma_window 个交易日）→ triggered=False, smoothed_corr=0.0
"""
```

### 测试（先写，必须红灯）

`tests/test_correlation_circuit_breaker.py` — 5 个场景：

1. **股债负相关不触发**：构造股票上涨 + 债券下跌（负相关）的 120 天数据。验证 `triggered=False`。

2. **股债正相关触发**：构造股票和债券同涨同跌（正相关）的 120 天数据。验证 `triggered=True`。

3. **SMA 平滑效果**：构造前 60 天正相关 + 后 60 天负相关的数据。验证 `smoothed_corr` 比 `raw_corr` 更接近 0（平滑滞后导致正相关残余被 SMA 削弱但未完全消除）。

4. **数据不足**：只给 30 天数据，corr_window=60。验证 `triggered=False` 且 `smoothed_corr=0.0`。

5. **等权篮子计算**：3 只股票各构造已知日收益率。验证 `stock_basket_returns` 输出 = 三者的逐日等权平均（误差 < 1e-10）。

### 约束

- 不写回撤止损、信号生成器等后续模块代码
- 日收益率使用对数收益率（与 Step 2/3/4 一致）
- `stock_basket_returns` 的 skipna 行为：某 ETF 缺数据时用其他 ETF 的平均，不全 NaN
- 熔断阈值默认 0.0（方向性讨论：> 0 触发），可参数化

### 验收标准

- [ ] `python -m pytest tests/test_correlation_circuit_breaker.py -v` — 5/5 绿
- [ ] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py tests/test_target_volatility.py -v` — 旧测试不红
- [ ] `python -c "from src.correlation_circuit_breaker import correlation_circuit_breaker; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 5"。
> 顾问审核通过并 commit 后，更新本文 Step 6。
> 禁止跳过步骤，禁止一次完成多步。
