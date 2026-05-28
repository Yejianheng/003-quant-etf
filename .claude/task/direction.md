# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：重拉 2013-2025 数据 + 重跑参数扫描 + 三基准对比

### 背景

当前数据范围 2018-2025（8 年），缺少 A 股最重要的压力测试场景（2015 股灾、2016 熔断）。5 只 ETF 上市日均在 2013 年前，可拉到 2013 年，覆盖 12 年完整市场周期。

方向性讨论阶段 4 压力测试 4.1 场景即为 2015 A 股股灾——必须有数据才能验证。

### 步骤

#### 步骤 1：拉取 2013-2025 数据

5 只 ETF，新浪数据源（东方财富不可达），覆盖 2013-01-01 ~ 2025-12-31。

```python
import akshare as ak
import pandas as pd
import os
os.makedirs("./data", exist_ok=True)

codes = {"510300": "沪深300", "159915": "创业板", "513100": "纳指", "518880": "黄金", "511010": "国债ETF"}

for code, name in codes.items():
    df = ak.fund_etf_hist_sina(symbol=code)
    df = df.rename(columns={"日期": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"})
    cols = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in cols if c in df.columns]
    df = df[available]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df.to_parquet(f"./data/{code}.parquet")
    print(f"{name} ({code}): {df.index[0].date()} ~ {df.index[-1].date()}, {len(df)} rows")
```

**注意**：
- 必须先 `import src.data_pipeline` 触发 monkey-patch（绕过 VPN 代理残留）
- 新浪 API 每次调用间隔 ≥ 5 秒（pre_bash.js 限流）
- 如数据已覆盖 2013-2025 则跳过

#### 步骤 2：数据验证

确认每文件行数 > 2500（12 年约 3000 交易日）、起始不晚于 2013-07-01。

#### 步骤 3：重跑 12 项参数扫描

使用现有 `scripts/run_phase2_scans.py`（读取 `./data/*.parquet`，自动使用新数据）。

**运行前必须先删除旧 CSV**：数据范围变了，旧 checkpoint 会误判参数组合"已完成"而跳过，导致结果仍是 2018-2025 的。

```bash
rm data/scan_2_*.csv
```

#### 步骤 4：三基准对比

对最优参数（trend_window=40），生成策略 vs 沪深300 vs 创业板 vs 纳指的同期对比表。对比指标：总收益、年化、波动率、Sharpe、最大回撤。

### 约束

- 不修改已有业务代码
- 数据文件覆盖 `./data/*.parquet`，不新增文件
- 扫描结果覆盖 `./data/scan_*.csv`
- 不触碰保护区

### 验收标准

- [ ] 5 个 parquet 文件起始 ≤ 2013-07-01，≥ 2500 行
- [ ] 12 项扫描全部完成，CSV 已更新
- [ ] 策略 vs 三基准对比表：策略在收益和回撤维度均优于所有单一指数
- [ ] 全量测试 79 passed / 3 skipped（零回归）

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
