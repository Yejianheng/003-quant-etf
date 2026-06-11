# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务 1：修复 tooltip 重复 + 表格改持仓

### 问题 1：tooltip 数据重复 6 倍

当前 `label` callback 每个 dataset 返回 6 行，6 个 dataset × 6 行 = 36 行。因为 `interaction.mode: 'index'` 本身已显示全部 dataset 值，callback 只需返回单行，或直接删掉自定义 callback 用 Chart.js 默认行为。

修复：删掉 `callbacks.label` 自定义函数，Chart.js 默认就是每条 dataset 一行 `名称: 值`，总共 6 行。

### 问题 2：表格与图表数据重复

表格当前显示 5 ETF 净值 + Δ%，和图表曲线完全重复。

修改：表格改为显示每日**持仓权重**。

新表结构（10 列）：

| 日期 | 纯防御净值 | 沪深300 | 创业板 | 纳指 | 黄金 | 国债ETF | 现金 | 操作 | Δ% |

- 沪深300~国债ETF 列：显示该日持仓权重（如 `50%`、`25%`、`—`）
- 现金列：`1 - 持仓权重合计`
- 操作列：相比前一日的变化（如 `卖出 纳指`、`买入 黄金`、`无需调仓`）
- Δ% 列：纯防御净值日收益率（保留）
- 权重为 0 或不在持仓中 → 显示 `—`

### 数据来源

持仓权重从回测 `records_df` 的 `defense_active` 字段获取：
```
defense_active = "创业板;黄金" → 创业板 50%, 黄金 50%, 其余 —
defense_active = "沪深300;创业板;纳指;国债ETF" → 各 25%
```

需扩展 `_build_table_data()` → 改为接收 `records_df`，同时提取 nav + active + positions 信息。

操作列：比较前后两日 `defense_active` 或 `position_names` 的变化。

### 文件

- 修改 `scripts/nav_chart.py`
- 适配 `tests/test_nav_chart.py`

### 测试

- 适配现有 3 个测试
- 新增：验证表格列包含「持仓」相关 header
- 全量 pytest 绿灯

### 优先级

P0，用户直接需求。
