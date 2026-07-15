# 执行指令

> 2026-07-15 | 数据管线加固：Web 核验 + 时间门禁 + 阻断机制

## 背景

513100 在 7/14 的 parquet 数据错误（close=2.160，真实=2.17）。根因：v211 session 09:31 拉取腾讯财经 API，返回盘中不完整日线，`update_single_etf` 无校验直接入库。

两个缺陷：①无时间门禁（盘中数据也被接受）②无外部核验（API 返回什么就存什么）。

## 涉及文件

| 文件 | 保护状态 | 改动性质 |
|------|---------|---------|
| `scripts/update_data.py` | 非保护区 | 重写 `update_single_etf()`，修改 `main()` |
| `scripts/nav_chart.py` | 非保护区 | 修改 `update_all_etfs()` 和 `main()` |
| `scripts/check_position.py` | 非保护区 | `仓位` 命令入口，数据更新后加核验阻断 |

`src/data_pipeline.py` 不动。

---

## 步骤 1 — `scripts/update_data.py`：时间门禁 + 拉取（不入库）

### 1.1 时间门禁

`update_single_etf()` 开头加判断：若 `end_date == 今天 且 当前时间 < 15:00`，将 `end_date` 改为昨天。

```python
from datetime import datetime
if end_date == date.today().strftime("%Y-%m-%d") and datetime.now().hour < 15:
    end_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
```

### 1.2 拉取逻辑（不入库）

按数据源优先级拉取：**腾讯 → 东方财富（含新浪 fallback）→ 两源均空则阻断**。

哪个源拉到数据就用哪个，不要求两个源都拉到。

返回 dict：
```python
# 拉到数据，待核验
{"ok": True, "needs_verify": True, "name": "纳指", "code": "513100",
 "source": "tx", "new_data": <DataFrame>, "latest_close": 2.170, "latest_date": "2026-07-14"}

# 不需要更新（已是最新）
{"ok": True, "needs_verify": False, "name": "纳指", "code": "513100", "reason": "up_to_date"}

# 两源均空，阻断
{"ok": False, "name": "纳指", "code": "513100", "reason": "no_data"}
```

**关键**：拉到数据后**不写入 parquet**，返回 `new_data` 和 `latest_close` 给上层，等 Web 核验通过后再入库。

### 1.3 `main()` 汇总

收集所有 ETF 结果，打印逐条状态：

- 全部 `needs_verify=False` → 打印"数据已是最新" → `sys.exit(0)`
- 有 `needs_verify=True` → 打印核验清单（见步骤 2）→ `sys.exit(0)`
- 有 `ok=False` → 打印失败项 → `sys.exit(1)`

---

## 步骤 2 — `scripts/update_data.py`：入库函数

新增 `save_verified_data(code, new_data, data_dir)` 函数：

```python
def save_verified_data(code: str, new_data: pd.DataFrame, data_dir: str = "data") -> None:
    """Web 核验通过后，将 new_data 合并写入 parquet。"""
    path = os.path.join(data_dir, f"{code}.parquet")
    existing = load_from_parquet(path)
    combined = pd.concat([existing, new_data])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()
    save_to_parquet(combined, path)
```

该函数独立于 `update_single_etf()`，由执行窗口 AI 在 Web 核验通过后直接调用，不经过拉取逻辑。

---

## 步骤 3 — Web 核验流程（执行窗口 AI 执行）

### 3.1 核验触发

`check_position.py`（或 `update_data.py`）输出待核验清单后，**执行窗口 AI 自动对每只需要核验的 ETF 调 WebFetch**：

```
WebFetch: https://q.stock.sohu.com/cn/{code}/lshq.shtml
提取最新交易日的收盘价，与脚本输出的 latest_close 对比。
偏差 ≤ 0.3% → 核验通过
偏差 > 0.3% → 核验失败
```

搜狐不可用时换东方财富：`https://quote.eastmoney.com/fund/{code}.html`

### 3.2 核验通过 → 入库

```bash
python -c "from scripts.update_data import save_verified_data; from src.data_pipeline import fetch_etf_daily_tx; ..."
```

或更直接：
```bash
python -c "
import pandas as pd
from scripts.update_data import save_verified_data
# 用核验通过的 close 构造 new_data 行，写入 parquet
"
```

### 3.3 核验失败 → 阻断

```
[核验失败] 513100 API返回=2.160 Web核验=2.170 偏差=0.46%
建议半小时后重试
```

---

## 步骤 4 — `scripts/check_position.py`：`仓位` 命令加核验阻断

`check_position.py` 是每日 `仓位` 命令的入口。**改为两次运行模式**：

**第一次运行**（拉取 + 输出核验清单）：
```
check_position.py
  → update_single_etf() ×5    # 拉取（不入库）
  → 收集 needs_verify=True 的 ETF
  → 打印核验清单 + 调用指令
  → sys.exit(0)
```

**执行窗口 AI**：WebFetch 核验 → 调 `save_verified_data()` 入库

**第二次运行**（信号 + 图表）：
```
check_position.py
  → update_single_etf() ×5    # 全部 up_to_date，跳过
  → check_freshness()
  → load_prices()
  → generate_signal()
  → nav_chart.main()
```

**改动**：`main()` 中 `update_single_etf()` 返回后，若有 `needs_verify=True` 的 ETF，打印核验清单并 `sys.exit(0)`。若全部 `needs_verify=False`（第二次运行），继续信号生成流程。

核验清单格式：
```
[待核验] 513100 腾讯 close=2.170
[待核验] 510300 腾讯 close=4.837
---
请执行窗口 AI WebFetch 核验以上收盘价：
  https://q.stock.sohu.com/cn/{code}/lshq.shtml
核验通过后：python -c "from scripts.update_data import save_verified_data; ..."
然后重新运行 仓位 命令。
```

---

## 步骤 5 — `scripts/nav_chart.py`：同步加固

### 5.1 `update_all_etfs()` 改为走 `update_single_etf()` 新逻辑

`update_all_etfs()` 调用 `update_single_etf()`（非 `update_data.main()`），保持与 `check_position.py` 一致的拉取行为。

### 5.2 `main()` 阻断

拉取后若有 `needs_verify=True` → 打印核验清单 → `sys.exit(0)`。与 `check_position.py` 第一次运行行为一致。

---

## 步骤 6 — 测试

### 6.1 写测试

`tests/test_data_validation.py`：
- 时间门禁：15:00 前 `end_date` 被截断到昨天
- 时间门禁：15:00 后 `end_date` 保持不变
- 拉取成功返回 `needs_verify=True`
- 两源均空返回 `ok=False`

### 6.2 跑全量测试

```bash
python -m pytest tests/ -x -q
```

---

## 步骤 7 — 端到端验证

```
python scripts/update_data.py   # 拉取 + 输出核验清单
# → 执行窗口 AI WebFetch 核验 → 入库
python scripts/nav_chart.py     # 生成图表
```

## 约束

- `src/data_pipeline.py` 不动
- 数据源优先级：腾讯 > 东方财富（含新浪 fallback），单源拉到即可
- 拉取 ≠ 入库，Web 核验通过后才入库
- 时间门禁：15:00 前不拉当日
- 偏差阈值：0.3%
- 阻断提示：`建议半小时后重试`
