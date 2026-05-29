# 顾问审查建议 — Ablation 汇总配置错误 + Look-Ahead 缺失

> 审查时间：2026-05-30 | 对应 outcome: v112 (模块 ablation)

## 审查结论

**驳回。两个阻塞问题必须修：1) 汇总表用错配置、2) Look-ahead bias 被跳过。**

## 阻塞 1：Ablation 汇总表使用了错误配置

### 问题

脚本 `scripts/ablation_summary.py` 的 `extract_mixed_row()` 只提取 `配置 == "混合"`（defense_ratio=0.70）的行。但当前系统已确认为 **纯防御最优**（defense_ratio=1.00），进攻层已搁置。报告混合配置的 ablation 结论会误导后续决策。

### 数据对比

| 模块 | 纯防御 ΔSharpe | 混合 ΔSharpe（outcome 报告值） | 偏差 |
|------|--------------|---------------------------|------|
| 趋势过滤 | **+0.71** | +0.27 | 2.6× 低估 |
| 波动率目标 | **0.00** | +0.10 | 虚报正面 |
| EWMA 协方差 | **0.00** | -0.02 | 方向相反 |
| 相关性熔断 | **+0.85** | +0.38 | 2.2× 低估 |

纯防御的真实排名：**熔断 (+0.85) > 趋势过滤 (+0.71) >> 波动率目标 (0) ≈ EWMA (0)**

### 关键发现

**Vol target 和 EWMA 协方差在纯防御中 12 年零贡献。** 纯防御等权组合的自然波动率 ~11.4%，与 10% 目标的差距始终在 1.5% 容忍带内，`scaling_factor` 永远返回 1.0。两个模块的代码在纯防御路径上从未改变过仓位。

这不代表模块无用——换成不同 ETF 组合或波动率环境时可能触发——但在当前纯防御配置下它们是死代码。

### 修复要求

1. 修改 `ablation_summary.py`：汇总表改用 `纯防御` 配置行
2. 更新 `output/ablation_summary.csv`
3. 更新 outcome.md 为纯防御结论
4. 纯防御结论需要明确标注：vol target 和 EWMA 在当前配置下无边际贡献

## 阻塞 2：Look-Ahead Bias 验证被跳过

direction.md 明确标注"最高优先级"任务，执行窗口未执行。回测引擎 `backtest_engine.py` line 113-143 信号生成和成交使用同一 `today` 收盘价的问题仍未验证。

已在上次 direction 中给出完整执行步骤（量化 T vs T+1 差异 → 根据量级决策 → 如需修复则验证信号对齐），直接沿用。

## 非阻塞项

### 代码变更（放行）

`signal_generator.py` 新增三个参数（`trend_filter_enabled`、`vol_scaling_enabled`、`covariance_method`），默认值保持生产行为不变。不触碰 protected-contracts.json 中的受保护值。可以保留。

但建议：`covariance_method` 在纯防御中无实际作用（vol target 不触发），是否保留由人决策。

### 测试（放行）

214 passed / 1 failed (预存) / 3 skipped — 零回归，新增 30 tests 通过。

### 工作区清洁

大量 `output/ablation_*.csv` 和 `output/nav_ablation_*.csv` 未跟踪。产出文件建议提交到 output/ 目录。

---

## 修正后的执行顺序

1. **先修 summary** — 改 `ablation_summary.py` 为纯防御配置，重跑汇总
2. **再修 outcome.md** — 用纯防御结论覆盖当前混合结论
3. **再做 look-ahead bias** — 沿用 108 号 direction 的步骤
4. **提交 output 文件** — 清理工作区

---

> 人做最终决策。
