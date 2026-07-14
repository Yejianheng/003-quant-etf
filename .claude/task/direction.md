# 执行指令

> 2026-07-14 | 修复：execution_lag=1 下由于隔夜跳空导致 T+1 开盘可用资金不足引发的 repo_cash < 0 漏洞

## 背景

在 `v211` 引入 `execution_lag=1` 开盘价执行机制后，我们发现 32% 的交易日出现了 `repo_cash < 0`（系统性负值）。
**根因**：系统在 T+1 开盘拿到的实际可用资金是 `total_at_open = old_value_open + repo_cash`，但扣减资金时却直接使用了基于 T 日收盘 `nav` 计算出的绝对目标金额 `exec_alloc["positions"]`。当隔夜出现跳空低开时（`total_at_open < T日nav`），按照绝对金额买入会导致资金透支，`repo_cash` 变成负数（形成无成本杠杆，严重污染回测数据）。

## 步骤

### 步骤 1 — 编写测试用例 (红灯检验)

**目标**：在 `tests/` 下（如 `test_backtest_engine.py` 或新建 `test_execution_lag.py`）构造一个 T+1 日开盘大幅跳空低开的场景。
**要求**：T 日收盘满仓，T+1 日开盘价远低于 T 日收盘价，导致 `total_at_open` 严重缩水。
**预期**：修改代码前，运行此测试必须失败（断言 `repo_cash >= 0` 不通过，因为透支产生负数）。

### 步骤 2 — 修复 backtest_engine.py (按比例缩放)

**文件**：`src/backtest_engine.py` (此文件为受保护文件，需严格走 validate → audit → 令牌修改流程)
**位置**：约 162 行，`execution_lag == 1 and pending_alloc is not None:` 逻辑块内。
**改动策略**：将绝对金额扣减改为**按实际开盘资金等比例缩放**扣减。

具体实现建议（在 `for name, target_dollar in exec_alloc["positions"].items():` 循环外先计算比例）：
```python
# exec_alloc 中记录了它生成时的总盘子大小 total_capital
scale_factor = total_at_open / exec_alloc["total_capital"] if exec_alloc["total_capital"] > 0 else 0.0

# 然后在循环中使用 scaled_target
for name, target_dollar in exec_alloc["positions"].items():
    ...
    scaled_target = target_dollar * scale_factor
    # 后续用 scaled_target 计算 current_value 的差值、执行价、股数 positions[name] 和 佣金 total_commission
```
*这样能严格遵循信号的配置比例，且保证总支出（含佣金前）不会超过实际可用的 total_at_open，杜绝负现金。*

### 步骤 3 — 跑全量测试 (绿灯检验)

1. 运行步骤 1 中的测试，确认变绿。
2. 运行所有现有测试（特别是涉及 `execution_lag=0` 和基础引擎特性的测试），确保无回归错误。

### 步骤 4 — 更新 2026 年图表验证

```bash
python scripts/nav_chart.py
```
这会重新跑回测并更新 `nav_2026.html`。打开查阅：
预期 02-02、03-23、06-08 这几天原本极为严重的 repo_cash 负值将被彻底消除（恢复到 0 附近正常残留水平），同时整体 Sharpe 和净值曲线会挤掉水分，回归真实。

## 约束
- 保持 `execution_lag=0` 路径的逻辑完全不变。
- 只有 T+1 开盘执行 (`execution_lag=1`) 且有 `pending_alloc` 时采用此缩放逻辑。
- 此文件处于保护区，务必执行 `validate` 和 `audit`，不要硬闯拦截。
- 按要求每步提交，不可跳过红灯验证直接改代码。