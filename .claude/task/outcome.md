# 执行结果

**时间**：2026-06-11
**任务**：direction.md 任务 1 — 净值归一化 + 底部分页跳转

## 完成清单

| 子任务 | 状态 | 说明 |
|------|------|------|
| 净值归一化 | ✅ | `nav / first_nav`，表格净值与图表 Y 轴（1.0 起）一致 |
| 页码跳转 | ✅ | 分页区新增页码输入框 + `jumpToPage()` JS 函数 |
| 测试适配 | ✅ | 4/4 绿灯，新增 `pageJumpInput` + `jumpToPage` 断言 |

## 改动文件

- `scripts/nav_chart.py` — 修改：`_build_table_data` 首日净值归一化、pagiation HTML 增加页码跳转、`jumpToPage()` JS、`renderTable()` 同步输入框
- `tests/test_nav_chart.py` — 修改：新增 `pageJumpInput` + `jumpToPage` 断言

## 关键实现细节

- **归一化**：`first_nav = float(records_df.iloc[0]["nav"])` → 每行 `nav / first_nav`，`prev_nav` 同步归一化
- **页码跳转**：输入页码 → `jumpToPage()` → 校验范围 → `changePage()` 逻辑 → 滚动到表格。非法输入自动恢复当前页号

请顾问窗口审查。
