# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 执行纪律（强制）

**每步完成 → 验证通过 → 提交 → 再进行下一步。**

---

## 当前任务：每日信号脚本 `scripts/daily_signal.py`

### 背景

策略年均 15 次交易，手动执行完全可行。需要一个收盘后运行的脚本：读最新数据 → 算信号 → 告诉用户今天做什么。

### 步骤 1：写测试 → 红灯

写 `tests/test_daily_signal.py`，场景：

**基础路径：**
- 5 只 ETF 全部加载 → 生成信号 → 输出报告含趋势强度/熔断/回撤/目标持仓
- 首次运行（无历史持仓状态文件）→ 输出"首次建仓"
- 连续两天信号不变 → 输出"无需调仓"
- 信号变化（某 ETF inactive）→ 输出"卖出"指令

**边界：**
- 仅 4 只 ETF parquet → 报错 exit code 1
- 交易日 < 120 → 报错 exit code 1
- 熔断触发 → 输出"全部清仓"

**异常：**
- 某 ETF parquet 缺失 → 跳过，不影响其余
- data/ 目录无 parquet → 加载失败报错

**跑 → 必须全红。** 因为 `scripts/daily_signal.py` 还不存在。

### 步骤 2：写主代码 → 绿灯

写 `scripts/daily_signal.py`，功能：
- `load_prices()`：加载 defense 5 ETF 的 parquet
- `generate_signal()`：调用现有引擎生成信号
- `format_signal_report()`：格式化为可读中文报告
- `main()`：入口，处理状态文件读写

输出格式见顾问提供的代码框架。

### 步骤 3：验证

- 全量测试零回归
- 用现有 parquet 实际运行一次，确认输出可读

### 验收

- 脚本可用：`python scripts/daily_signal.py` 输出完整信号报告
- 8 条新测试全绿 + 全量零回归

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
