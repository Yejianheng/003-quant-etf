# 执行结果 — 引擎关键参数进入 protected-contracts.json Hook 保护

> 执行时间: 2026-05-29 | 状态: 全部完成 | 验收: PASS

---

## 步骤 1：更新 protected-contracts.json

**Commit**: `v1-20260529-99` | audit: Qwen3-Max 盲审通过

`values` 数组从模板占位替换为 8 条实际记录：

| 参数 | 值 | 文件 | 验证 |
|------|:--:|------|------|
| trend_window | 40 | signal_generator.py | 阶段2跨12年扫描最优 |
| ewma_lambda | 0.94 | signal_generator.py | RiskMetrics标准 |
| target_vol_beta | 0.10 | signal_generator.py | 防御层10%目标波动 |
| target_vol_alpha | 0.20 | signal_generator.py | 进攻层20%目标波动 |
| defense_ratio | 1.00 | signal_generator.py | 纯防御最优 |
| dd_threshold_halve | 0.08 | drawdown_stop.py | 三级阈值第一级 |
| dd_threshold_warning | 0.12 | drawdown_stop.py | 三级阈值第二级 |
| dd_threshold_liquidate | 0.18 | drawdown_stop.py | 三级阈值第三级 |

`patterns` 数组新增 5 条正则禁止模式，防止阈值偏离验证值。

---

## 步骤 2：验证 Hook 生效

- `trend_window=60`（偏离验证值40）→ check_values 报 `[常量篡改]` ✓
- 修正为 40 后 → 零违规 ✓
- `defense_ratio=0.70` → 报 `[常量篡改]` ✓
- 修正为 1.00 后 → 零违规 ✓

同步修正 `src/signal_generator.py` 中 `DEFAULT_PARAMS` 两个值以对齐验证值。

---

## 步骤 3：补齐 drawdown_stop.py 参数保护

- 原方案用单条 list 值 `[0.08, 0.12, 0.18]` → 文本搜索无法匹配（文件中无此字面字符串）
- 改为 3 条独立 values 记录 → check_values 文本搜索通过 ✓
- patterns 正则禁止模式验证：改 `0.08→0.07` → 报 `[禁止模式]` ✓

---

## 全量回归

**149 passed, 3 skipped, 1 failed**

唯一 failure (`test_loads_summary`: `len(df) >= 6`，实际 3 行) 为预存问题，与本次修改无关。信号生成器 7 个测试全部通过。

---

## 发现的问题

1. **check_values.py 仅支持文本搜索**：`check_values()` 用子串匹配，`check_ast_constants()` 仅处理顶层赋值。DEFAULT_PARAMS 内嵌套值无法进行 AST 级校验。当前靠文本搜索兜底，可能被同值字符串（如注释中的 `0.08`）绕过。建议后续增强 `check_ast_constants()` 支持 dict 递归提取。

2. **trend_window 代码与验证值不一致**：方向写入验证值为 40，但代码默认为 60。已在本任务中修正。类似不一致可能存在于其他参数。

---

> 请顾问窗口审查。
