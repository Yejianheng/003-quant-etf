# 顾问审查建议

> 顾问写入。读完 outcome.md + git diff 后填写。**本文件是给人看的决策材料**，不直接放行。

## 审查结论

**建议：放行**

## 分析

### 逻辑正确性

- `stock_basket_returns`：逐 ETF 算对数收益率 → DataFrame → `mean(axis=1, skipna=True)`。某 ETF 缺数据用其余均值，正确。
- `rolling_correlation`：pandas `.rolling(window).corr()` 一行，干净。
- `correlation_circuit_breaker`：
  - 日期对齐 `intersection`：主动处理中美交易日不同（沪深300/纳指日历交叉），设计细心。
  - 数据不足 `< corr_window + sma_window` → 返回默认值，正确。
  - `smoothed_corr > threshold`（默认 0.0），与方向性讨论一致。
  - 额外返回 `raw_corr` 用于调试，不违反 spec。

### 副作用评估

- 新建文件，未修改现有模块。零副作用。
- 测试全合成数据，无外部依赖。正/负相关场景通过共享/反向噪声构造，设计聪明。

### 安全合规

- 未触碰 protected-files.json。
- 无硬编码凭证。

## 驳回理由（如驳回）

（无）

## 下一步

放行 → commit Step 5 → 更新 direction.md 写入 Step 6（回撤硬止损）。

---

> 人做最终决策。人批准后创建 `.claude/.gate/audit_ok_<file>` 标记。
