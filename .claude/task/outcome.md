# 执行结果 — 阶段 2 参数扫描基础设施改造

**日期**：2026-05-28

## 改动摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/signal_generator.py` | 修改 | A: trend_threshold 参数化；B: drawdown_thresholds 传参；C: 进攻层波动率缩放；D: defense_ratio 默认值 |
| `src/drawdown_stop.py` | 修改 | B: drawdown_stop() 支持自定义 thresholds 参数 |
| `src/backtest_engine.py` | 修改 | D: run_backtest 传递 defense_ratio；E: parameter_scan checkpoint 持久化 |

## 改造详情

### A. trend_threshold ✅
- `DEFAULT_PARAMS` 新增 `"trend_threshold": 0.0`
- 趋势过滤条件 `ts > 0` → `ts > p["trend_threshold"]`
- 默认 0.0 保持向后兼容

### B. drawdown_stop() 阈值可配置 ✅
- `drawdown_stop(drawdown, thresholds=None)`: 新增可选参数
- `None` 时走原始硬编码四级逻辑（normal/warning/halve/liquidate），100% 向后兼容
- 自定义 thresholds 时按边界遍历匹配 multiplier，level 按 multiplier 映射

### C. target_vol_alpha 进攻层波动率缩放 ✅
- 进攻层等权分配后，计算选中标的 EWMA 协方差 → 预测波动率 → scaling_factor
- 缩放逻辑与防御层对称：`sf_alpha = scaling_factor(target_vol_alpha, predicted_vol, vol_tolerance)`
- 进攻层空仓时跳过缩放

### D. defense_ratio 贯穿回测链路 ✅
- `DEFAULT_PARAMS` 新增 `"defense_ratio": 0.70`
- `run_backtest()` 从 params 读取 defense_ratio 传递给 `allocate_capital()`

### E. parameter_scan() checkpoint 持久化 ✅
- 新增 `checkpoint_path` 可选参数
- 每完成一个参数组合追加写入 CSV（首行写表头）
- 已有 checkpoint 文件时跳过已完成组合（按参数列去重），实现断点续扫
- 返回时合并 checkpoint 已有数据，按 Sharpe 降序

## 测试结果

```
全量 69 tests: 69 passed / 0 failed
```

## 验收标准

- [x] A-D: `from src.signal_generator import generate_signal` 无报错
- [x] 默认参数下全量测试 69 passed（零回归）
- [x] `drawdown_stop(-0.10, thresholds=[(0.08, 1.0), (0.12, 0.5), (0.18, 0.0)])` → `{"level": "halve", "position_multiplier": 0.5}`
- [x] `parameter_scan(prices, {"trend_window": [60, 80]}, checkpoint_path="./data/scan_test.csv")` 生成 CSV 含 2 行数据
- [x] 断点续扫：重复组合自动跳过，CSV 不重复写入
- [x] 保护区：未触碰

---

> 请顾问窗口审查。
