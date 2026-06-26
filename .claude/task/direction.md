# 执行指令

> 2026-06-26 | 封闭版本：提交 + README 更新

## 背景

顾问侧完成全量策略回顾和测试。新增必读文件 `attribution/math-limits-and-live-params.md`（数学极限 vs 实盘参数 + 五层风险源准入流程）。项目日志已更新。需提交并更新 README。

## 操作

### 步骤 1 — 提交所有新增和修改文件

```bash
git add attribution/math-limits-and-live-params.md
git add 项目日志/2026-06-26.md
git add tests/test_sma_param_scan.py
git add tests/test_sma_threshold_cross.py
git add tests/test_sma_beta_stability.py
git add tests/test_sma_slow_bear.py
git add tests/test_trend_net_return.py
git add tests/test_trend_smoothing.py
git add tests/test_trend_threshold_scan.py
git add tests/test_walk_forward_trend_window.py
git add tests/test_crude_risk_weight.py
git add tests/test_crude_risk_coverage.py
git add tests/test_crude_vol_stability.py
git add scripts/walk_forward_trend_window.py
git commit -m "v207-20260626: 封闭 — 全量策略回顾 + 数学极限验证 + 风险源准入流程 + 必读文件"
```

### 步骤 2 — 更新 README.md

在 README.md 的版本历史区域，新增 v207 章节。内容如下：

---

## v207 — 全量策略回顾 + 系统封闭（2026-06-26）

### 策略核心公理

系统定位为**不依赖 alpha 的多风险源 beta 管理系统**：通过统一风险尺度（trend_strength = 年化收益 / 年化波动率）识别有效风险源，在不同宏观状态之间动态迁移，并通过熔断机制处理所有风险源同时失效的极端情况。

### 回顾结论

trend_strength 的价值在跨资产归一化和已知统计分布（近似 t 分布），不在预测准确率。五种趋势确认方法中，Trend Strength 为默认，Dual MA 为已验证备选（净收益更优但均线框架在方向性讨论阶段被否决）。

### 数学极限验证

| 测试 | 结论 |
|------|------|
| **SMA 信号平滑** | 单点判断在零轴附近存在统计缺陷（sma=3 砍掉 56% whipsaw）。数学正确，但年化收益降幅超过手续费节省，实盘待定 |
| **Walk-forward trend_window** | 固定 40 比滚动最优更稳健。追最优在 2022 年翻车（Sharpe -3.132 vs 固定 40 -0.091） |
| **原油风险源** | 独立风险源（互补占比 51.6%），但不满足防御层波动率可控条件（P95/P5=3.27），排除 |
| **threshold 扫描** | 效果有限，SMA 已解决问题 |
| **含成本净收益对比** | 五方法全量对比，Breakout 年化成本 9.92% 不可接受 |

### 风险源准入流程

新增五层准入测试：独立性 → 极端覆盖率 → 风险收益结构 → 风险权重压力 → 生产稳定性。原油案例完成全流程验证，第三层失败直接排除。详见 `attribution/math-limits-and-live-params.md`。

### 文档债务修复

protected-contracts.json 和 3-core-mechanism.md 同步至实际代码参数（target_vol_beta 0.08→0.18, vol_tolerance 0.012→0.027）。

### 测试状态

437 passed / 6 failed（golden dataset 偏移 / 已有问题）/ 1 skipped，零新增回归。

---

### 步骤 3 — 推送

```bash
git push
```

## 约束

- README 新增内容放在版本历史区域，保持现有格式
- 提交信息按项目规范（v207-20260626）
