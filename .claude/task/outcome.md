# 执行结果

> 2026-06-23 | 数据源加固 — 腾讯财经入主源 + 图表新鲜度门禁

## 步骤 1 — 数据管线：腾讯财经入主源 ✅

**修改文件**：
- `src/data_pipeline.py` — 新增 `fetch_etf_daily_tx` 函数，使用 `ak.stock_zh_a_hist_tx`。列映射 `amount→volume（×100）`，含拆分检测。
- `scripts/update_data.py` — 导入 `fetch_etf_daily_tx`，修改 `update_single_etf` 先调腾讯（3s 限流），失败则回退 `fetch_etf_daily`（东方财富 → 新浪），每步打印明确日志。

**测试**：新增 `tests/test_data_pipeline_tx.py`（6 测）+ 更新 `tests/test_update_data.py`（3 测 mock）

## 步骤 2 — 新鲜度门禁 ✅

**修改文件**：
- `src/data_pipeline.py` — 新增 `check_freshness` 函数
- `scripts/nav_chart.py` — update 后插入门禁，未通过 raise RuntimeError
- `scripts/check_position.py` — 数据更新后插入门禁，未通过 sys.exit(1)

**测试**：新增 `tests/test_freshness.py`（3 测）+ 更新存量测试 mock

## 步骤 3 — 更新图表并验证 ✅

```bash
python scripts/nav_chart.py
# 5 ETF 全部更新到今日 → nav_2026.html 生成成功
```

159915 最新日期验证：2026-06-23（通过腾讯源获取）

## 数据源优先级

```
腾讯财经 (ak.stock_zh_a_hist_tx, qfq) → 东方财富 (ak.fund_etf_hist_em, qfq, 3次重试+退避) → 新浪 (ak.fund_etf_hist_sina, qfq)
```

## 测试总览

**29 测全绿**（13 新增 + 16 存量适配零回归）
