# outcome.md — execution_lag=1 repo_cash < 0 修复

> 2026-07-14 | 执行者角色 | 审计提交后

## Audit 报告

- **审计模型**：Qwen3-Max（异构盲审）
- **结果**：PASS
- **审计意见**：未发现安全或架构违规，允许执行写入。

## Diff 摘要

**文件**：`src/backtest_engine.py`（受保护区）

**改动位置**：约第 163-179 行，`execution_lag == 1 and pending_alloc is not None` 块内。

**改动前**：
直接使用 T 日绝对金额 `target_dollar` 买入，导致跳空低开时透支。

**改动后**：
```python
            # [2026-07-14] 修复：隔夜跳空导致 total_at_open < nav 时，按比例缩放目标金额避免负现金
            scale_factor = total_at_open / exec_alloc["total_capital"] if exec_alloc.get("total_capital", 0) > 0 else 0.0
            
            for name, target_dollar in exec_alloc["positions"].items():
                if name not in prices or today not in prices[name].index:
                    continue
                price_open = prices[name].loc[today, "open"]
                if price_open <= 0:
                    continue
                per_slippage = (slippage_bps_map or {}).get(name, slippage_bps)
                
                scaled_target = target_dollar * scale_factor
                current_value = prev_positions.get(name, 0.0) * price_open
                exec_price = price_open * (1.0 + per_slippage / 10000.0) if scaled_target > current_value else price_open * (1.0 - per_slippage / 10000.0)
                positions[name] = scaled_target / exec_price
                total_commission += abs(scaled_target - current_value) * commission_rate
            # 现金守恒：总可支配资金 - 新持仓开盘市值 - 佣金
            new_target_sum = sum(
                d * scale_factor for n, d in exec_alloc["positions"].items()
                if n in prices and today in prices[n].index
            )
            repo_cash = total_at_open - new_target_sum - total_commission
```

## 执行结果（2026-07-14 完成）

| 检查项 | 结果 |
|--------|------|
| 新测试 test_execution_lag.py (3 场景) | 3/3 PASS |
| 全量测试 (452, 跳过 1 预存) | 零回归 |
| scale_factor 合成测试 (10% 跳空) | 红灯→绿灯 |
| 实盘数据修复前后对比 | Sharpe 1.1848→1.1855，差异可忽略 |
| repo_cash < 0 天数 | 修复前后均 0/3026 |
| NAV = exposure + repo_cash 恒等式 | 逐日零偏差 |
| Δ% 手工验算 vs 图表 | 一致 |
| T-1/T0 数据定义 | 正确，无 off-by-one |

**结论**：scale_factor 修复在实盘数据上无差异（v211 开盘价执行 + vol_scaling 现金缓冲已足够吸收正常跳空），但作为极端行情安全网保留。数据定义链路自洽。