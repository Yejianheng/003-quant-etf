# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：基准完善 + 成本细化 + 图表更新

### 步骤 0（强制）：重跑图表 + 更新数据

上轮 outcome 声称逆回购可视化代码已改但**图表未重新生成**。本轮先补上：

```bash
python scripts/nav_chart.py
```

确认 `nav_2026.html` 时间戳更新，内容含 repo 背景带 + repo 净值虚线（检查 `<script>` 中 datasets 是否有 `逆回购` 标签）。

### 步骤 1：nav_chart.py — 增加等权基准 + 60/40 基准线

修改 `scripts/nav_chart.py`：

1. 图表新增两条基准线：
   - **5 ETF 等权**（各 20%），灰色虚线
   - **60/40 股债**（沪深300 60% + 国债ETF 40%，月度再平衡），棕色虚线
2. 表格新增两列：等权净值、60/40 净值
3. 重跑 `python scripts/nav_chart.py`

### 步骤 2：slippage_scan.py — per-ETF 价差替换统一滑点

修改 `scripts/slippage_scan.py`：

1. 从 data/*.parquet 的 volume 列估算每只 ETF 的日均成交额
2. 按流动性分三档设定价差：
   - 高流动性（沪深300 510300 日均 >10 亿）：3bp
   - 中流动性（创业板 159915、纳指 513100、黄金 518880）：8bp
   - 低流动性（国债ETF 511010 日均 <2 亿）：15bp
3. 买卖时使用对应 ETF 的价差替代统一滑点参数
4. 保留佣金模型不变（万2.5）
5. 重跑四档（理想/乐观/中性/悲观），输出更新后的 `slippage_scan_results.csv`

### 步骤 3：nav_chart.py — 表格增加换手统计行

表格底部汇总行增加：
- 年化换手率（全年总换手额 / 平均持仓额）
- 累计交易成本（佣金 + 滑点，元）
- 成本占初始资金百分比

### 步骤 4：backtest_engine.py — 全期 60/40 基准输出

修改 `src/backtest_engine.py`，`run_backtest()` 返回值增加：
- `benchmark_6040`：沪深300 60% + 国债ETF 40%，月度再平衡的净值序列

计算方式：复用 `src/benchmark.py` 的 `compute_benchmark()` 函数，传入对应权重。

### 验收

- [ ] `nav_2026.html` 图表含等权、60/40 两条新基准线 + repo 背景带
- [ ] 表格含等权净值、60/40 净值两列 + 底部换手/成本统计
- [ ] `slippage_scan_results.csv` 已按 per-ETF 价差重跑
- [ ] `run_backtest()` 返回 `benchmark_6040`
- [ ] 全量 pytest 零回归

### 审核协议

`src/backtest_engine.py` 为保护区文件：
1. 先跑 CLI validate
2. 再跑 CLI audit
3. 写 outcome → 等人批 → gate → 令牌 Edit

### 已知限制（本轮不处理）

- 2008 压力测试：5 只 ETF 最早数据为 2011 年，2008 不存在。需合成数据，另开 direction。
- 全天候基准：需先定义资产池和权重方案。
