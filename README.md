# 003-quant-etf

ETF 多资产动量轮动量化系统。AI 辅助纪律执行和标的筛选。核心矛盾——人不会代码因此必须依赖 AI 做技术判断——决策责任不可外包。

---

## 策略概要

**纯防御 ETF 动量轮动**（进攻层已搁置）。五只防御标的（沪深300、创业板、纳指、黄金、国债ETF），日频信号链：

```
趋势过滤（Trend Strength > 0）→ 等权分配 → EWMA 协方差 → Vol Target 缩放
    ↓
相关性熔断（股债正相关则全仓 repo）
    ↓
回撤硬止损（-8% 减半 / -12% 警告 / -18% 清仓）
    ↓
最终敞口 = min(vol_scaling_factor, drawdown_multiplier, circuit_breaker_multiplier)
```

完整策略规格见 [方向性讨论.md](方向性讨论.md)。完整测试证据见 [测试报告.md](测试报告.md)。

## 核心参数

| 参数 | 值 | 说明 |
|------|-----|------|
| trend_window | 40 | 趋势判断窗口（30-50 窄带最优，跨期验证通过） |
| **target_vol_beta** | **8%** | **目标波动率（v184 边际换率扫描最优，0.06→0.08 换率 1.05）** |
| vol_tolerance | 1.2% | 容忍带（= beta × 15%，等比缩放） |
| ewma_lambda | 0.94 | RiskMetrics 标准 |
| corr_threshold | 0.0 | 任何正相关即熔断 |
| defense_ratio | 1.00 | 纯防御（进攻层搁置） |
| drawdown 三级 | 8% / 12% / 18% | 减半 / 警告 / 清仓 |

全部参数受 Hook 保护（`protected-contracts.json`），篡改需走 audit 流程。

## 全量绩效（2014-2026，T+1 执行，sf 已生效，target_vol_beta=0.08）

| 指标 | **策略** | 沪深300 | 创业板 | 纳指 |
|------|---------|--------|--------|------|
| Sharpe | **1.206** | 0.19 | 0.31 | 0.20 |
| 年化 | **9.06%** | 4.8% | 12.6% | 6.5% |
| 波动率 | **7.52%** | 22.2% | 33.1% | 31.3% |
| 最大回撤 | **-7.45%** | -46.3% | -69.6% | -85.5% |
| 最差年 | **-3.6%** (2018) | — | — | — |

### sf 漏洞（2026-06-12 发现、验证、修复）

**波动率缩放（sf）存在代码缺陷：被计算但从未被 `allocate_capital` 使用。** 79.1% 交易日 sf≠1.0，仓位从未响应。详见 [策略漏洞验证报告](strateg_漏洞验证_20260612.md)。

**修复两步**（v184→v185）：
1. `portfolio_manager.py` L14：`drawdown_stop["position_multiplier"]` → `execution["final_multiplier"]`，sf 生效
2. `target_vol_beta` 0.10→0.08，`vol_tolerance` 0.015→0.012，基于全量扫描——0.06→0.08 边际换率 1.05（每 1% 回撤换 1.05% 年化），前后半段均稳健

**修复前后对比（T+1，2014-2026）**：

| 指标 | 修复前（无 sf） | sf 生效 + beta=0.10 | **sf 生效 + beta=0.08** |
|------|:---:|:---:|:---:|
| Sharpe | 1.017 | 1.130 | **1.206** |
| 年化 | 11.72% | 9.78% | **9.06%** |
| 最大回撤 | -13.91% | -8.74% | **-7.45%** |
| 最差 12 月 Sharpe | -1.146 | -0.991 | **-0.762** |
| 2018 年 | -6.5% | -5.2% | **-3.6%** |
| 2022 年 | — | -1.3% | **-0.8%** |

**有效原因**：sf = target_vol_beta / predicted_vol。波动率聚集效应——今日高波明日大概率继续高波——sf 在崩盘次日即降敞口。不对称设计（仅缩仓不加仓），纯防御。

**target_vol_beta 扫描（全量 2014-2026，等比容忍带）**：

| beta | Sharpe | 年化 | 回撤 | 边际换率 | 前后半稳健 |
|------|--------|------|------|---------|----------|
| 0.04 | 1.458 | 5.95% | -3.83% | — | ✅ |
| 0.06 | 1.327 | 7.99% | -6.32% | 0.81 | ✅ |
| **0.08** | **1.206** | **9.06%** | **-7.45%** | **1.05** | ✅ |
| 0.10 | 1.130 | 9.78% | -8.74% | 0.57 | ❌ 前半 0.75 |
| 0.12 | 1.097 | 10.45% | -10.69% | 0.41 | ❌ |
| 无sf | 1.017 | 11.72% | -13.91% | — | — |

> 0.08 是边际换率最优（0.06→0.08 每 1% 回撤换 1.05% 年化），过 0.08 换率掉到 0.57。

## 测试状态

