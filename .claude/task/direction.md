# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：阶段 2 参数扫描 — 基础设施准备

### 背景

回测引擎已跑通真实数据，但默认参数下绩效极差（Sharpe -0.01，最大回撤 -23.83% 超 20% 硬约束）。`parameter_scan()` 入口已存在，但 4 个硬编码参数阻塞全部 16 项扫描。本次任务**只做基础设施改造**，不跑实际扫描。

### 改造项

#### A. `trend_threshold` — 趋势过滤阈值（阻塞扫描 2.2）

当前 `signal_generator.py:45` 硬编码 `ts > 0`。需改为 `ts > p["trend_threshold"]`。

**修改文件**：`src/signal_generator.py`
- `DEFAULT_PARAMS` 新增 `"trend_threshold": 0.0`（默认 0 保持向后兼容）
- 第 45 行 `if trend_strengths[name] > 0` → `if trend_strengths[name] > p["trend_threshold"]`

#### B. `drawdown_stop()` — 回撤止损阈值可配置（阻塞扫描 2.10）

当前 `src/drawdown_stop.py` 硬编码三级阈值。需支持通过参数覆盖。

**修改文件**：`src/drawdown_stop.py`
- `drawdown_stop()` 新增可选参数 `thresholds: list[tuple[float, float]] | None = None`
- 格式：`[(abs_dd_boundary, position_multiplier), ...]`，如 `[(0.08, 1.0), (0.12, 0.5), (0.18, 0.0)]`
- 传入 `None` 时使用当前默认值，保持向后兼容
- 值 < 第一个 boundary → multiplier=1.0；遍历 boundaries 递增

**修改文件**：`src/signal_generator.py`
- `DEFAULT_PARAMS` 新增 `"drawdown_thresholds": None`
- `generate_signal()` 调用 `drawdown_stop(current_dd)` → `drawdown_stop(current_dd, thresholds=p.get("drawdown_thresholds"))`

#### C. `target_vol_alpha` — 进攻层波动率缩放（阻塞扫描 2.7）

当前进攻层只做等权分配，未按设计文档执行目标波动率缩放。`target_vol_alpha` 在 DEFAULT_PARAMS 中声明但从未使用。

**修改文件**：`src/signal_generator.py`
- 进攻层计算完 `offense_weights` 后，对进攻标的计算 EWMA 协方差 → 预测波动率 → scaling_factor → 缩放进攻仓位
- 缩放逻辑与防御层对称：`sf_alpha = scaling_factor(p["target_vol_alpha"], predicted_vol_alpha, p["vol_tolerance"])`
- 进攻层空仓时跳过缩放
- 缩放后的权重乘入 `offense_weights`

#### D. `defense_ratio` — 资金分配比例可配置（阻塞扫描 2.11）

`allocate_capital()` 已接受 `defense_ratio` 参数，但 `run_backtest()` 未传递。

**修改文件**：`src/backtest_engine.py`
- `run_backtest()` 第 62 行调用 `allocate_capital(signal, portfolio_value)` → 增加 `defense_ratio` 参数
- 从 `params` 中读取 `defense_ratio`，默认 0.70
- 需同时传参给 `allocate_capital()`

**修改文件**：`src/signal_generator.py`
- `DEFAULT_PARAMS` 新增 `"defense_ratio": 0.70`

#### E. 参数扫描结果持久化

当前 `parameter_scan()` 结果仅存内存，大规模扫描中途崩溃丢失全部结果。

**修改文件**：`src/backtest_engine.py`
- `parameter_scan()` 新增可选参数 `checkpoint_path: str | None = None`
- 传入路径时，每完成一个参数组合即追加写入 CSV（首行写表头）
- CSV 列：参数列 + 绩效指标列（排除 `records_df` / `benchmark_nav`）
- 已有 checkpoint 文件时跳过已完成的组合（按参数列去重），实现断点续扫

### 约束

- 只修改 `src/signal_generator.py`、`src/drawdown_stop.py`、`src/backtest_engine.py`
- 不新增文件
- 每个改造项向后兼容：默认参数下现有行为不变
- 不触碰保护区

### 验收标准

- [ ] A-D 四项：`from src.signal_generator import generate_signal` 无报错
- [ ] 默认参数下 `run_backtest(prices)` 输出与改造前一致（全量回归 69 passed）
- [ ] `drawdown_stop(-0.10, thresholds=[(0.08, 1.0), (0.12, 0.5), (0.18, 0.0)])` 返回 `{"level": "halve", "position_multiplier": 0.5}`
- [ ] `parameter_scan(prices, {"trend_window": [60, 80]}, checkpoint_path="./data/scan_test.csv")` 生成 CSV 文件且含 2 行数据
- [ ] 全量测试 69+ passed（新增/修改的测试用例也绿）
- [ ] `python -m pytest tests/ -v` — 零 failed

### 运行验证命令

```python
# 1. 默认参数回归
from src.data_pipeline import load_from_parquet
from src.backtest_engine import run_backtest, parameter_scan

codes = {"510300": "沪深300", "159915": "创业板", "513100": "纳指", "518880": "黄金", "511010": "国债ETF"}
prices = {name: load_from_parquet(f"./data/{code}.parquet") for code, name in codes.items()}
result = run_backtest(prices)
print(f"总收益={result['total_return']:.4f}, Sharpe={result['sharpe_ratio']:.4f}")

# 2. 改造项验证
from src.drawdown_stop import drawdown_stop
print(drawdown_stop(-0.10, thresholds=[(0.08, 1.0), (0.12, 0.5), (0.18, 0.0)]))

# 3. checkpoint 验证
results = parameter_scan(prices, {"trend_window": [60, 80]}, checkpoint_path="./data/scan_test.csv")
print(f"扫描 {len(results)} 组合，CSV 已保存")
```

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
