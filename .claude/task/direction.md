# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 执行纪律（强制）

**每步完成 → 验证通过 → 提交 → 再进行下一步。** 禁止批量执行后统一提交。

## 前置修复：顾问角色 Bash 门禁误杀纯读命令

**问题**：`pre_bash.js` L110 角色门禁逻辑 `taskPaths.length > 0 &&` 导致所有不涉及文件路径的命令（`ls`、`git status`、`python -c "..."` 等）被误拦。

**根因**：空路径数组时 `length > 0` 为 false → `allTaskFiles` 为 false → exit 2。

**修复**：`.claude/hooks/pre_bash.js` L110，改一行：

```javascript
// 改前
const allTaskFiles = taskPaths.length > 0 && taskPaths.every(function(p) { return p.includes(".claude/task/"); });
// 改后
const allTaskFiles = taskPaths.length === 0 || taskPaths.every(function(p) { return p.includes(".claude/task/"); });
```

**含义**：没提取到文件路径 → 纯读命令 → 放行。有路径但全在 `.claude/task/` → 放行。其他 → 拦截。

**注意**：`.claude/hooks/` 是保护区目录，需走 validate→audit→token 流程。

---

## 当前任务：进攻层架构验证 — 动态 ETF 接入 + 6 风险源稳定性测试

### 目标

从 2013 年起跑一次完整回测，进攻层 ETF 随上市日期动态接入（有就有，没有就没有），验证：
1. 进攻层 ETF 从 0→6 逐步增加的过程中，策略是否持续有效
2. 6 风险源全部就位后，K 值多少最稳定
3. 与三基准的同期对比

### 核心设计：动态 ETF 接入

```
2013 ─────── 2016-08 ─────── 2017-08 ─────── 2019-04 ─────── 2020-03 ─────── 2025
防御 5 只     +证券+军工       +有色          +酒+半导体      +创新药
进攻 K=0     K≤2            K≤3           K≤5            K≤6
```

回测引擎改动：`run_backtest` 的日期计算从 **交集** 改为 **并集**，即每日只要有一只有数据就跑，缺数据的 ETF 当天不参与。

### 固定参数

| 参数 | 值 | 说明 |
|------|:--:|------|
| trend_window | 40 | 阶段 2 扫描最优 |
| ewma_lambda | 0.94 | RiskMetrics 标准 |
| target_vol_beta | 0.10 | 防御层 10% 目标波动 |
| target_vol_alpha | 0.20 | 进攻层 20% 目标波动 |
| defense_ratio | 0.70 | 防御 70% / 进攻 30% |
| 其余 | DEFAULT_PARAMS | 不变 |

**参数修正触发条件**（不在此次测试范围内，仅记录）：
- 进攻层空仓率 > 80% → 复查 trend_window（行业 ETF 波动大，40 日可能太短）
- 所有 K 所有时段系统性跑输纯防御 → 复查整条 offense 链路
- 全时段全 K 稳定跑赢 → 参数无需修正

### 配置

| 配置 | 含义 |
|------|------|
| 纯防御 | defense_ratio=1.0，进攻层不参与 |
| 防御+K=2~6 | defense_ratio=0.70，offense_top_k=2/3/4/5/6 |

共 6 种配置（纯防御 + K=2,3,4,5,6 各一）。

### 输出要求

每种配置输出一张 **同期三基准对比表**（策略 + 沪深300 + 创业板 + 纳指），指标：总收益 / 年化 / 波动率 / Sharpe / 最大回撤。

全部跑完后输出：
1. **K 值收益曲线**：6 种配置的净值曲线叠在同一张图上
2. **进攻层演进过程**：随 ETF 新增，进攻层持仓数、空仓率、行业分布的变化
3. **稳定性排名**：各 K 值跑赢三基准数、最大回撤、进攻层空仓率
4. **推荐 K 值 + 理由**

---

### 步骤 0：检查数据实际日期范围（强制前置）

执行窗口先跑一次全量检查：

```
python -c "
import pandas as pd, os
for f in sorted(os.listdir('data')):
    if f.endswith('.parquet'):
        df = pd.read_parquet(f'data/{f}')
        print(f'{f}: {df.index.min().date()} ~ {df.index.max().date()} ({len(df)} rows)')
"
```

输出作为 direction.md 补充，用于确认：
- 每只 ETF 的实际数据起始日
- 防御 5 只最早共同起始日（预期 2013-07 附近）
- 进攻 6 只各自的上市日期

**不修改 direction，仅记录事实。**

---

### 步骤 1：建测试，跑红灯

新建 `tests/test_dynamic_backtest.py`：

```
基础路径：
  - run_backtest(含 2020 年才上市的 ETF) → 回测从最早防御 ETF 日期开始（非交集）
  - 2013 年某日的 signal 中 offense.rankings 为空 → K=0，进攻资金全进 repo

边界：
  - prices 中某 ETF 的 DataFrame 为空 → 跳过该 ETF，不影响回测
  - 日期并集中缺失某 ETF 的某天 → 该 ETF 当日不参与进攻排名

引擎改动验证：
  - union_dates(prices) → 返回日期并集，非交集
  - get_available_etfs(prices, date) → 返回该日期有数据且 ≥min_history 的 ETF 列表
```

跑 → 必须全红 → 提交。

---

### 步骤 2：改引擎 + 写回测脚本

#### 2.1 改 `src/backtest_engine.py`：
- `run_backtest` 日期计算：交集 → 并集
- 每日信号生成前：过滤出当前日期之前已有 ≥120 天数据的 ETF
- ETF 动态接入：新 ETF 满足 min_history 后自动进入进攻层候选

#### 2.2 写 `scripts/run_dynamic_backtest.py`：
- 加载防御 5 只 + 进攻 6 只数据（防御全量加载，进攻按文件存在加载）
- 遍历 6 种配置（纯防御 + K=2~6）
- 每种配置跑 `run_backtest`
- 输出绩效 CSV + 三基准对比表

#### 2.3 跑步骤 1 的测试 → 全绿

#### 2.4 提交

---

### 步骤 3：运行全部回测（6 种配置）

逐配置执行，每完成一个输出三基准对比表。

6 种配置跑完后，确认全量测试零回归。

提交。

---

### 步骤 4：生成分析报告

写 `scripts/analyze_dynamic_results.py`：
1. 读 6 种配置的结果 CSV
2. 画 K 值收益对比图（6 条净值曲线叠图）
3. 计算各 K 值的跨全期绩效 + 进攻层空仓率 + 参与率
4. 输出推荐 K 值

跑测试 → 全绿 → 提交。

---

### 步骤 5：最终输出

将分析结论写入 outcome.md：
- 推荐 K 值 + 支撑数据
- 每种配置 vs 三基准的完整对比表
- 进攻层从 0→6 的演进过程
- 风险提示

提交。

---

### 约束

- 每步独立提交
- 旧测试安全带：每步跑全部测试，零回归
- 参数固定不调参
- 数据覆盖：2013 ~ 最新可用日期

### 验收标准

- [ ] 步骤 0：数据日期范围确认
- [ ] 步骤 1：测试写就，跑红灯，提交
- [ ] 步骤 2：引擎改造 + 脚本完成，测试全绿，提交
- [ ] 步骤 3：6 种配置全部跑完，零回归，提交
- [ ] 步骤 4：分析模块完成，提交
- [ ] 步骤 5：outcome.md 写入最终结论，提交
- [ ] 每种配置都输出三基准对比表
- [ ] 全量测试零回归

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
