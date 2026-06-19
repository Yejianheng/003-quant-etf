# 下一会话

> 顾问每次会话结束前更新。新会话顾问读取此文件恢复上下文。

## 当前阶段

策略封闭。A 股版 v0.18-release + 美股跨市场验证均已完成。系统 8 参数全扫描无盲区，策略逻辑跨市场成立。

## 本次结论

1. **A 股版封闭**：v0.18-release，8 参数全扫描，T+1 可执行基准，Sharpe 1.06
2. **美股版验证通过**：同参数盲搬至 SPY/QQQ/GLD/TLT/BIL，Sharpe 0.86，碾压全部基准
3. **跨市场成立**：同区间（2013-2026）A 股 Sharpe 1.13 vs 美股 1.04，两者均远超各自基准
4. **最优久期不同**：A 股 SHY（短久期），美股 TLT（长久期 20Y+）——股债负相关稳定性差异
5. **2008 验证**：策略 -5.1% vs SPY -56.4%，回撤止损生效（熔断未触发，股债负相关）
6. **2022 验证**：策略 +0.7% vs 60/40 -22.9%，熔断大量触发转入 repo，避开股债双杀
7. **报表补全完成**：22 行逐年表 + 同区间 A/B 对照 + 2008/2022 专项 + 最终结论，outcome + recommendation 双通过

## 待处理

- [ ] G3（全天候基准）：搁置
- [ ] 美股版参数重扫（0.18 对美股未必最优）
- [ ] 进攻层复活（美股有 11 个行业 XL* ETF，截面动量可能在美股上成立）
- [ ] 东方财富 API 网络排查（恢复可将 SPY 延至 1993，覆盖 2000 互联网泡沫）
- [ ] FRED NASDAQ100 集成（1993+，作为 QQQ 早期代理，代码阻力低）← 推荐下一项

## 重要上下文

### 核心参数（v0.18-release，T+1 可执行）

```
target_vol_beta = 0.18
vol_tolerance = 0.027
trend_window = 40
ewma_lambda = 0.94
corr_window = 60, corr_sma_window = 5, corr_threshold = 0.0
drawdown = [0.08, 0.12, 0.18]
defense_ratio = 1.00
```

### A 股 vs 美股绩效

| | A股 (2012-2026) | 美股 (2005-2026) | 同区间 A股 (2013-2026) | 同区间 美股 |
|------|:--:|:--:|:--:|:--:|
| Sharpe | 1.06 | 0.86 | 1.13 | 1.04 |
| 回撤 | -13.8% | -17.0% | -9.2% | -10.3% |

### 核心文件

- `attribution/system_audit.md` — A 股系统审计（9 节完整技术文档）
- `attribution/us_validation.md` — 美股跨市场验证（9 节）
- `scripts/backtest_us.py` — 美股回测模块（FRED 债券合成 + AKShare 三级 fallback）
- `src/signal_generator.py` — 六步决策链（已参数化支持跨市场）
- `src/backtest_engine.py` — 日循环回测引擎（已参数化 repo_rate/defense_names/benchmark_specs）
- `output/us_comparison_TLT.csv` — 美股最优配置全期对照
- `output/us_bond_duration_comparison.csv` — 久期三档对比
- `项目日志/2026-06-18.md` — 全天记录（13 章）

### 遗留提示

- outcome §3 对照表未注明 execution_lag（recommendation 建议补注）
- FRED 债券合成不含凸性调整，极端利率年份 TLT 误差可能 2-3pp
