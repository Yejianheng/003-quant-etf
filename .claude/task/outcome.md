# 执行结果

> 2026-06-12 | v181 direction 执行完毕

## 任务：策略漏洞验证 — sf 生效 + 慢熊检测

### 验证 1：sf 未生效 — 已确认

- `allocate_capital` 只读取 `signal["drawdown_stop"]["position_multiplier"]`，从未读取 `signal["execution"]["final_multiplier"]`
- 全量 3006 个交易日中，sf ≠ 1.0 占比 79.1%
- 末端验证：sf=0.5216 时 exposure 仍为 1,000,000（应约为 521,628）
- **结论：已验证，sf 从未被应用**

### 验证 2：trend_strength 慢熊表现 — 部分成立

- 纳指 2018 年 0 轴穿越 6 次，信号变化频率 29.8%（与全期 28.2% 接近）
- Q1-Q2 存在趋势模糊期（2-5 月纳指 trend_strength 在 ±0.5 摇摆）
- A 股才是 2018 年真正弱项（沪深 300 positive 仅 21%），趋势过滤正确排除
- price_ma 方法变化频率更高 (36.0%)，不优于 trend_strength
- **结论：慢熊穿越不严重，暂不需要紧急修复**

### 验证 3：sf 修复影响 — 净正向

全量 2014-2026 (T+1)：
- Sharpe: 1.017 → 1.130 (+0.112)
- 总收益: 275.2% → 204.4% (-70.8pp)
- 最大回撤: -13.91% → -8.74% (+5.17pp)

2020 年效果最明显：回撤从 -8.56% 降至 -3.37%
**结论：sf 修复是净正向的，Sharpe 提升、回撤收窄**

### 交付物

- `tests/test_verify_sf_not_applied.py` — 验证 1 分析脚本
- `tests/test_slow_bear.py` — 验证 2 慢熊分析脚本
- `tests/test_sf_enabled.py` — 验证 3 sf 生效对比脚本
- `strateg_漏洞验证_20260612.md` — 完整验证报告

### 测试

- 全量 pytest: 328 passed, 2 failed (test_nav_chart.py 预存失败，非本次引入), 1 skipped
- 未修改任何 src/ 生产代码

---

**请顾问窗口审查。**
