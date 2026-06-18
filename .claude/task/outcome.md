# 执行结果

> 执行时间：2026-06-18 | 方向来源：.claude/task/direction.md

## 任务：股债相关性经济驱动力分解

### 步骤 1：拉取宏观数据 ✅

- `data/macro_indicators.parquet` 已生成（10994 行 × 5 列，覆盖 1990-2026）
- 数据源：`ak.bond_zh_us_rate()`（日频国债）+ `ak.macro_china_cpi_monthly()`（月频CPI→日频填充）
- 列：yield_10y, yield_2y, yield_spread, cpi_yoy, us_cn_spread

### 步骤 2：对齐 smoothed_corr ✅

- smoothed_corr: 3064 天 → 对齐后 2747 个共同交易日
- 特征相关性：CN 10Y 与 US-CN Spread -0.736（最高相关对）

### 步骤 3：OLS 回归 + 分阶段 ✅

**全期回归**（2747 样本）：

| 因子 | beta | SE | t | p | sig |
|------|------|------|------|------|------|
| const | -0.6379 | 0.0226 | -28.18 | <0.001 | *** |
| CN 10Y | +0.1962 | 0.0071 | +27.51 | <0.001 | *** |
| 10Y-2Y Spread | -0.1431 | 0.0159 | -8.99 | <0.001 | *** |
| CPI YoY | -0.0143 | 0.0064 | -2.22 | 0.027 | * |
| US-CN Spread | +0.0192 | 0.0032 | +6.08 | <0.001 | *** |

**R² = 0.319, adj R² = 0.318**

**因子贡献排序**：CN 10Y (0.1244) > 10Y-2Y Spread (0.0276) > US-CN Spread (0.0275) > CPI YoY (0.0068)

CN 10Y 贡献是第二名的 4.5 倍，是唯一有实际影响力的变量。

**CB 触发期 vs 非触发期**：
- CN 10Y: 3.48 vs 2.92（+0.56pp, p<0.001）
- US-CN Spread: -1.07 vs -0.27（-0.80pp, p<0.001）
- 10Y-2Y Spread: 0.43 vs 0.46（-0.03pp, p<0.001）
- CPI YoY: 无显著差异（p=0.57）

**2022 年专项**：CB 触发 49.6%（全期 28.4%），但所有因子 z-score < 0.5σ。US-CN Spread 从全期 -0.49 翻转为 +0.20（美债急升），是最异常信号。

### 步骤 4：system_audit.md §6.8 已写入 ✅

包含：全期回归表、因子贡献排序、分年汇总表、CB对比表、2022专项、对熔断机制的5点启示。

### 验收核对

- [x] `data/macro_indicators.parquet` 已生成
- [x] 回归因子系数表 + R²
- [x] 分年因子均值表（重点 2022）
- [x] `attribution/system_audit.md` §6.8 已写入
- [x] 新测试 6/6 绿灯（`tests/test_macro_corr_decomposition.py`）
- [x] 未改生产代码，全量测试零回归（预存失败 6 个确认无关）

### 核心结论

1. **R² = 0.32** — 宏观能解释 32%，68% 来自微观结构
2. **CN 10Y 是唯一主导变量** — 贡献是第二名 4.5 倍
3. **CPI 几乎无用** — 统计显著但经济意义可忽略
4. **2022 年宏观不极端** — 所有因子 < 0.5σ，熔断捕获的是相关性临界行为
5. **建议保留熔断，宏观不进决策链** — 32% 不够做确定性预警

### 新增/修改文件

| 文件 | 操作 | 备注 |
|------|------|------|
| `scripts/macro_corr_decomposition.py` | 新增 | 分析脚本，不改生产代码 |
| `tests/test_macro_corr_decomposition.py` | 新增 | 6 测试全绿 |
| `data/macro_indicators.parquet` | 新增 | 宏观数据缓存 |
| `attribution/system_audit.md` | 修改 | 新增 §6.8 |

---

请顾问窗口审查。
