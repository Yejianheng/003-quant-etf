# 执行指令

> 2026-06-23 | 数据源加固 — 腾讯财经入主源 + 图表新鲜度门禁

## 背景

东方财富 WAF 不稳定，新浪数据延迟半天，今日创业板 (159915) 两个源都拿不到 6-23 数据。经顾问验证，腾讯财经 (`ak.stock_zh_a_hist_tx`) 对 5 只防御 ETF 全部覆盖到 2013 年、今日数据齐全。决定引入腾讯财经并提升为主数据源。

## 操作

分三步，逐步执行，每步完成后汇报。

### 步骤 1 — 数据管线：腾讯财经入主源

**修改文件**：`src/data_pipeline.py`

新增函数 `fetch_etf_daily_tx(code, start_date, end_date)`：
```
// [2026-06-23] 新增：腾讯财经数据源（主源），ak.stock_zh_a_hist_tx
// 列映射：date/open/high/low/close → 与 em/sina 统一，amount → volume（腾讯 amount 含义是成交量/手，需 ×100 转换为股）
// 限流：每只 ETF 请求间隔 ≥ 3 秒（pre_bash hook 已有 _tx 3s 间隔，此处加 time.sleep 兜底）
// 返回结构与 fetch_etf_daily 一致的 DataFrame（cols: date/open/high/low/close/volume，date 为 index）
```

调整数据源优先级 — **腾讯 > 东方财富 > 新浪**：
- `fetch_etf_daily` 内部改为：先调腾讯 → 失败/空则东方财富 → 失败/空则新浪
- 或者保持原有函数签名不变，在 `update_single_etf` 中依次尝试三个源

**修改文件**：`scripts/update_data.py`

- `update_single_etf` 中调用顺序改为：腾讯 → 东方财富 → 新浪
- 每个源失败后打印明确日志（如 `[159915] 腾讯财经无新数据，尝试东方财富...`）

### 步骤 2 — 新鲜度门禁：数据不齐禁止生成图表

**修改文件**：`scripts/nav_chart.py`

在 `update_all_etfs` 之后、`load_prices` 之后，增加新鲜度校验：

```
// [2026-06-23] 新增：新鲜度门禁 — 任一 ETF 最新日期 ≠ 今天 → 中止图表生成并报告
// 校验逻辑：遍历 5 只 ETF parquet，取 index.max().date()，与 date.today() 比较
// 不一致的 ETF 收集到列表，全部通过才继续，否则 raise RuntimeError 列出未更新品种
```

**修改文件**：`scripts/check_position.py`

同样在更新数据后加新鲜度门禁（复用 nav_chart 的校验逻辑，或提取为共享函数）。

### 步骤 3 — 更新图表并验证

```bash
python scripts/nav_chart.py
```

确认：5 只 ETF 全部最新 → 图表生成成功 → 打开 `nav_2026.html` 抽查最后一行日期和净值。

## 约束

- **抓取频率**：腾讯财经 `stock_zh_a_hist_tx` 每只 ETF 之间 `time.sleep(3)`，不并行请求。pre_bash.js 已有 `_tx` 3s 间隔 Hook，但仍需代码层兜底。
- **新鲜度门禁**：全部数据源尝试完毕后任一 ETF 未更新到今日 → **禁止生成图表**，打印 `[门禁] 以下 ETF 未更新到今日：159915（最新 2026-06-22），图表生成已中止。请稍后重试。`
- **保护区**：`src/data_pipeline.py` 在保护区清单中。修改前必须先跑 `validate` → `audit` 流程。
- **测试先行**：每个步骤遵守红灯检验（先写测试 → 红灯 → 写代码 → 绿灯 → 提交）。

---

## 步骤 4 — 补充修改记录（顾问审查要求）

以下 4 个文件缺少 `[2026-06-23]` 修改记录，需在文件头补充：

| 文件 | 记录内容 |
|------|---------|
| `src/data_pipeline.py` | `# [2026-06-23] 新增：fetch_etf_daily_tx 腾讯财经主源 + check_freshness 新鲜度门禁` |
| `scripts/update_data.py` | `# [2026-06-23] 修改：数据源优先级调整为腾讯 > 东方财富 > 新浪` |
| `scripts/nav_chart.py` | `# [2026-06-23] 新增：新鲜度门禁 — 数据不齐禁止生成图表` |
| `scripts/check_position.py` | `# [2026-06-23] 新增：新鲜度门禁 — 数据不齐禁止输出仓位` |

> `src/data_pipeline.py` 在保护区，修改记录属于注释追加不改变逻辑，走快速 validate→audit。

## 步骤 5 — 全量回归测试

```bash
python -m pytest tests/ --ignore=tests/test_slippage.py -q
```

> test_slippage.py 有已有 REPO_ANNUAL_RATE 导入错误，与本改动无关，排除后跑。

确认：全部通过，零回归。

## 步骤 6 — 更新 outcome.md

在现有 outcome.md 末尾追加步骤 4-5 的执行结果。

## 约束

- **抓取频率**：腾讯财经 `stock_zh_a_hist_tx` 每只 ETF 之间 `time.sleep(3)`，不并行请求。pre_bash.js 已有 `_tx` 3s 间隔 Hook，但仍需代码层兜底。
- **新鲜度门禁**：全部数据源尝试完毕后任一 ETF 未更新到今日 → **禁止生成图表**，打印 `[门禁] 以下 ETF 未更新到今日：159915（最新 2026-06-22），图表生成已中止。请稍后重试。`
- **保护区**：`src/data_pipeline.py` 在保护区清单中。步骤 4 修改注释也需走 validate → audit 流程。
- **测试先行**：每个步骤遵守红灯检验（先写测试 → 红灯 → 写代码 → 绿灯 → 提交）。

## 输出要求

每步完成后汇报，全部完成后更新 outcome.md。
