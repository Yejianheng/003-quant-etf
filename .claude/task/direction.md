# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：阶段 2 参数扫描 — 12 项独立网格扫描

### 背景

基础设施改造（v1-20260528-36）已将全部阻塞参数开放。现在在真实数据上跑 12 项独立参数扫描（阶段 2 中 2.5/2.9/2.15/2.16 涉及结构调整，暂不纳入）。

### 扫描清单

每项独立扫描，不交叉。结果写 `./data/scan_2X.csv`（checkpoint 模式，支持断点续扫）。

| 扫描 | 参数 | 网格 |
|------|------|------|
| 2.1 | `trend_window` | `[20, 40, 60, 80, 120]` |
| 2.2 | `trend_threshold` | `[0.0, 1.0, 1.5, 2.0, 2.5, 3.0]` |
| 2.3 | `momentum_short`, `momentum_long` | `[(20,60), (20,80), (40,120)]` |
| 2.4 | `offense_top_k` | `[2, 3, 4, 5]` |
| 2.6 | `target_vol_beta` | `[0.08, 0.10, 0.12]` |
| 2.7 | `target_vol_alpha` | `[0.15, 0.20, 0.25]` |
| 2.8 | `vol_tolerance` | `[0.01, 0.015, 0.02]` |
| 2.10 | `drawdown_thresholds` | 3 组（见下方） |
| 2.11 | `defense_ratio` | `[0.60, 0.70, 0.80]`（Alpha 比例 = 1 - defense_ratio） |
| 2.12 | `corr_window` | `[40, 60, 80]` |
| 2.13 | `corr_threshold` | `[0.0, 0.1, 0.2]` |
| 2.14 | `ewma_lambda` | `[0.90, 0.94, 0.97]` |

**2.10 回撤阈值三组**：
```python
dd_groups = {
    "10_15_18": [(0.10, 1.0), (0.15, 0.5), (0.18, 0.0)],
    "12_15_18": [(0.12, 1.0), (0.15, 0.5), (0.18, 0.0)],
    "12_18_20": [(0.12, 1.0), (0.18, 0.5), (0.20, 0.0)],
}
```
用 `param_grid = {"drawdown_thresholds": list(dd_groups.values())}` 扫描，结果中反查 key 标注组名。

### 扫描脚本

在项目根目录创建 `scripts/run_phase2_scans.py`：

```python
"""阶段 2 参数扫描 — 12 项独立网格扫描，结果写入 ./data/scan_2X.csv"""
import sys
sys.path.insert(0, ".")

from src.data_pipeline import load_from_parquet
from src.backtest_engine import parameter_scan

CODES = {"510300": "沪深300", "159915": "创业板", "513100": "纳指", "518880": "黄金", "511010": "国债ETF"}

dd_groups = {
    "10_15_18": [(0.10, 1.0), (0.15, 0.5), (0.18, 0.0)],
    "12_15_18": [(0.12, 1.0), (0.15, 0.5), (0.18, 0.0)],
    "12_18_20": [(0.12, 1.0), (0.18, 0.5), (0.20, 0.0)],
}

SCANS = [
    ("2.1", {"trend_window": [20, 40, 60, 80, 120]}),
    ("2.2", {"trend_threshold": [0.0, 1.0, 1.5, 2.0, 2.5, 3.0]}),
    ("2.3", {"momentum_short": [20, 20, 40], "momentum_long": [60, 80, 120]}),
    ("2.4", {"offense_top_k": [2, 3, 4, 5]}),
    ("2.6", {"target_vol_beta": [0.08, 0.10, 0.12]}),
    ("2.7", {"target_vol_alpha": [0.15, 0.20, 0.25]}),
    ("2.8", {"vol_tolerance": [0.01, 0.015, 0.02]}),
    ("2.10", {"drawdown_thresholds": list(dd_groups.values())}),
    ("2.11", {"defense_ratio": [0.60, 0.70, 0.80]}),
    ("2.12", {"corr_window": [40, 60, 80]}),
    ("2.13", {"corr_threshold": [0.0, 0.1, 0.2]}),
    ("2.14", {"ewma_lambda": [0.90, 0.94, 0.97]}),
]

def main():
    print("加载真实数据...")
    prices = {}
    for code, name in CODES.items():
        df = load_from_parquet(f"./data/{code}.parquet")
        prices[name] = df
        print(f"  {name}: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")

    common = sorted(set.intersection(*[set(df.index) for df in prices.values()]))
    print(f"共同交易日: {len(common)}")

    for scan_id, param_grid in SCANS:
        path = f"./data/scan_{scan_id.replace('.', '_')}.csv"
        print(f"\n{'='*50}")
        print(f"扫描 {scan_id}: {list(param_grid.keys())} → {path}")
        print(f"组合数: ", end="")
        count = 1
        for v in param_grid.values():
            count *= len(v)
        print(count)

        results = parameter_scan(prices, param_grid, checkpoint_path=path)
        if results:
            best = results[0]
            print(f"最优: Sharpe={best.get('sharpe_ratio',0):.4f}, "
                  f"年化={best.get('annual_return',0):.4f}, "
                  f"最大回撤={best.get('max_drawdown',0):.4f}")
        print(f"结果已保存: {path}")

    print("\n全部扫描完成。")

if __name__ == "__main__":
    main()
```

### 扫描 2.3 参数组合说明

`momentum_short` 和 `momentum_long` 需要配对扫描，当前 `parameter_scan` 做笛卡尔积。对于 2.3，需配对 `[(20,60), (20,80), (40,120)]`，不是 3×3=9 组合。

处理方法：不直接用 `parameter_scan` 的网格模式，改为手动循环 3 组分别调 `run_backtest`。或在脚本中特殊处理——将 `momentum_short` 和 `momentum_long` 分别作为 list 传入但用索引配对。**推荐手写循环**，因为只有 3 组：

```python
momentum_pairs = [(20, 60), (20, 80), (40, 120)]
# 循环 run_backtest 3 次，手动写 CSV
```

### 约束

- 仅读取 `data/*.parquet` + 写入 `data/scan_*.csv`，不修改已有业务代码
- 使用 checkpoint 模式，断点续扫
- 不触碰保护区

### 验收标准

- [ ] `scripts/run_phase2_scans.py` 可运行，12 项扫描全部完成
- [ ] `data/` 下生成 12 个 scan_*.csv 文件（每文件 ≥ 3 行数据）
- [ ] 每个 CSV 按 Sharpe 降序排列
- [ ] 全量测试 69 passed（回归验证）
- [ ] 扫描结果汇总：打印每项扫描的最优参数及对应绩效

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
