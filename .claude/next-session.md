# 下一会话

> 顾问每次会话结束前更新。新会话顾问读取此文件恢复上下文。

## 当前阶段

回测开发 → 阶段 2 参数扫描（基础设施准备）。5 项改造已写入 direction.md，等待执行窗口执行。

## 已完成

- [x] Step 1-10：数据管线 → 回测主循环 → HTML 报告（35 commits）
- [x] 真实数据回测：5 ETF 跑通，但绩效极差（Sharpe -0.01，最大回撤 -23.83%）
- [x] 技术隐患 4/4 清零
- [x] 全量测试：69 passed / 0 failed

## 当前任务（direction.md 已就绪）

- [ ] **阶段 2 基础设施改造**（5 项）：
  - A. `trend_threshold` 可配置
  - B. `drawdown_stop()` 阈值参数化
  - C. `target_vol_alpha` 接入进攻层波动率缩放
  - D. `defense_ratio` 贯穿回测链路
  - E. `parameter_scan()` checkpoint 持久化

## 待处理（后续）

- [ ] 阶段 2：16 项参数扫描执行（等基础设施就位）
- [ ] 进攻层行业 ETF 候选池构建（流动性/规模筛选）
- [ ] 阶段 3-6：组合验证 → 压力测试 → 样本外 → 模拟实盘
- [ ] 方向性讨论 未定事项（基准权重、国债久期等）

## 重要上下文

### AKShare 网络问题
- 东方财富 K 线 API 有严格反爬：~1-2 次/分钟正常，超出触发 `RemoteDisconnected`
- `data_pipeline.py` 已做 monkey-patch（requests.Session.trust_env=False）绕过 VPN 代理残留
- 当前使用新浪数据源 `fund_etf_hist_sina`（东方财富不可达）
- pre_bash.js 限流：东方财富 API 最低间隔 5s，60s 内 3 次触发 60s 冷却

### 安全架构
- settings.json 的 hooks 配置是关键——缺失会导致所有防护失效
- protected-files.json 修改需走 audit 协议（token + marker）
- audit marker 创建用 Node.js（避免 Python/bash 中文编码问题）
- pre_bash.js 的 `\d+` 不能回退为 `\d*`

### 关键参数
- EWMA λ=0.94, ddof=1 样本标准差, 对数收益率（全模块一致）
- 防御 70% / 进攻 30%, 互不穿透
- 回撤止损：8% 告警 / 12% 减半 / 18% 清仓
- 相关性熔断：60 日滚动 + 5 日 SMA, 阈值 0

### 策略绩效（基线，调参前）
- 总收益 -0.70% vs 基准 +34.85%，跑输 35pp
- 最大回撤 -23.83% 超 20% 硬约束
- 根因：趋势过滤过于保守，大部分时间空仓/现金

## 最后状态

2026-05-28：顾问写入 direction.md（阶段 2 基础设施准备），等待执行窗口。
