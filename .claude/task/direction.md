# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet
Step 2  趋势强度      年化收益率 / 年化波动率
Step 3  截面动量      20+60 日 z-score 合成排名
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA
Step 6  回撤硬止损    8/12/18 三层
Step 7  信号生成器    编排 Step 2-6
Step 8  组合管理器    仓位计算 + 资金路由
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 1 — 数据管线

### 任务

从 AKShare 拉取 ETF 历史日线数据，存储为 Parquet 文件。覆盖防御层全部标的（沪深300/创业板/纳指/黄金/国债ETF）的 ETF 行情。

### 测试（先写，必须红灯）

`tests/test_data_pipeline.py` — 3 个场景：

1. **正常拉取**：调用 fetch_etf_daily("510300", "2024-01-01", "2024-12-31")，返回非空 DataFrame，含列 open/high/low/close/volume，index 为日期
2. **空参数处理**：起止日期为周末/节假日时，不抛异常，返回空 DataFrame
3. **存储读取往返**：DataFrame 写入 Parquet → 读回 → 与原 DataFrame 完全一致（列、值、行数）

### 代码（测试红灯后再写）

`src/data_pipeline.py` — 两个函数：

```python
fetch_etf_daily(code, start_date, end_date)
"""
从 AKShare 拉取单只 ETF 日线，返回 pandas DataFrame。
code: ETF 代码，如 "510300"（沪深300ETF）
"""
  → 调 akshare.fund_etf_hist_em(symbol=code, start_date=..., end_date=..., adjust="qfq")
  → 保留列：日期(设为index)、开盘、最高、最低、收盘、成交量
  → 英文列名：date/open/high/low/close/volume

save_to_parquet(df, path)
load_from_parquet(path) → DataFrame
"""
Parquet 读写，保留 index。
"""
```

对照表文件 `src/etf_universe.py` — ETF 代码映射：

```python
# 防御层标的 → ETF 代码（上交所）
ETF_UNIVERSE = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}
```

### 约束

- 不写趋势强度、动量、回测等任何后续模块代码
- AKShare 首次调用可能较慢，测试需设合理超时（60s）
- Parquet 写入 `data/` 目录

### 验收标准

- [ ] `python -m pytest tests/test_data_pipeline.py -v` — 3/3 绿
- [ ] `python -c "from src.data_pipeline import fetch_etf_daily; df=fetch_etf_daily('510300','2024-01-01','2024-01-31'); print(df.shape)"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 1"。
> 顾问审核通过并 commit 后，更新本文 Step 2。
> 禁止跳过步骤，禁止一次完成多步。
