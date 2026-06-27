# 执行指令

> 2026-06-27 | 5分钟执行间隔测试

## 背景

用户实盘操作：T+1 日 9:30 隔夜卖单成交 → 9:31 定时买单成交。保守场景按 5 分钟间隔估算。

回测基准假设买卖同价（T+1 close）。本次测试量化 5 分钟间隔引入的跟踪误差，不修改任何源代码。

## 测试设计

三个测试，全部在 `tests/test_execution_gap.py`。不修改 `src/` 下任何文件。

### 测试 A — 上限测试：开盘 vs 收盘执行

直接调用 `run_backtest()`（现有接口，不改参数），拿到每日持仓和信号。对每次换手事件：
- **close 执行**：用 T+1 收盘价，重新计算组合净值（验证与回测输出一致）
- **open 执行**：买卖均改用 T+1 开盘价，重新计算组合净值

对比两条净值曲线：年化收益差、Sharpe 差、回撤差。开盘和收盘的差异 = 全天最大漂移，5 分钟间隔的影响必然小于此值。

数据来源：`data/*.parquet` 含 OHLC 中的 open 和 close 列。

### 测试 B — 5 分钟间隔 Monte Carlo

1. 拿到换手事件列表（日期、卖出 ETF、买入 ETF）
2. 对每笔换手，卖出价 = 当日开盘价（精确）
3. 买入价 = 当日开盘价 + 5min 漂移，漂移从历史 open-to-close 收益分布 bootstrap：
   - 单日 σ_intraday = std(open_to_close_returns)，每只 ETF 各自计算
   - σ_5min = σ_intraday / sqrt(48)，48 = 240分钟 / 5分钟
   - 考虑卖买 ETF 的 daily 相关性，生成相关的随机抽样
4. N=1000 次模拟，每次对所有换手事件独立抽样
5. 输出：年化收益偏移分布（均值、标准差、95% CI）

### 测试 C — 跨风险源切换

筛选换手事件中卖出 ETF 和买入 ETF 属于不同风险源的（如权益→黄金、权益→国债）。
重复 MC 模拟，单独统计。这类切换相关性最低，跟踪误差最大。

## 步骤

### 步骤 1 — 写测试文件 skeleton + 测试 A

文件：`tests/test_execution_gap.py`

```python
# 测试 A: open vs close 执行
def test_open_vs_close_execution():
    # 1. 调用 run_backtest(execution_lag=1) 拿信号
    # 2. 从 data/*.parquet 读 open/close 价格
    # 3. 用 open 价重算每笔换手的成交
    # 4. 输出两条净值曲线对比
    # 断言: 年化收益差 < 0.3pp
```

跑 → 必须红（测试文件新建，未实现）

### 步骤 2 — 实现测试 A

实现后跑 → 必须绿。

### 步骤 3 — 写测试 B

```python
# 测试 B: 5分钟间隔 MC
def test_five_minute_gap_monte_carlo():
    # 1. 提取换手事件
    # 2. 计算每只 ETF 的 σ_intraday
    # 3. N=1000 MC
    # 4. 输出分布统计
    # 断言: 均值绝对值 < 0.05pp/年
```

跑 → 红 → 实现 → 绿。

### 步骤 4 — 写测试 C

```python
# 测试 C: 跨风险源切换
def test_cross_asset_gap():
    # 1. 筛选跨风险源换手
    # 2. 单独 MC
    # 3. 对比同风险源 vs 跨风险源
```

跑 → 红 → 实现 → 绿。

### 步骤 5 — 全量测试 + 写 outcome

```bash
pytest tests/test_execution_gap.py -v
pytest  # 全量确认无回归
```

## 约束

- **不修改 src/ 下任何文件**
- 测试文件独立，只 import 现有公开接口
- 每步提交