**300 passed / 1 failed（预存外部依赖）/ 3 skipped / 零新增回归**

两轮完整测试（旧六阶段 + 新 P0-P3）覆盖：
- 四个模块独立贡献（Ablation：熔断 +0.85 > 趋势过滤 +0.71 >> vol/EWMA = 0）
- 四 Regime 压力测试 + 极端流动性冲击 + 合成无趋势横盘
- 样本外验证（验证期 2021-2026 Sharpe 1.29，同期沪深300 -0.04）
- 滑点/手续费/摩擦鲁棒性扫描
- Look-Ahead Bias 量化（ΔSharpe 0.18，已修正）
- Vol Target 触发审计（79% 交易日触发，系统最高频模块）
- 生存者偏差审计（ETF 上市日校正，无前视偏差）
- Golden Dataset 回归基准
- Trend Window 跨期稳定性验证（40 是 30-50 窄带唯一存活窗口）

详见 [测试报告.md](测试报告.md)。

## 架构

```
src/
├── config.py                       # 配置入口
├── data_pipeline.py                # Step 1：AKShare → Parquet
├── etf_universe.py                 # Step 1：ETF 代码映射
├── trend_strength.py               # Step 2：趋势强度 + 趋势确认机制
├── cross_sectional_momentum.py     # Step 3：截面动量（进攻层用，当前闲置）
├── target_volatility.py            # Step 4：EWMA 协方差 + 缩放因子
├── correlation_circuit_breaker.py  # Step 5：股债相关 + SMA 熔断
├── drawdown_stop.py                # Step 6：8/12/18 三层回撤止损
├── signal_generator.py             # Step 2-6 编排入口
├── portfolio_manager.py            # Step 7：仓位计算 + 资金路由
├── recorder.py                     # 日记录器
├── benchmark.py                    # 基准计算
└── backtest_engine.py              # 回测主循环 + 参数扫描
```

以上 10 个核心引擎文件均受 `protected-files.json` Hook 保护。

## 协作模式

双窗口角色分工，Hook 强制执行边界。

### 顾问窗口（触发词：`顾问`）

- 信息检索：读代码、查日志、git status/log/diff
- 分析决策：审查执行结果、判断审计报告、定技术方案
- 任务调度：写 direction.md 分派任务
- 写入权限：仅 5 个协议文件（role.json / next-session.md / direction.md / outcome.md / recommendation.md）
- 禁止：改业务代码、跑脚本、git commit/push

### 执行窗口（触发词：`执行`）

- 读 direction.md，逐项执行，不询问确认
- 写 outcome.md 汇报结果
- 所有实际操作：跑脚本、改代码、git commit/push、写项目日志、发 release
- 保护区文件修改走 audit 流程（validate → audit → 令牌放行）

### 数据流

```
顾问窗口                    执行窗口
  │                           │
  ├─ 读/分析/决策             ├─ 读 direction.md
  ├─ 写 direction.md ────────→├─ 执行任务
  ├←──── 审查 outcome.md ─────┤
  └─ 写 recommendation.md     └─ git commit/push
```

### 设计原则

决策责任不可外包。顾问做技术判断，执行做精确操作。Hook 在两层之间强制执行边界——代价是流程绕一点，回报是零越界。

---

## 快速开始

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## 版本

### v185 — sf 修复 + target_vol_beta 优化（2026-06-12）

- **sf 修复**：`portfolio_manager.py` `position_multiplier` → `final_multiplier`，波动率缩放正式生效
- **参数优化**：`target_vol_beta` 0.10→0.08（全量扫描边际换率最优），`vol_tolerance` 0.015→0.012（等比缩放）
- **绩效**：Sharpe 1.017→1.206(+0.189)，年化 11.72%→9.06%，回撤 -13.91%→-7.45%(+6.46pp)
- **修复后图表**：`nav_2026.html` 已更新

### v184 — sf 漏洞发现与验证（2026-06-12）

- **发现**：波动率缩放 sf 被计算但从未被 `allocate_capital` 使用，79% 交易日空转
- **验证**：3 个独立脚本确认，修复后 Sharpe +0.112，回撤 -5.17pp
- **交付**：`tests/test_verify_sf_not_applied.py` / `test_slow_bear.py` / `test_sf_enabled.py` + 完整验证报告
- **修复**：仅验证，未改生产代码

### v1.0 — 系统冻结（2026-05-30）

- **六道门禁全线绿灯**
- 纯防御最优，进攻层搁置
- 10 核心源文件 + 42 测试文件 + 8 Hook 参数保护
- 300 条测试，零新增回归
- Golden Dataset 基准就位
- 趋势窗口跨期稳定性验证通过
- 源码/参数/文件三级 Hook 锁定

### v1.0.0 — 回测引擎端到端可运行（2026-05-27）

- 10 步回测开发计划全部完成
- 五模块决策链 + 日循环引擎 + 参数扫描入口
- 架构防火墙三层 Hook 就位
