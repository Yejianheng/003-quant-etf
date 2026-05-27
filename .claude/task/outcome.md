# Step 6 执行结果 — 回撤硬止损

**步骤**：Step 6 — 回撤硬止损（8/12/18 三层 drawdown stop）

**日期**：2026-05-27

## 改动摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/drawdown_stop.py` | 新增 | 两个函数：compute_drawdown / drawdown_stop |
| `tests/test_drawdown_stop.py` | 新增 | 回撤止损测试 — 5 场景 |

## 测试结果

```
tests/test_drawdown_stop.py              — 5 passed ✅ （新）
tests/test_trend_strength.py             — 5 passed + 1 skipped ✅ （旧，零回归）
tests/test_cross_sectional_momentum.py   — 7 passed ✅ （旧，零回归）
tests/test_target_volatility.py          — 11 passed ✅ （旧，零回归）
tests/test_correlation_circuit_breaker.py — 8 passed ✅ （旧，零回归）
```

红灯确认：首跑 `ModuleNotFoundError: No module named 'src.drawdown_stop'`，实现后 5/5 全绿。

## 验收标准

- [x] `python -m pytest tests/test_drawdown_stop.py -v` — 5/5 绿
- [x] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py tests/test_target_volatility.py tests/test_correlation_circuit_breaker.py -v` — 旧测试不红（31 passed, 1 skipped）
- [x] `python -c "from src.drawdown_stop import compute_drawdown, drawdown_stop; print('OK')"` — 无报错

## 实现概要

- `compute_drawdown(portfolio_values)`: `expanding().max()` 计算 running_max → `(value - running_max) / running_max`，返回负小数 Series
- `drawdown_stop(drawdown)`: 取绝对值与 0.08/0.12/0.18 比较 → 返回 `{"level": ..., "position_multiplier": ...}`
- 5 场景覆盖：无回撤、四层触发、先新高后回撤、回撤恢复 running_max 不降、序列逐日验证

## 未触及保护区

本次新建文件均不在 protected-files.json 中。

---

> 请顾问窗口审查 Step 6。
