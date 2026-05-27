# Step 4 执行结果 — 目标波动率

**步骤**：Step 4 — 目标波动率（EWMA 协方差 + 容忍带）

**日期**：2026-05-27

## 改动摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/target_volatility.py` | 新增 | EWMA 协方差矩阵 / 组合波动率 / 仓位缩放系数 |
| `tests/test_target_volatility.py` | 新增 | 目标波动率测试 — 5 场景 11 用例 |

## 测试结果

```
tests/test_target_volatility.py        — 11 passed ✅ （新）
tests/test_trend_strength.py           — 5 passed + 1 skipped ✅ （旧，零回归）
tests/test_cross_sectional_momentum.py — 7 passed ✅ （旧，零回归）
```

红灯确认：首跑 `ModuleNotFoundError: No module named 'src.target_volatility'`，实现后全绿。

## 验收标准

- [x] `python -m pytest tests/test_target_volatility.py -v` — 11/11 绿
- [x] `python -m pytest tests/test_trend_strength.py tests/test_cross_sectional_momentum.py -v` — 旧测试不红
- [x] `python -c "from src.target_volatility import ewma_covariance, scaling_factor; print('OK')"` — 无报错

## 实现概要

- `ewma_covariance(prices, lambda_=0.94, window=252)`: 内部计算对数收益率 → EWMA 加权协方差（`w_t ∝ λ^(T-1-t)`）→ 年化 × 252
- `portfolio_volatility(weights, cov_matrix)`: `sqrt(w^T Σ w)`
- `scaling_factor(target_vol, predicted_vol, tolerance=0.015)`: 容忍带内 → 1.0；predicted ≤ 0 → 1.0（异常保护）；带外 → target/predicted

## 未触及保护区

本次新建文件均不在 protected-files.json 中。

---

> 请顾问窗口审查 Step 4。
