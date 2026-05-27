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
Step 7  信号生成器    编排 Step 2-6                        ✅ 已完成
Step 8  组合管理器    仓位计算 + 资金路由                  ✅ 已完成
Step 9  Recorder      日志记录 + 基准计算                  ← 当前
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 9 — Recorder

### 背景

Recorder 是回测的"黑匣子"——记录每一天的组合状态和信号，同时计算基准收益用于最终对比。这是回测报告中所有数字的来源。

```
基准：沪深300 + 创业板 + 纳指 + 黄金 + 国债 ETF
      按防御层参考权重（25/10/15/10/40）月度机械再平衡
      逆回购不在基准内
```

### 任务

#### 9a. 日记录 `src/recorder.py`

```python
init_recorder() -> dict
"""
初始化空记录器。
返回: {"records": []}
"""

record_daily(
    recorder: dict,
    date: str,
    nav: float,
    signal: dict,
    positions: dict[str, float],
) -> None
"""
追加一条日记录到 recorder["records"]。
记录字段: date, nav, exposure, repo_amount, final_multiplier,
          circuit_breaker_triggered, drawdown_level, drawdown,
          n_positions, position_names, defense_active, offense_top
不返回值，直接修改 recorder（in-place）。
"""

get_records_df(recorder: dict) -> "pd.DataFrame"
"""
将 records 列表转为 DataFrame，date 列设为 DatetimeIndex。
"""
```

#### 9b. 基准计算 `src/benchmark.py`

```python
BENCHMARK_WEIGHTS = {
    "沪深300": 0.25,
    "创业板": 0.10,
    "纳指": 0.15,
    "黄金": 0.10,
    "国债ETF": 0.40,
}

compute_benchmark(
    prices: dict[str, pd.DataFrame],
    weights: dict[str, float] | None = None,
) -> pd.Series
"""
计算基准组合净值曲线。
prices: 同 signal_generator 的 prices 格式。
weights: 基准权重，默认 BENCHMARK_WEIGHTS。
返回: 基准净值 Series，index=日期 DatetimeIndex，起始值=1.0。

计算逻辑：
1. 提取每只基准标的 close 列
2. 计算日对数收益率 = ln(P_t/P_{t-1})
3. 篮子日收益率 = Σ(weight_i × return_i)
4. 累积：基准净值 = exp(cumsum(篮子日收益率))
5. 不做月度再平衡模拟（简化处理，用买入持有近似）
   → 注释说明：月度再平衡的摩擦成本约 2-4bp/月，对长期回测结果影响 <0.5%
"""
```

### 测试（先写，必须红灯）

`tests/test_recorder.py` — 3 个场景：

1. **初始化和记录**：init → record 3 天 → get_records_df。验证行数=3，列含 nav/exposure/repo_amount/drawdown_level。

2. **字段正确性**：record 一条 → 验证 date/nav/positions 写入正确。

3. **空 recorder 转 DataFrame**：init → 直接 get_records_df。验证返回空 DataFrame（非报错）。

`tests/test_benchmark.py` — 2 个场景：

1. **基准净值计算**：构造 5 只基准标的各 60 天价格（全部单边上涨，日收益率≈0.001）。验证基准净值 ≈ exp(0.001×60) ≈ 1.062，且净值单调递增。

2. **权重自定义**：传入等权 weights={k: 0.2 for k in ...}。验证结果与默认权重结果不同。

### 约束

- recorder 用 list-of-dicts 结构，不做文件 I/O（Step 10 回测主循环负责写文件）
- benchmark 不做月度再平衡模拟，用买入持有近似
- `get_records_df` 返回的 DataFrame 中 date 设为 index（DatetimeIndex）

### 验收标准

- [ ] `python -m pytest tests/test_recorder.py tests/test_benchmark.py -v` — 5/5 绿
- [ ] `python -m pytest tests/test_signal_generator.py tests/test_portfolio_manager.py -v` — 旧测试不红
- [ ] `python -c "from src.recorder import init_recorder, record_daily; from src.benchmark import compute_benchmark; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 9"。
> 顾问审核通过并 commit 后，更新本文 Step 10。
> 禁止跳过步骤，禁止一次完成多步。
