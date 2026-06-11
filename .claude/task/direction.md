# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务 1：创建 `仓位` 三合一脚本

### 需求

新建 `scripts/check_position.py`。执行窗口输入 `仓位` 时，运行此脚本，一步完成三件事：
1. 更新 5 ETF 数据
2. 输出当前持仓 + 操作指令
3. 更新 `nav_2026.html` 图表

### 脚本行为

```
$ python scripts/check_position.py

=== 2026-06-11 仓位报告 ===

【当前持仓】
  沪深300    24.8%
  创业板      21.3%
  纳指        19.6%
  黄金        —
  国债ETF    34.3%
  现金        0.0%

【操作指令】
  无需调仓

【风控状态】
  趋势过滤：4/5 通过（黄金剔除）
  波动率缩放：sf=1.18
  相关性熔断：正常（-0.23）
  回撤止损：normal（-3.2%）

图表已更新 → nav_2026.html
```

### 实现方式

```python
# 复用现有模块
from scripts.update_data import update_single_etf       # 更新数据
from scripts.daily_signal import load_prices              # 加载数据
from src.signal_generator import generate_signal, DEFAULT_PARAMS, DEFENSE_NAMES
from src.etf_universe import ETF_UNIVERSE
from scripts.nav_chart import main as update_chart        # 更新图表
```

步骤：
1. 更新 5 ETF parquet（调 `update_single_etf`）
2. 加载数据（调 `daily_signal.load_prices`）
3. 生成信号（调 `generate_signal`）
4. 格式化输出持仓报告（持仓比例 = signal['defense']['target_weights']）
5. 输出操作指令（比较上一次 signal，调 `daily_signal._compare_signals`）
6. 输出风控状态（熔断/回撤/趋势过滤状态）
7. 调 `update_chart()` 生成 `nav_2026.html`

### 输出格式

- 持仓：`target_weights` 按比例显示，未持有的 ETF 标 `—`
- 操作指令：`daily_signal._compare_signals()` 返回的动作列表
- 风控：趋势过滤通过数、sf 值、熔断相关系数、回撤档位

### 文件

- 新建 `scripts/check_position.py`
- 不修改任何现有文件
- `nav_2026.html` 输出到项目根目录

### 测试

1. 先写 `tests/test_check_position.py`，红灯
2. 覆盖：
   - 基础：5 parquet 存在 → 脚本正常执行，输出含「仓位报告」「当前持仓」「操作指令」「nav_2026.html」
   - 输出内容：含 5 只 ETF 名称
   - 图表：确认根目录 nav_2026.html 被生成且包含 6 条 dataset
3. 主代码写完后全量 pytest 绿灯

### 优先级

P0，用户直接需求。

---

## 任务 2：创建命令注册表

新建 `.claude/commands.json`，让执行窗口识别 `仓位` 命令：

```json
{
  "仓位": {
    "script": "scripts/check_position.py",
    "description": "更新数据 → 持仓报告 + 操作指令 + 更新图表"
  }
}
```

执行者启动时读此文件。用户输入匹配到 key → 直接跑对应 script，不读 direction.md。

### 文件

- 新建 `.claude/commands.json`
- 不修改任何现有文件
