# 下一会话

> 顾问每次会话结束前更新。新会话顾问读取此文件恢复上下文。

## 当前阶段

策略封闭 + 数据管线就位。今日完成展示层修复 + 数据校验脚本。

## 本次结论

1. **图表现金列修复**：权重还原 1/N 等权（信号层），现金列二元判断（空仓=100%，其余=0）。不再将执行层 multiplier 混入信号层展示。
2. **recorder/backtest T+1 窗口修复**：record_daily 改用 exec_alloc，repo_amount 反映实际持仓。
3. **数据校验脚本**：verify_data.py 新鲜度/行数/空值三类检查，集成到 update_data 末尾。
4. **管线巡检通过**：5 只防御 ETF 全部 3130 行、2013-07-31 ~ 最新、零 NaN。

## 待处理

- [ ] 东方财富 API 网络排查（恢复可将 SPY 延至 1993）
- [ ] FRED NASDAQ100 集成（1993+，作为 QQQ 早期代理）
- [ ] 美股版参数重扫（0.18 对美股未必最优）
- [ ] 进攻层复活（美股 XL* ETF 截面动量）

## 重要上下文

### 核心参数（v0.18-release，不变）

```
target_vol_beta = 0.18
vol_tolerance = 0.027
trend_window = 40
ewma_lambda = 0.94
corr_window = 60, corr_sma_window = 5, corr_threshold = 0.0
drawdown = [0.08, 0.12, 0.18]
defense_ratio = 1.00
```

### 今日改动摘要

| 文件 | 改动 |
|------|------|
| `src/recorder.py` | exposure 优先 positions_detail |
| `src/backtest_engine.py` | record_daily 传 exec_alloc |
| `scripts/nav_chart.py` | 权重纯等权 + 现金二元 |
| `scripts/verify_data.py` | 新建，3 项数据校验 |
| `scripts/update_data.py` | 末尾集成 verify_data |
| `tests/test_recorder.py` | 新增 TestPositionsDetail |
| `tests/test_nav_chart.py` | 新增 test_cash_column_binary_logic |
| `tests/test_verify_data.py` | 新建，3 场景 |

### 提交记录

```
v194-20260622-3: 集成 — update_data 末尾调用 verify_data
v194-20260622-2: 新增 — scripts/verify_data.py 数据校验脚本
v194-20260622-1: 测试 — verify_data 新鲜度/行数/空值三类检查
v193-20260622-2: 修复 — nav_chart 权重还原纯等权，现金列二元判断
v193-20260622-1: 测试 — 现金列二元语义（空仓=100%，持仓=0）
v192-20260622-7: 文档 — 补充修改记录
v192-20260622-5: 修复 — nav_chart 权重展示实际仓位（后被 v193 还原）
v192-20260622-4: 测试 — 权重+现金恒等式
v192-20260622-3: 修复 — backtest T+1 传 exec_alloc
v192-20260622-2: 修复 — recorder exposure 优先 positions_detail
v192-20260622-1: 测试 — recorder positions_detail
```
