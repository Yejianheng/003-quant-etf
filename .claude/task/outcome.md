# 执行结果 — 修复 HTML 可视化报告 3 个 bug

**日期**：2026-05-27

## 改动摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/visualization.py` | 修改 | Bug1-3 修复 + 修改记录 |

## 修复内容

### Bug 1：NAV 图比例尺错位 ✅

- `nav_list` 归一化：`nav_raw / nav_raw[0]`，起点 1.0，与基准同比例尺
- Y 轴 tick：`v.toFixed(2)` 替代 `(v/10000).toFixed(0) + '万'`

### Bug 2：日期未对齐 ✅

- `bench_aligned = benchmark_nav.reindex(records_df.index).ffill()`，基准数据裁剪到与策略 NAV 相同日期
- 移除未使用的 `benchDates` 变量

### Bug 3：Calmar 显示 `-0.00` ✅

- 年化收益 < 0 时显示 `N/A`（Calmar 对负收益策略无参考意义）
- 年化收益 ≥ 0 时格式化为 `.3f`

## 测试结果

```
tests/test_visualization.py — 6 passed
全量 69 tests: 66 passed, 3 skipped（零回归）
```

## 验收标准

- [x] `from src.visualization import generate_report` 无报错
- [x] NAV 图策略线归一化，与基准线同起点 1.0
- [x] Calmar 显示 `N/A`，不再 `-0.00`
- [x] 报告已重新生成：`./reports/backtest_report.html`
- [x] 全量测试 66 passed, 3 skipped

---

> 请顾问窗口审查。
