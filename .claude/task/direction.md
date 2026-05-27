# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：修复 HTML 可视化报告 3 个 bug

### 背景

`src/visualization.py` 生成的 HTML 报告存在 3 个问题，均需修复。

### Bug 1：NAV 图比例尺错位（致命）

策略 NAV 是绝对金额（~1,000,000），基准 NAV 是归一化净值（~1.0），画在同一 Y 轴导致基准线不可见。

**修复**：将策略 NAV 归一化为 `nav / nav[0]`，与基准同起点 1.0。Y 轴 tick 回调同步改为显示归一化净值（保留 2 位小数），去掉 `/10000` 转万的逻辑。

### Bug 2：日期未对齐

`records_df` 从 2018-07-03 开始（min_days=120），`benchmark_nav` 从 2018-01-02 开始。当前 `benchDates` 采集了但从未使用，`benchData` 被塞进 NAV 的日期标签。

**修复**：benchmark 数据集改用 `benchDates` 作为 x 轴标签。由于 Chart.js 单图不支持双 x 轴，改为**将 benchmark_nav 裁剪到与 records_df 相同的日期范围**——取 `benchmark_nav.index` 与 `records_df.index` 的交集（或直接对 records_df 的日期做 `benchmark_nav.loc[dates]` 取值）。

### Bug 3：Calmar 显示 `-0.00`（展示缺陷）

`calmar_ratio` = -0.004，`.2f` 格式化为 `-0.00`，看起来像 0。

**修复**：Calmar 格式改为 3 位小数（`f"{v:.3f}"`）。此外，当 `annual_return < 0` 时，Calmar 为负值无实际参考意义，可在值后面追加备注 `(策略亏损)` 或直接显示 `N/A`——由执行者判断哪种更合理。

### 约束

- 只修改 `src/visualization.py`，不动其他文件
- 生成新 HTML 后验证 `benchmark_nav` 在图表中肉眼可见
- 不触碰保护区

### 验收标准

- [ ] `from src.visualization import generate_report` 无报错
- [ ] NAV 图：策略线和基准线均肉眼可见，起点均为 1.0 附近
- [ ] 指标卡片：Calmar 不再显示 `-0.00`
- [ ] 浏览器打开 HTML，两张图 + 指标卡片全部正常渲染
- [ ] `python -m pytest tests/test_visualization.py -v` — 全绿（必要时更新测试期望值）
- [ ] 全量测试不变（66 passed, 3 skipped）

### 运行验证命令

```python
from src.data_pipeline import load_from_parquet
from src.backtest_engine import run_backtest
from src.visualization import generate_report

codes = {"510300": "沪深300", "159915": "创业板", "513100": "纳指", "518880": "黄金", "511010": "国债ETF"}
prices = {}
for code, name in codes.items():
    df = load_from_parquet(f"./data/{code}.parquet")
    prices[name] = df

result = run_backtest(prices)
path = generate_report(result)
print(f"报告已生成: {path}")
```

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
