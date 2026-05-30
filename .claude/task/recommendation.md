# 顾问审查建议 — 每日信号脚本

> 审查时间：2026-05-30 | 对应 outcome: daily_signal.py

## 审查结论

**放行。14 测试全绿，实跑输出正确。323 passed 零新增回归。**

## 验证

- 测试覆盖：基础 7 + 边界 3 + 异常 2 + 杂项 2 = 14 条
- 红灯流程：测试先红 → 代码后绿 ✓
- 实跑验证：2026-05-28 数据，黄金负趋势正确排除，其余 4 只等权，熔断正常，回撤 normal
- 全量回归：323 passed / 1 failed（预存）/ 3 skipped

## 脚本功能

```
python scripts/daily_signal.py
```

输出：趋势强度 → 熔断状态 → 回撤等级 → 目标持仓 → 操作指令（首次建仓/无需调仓/卖出X买入Y/全部清仓）

状态文件 `data/position_state.json` 跨日持久化，用于比较前后两日信号变化。

## 待提交

工作区有未跟踪文件（daily_signal.py + test + position_state.json），需提交。

---

> 人做最终决策。
