# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：提升年化收益 — target_vol_beta 0.08→0.10

### 背景

v185 将 `target_vol_beta` 从 0.10 降到 0.08，年化从 14%→9%。v186 50/50 组合挽回一部分到 10.47%。当前实际年化 8.63%，回撤 -7.71%，远在 20% 硬约束内。用户明确可以接受更多回撤换更高收益。

### 步骤 1：target_vol_beta 0.08 → 0.10

修改 `src/signal_generator.py`，`DEFAULT_PARAMS`：
```
"target_vol_beta": 0.10,
"vol_tolerance": 0.015,
```

`vol_tolerance` 同步恢复为 `0.015`（= beta×15%，等比缩放）。

### 步骤 2：重跑验证

```bash
python scripts/four_tables.py
python scripts/nav_chart.py
```

对比修复前后：

| 指标 | 修复前 (0.08) | 修复后 (0.10) |
|------|------|------|
| 年化 | 8.6% | ? |
| 回撤 | -7.7% | ? |
| Sharpe | 1.35 | ? |

### 步骤 3（条件）：如果年化仍 < 10%

修改 `src/signal_generator.py`，50/50 → 70/30：
```
final_multiplier = 0.7 * dd_mult + 0.3 * min(sf, dd_mult)
```

重跑验证。

### 验收

- [ ] target_vol_beta 恢复为 0.10
- [ ] 年化回升 > 10%（预期 ~12-14%）
- [ ] 回撤仍在 20% 以内
- [ ] 全量 pytest 零回归
- [ ] `nav_2026.html` + `four_tables_report.html` 更新

### 审核协议

`src/signal_generator.py` 在保护区 + `protected-contracts.json` 的 `target_vol_beta` 为受保护值。需走内容级保护流程：

1. 先跑 CLI validate
2. 再跑 CLI audit
3. 写 outcome → 等人批 → gate → 令牌 Edit
4. 修改后跑 `check_values.py` 确认新值写入
