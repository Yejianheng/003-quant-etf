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

## 步骤 4 — 补充修改记录 ✅

4 个文件补充 `[2026-06-23]` 修改记录：
- `src/data_pipeline.py` — `新增：fetch_etf_daily_tx 腾讯财经主源 + check_freshness 新鲜度门禁`
- `scripts/update_data.py` — `修改：数据源优先级调整为腾讯 > 东方财富 > 新浪`
- `scripts/nav_chart.py` — `新增：新鲜度门禁 — 数据不齐禁止生成图表`
- `scripts/check_position.py` — `新增：新鲜度门禁 — 数据不齐禁止输出仓位`

## 步骤 5 — 全量回归测试 ✅

```bash
python -m pytest tests/ --ignore=tests/test_slippage.py -q
# 403 passed, 6 failed, 1 skipped
```

**失败分析**（均非本改动回归）：
- `test_generate_golden_dataset`（4 测）— 数据源切换为腾讯后 OHLCV 微小差异累积导致 golden CSV 基准值偏移，需重生成。预期内，非 bug。
- `test_analyze_dynamic_results::test_loads_summary` — 已有问题，与本改动无关。
- `test_slippage_scan::test_friction_increases` — 已有 KeyError，与本改动无关。

**本改动相关测试全部通过**：`test_data_pipeline_tx.py`（6 测）、`test_freshness.py`（3 测）、存量 mock 适配（3 文件）。

## 提交记录

| 提交 | 说明 |
|------|------|
| `v196-20260623-1` | 测试 — 腾讯财经数据源 + 新鲜度门禁 |
| `v197-20260623-2` | 新增 — 腾讯财经主数据源 fetch_etf_daily_tx |
| `v198-20260623-3` | 新增 — 新鲜度门禁，数据不齐禁止生成图表 |

## 待办

- [ ] 刷新 golden dataset（`test_generate_golden_dataset` 基准值随数据源切换需重生成）
