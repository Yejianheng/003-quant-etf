# 执行指令

> 2026-06-26 | 封闭版本：提交 + README + 推送

## 操作

### 步骤 1 — 提交所有文件

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
git add data/159935.parquet
git add .claude/task/outcome.md
git commit -m "v207-20260626: 封闭 — 全量策略回顾 + 模型空间验证 + 风险源准入流程 + 必读文件"
```

### 步骤 2 — 更新 README.md

在版本历史区新增 v207。内容：

---

## v207 — 全量策略回顾 + 系统封闭（2026-06-26）

### 策略定位

**风险源状态切换系统。** 不是 ETF 轮动——资产只是插槽，框架交易的是风险源在不同宏观状态下的切换。设计公理：

> 不依赖 alpha 的多风险源 beta 管理系统，通过统一风险尺度（trend_strength = 年化收益 / 年化波动率）识别有效风险源，在不同宏观状态间动态迁移，熔断处理所有风险源同时失效的极端情况。

### 核心简洁性

**不判断风险源生命周期，只管理风险源当前状态。** trend_strength 不是预测工具，是风险调整后的状态识别器。系统不需要知道"这个资产未来十年会不会失效"，只需要知道"今天是否值得暴露资本"。

### 模型空间验证

| 测试 | 结论 |
|------|------|
| **美股跨市场（v190）** | 同一框架换 SPY/QQQ/GLD/TLT/IEF，Sharpe 0.86，策略逻辑跨市场成立 |
| **SMA 信号噪声** | 单点判断在零轴附近存在统计缺陷（sma=3 砍掉 56% whipsaw）。数学正确，收益降幅超手续费节省，实盘待定 |
| **原油风险源** | 独立风险源成立（互补占比 51.6%），但不满足防御层波动率可控条件（P95/P5=3.27），排除 |
| **Walk-forward trend_window** | 固定 40 比滚动最优更稳健——追最优在 2022 年翻车（-3.132 vs -0.091） |
| **趋势确认机制对比** | Dual MA 净收益最高（1.200 vs 1.006），均线框架在方向性讨论阶段被否决，保留为已验证备选 |

### 风险源准入流程

五层测试：独立性 → 极端覆盖率 → 风险收益结构 → 风险权重压力 → 生产稳定性。原油案例完成全流程验证，第三层失败直接排除。详见 `attribution/math-limits-and-live-params.md`。

### 框架失效边界

唯一理论失效：趋势持续时间短于观察窗口，trend_strength 信息优势消失。风险源矩阵退化不是失效条件——不同资产暴露在不同类型的不确定性上，宏观状态切换不会消失。

### 架构的独特性

五个学术界独立零件（TSMOM 信号、EWMA 波动率缩放、风险平价思想、凯利式不对称暴露、相关性熔断）拼成了学术界没组合过、机构（公募）做不到、零售卖不动的完整系统。真正匹配的是养老基金和主权基金——几十年时间尺度、首要目标不毁灭。

### 自我评价

**个人投资 10 分。** 个人投资的数学极限不是收益最大化，是毁灭概率最小化。

**适合养老/捐赠/主权基金。** 不适用公募基金——季度考核和相对收益基准与框架的跟踪误差不兼容。

### 测试状态

437 passed / 6 failed（golden dataset 偏移 / 已有问题）/ 1 skipped，零新增回归。

---

### 步骤 3 — 推送

```bash
git push
```
