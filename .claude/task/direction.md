# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet                ✅ 已完成
Step 2  趋势强度      年化收益率 / 年化波动率            ← 当前
Step 3  截面动量      20+60 日 z-score 合成排名
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA
Step 6  回撤硬止损    8/12/18 三层
Step 7  信号生成器    编排 Step 2-6
Step 8  组合管理器    仓位计算 + 资金路由
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 2 — 趋势强度

### 背景

趋势强度是全系统统一的"买不买"信号（方向性讨论.md 决策链第一关）：

```
趋势强度 = 年化收益率 / 年化波动率
年化收益率 = ln(P_t / P_{t-N}) × (252 / N)
年化波动率 = std(日收益率) × √252

趋势强度 ≤ 0 → 排除（下跌或横盘，不暴露风险）
趋势强度 > 0 → 进入候选
```

输入是 close 价格的 pandas Series（DatetimeIndex），输出是标量趋势强度值。

### 任务

#### 2a. 趋势强度模块 `src/trend_strength.py`

```python
annualized_return(prices: pd.Series, window: int = 60) -> float
"""
计算年化收益率。
prices: 收盘价 Series，index 为日期（DatetimeIndex），按时间升序。
window: 回看窗口（交易日数），默认 60。
公式：ln(P_t / P_{t-N}) × (252 / window)
"""

annualized_volatility(prices: pd.Series, window: int = 60) -> float
"""
计算年化波动率。
prices: 同上。
公式：std(日对数收益率) × √252
日收益率使用对数收益率 ln(P_t / P_{t-1})，skipna=True。
"""

trend_strength(prices: pd.Series, window: int = 60) -> float
"""
计算趋势强度 = 年化收益率 / 年化波动率。
prices 长度不足 window → 返回 0.0（数据不足，不参与交易）。
波动率为 0（如停牌）→ 返回 0.0。
"""
```

#### 2b. 日志模块 `src/logging_config.py`

解决 issues.md #2（无日志机制）：

```python
get_logger(name: str) -> logging.Logger
"""
返回统一配置的 logger。
格式：`%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
默认级别 INFO，同时输出到 stdout 和 logs/app.log。
logs/ 目录自动创建。
"""
```

每个后续模块通过 `logger = get_logger(__name__)` 获取 logger。

### 测试（先写，必须红灯）

`tests/test_trend_strength.py` — 4 个场景：

1. **上涨趋势**：构造 120 天单边上涨 close 序列（对数收益率恒定正），window=60。验证 trend_strength > 0 且年化收益率 ≈ 设定值、年化波动率 ≈ 0。

2. **下跌趋势**：构造 120 天单边下跌 close 序列（对数收益率恒定负），window=60。验证 trend_strength < 0。

3. **数据不足**：传入长度 30 的 Series，window=60。验证 trend_strength 返回 0.0。

4. **真实数据往返**：用 `fetch_etf_daily("510300", "2024-01-01", "2024-06-30")` 取真实数据，调 trend_strength(close, window=60)，验证返回 float 且非 NaN。

`tests/test_logging_config.py` — 1 个场景：

1. **logger 正常输出**：get_logger("test") 返回 Logger 实例，level=INFO，有 StreamHandler。

### 约束

- 不写截面动量、目标波动率等后续模块代码
- 日收益率使用对数收益率（与方向性讨论一致），不用简单收益率
- `annualized_volatility` 的 `std(ddof=1)`（样本标准差）
- 输入 prices 假设已是 DatetimeIndex 且升序排列，不需函数内排序

### 验收标准

- [ ] `python -m pytest tests/test_trend_strength.py tests/test_logging_config.py -v` — 5/5 绿
- [ ] `python -m pytest tests/test_data_pipeline.py -v` — 3/3 绿（安全带，Step 1 不受影响）
- [ ] `python -c "from src.trend_strength import trend_strength; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 2"。
> 顾问审核通过并 commit 后，更新本文 Step 3。
> 禁止跳过步骤，禁止一次完成多步。
