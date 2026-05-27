# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet                ✅ 已完成
Step 2  趋势强度      年化收益率 / 年化波动率            ✅ 已完成
Step 3  截面动量      20+60 日 z-score 合成排名          ← 当前
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA
Step 6  回撤硬止损    8/12/18 三层
Step 7  信号生成器    编排 Step 2-6
Step 8  组合管理器    仓位计算 + 资金路由
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 3 — 截面动量

### 背景

截面动量是进攻层的"买哪个"信号（方向性讨论.md 决策链第二关）。

与趋势强度（时间序列，单资产看自身趋势）不同，截面动量是**横向比较**：同一时间点，所有候选资产中谁更强。

```
各窗口动量得分 = ln(P_t / P_{t-N})        ← 对数收益率
20 日 + 60 日两个窗口
     ↓
各自截面上 z-score 标准化（跨资产，非跨时间）
     ↓
等权合成综合排名得分 = (z_20 + z_60) / 2
```

- 输入：多资产收盘价 DataFrame（index=日期 DatetimeIndex，columns=ETF 代码，values=close）
- 输出：最新一个交易日的综合排名得分 Series（index=ETF 代码，values=得分），降序即排名

### 任务

`src/cross_sectional_momentum.py` — 三个函数：

```python
momentum_score(prices: pd.DataFrame, window: int) -> pd.Series
"""
计算单窗口动量得分（对数收益率）。
prices: 多资产收盘价，每列一只 ETF。
window: 回看窗口（交易日数）。
返回: 每只 ETF 的 ln(P_t / P_{t-N})，index=ETF 代码。
缺失数据（该 ETF 价格长度不足 window）→ 该 ETF 得分为 NaN。
"""

cross_sectional_zscore(scores: pd.Series) -> pd.Series
"""
截面上 z-score 标准化。
scores: 每只 ETF 的动量得分。
公式: (x - mean) / std(ddof=1)
返回: z-score，NaN 输入 → NaN 输出（不参与 mean/std 计算）。
"""

composite_momentum(prices: pd.DataFrame, window_short: int = 20, window_long: int = 60) -> pd.Series
"""
双窗口截面动量合成。
1. 计算 20 日动量得分 → 截面 z-score
2. 计算 60 日动量得分 → 截面 z-score
3. 等权合成: (z_20 + z_60) / 2
4. 按得分降序排列
返回: Series，index=ETF 代码，values=综合得分，按降序。
全部 ETF 数据不足 → 返回空 Series。
"""
```

### 测试（先写，必须红灯）

`tests/test_cross_sectional_momentum.py` — 5 个场景：

1. **上涨 vs 横盘排名**：构造 2 只 ETF 价格（A 单边上涨 + B 横盘），window=20。验证 A 的 composite_momentum 得分 > B。

2. **全部相同**：3 只 ETF 完全相同的价格序列。验证所有 z-score 接近 0（abs < 0.001）。

3. **单资产**：只有 1 只 ETF。验证 z-score = 0.0 且 composite_momentum 非空。

4. **数据不足**：价格长度 30 天，window=60。验证 composite_momentum 返回空 Series。

5. **z-score 性质**：构造 5 只 ETF 不同涨幅。验证 z-score 的 mean ≈ 0（abs < 1e-10）、std ≈ 1.0（abs(1.0 - std) < 0.01）。

### 约束

- 不写目标波动率、相关性熔断等后续模块代码
- 对数收益率计算与 Step 2 保持一致：`ln(P_t / P_{t-N})`
- `cross_sectional_zscore` 的 `std(ddof=1)`（样本标准差，与 Step 2 一致）
- NaN 处理：skipna（NaN 不参与 mean/std，z-score 结果仍是 NaN），不死板填充 0
- `composite_momentum` 返回结果按得分降序排列（最高分在前）

### 验收标准

- [ ] `python -m pytest tests/test_cross_sectional_momentum.py -v` — 5/5 绿
- [ ] `python -m pytest tests/test_trend_strength.py tests/test_data_pipeline.py -v` — 旧测试不红（AKShare 相关跳过除外）
- [ ] `python -c "from src.cross_sectional_momentum import composite_momentum; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 3"。
> 顾问审核通过并 commit 后，更新本文 Step 4。
> 禁止跳过步骤，禁止一次完成多步。
