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
Step 7  信号生成器    编排 Step 2-6                        ← 当前
Step 8  组合管理器    仓位计算 + 资金路由
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 7 — 信号生成器

### 背景

信号生成器是决策链的编排层。它不实现任何算法，只按顺序调用 Step 2-6 的模块，输出一笔结构化的调仓信号。这是回测引擎和实盘执行共用的唯一入口。

```
输入：当日全量数据（价格、净值、参数）
  │
  ├─ 趋势强度（Step 2）→ 每个资产的趋势方向
  ├─ 截面动量（Step 3）→ 进攻层排名
  ├─ 目标波动率（Step 4）→ 仓位缩放系数
  ├─ 相关性熔断（Step 5）→ 资金是否进逆回购
  └─ 回撤硬止损（Step 6）→ 最终仓位乘数（覆盖前面一切）
  │
输出：Signal dict
```

### 任务

`src/signal_generator.py` — 一个函数：

```python
generate_signal(
    prices: dict[str, pd.DataFrame],
    portfolio_value: pd.Series,
    params: dict | None = None,
) -> dict
"""
生成当日调仓信号。

prices: {
    "沪深300": DataFrame (open/high/low/close/volume, index=日期),
    "创业板": DataFrame,
    "纳指": DataFrame,
    "黄金": DataFrame,
    "国债ETF": DataFrame,
    # 进攻层行业 ETF 候选（可选，暂不传则不计算进攻信号）
}
portfolio_value: 组合净值 Series，index=日期，按时间升序。
params: 可选参数字典，默认值见下方。

返回 Signal dict:
{
    "date": str,                    # 信号日期 YYYY-MM-DD
    "defense": {
        "trend_strengths": {name: float},  # 每只防御标的趋势强度
        "active": [name, ...],             # 趋势强度 > 0 的标的
        "target_weights": {name: float},   # 目标波动率缩放后的权重
        "scaling_factor": float,           # 仓位缩放系数
    },
    "offense": {
        "rankings": [{name: score}, ...],  # 截面动量排名（降序，top 3）
        "target_weights": {name: float},   # 等权目标权重
    },
    "circuit_breaker": {
        "triggered": bool,           # 相关性熔断是否触发
        "smoothed_corr": float,      # 平滑相关性
    },
    "drawdown_stop": {
        "level": str,                # normal/warning/halve/liquidate
        "position_multiplier": float, # 最终仓位乘数
        "drawdown": float,           # 当前回撤
    },
    "execution": {
        "final_multiplier": float,   # = min(scaling_factor, position_multiplier) → 或被熔断覆写为 0
        "funds_to_repo": bool,       # 资金是否路由到逆回购
    },
}

默认参数：
{
    "trend_window": 60,
    "momentum_short": 20,
    "momentum_long": 60,
    "offense_top_k": 3,
    "target_vol_beta": 0.10,
    "target_vol_alpha": 0.20,
    "vol_tolerance": 0.015,
    "ewma_lambda": 0.94,
    "corr_window": 60,
    "corr_sma_window": 5,
    "corr_threshold": 0.0,
}
```

### 逻辑流程

```
1. 从 prices 提取各资产 close 列
2. 防御层趋势强度：
   for each 防御标的 in ["沪深300","创业板","纳指","黄金","国债ETF"]:
       trend_strength(close, window=trend_window)
   active = [name for name, ts in trend_strengths if ts > 0]

3. 防御层目标波动率：
   取 active 标的的 close 组成 DataFrame
   ewma_covariance(prices, lambda_=ewma_lambda)
   portfolio_volatility(target_weights, cov)  ← 权重来自 etf_universe 参考权重（仅 active 部分，归一化）
   scaling_factor(target_vol_beta, predicted_vol, vol_tolerance)

4. 进攻层截面动量（如有行业 ETF 候选）：
   composite_momentum(prices, momentum_short, momentum_long)
   取 top 3，等权分配

5. 相关性熔断：
   股票篮子 = {"沪深300": close, "创业板": close, "纳指": close}
   correlation_circuit_breaker(股票篮子, 国债ETF_close, corr_window, corr_sma_window, corr_threshold)

6. 回撤硬止损：
   compute_drawdown(portfolio_value) → 取最后值
   drawdown_stop(drawdown) → level + multiplier

7. execution 汇总：
   - 熔断触发 → funds_to_repo=True, final_multiplier=0
   - 否则 final_multiplier = min(scaling_factor, position_multiplier)
```

### 测试（先写，必须红灯）

`tests/test_signal_generator.py` — 4 个场景（全用合成数据）：

1. **全绿正常信号**：构造防御层 5 标的全部单边上涨（趋势 > 0）、无回撤、股债负相关。验证 defense.active 含全部 5 标的，circuit_breaker.triggered=False，drawdown_stop.level="normal"，final_multiplier > 0。

2. **趋势过滤排除**：沪深300 下跌（趋势 < 0），其余上涨。验证 defense.active 不含 "沪深300"。

3. **熔断覆盖**：股债正相关。验证 circuit_breaker.triggered=True，execution.funds_to_repo=True，final_multiplier=0。

4. **回撤止损覆盖**：组合净值大幅回撤 20%。验证 drawdown_stop.level="liquidate"，position_multiplier=0.0，final_multiplier=0。

### 约束

- 信号生成器只做编排，不实现算法。所有计算委托给 Step 2-6 模块。
- 防御层参考权重来自 `src/etf_universe.py` 的 `ETF_UNIVERSE` 字典顺序，暂用等权（各 20%）。方向性讨论的参考权重（25/10/15/10/40）在 Step 8 组合管理器中实现。
- 进攻层候选暂不传入（`prices` 中无行业 ETF key），`offense` 字段返回空结构 `{"rankings": [], "target_weights": {}}`。
- 参数全部可配，默认值与方向性讨论一致。

### 验收标准

- [ ] `python -m pytest tests/test_signal_generator.py -v` — 4/4 绿
- [ ] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py tests/test_target_volatility.py tests/test_correlation_circuit_breaker.py tests/test_drawdown_stop.py -v` — 旧测试不红
- [ ] `python -c "from src.signal_generator import generate_signal; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 7"。
> 顾问审核通过并 commit 后，更新本文 Step 8。
> 禁止跳过步骤，禁止一次完成多步。
