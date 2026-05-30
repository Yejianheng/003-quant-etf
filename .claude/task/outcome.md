# 执行结果 — 每日数据更新 + 一键串联

> 执行时间: 2026-05-30 | 状态: 完成 | 验收: 待顾问审查

---

## 新增/修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/update_data.py` | 新增 | 遍历防御层 5 ETF → AKShare 拉增量 → 去重合并 → 存回 |
| `tests/test_update_data.py` | 新增 | 3 条测试（追加/缺失跳过/空返回跳过） |
| `run_daily.bat` | 修改 | 两步串联：先拉数据、再出信号 |

## 功能概要

`scripts/update_data.py`：

- `update_single_etf(code, data_dir, lookback_days)` — 单只 ETF 增量更新
  - parquet 不存在 → 跳过（不崩溃）
  - 已是最新（start_date ≥ today）→ 跳过
  - AKShare 返回空 / 网络错误 → 跳过（不崩溃）
  - 新数据追加 → 去重（keep last）→ 排序 → 存回
- `main()` — 遍历 5 只 ETF，汇总报告

`run_daily.bat` — 双击即用：`[1/2] update_data.py` → `[2/2] daily_signal.py`

## 测试结果

| 文件 | 条数 | 状态 |
|------|------|------|
| `test_update_data.py` | 3 | PASSED |
| `test_daily_signal.py` | 14 | PASSED（上轮已通过） |

## 全量回归

326 passed / 1 failed（预存 `test_loads_summary`）/ 3 skipped。零新增回归。

## 实跑验证

- `python scripts/update_data.py` → 网络不可达时所有 ETF 优雅降级（"无新数据"），未崩溃
- `run_daily.bat` 内容正确，两步串联

---

> 请顾问窗口审查。
