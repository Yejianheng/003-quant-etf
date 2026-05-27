# 下一会话

> 顾问每次会话结束前更新。新会话顾问读取此文件恢复上下文。

## 当前阶段

回测开发 — **10 步全部完成**，下一步进入真实数据回测 + 参数验证阶段。

## 已完成

- [x] Step 1-10：数据管线 → 回测主循环，13 源文件 + 12 测试文件
- [x] 五模块决策链：趋势强度 → 截面动量 → 目标波动率 → 相关性熔断 → 回撤止损
- [x] 信号生成器（编排层）+ 组合管理器（进攻空仓不回流）+ Recorder + 基准计算
- [x] 回测引擎：日循环 + 参数扫描入口，无前视偏差
- [x] 技术隐患 4/4 清零
- [x] pre_bash.js 限流系统（从 002 移植，滑动窗口 60s/3→60s/6→120s 冷却）
- [x] settings.json hook 配置已激活（之前缺失，三层防护从未生效——已修复）
- [x] protected-files.json 已包含 .claude/settings.json
- [x] pre_bash.js `\d*` → `\d+` bug 已修复（裸 `>` 被吃掉导致写保护失效）
- [x] 全量测试：60 passed / 3 skipped（AKShare 限流） / 0 failed

## 待处理

- [ ] 拉真实 ETF 数据跑完整回测（清代理、等东方财富冷却后调用 fetch_etf_daily）
- [ ] 方向性讨论 阶段 2：16 项全参数扫描（当前仅在合成牛市数据上预跑了 12 组合）
- [ ] 进攻层行业 ETF 候选池构建（流动性/规模筛选）
- [ ] 模拟实盘模块（滑点、整数股数、手续费）

## 重要上下文

### AKShare 网络问题
- 东方财富 K 线 API 有严格反爬：~1-2 次/分钟正常，超出触发 `RemoteDisconnected`
- `data_pipeline.py` 已做 monkey-patch（requests.Session.trust_env=False）绕过 VPN 代理残留
- 调用前需确保：① 无 VPN 代理干扰 ② 东方财富冷却期已过（上次大量请求在 ~17:00）
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

## 最后状态

2026-05-27：v1.0.0 发布，10 步计划全部完成 + 安全漏洞修复，32 commits，工作区干净。
