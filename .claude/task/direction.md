# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：策略漏洞验证 — sf 生效 + 慢熊检测

### 背景

顾问审查发现两个策略漏洞，需要在**不修改现有生产代码**的前提下验证：
1. 波动率缩放 sf 算出来了但没被 `allocate_capital` 应用
2. 趋势过滤对慢熊不敏感（trend_strength 微正微负）

### 验证 1：sf 是否真的未生效

验证方式（只读分析，不改代码）：

1. 对比 `signal["defense"]["scaling_factor"]` 与 `signal["execution"]["final_multiplier"]` 的差异
2. 追踪 `allocate_capital` 源码，确认它只用 `drawdown_stop["position_multiplier"]`，没用 `execution["final_multiplier"]`
3. **额外检查**：`backtest_engine.py` L138-141 清盘恢复路径是唯一手动设置 `final_multiplier` 的地方，虽最终也不被 `allocate_capital` 消费，但验证报告应记录此处
4. 抽样 200 个交易日，统计 sf ≠ 1.0 的占比
5. 如果 sf 确实被丢弃，输出「已验证，sf 从未被应用」

### 验证 2：trend_strength 在慢熊场景的表现

1. 写一个独立的慢熊验证脚本 `tests/test_slow_bear.py`：
   - 从 parquet 加载 2018 年数据
   - 统计 2018 年每日各 ETF 的 trend_strength 分布
   - 统计 2018 年信号变化频率（与全期对比）
   - 分析 2018 年纳指 trend_strength 在 0 上下穿越次数

2. **输出**：控制台打印统计表格 + 结果写入 `data/slow_bear_2018.csv`

3. 可选：使用 `trend_confirmation(method="price_ma")` 重跑 2018 年信号（不改 DEFAULT_PARAMS，仅测试脚本传参），对比结果：
   - 信号变化次数
   - 累计收益差异
   - 回撤差异

### 验证 3（如果验证 1 确认 sf 未生效）

写独立测试脚本 `tests/test_sf_enabled.py`，验证 sf 生效后的影响：

- **注入方式**：使用 `unittest.mock.patch` 猴子补丁 `src.portfolio_manager.allocate_capital`，将其中的 `dd_mult = signal["drawdown_stop"]["position_multiplier"]` 替换为 `dd_mult = signal["execution"]["final_multiplier"]`（后者已 = min(sf, dd_mult)）。补丁仅测试脚本内生效，不修改 src/
- 通过 params 传递参数（不改 DEFAULT_PARAMS）
- 仅测纯防御配置
- 对比 2018 年、2019 年、2020 年三年的差异
- 全量对比 2014-2026

### 输出

所有结论写入 `strateg_漏洞验证_20260612.md`（项目根目录），含：
1. sf 是否真的未生效 → 证据
2. 慢熊 2018 年 trend_strength 穿越频率
3. 两个修复的预期影响（如已测）

### 约束

- **不修改任何 src/ 下的生产代码**
- **不修改 DEFAULT_PARAMS**
- 所有测试通过传参覆盖
- 测试脚本放 tests/ 目录
- 验证报告放项目根目录

### 测试

- 新增测试红灯 → 全绿
- 全量 pytest 绿灯
