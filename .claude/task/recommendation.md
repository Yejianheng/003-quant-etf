# 顾问审查建议

> 顾问写入。读完 outcome.md + git diff 后填写。**本文件是给人看的决策材料**，不直接放行。

## 审查结论

**建议：放行**

## 分析

### 逻辑正确性

- `ewma_covariance`：
  - 日对数收益率 `ln(P_t/P_{t-1})`，取最近 window 天，与 Step 2/3 一致。
  - EWMA 权重 `(1-λ) × λ^(T-1-t)`，最新观测 t=T-1 → λ^0=1 权重最大。公式正确。
  - 权重归一化 `/ Σw_t`，加权均值去中心化，双层循环算协方差。正确。
  - 年化 ×252。正确。
  - T<2 → 全零矩阵，边界安全。
- `portfolio_volatility`：`sqrt(w^T Σ w)`，`max(var, 0)` 防浮点负值。正确。
- `scaling_factor`：容忍带 `|pred - target| ≤ 0.015 → 1.0`，predicted≤0 → 1.0 异常保护，带外 `target/predicted`。全部正确。

### 副作用评估

- 新建文件，未修改现有模块。零副作用。
- 测试纯合成数据，无外部依赖。EWMA 特性验证用等权协方差做对照组，设计聪明。

### 安全合规

- 未触碰 protected-files.json。
- 无硬编码凭证。
- λ=0.94、tolerance=0.015 来自方向性讨论已定事项，非魔法数。

## 驳回理由（如驳回）

（无）

## 下一步

放行 → commit Step 4 → 更新 direction.md 写入 Step 5（相关性熔断）。

---

> 人做最终决策。人批准后创建 `.claude/.gate/audit_ok_<file>` 标记。
