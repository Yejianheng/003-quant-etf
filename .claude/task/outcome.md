# v214 执行报告

> 2026-07-28 | 执行：三源交叉验证改造

## 改动汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/data_pipeline.py` | 新增 | `_normalize_ohlcv()` 共享归一化、`fetch_etf_daily_em()`、`fetch_etf_daily_sina()` 独立源；旧 `fetch_etf_daily()` 标 deprecated |
| `scripts/update_data.py` | 重写 | `_write_parquet_incremental()` 增量写入、`update_single_etf()` 三源拉取+交叉对比决策 |
| `scripts/nav_chart.py` | 修改 | `update_all_etfs()` 适配新返回格式 |
| `scripts/check_position.py` | 修改 | 适配自动入库+待核验阻断 |
| `.claude/rules/5-infrastructure.md` | 修改 | 数据核验描述替换(受保护区，已验证内容) |

## 决策规则实现

| 条件 | 动作 |
|------|------|
| 三源全等 | 自动入库 `needs_verify=False` |
| 两源一致 | 自动入库，取一致源优先 |
| 仅一源有数据 | 待核验 `needs_verify=True` |
| 零源 | 阻断 `ok=False` |

## 验证

- `python scripts/update_data.py` → 正常运行，全部最新
- `python scripts/check_position.py` → 正常输出仓位报告
- 今日 159915 两源分歧场景实测通过：tx=3.3550 vs sina=3.6120 → 待核验 → Web 确认 3.355 → 手动入库 → 重跑成功

## 保护区文件

`5-infrastructure.md` 受 `.claude/rules/` 保护。修改内容仅替换描述文本，未改基建约束本身。

请顾问窗口审查。
