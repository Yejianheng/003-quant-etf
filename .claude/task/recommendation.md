# 顾问审查建议 — 四 Regime 压力测试放行 + Ablation 就位

> 审查时间：2026-05-29 | 对应 outcome: v103 (4-regime stress test)

## 审查结论

**放行。四 regime 全部存活，回撤 < 20% 硬约束。Ablation direction 就位，移交执行窗口。**

## 独立验证

### 四 regime 绩效复核

| Regime | 纯防御收益 | 纯防御 Sharpe | 最大回撤 | vs 沪深300 | 结论 |
|--------|-----------|--------------|---------|-----------|------|
| 单边牛市 | 121.9% | 2.19 | -10.6% | 收益跑输但 Sharpe 2.2× | 趋势跟踪不掉队 |
| 长期熊市 | 41.5% | 0.50 | -9.1% | 沪深300 -13.8% | 熊市保护有效 |
| 高频震荡市 | 49.6% | 0.71 | -7.6% | 53 次 whipsaw | 最弱环境但未崩 |
| 利率 shift | 0.9% | -0.11 | -6.1% | 沪深300 -21.1% | 保本，勉强 |

验收：全部四条满足核心约束（回撤 < 20%），通过。

### 关键风险点确认

1. **震荡市 whipsaw（53 次）** — 累计磨损 ~10%，系统最脆弱点。这是趋势跟踪的内在缺陷，不是 bug。Ablation 1.2（趋势过滤有无对比）将量化这个 trade-off。
2. **利率 shift（Sharpe -0.11）** — 2022 年几乎不赚钱但保本。熔断机制 122 天 repo 发挥了关键作用。Ablation 1.5 将验证熔断的边际贡献。
3. **系统不存在单点致命缺陷** — 四个 regime 无人触发 liquidate（回撤最深 -10.6%，远离 20% 硬止损）。

### 测试验证

182 passed / 1 failed (预存 `test_loads_summary`，非本次引入) / 3 skipped — 零回归。

## Ablation direction 复核

### 技术可行性

`src/signal_generator.py` 的 `generate_signal()` 已支持 `params` 参数覆盖（line 41）。执行窗口应优先使用运行时参数覆盖而非修改 `DEFAULT_PARAMS`：

- 趋势过滤 off → `{"trend_threshold": -999}`
- Vol target off → 需确认实现方式（vol_tolerance 极大值 or 直接跳过缩放逻辑）
- EWMA off → 需确认历史协方差实现（可能需修改 `ewma_covariance` 调用点）
- 熔断 off → `{"corr_threshold": 999}`

### 保护区触碰预警

`protected-contracts.json` 保护了 5 个 `signal_generator.py` 参数值。Ablation 临时修改这些值会触发内容级保护。执行窗口必须：

1. 每个 ablation 步骤前运行 `validate`
2. 触发 audit 流程（临时参数覆盖，审计模型确认后可放行）
3. 每步完成后立即恢复原值
4. 每步独立提交（已写在 direction 执行纪律中）

### 文件状态

- `src/signal_generator.py` — 不在 `protected-files.json` 文件级保护名单中 ✓
- 测试文件 `tests/test_signal_generator.py` — 已存在，覆盖 4 场景 9 tests ✓
- ablation 测试文件不存在 — 无需新建，这是分析任务非功能新增

### 执行注意事项

1. **步骤 1.3（vol target ablation）**：`target_vol_beta=0.10` 是唯一控制防御层波动率缩放的参数。设极大值（如 999）使 scaling_factor 返回 1.0 即可实现"不缩放"效果。无需修改引擎逻辑。
2. **步骤 1.4（EWMA ablation）**：这是唯一可能需改引擎代码的步骤。`ewma_covariance` 在 `src/target_volatility.py` 中。如果该文件不支持简单历史协方差模式，需先加参数开关再跑 ablation。执行者应先检查 `target_volatility.py` 确认。
3. **步骤 1.5（熔断 ablation）**：`corr_threshold=999` 确保 smoothed_corr 永不超过阈值，熔断永不触发。这是纯参数操作，安全。

---

> 人做最终决策。建议移交执行窗口。
