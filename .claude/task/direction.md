# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务 1：净值归一化 + 底部分页跳转

### 修改 1：表格净值归一化

`_build_table_data()` L122：`nav = float(row["nav"])` 是原始回测值（百万级），和图表 Y 轴（从 1.0 起）不一致。

修复：除以首日净值归一化。

```python
first_nav = float(records_df.iloc[0]["nav"])
...
nav = float(row["nav"]) / first_nav
```

### 修改 2：底部分页增加页码跳转

表格下方翻页区域当前只有"上一页 / 第 X/N 页 / 下一页"。在总页数旁边加一个页码输入框 + 跳转按钮：

```
上一页 | 第 1/6 页 | 到第 [__] 页 [跳转] | 下一页
```

输入页码 → 点跳转 → `changePage(target - currentPage)`，超出范围提示"页码范围 1-N"。

### 文件

- 修改 `scripts/nav_chart.py`

### 测试

- 适配现有测试
- 全量 pytest 绿灯

### 优先级

P0。
