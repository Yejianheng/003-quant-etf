# Step 8 执行结果 — 组合管理器

**步骤**：Step 8 — 组合管理器（仓位计算 + 资金路由）

**日期**：2026-05-27

## 改动摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/portfolio_manager.py` | 新增 | `allocate_capital()` — 信号→仓位转换，资金路由 |
| `tests/test_portfolio_manager.py` | 新增 | 组合管理器测试 — 5 场景 |

## 测试结果

```
tests/test_portfolio_manager.py  — 5 passed ✅ （新）
tests/test_signal_generator.py   — 4 passed ✅ （旧，零回归）
```

红灯确认：首跑 `ModuleNotFoundError: No module named 'src.portfolio_manager'`，实现后 5/5 全绿。

## 验收标准

- [x] `python -m pytest tests/test_portfolio_manager.py -v` — 5/5 绿
- [x] `python -m pytest tests/test_signal_generator.py -v` — 旧测试不红（4 passed）
- [x] `python -c "from src.portfolio_manager import allocate_capital; print('OK')"` — 无报错

## 实现概要

- `allocate_capital(signal, total_capital, defense_ratio=0.70)` — 纯函数，无副作用
- 6 步管线：基础资金池 → 回撤止损覆盖 → 熔断全进逆回购 → 防御层分配 → 进攻层分配（空仓不回流）→ 汇总
- 进攻层空仓时 offense_pool 进逆回购，不回流防御层（Beta 70% / Alpha 30% 风险预算不可污染）
- 权重归一化由 signal_generator 保证，本层不做内部归一化
- 浮点数计算，不处理整数股数

## 未触及保护区

本次新建文件均不在 protected-files.json 中。

---

> 请顾问窗口审查 Step 8。
