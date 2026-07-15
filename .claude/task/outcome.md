# outcome.md — 数据管线加固：时间门禁 + Web 核验 + 阻断机制

> 2026-07-15 | 执行者角色 | 三文件改动 + 测试 + 端到端验证

## 改动文件

| 文件 | 改动 | 保护状态 |
|------|------|---------|
| `scripts/update_data.py` | 重写：时间门禁 + 拉取不入库 + 待核验 dict 返回 | 非保护区 |
| `scripts/nav_chart.py` | `update_all_etfs()` 返回结构化结果 + `main()` 阻断逻辑 | 非保护区 |
| `scripts/check_position.py` | `main()` 中 `仓位` 命令加核验阻断 | 非保护区 |
| `tests/test_data_validation.py` | 新增 6 个测试：时间门禁/拉取/阻断/回退 | 非保护区 |

`src/data_pipeline.py` 未触动。

## 改动说明

### 1. 时间门禁（`update_data.py`）

交易日 15:00 前 `end_date` 截断到昨天，防止盘中拉取不完整日线。

### 2. 拉取不入库（`update_data.py`）

数据源优先级：腾讯 > 东方财富（含新浪 fallback），单源拉到即用。拉到数据返回 `needs_verify=True` + `new_data`（DataFrame），**不写入 parquet**。待 Web 核验通过后再入库。

返回格式：
```python
# 拉到数据待核验
{"ok": True, "needs_verify": True, "name": str, "code": str,
 "source": "tx"|"em", "new_data": DataFrame,
 "latest_close": float, "latest_date": str}
# 已是最新
{"ok": True, "needs_verify": False, "reason": "up_to_date"}
# 两源均空
{"ok": False, "reason": "no_data"}
```

### 3. Web 核验清单（三文件统一）

`update_data.py`、`nav_chart.py`、`check_position.py` 在 `needs_verify=True` 时打印统一格式待核验清单 + 自动论证指令 → `sys.exit(0)`。核验通过后重新执行命令，此时数据已是最新，跳过拉取直接进入后续流程。

### 4. 阻断机制（`nav_chart.py` / `check_position.py`）

- `no_data`（两源均空）→ 阻断，打印"建议半小时后重试"
- `needs_verify`（待核验）→ 阻断，打印核验清单
- 核验通过 → 正常生成图表/仓位报告

## 测试结果

| 套件 | 结果 |
|------|------|
| `test_data_validation.py` (6 tests) | 6/6 PASS |
| `test_slippage.py` (3 tests) | 3/3 PASS（零回归） |

测试覆盖：
- 15:00 前 `end_date` 截断到昨天（`test_before_15_skip_when_already_today`）
- 15:00 后 `end_date` 保持今天（`test_after_15_fetch_today`）
- 拉取成功返回 `needs_verify=True`（`test_fetch_ok_returns_needs_verify`）
- 腾讯空 → 东方回退（`test_tx_fallback_to_em`）
- 两源均空 → `ok=False`（`test_both_empty`）
- 已是最新 → `needs_verify=False`（`test_up_to_date`）

## 端到端验证

```
python scripts/update_data.py → "所有 ETF 已是最新，无需更新。" ✅
python scripts/nav_chart.py   → "净值对比图已生成：nav_2026.html" ✅
513100 7/14: close=2.170 涨跌幅=+0.09% ✅
```

## 约束遵守

- ✅ `src/data_pipeline.py` 不动
- ✅ 数据源优先级：腾讯 > 东方财富（含新浪 fallback）
- ✅ 拉取 ≠ 入库，Web 核验通过后才入库
- ✅ 时间门禁：15:00 前不拉当日
- ✅ 阻断提示统一：`建议半小时后重试`
