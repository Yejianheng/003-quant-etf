# v214 执行报告

> 2026-07-28 | 执行：三源交叉验证改造
> 2026-07-28 | 提交：`c531189` v214-20260728，14 files changed，工作区干净

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

---

## 全面核查（2026-07-28）

执行 4 步核查后的结果：

| 步骤 | 结果 |
|------|------|
| 1 — 数据管线 | ✅ 5 只 ETF 全部最新(7/28)，无待核验/阻断 |
| 2 — 仓位报告 | ✅ 权重 0.0 + 现金 1.0 = 1.0，无负数 |
| 3 — 图表 | ⚠️ 见下方 bug |
| 4 — 信号回测 | ✅ 格式完整，final_mult=1.0 在 [0,1] |

### 发现 1 处显示层 bug

**位置**：`scripts/nav_chart.py:364-365`

**现象**：7/20~7/28 全现金期间，图表 `cash` / `repo_amount` 列显示 **0%**（应为 **100%**），repo 列渲染为 `—`

**根因**：`cash = round(1.0 - prev_final_mult, 4)`，全现金时 `final_multiplier=1.0`（因 defense_active=[] 时的默认值），导致 `1.0 - 1.0 = 0.0`。应判断 `is_all_cash` 条件，True 时直接设 1.0。

**影响**：仅影响全空仓时段的显示，策略计算和持仓权重列均正常（7/20 后各权重正确显示 `—`）。

**不修复**（按约束只读检查）。

---

## 修复：图表全现金时段 cash/repo 列显示（2026-07-28）

**修改**：`scripts/nav_chart.py:364-365`
- `cash` / `repo_amount`：`prev_final_mult` → `sum(weights.values())`
- 全现金时 weights 和为 0 → `1.0 - 0 = 1.0` ✅

**验证**：

| 日期 | cash(改前) | cash(改后) |
|------|-----------|-----------|
| 7/17 | 14% | 14% (不变) |
| 7/20~7/28 | 0% | **100%** |

**图表生成**：`nav_2026.html` 已更新。

---

## 保护区：3-core-mechanism.md 追加语义陷阱文档（2026-07-28）

**Audit 结果**：✅ Qwen3-Max 盲审通过，无安全/架构违规

**修改预览**：末尾追加「常见陷阱：final_multiplier 在全空仓时的语义」章节，纯文档补充，不改业务逻辑。

**写入令牌就绪**，等待批准。

请顾问窗口审查。
