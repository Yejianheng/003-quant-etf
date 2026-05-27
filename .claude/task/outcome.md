# Step 5 执行结果 — 相关性熔断

**步骤**：Step 5 — 相关性熔断（股债滚动相关性 + SMA 熔断判断）

**日期**：2026-05-27

## 改动摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/correlation_circuit_breaker.py` | 新增 | 三个函数：stock_basket_returns / rolling_correlation / correlation_circuit_breaker |
| `tests/test_correlation_circuit_breaker.py` | 新增 | 相关性熔断测试 — 5 场景 8 用例 |

## 测试结果

```
tests/test_correlation_circuit_breaker.py — 8 passed ✅ （新）
tests/test_trend_strength.py              — 5 passed + 1 skipped ✅ （旧，零回归）
tests/test_cross_sectional_momentum.py    — 7 passed ✅ （旧，零回归）
tests/test_target_volatility.py           — 11 passed ✅ （旧，零回归）
```

红灯确认：首跑 `ModuleNotFoundError: No module named 'src.correlation_circuit_breaker'`，实现后全绿。

## 验收标准

- [x] `python -m pytest tests/test_correlation_circuit_breaker.py -v` — 8/8 绿
- [x] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py tests/test_target_volatility.py -v` — 旧测试不红
- [x] `python -c "from src.correlation_circuit_breaker import correlation_circuit_breaker; print('OK')"` — 无报错

## 实现概要

- `stock_basket_returns(stock_prices)`: 每只 ETF 独立算对数收益率 → DataFrame → row-wise mean(skipna)
- `rolling_correlation(series_a, series_b, window)`: pandas `.rolling(window).corr()`
- `correlation_circuit_breaker(...)`: 篮子收益 → 债券收益 → 日期对齐（中美交易日取交集）→ 滚动相关 → SMA → 阈值判断
- 数据不足（< corr_window + sma_window 交易日）返回 triggered=False, smoothed_corr=0.0

## 未触及保护区

本次新建文件均不在 protected-files.json 中。

---

> 请顾问窗口审查 Step 5。
