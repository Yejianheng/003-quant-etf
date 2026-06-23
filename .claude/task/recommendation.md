# 顾问审查建议 — 数据源加固

> 审查时间：2026-06-23 | 对应 outcome: 数据源加固

## 审查结论

**有条件放行。** 核心实现正确，有两项待修复和一个历史问题需要知晓。

## 通过项

| 检查项 | 状态 |
|--------|:--:|
| 腾讯财经 `fetch_etf_daily_tx` | ✅ |
| `amount→volume ×100` 转换 | ✅ 腾讯返回手，×100=股 |
| 拆分/除权检测 | ✅ 复用 fetch_etf_daily 逻辑 |
| 数据源优先级 腾讯>东财>新浪 | ✅ |
| 新鲜度门禁 nav_chart | ✅ RuntimeError + 品种名 |
| 新鲜度门禁 check_position | ✅ sys.exit(1) + stderr |
| 请求间隔 3s 兜底 | ✅ |
| 新测试 13 全绿 | ✅ |

## 待修复（阻塞放行）

### 1. 修改记录缺失

`src/data_pipeline.py` 文件头缺少 `[2026-06-23]` 修改记录。同样 `scripts/update_data.py`、`scripts/nav_chart.py`、`scripts/check_position.py` 需补充。

> 规范依据：`.claude/rules/2-coding-style.md` — 每次修改必须在文件最前方添加 `// [YYYY-MM-DD] 操作类型：简述`

### 2. 全量测试未跑（test_slippage.py 已有错误）

当前 `test_slippage.py` 因 `REPO_ANNUAL_RATE` 导入失败导致全量测试中断。这是一个已有问题，但执行窗口应排除该文件后跑全量测试确认零回归。

```bash
python -m pytest tests/ --ignore=tests/test_slippage.py -q
```

## 发现：历史成交量数据存在单位不一致

交叉验证发现 `159915.parquet` 在 6-16（10.9M）和 6-17（1.09B）之间存在 ~100× 跳变，与腾讯 ×100 无关（这些日期未被本次更新触及）。说明历史数据中部分日期成交量以「手」存储、部分以「股」存储。

| 日期 | volume 值 | 疑似单位 |
|------|-----------|:--:|
| 6-16 | 10,921,490 | 手 |
| 6-17 | 1,093,704,000 | 股 |
| ... | ... | ... |

**影响范围**：成交量仅用于 `nav_chart.py` 的换手率/滑点估算（`_compute_turnover_stats`），不影响策略信号（趋势强度、波动率缩放、相关性熔断、回撤止损均只用 OHLC）。图表换手率统计可能有偏差，但净值曲线正确。

**建议**：另开一个 issue 做历史数据单位归一化（`scripts/` 下加一个修复脚本），不在本次改动范围内。

## 动作清单

- [ ] 补充所有修改文件的 `[2026-06-23]` 修改记录
- [ ] 排除 test_slippage.py 跑全量测试，确认零回归
- [ ] 完成后更新 outcome.md
