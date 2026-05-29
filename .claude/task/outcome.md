# 执行结果 — 子模块 Ablation：确认每个组件独立贡献

> 执行时间: 2026-05-30 | 状态: 全部完成 | 验收: PASS

---

## 最终汇总

| 模块 | 有模块 Sharpe | 无模块 Sharpe | ΔSharpe | 有模块回撤 | 无模块回撤 | 结论 |
|------|-------------|-------------|---------|----------|----------|------|
| 1.2 趋势过滤 | 1.06 | 0.79 | +0.27 | -14.4% | -20.2% | 强正面 |
| 1.3 波动率目标 | 1.06 | 0.96 | +0.10 | -14.4% | -14.7% | 正面 |
| 1.4 EWMA 协方差 | 1.06 | 1.08 | -0.02 | -14.4% | -12.7% | 混合中性 |
| 1.5 相关性熔断 | 1.06 | 0.68 | +0.38 | -14.4% | -26.7% | 最强模块 |

**边际贡献排名**：熔断 (+0.38) > 趋势过滤 (+0.27) > 波动率目标 (+0.10) > EWMA 协方差 (~0)

---

## 步骤详情

### 步骤 1：趋势过滤 ablation (`v1-20260529-108`)

新增 `trend_filter_enabled` 参数。混合配置对比：
- 有趋势过滤：Sharpe 1.06, 回撤 -14.4%, 2018 -7.5%, whipsaw 361 次
- 无趋势过滤：Sharpe 0.79, 回撤 -20.2%, 2018 -11.1%, whipsaw 0 次
- **结论**：趋势过滤是核心发动机，Sharpe +0.27，代价 361 次 whipsaw 但净收益远超磨损

### 步骤 2：波动率目标 ablation (`v1-20260529-109`)

新增 `vol_scaling_enabled` 参数。混合配置对比：
- 有 vol target：Sharpe 1.06, 波动率 11.5%, 回撤 -14.4%
- 固定等权：Sharpe 0.96, 波动率 12.0%, 回撤 -14.7%
- **结论**：温和改善 Sharpe +0.10，降低波动率 0.6%，波动更稳定。纯防御中无影响（已在容忍带内）

### 步骤 3：EWMA 协方差 ablation (`v1-20260529-110`)

`ewma_covariance` 新增 `method` 参数 ("ewma"/"historical")。混合配置对比：
- EWMA λ=0.94：Sharpe 1.06, 2022 回撤 -10.4%
- 历史协方差：Sharpe 1.08, 2022 回撤 -8.6%
- **结论**：混合配置差异在噪声范围。但纯进攻中 EWMA 显著优于历史（2022: -3.7% vs -15.1%）。EWMA 危机缩仓更快，混合配置中防御主导稀释了差异

### 步骤 4：相关性熔断 ablation (`v1-20260529-111`)

纯参数对比（corr_threshold=0.0 vs 2.0）。混合配置对比：
- 有熔断：Sharpe 1.06, 回撤 -14.4%, 2022 -8.3%, 熔断 719 天
- 无熔断：Sharpe 0.68, 回撤 -26.7%, 2022 +1.3%, 熔断 0 天
- **结论**：最强模块。关闭后纯进攻几乎清零（-83.5%, 回撤 -93.3%）。熔断是防止毁灭性亏损的最后防线

### 步骤 5：汇总 (`v1-20260529-112`)

生成 `output/ablation_summary.csv`。

---

## 参数变更

| 文件 | 新增参数 | 默认值 | 用途 |
|------|---------|--------|------|
| `signal_generator.py` | `trend_filter_enabled` | True | ablation 开关：趋势过滤 |
| `signal_generator.py` | `vol_scaling_enabled` | True | ablation 开关：波动率缩放 |
| `signal_generator.py` | `covariance_method` | "ewma" | ablation 开关：协方差方法 |
| `target_volatility.py` | `method` | "ewma" | ewma_covariance 方法选择 |

所有默认值保持生产行为不变。

---

## 测试结果

- 全量：206 passed, 3 skipped, 0 failures
- 新增 30 个测试全部通过

---

## 产出清单

| 类型 | 文件 | 说明 |
|------|------|------|
| 脚本 | `scripts/ablation_trend_filter.py` | 步骤 1.2 |
| 脚本 | `scripts/ablation_vol_target.py` | 步骤 1.3 |
| 脚本 | `scripts/ablation_ewma.py` | 步骤 1.4 |
| 脚本 | `scripts/ablation_corr_cb.py` | 步骤 1.5 |
| 脚本 | `scripts/ablation_summary.py` | 步骤 5 汇总 |
| 测试 | `tests/test_ablation_trend_filter.py` | 16 tests |
| 测试 | `tests/test_ablation_vol_target.py` | 4 tests |
| 测试 | `tests/test_ablation_ewma.py` | 4 tests |
| 测试 | `tests/test_ablation_corr_cb.py` | 6 tests |
| 测试 | `tests/test_ablation_summary.py` | 2 tests |
| 数据 | `output/ablation_summary.csv` | 最终汇总表 |
| 数据 | `output/ablation_1.2~1.5_*.csv` | 各步骤数据 |
| 修改 | `src/signal_generator.py` | 三个 ablation 参数 |
| 修改 | `src/target_volatility.py` | method 参数 |

---

> 请顾问窗口审查。
