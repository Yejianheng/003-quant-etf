# Step 7 执行结果 — 信号生成器

**步骤**：Step 7 — 信号生成器（编排 Step 2-6）

**日期**：2026-05-27

## 改动摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/signal_generator.py` | 新增 | 信号生成器编排层，回测/实盘共用入口 |
| `tests/test_signal_generator.py` | 新增 | 信号生成器测试 — 4 场景 |

## 测试结果

```
tests/test_signal_generator.py              — 4 passed ✅ （新）
tests/test_trend_strength.py                — 5 passed + 1 skipped ✅ （旧，零回归）
tests/test_cross_sectional_momentum.py      — 7 passed ✅ （旧，零回归）
tests/test_target_volatility.py             — 11 passed ✅ （旧，零回归）
tests/test_correlation_circuit_breaker.py   — 8 passed ✅ （旧，零回归）
tests/test_drawdown_stop.py                 — 5 passed ✅ （旧，零回归）
```

红灯确认：首跑 `ModuleNotFoundError: No module named 'src.signal_generator'`，实现后 4/4 全绿。

## 验收标准

- [x] `python -m pytest tests/test_signal_generator.py -v` — 4/4 绿
- [x] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py tests/test_target_volatility.py tests/test_correlation_circuit_breaker.py tests/test_drawdown_stop.py -v` — 旧测试不红（36 passed, 1 skipped）
- [x] `python -c "from src.signal_generator import generate_signal; print('OK')"` — 无报错

## 实现概要

- `generate_signal(prices, portfolio_value, params)` — 纯编排，不实现算法
- 7 步管线：close 提取 → 趋势强度 → 目标波动率 → 截面动量 → 相关性熔断 → 回撤止损 → execution 汇总
- 防御层参考权重暂用等权；进攻层无候选时返回空结构
- 熔断触发时 final_multiplier=0 + funds_to_repo=True（覆盖一切）
- 默认参数与方向性讨论一致

## 未触及保护区

本次新建文件均不在 protected-files.json 中。

---

> 请顾问窗口审查 Step 7。
