# 执行指令

> 2026-06-25 | 信号间隔自动补全 — 检测空白期，逐日回放，报告准确标注变化日期

## 背景

今天 check_position 输出"国债ETF的趋势已转负（从上一期 6/11 的 active 池中剔除）"——这句话在 14 天空白期下是错的。真实情况：6/11~6/24 每一天国债 ETF 趋势都为正，只有 6/25 才转负。`_compare_signals` 只做首尾差集，无论中间隔了多少天、有没有变化，全部压缩成一句"从上一期剔除"。

图表侧：`nav_chart.py` 走 `run_backtest` 全量回放，仓位变化天然落在正确日期，**图表不需要改**。

报告侧：`check_position.py` 需要补全缺失天的信号，准确报告哪天变了什么。

## 操作

### 步骤 1 — daily_signal.py：新增间隔回放函数

**修改文件**：`scripts/daily_signal.py`

新增函数 `_replay_gap(prices, state)`：

```python
def _replay_gap(prices, state):
    """逐日回放 state.last_date 到最新数据日之间的趋势信号。
    返回: {
        "gap_trading_days": int,       # 间隔交易日数
        "last_date": str,              # state 中的日期
        "today": str,                  # 最新数据日期
        "daily_active": [{date, active}],  # 逐日 active 集合
        "changes": [{date, event, etf}],   # 变化事件（按时间排列）
    }
    """
```

回放逻辑：
1. 从 `state["last_date"]` 次日起，到 prices 最新日期止，生成交易日列表
2. 每个交易日：用 `close[close.index <= 该日]` 切片 → 调 `trend_strength` 算每只 ETF 趋势 → 确定 active 集合
3. 相邻两天 active 集合对比，有变化记录 event（added/removed）
4. 上限：最多回放 60 个交易日

> 只算趋势强度即可，不需要完整六步信号——active 集合的变化仅取决于 trend_strength > 0。

### 步骤 2 — check_position.py：集成回放 + 修正报告

**修改文件**：`scripts/check_position.py`

在 `_load_state` 之后、生成信号之前：
1. 若有 state 且 `last_date < today` → 调用 `_replay_gap`
2. 输出"期间回顾"段：

**情况 A：间隔内无变化**
```
=== 2026-06-25 仓位报告 ===
上次信号：2026-06-11（距今 10 个交易日）

【期间回顾】
  6/11 → 6/25  持续持有 4 只（沪深300、创业板、纳指、国债ETF），无变化
```

**情况 B：间隔内有变化**
```
=== 2026-06-25 仓位报告 ===
上次信号：2026-06-11（距今 10 个交易日）

【期间回顾】
  6/11 → 6/16  4 只（沪深300、创业板、纳指、国债ETF），无变化
  6/17         卖出 国债ETF（趋势转负）
  6/17 → 6/25  3 只（沪深300、创业板、纳指），无变化
```

**操作指令**基于 `_replay_gap` 的最后一天 active vs 今天 signal active 做差集（而不是跟 14 天前的 state 做差集）。

### 步骤 3 — daily_signal.py 的 format_signal_report 同步修改

`format_signal_report` 增加"期间回顾"段，逻辑同上。

### 步骤 4 — 保存 state

`check_position.py` 和 `daily_signal.py` 运行结束后保存 state（`_save_state`），避免下次运行重复回放。

### 步骤 5 — 测试

新增 `tests/test_signal_gap.py`：

| 测试 | 场景 |
|------|------|
| `test_replay_gap_no_change` | 间隔 14 天空白，趋势全程不变 → 回放确认 0 changes |
| `test_replay_gap_one_change` | 间隔内第 5 天某 ETF 转负 → changes 含 1 条 removed 事件 |
| `test_replay_gap_multi_change` | 间隔内先剔除再恢复 → changes 含 2 条事件 |
| `test_replay_gap_first_run` | state=None → 跳过回放，正常输出 |
| `test_report_output_includes_replay` | 集成测试：mock state 14 天前 → 报告含"期间回顾"段 |

### 步骤 6 — 全量回归

```bash
python -m pytest tests/ --ignore=tests/test_slippage.py -q
```

## 约束

- 不改动 `src/` 下保护区文件
- 图表（nav_chart.py）不改——`run_backtest` 已天然回放所有日期
- 回放上限 60 个交易日
- 测试先行（红灯 → 绿灯）
