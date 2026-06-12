# 执行结果

**时间**：2026-06-12
**任务**：T+1 表格数据前移 + 操作列含权重变化

## 完成清单

| 子任务 | 状态 | 说明 |
|------|------|------|
| T+1 数据前移 | ✅ | X 日持仓权重来自 X-1 日 signal，操作比较 X-1 vs X-2 的 defense_active |
| 操作列权重格式 | ✅ | `卖出 A(33%→0), 买入 B(0→25%)、C(0→25%)` |
| 表头改名 | ✅ | 「操作」→「今日调仓」 |
| 首日建仓 | ✅ | 第 0 行 + 第 1 行（无 i-2）均显示「建仓」 |
| 无调仓 | ✅ | 无变化显示 `—` |
| 测试适配 | ✅ | 4/4 绿灯，零回归 |

## 改动文件

- `scripts/nav_chart.py` — 重写 `_build_table_data()`、新增 `_format_action()` + `_defense_active_weights()`
- `tests/test_nav_chart.py` — 「操作」→「今日调仓」、操作列断言更新

## 关键实现细节

- **shift 逻辑**：`i=0` → 首日 signal；`i≥1` → `records_df.iloc[i-1]` 的 defense_active
- **操作比较**：`i=0,1` → `"建仓"`；`i≥2` → `_format_action(old_weights, new_weights)`，old = i-2, new = i-1
- **等权解析**：`_defense_active_weights()` 从 defense_active 分号分隔字符串解析 → `1/N` 等权
- **权重格式**：卖出（旧%→新%）在前，买入在后，同方向顿号连接，方向间逗号分隔

## 测试结果

```
nav_chart: 4 passed
全量: 334 passed, 1 failed (预存在/无关), 3 skipped
```

请顾问窗口审查。
