# 顾问审查建议

> 顾问写入。读完 outcome.md + git diff 后填写。**本文件是给人看的决策材料**，不直接放行。

## 审查结论

**建议：放行**

## 分析

### 逻辑正确性

- `compute_drawdown`：`expanding().max()` 跑滚动峰值 → `(value - peak) / peak`。一行核心逻辑，正确。
- `drawdown_stop`：`abs(drawdown)` 四级 if-else，阈值 0.08/0.12/0.18，multiplier 1.0/1.0/0.5/0.0。与方向性讨论完全一致。
- 场景 3（先新高后回撤）验证了 running_max 跟随新高的关键行为——回撤基于 150 而非 100。
- 场景 4（回撤恢复）验证了反弹不降 running_max——不因价格回升而错误"复仓"。

### 副作用评估

- 新建文件，未修改现有模块。零副作用。
- 全模块 35 行，无依赖（仅 pandas），零冗余。

### 安全合规

- 未触碰 protected-files.json。
- 无硬编码凭证。

## 驳回理由（如驳回）

（无）

## 下一步

放行 → commit Step 6 → 更新 direction.md 写入 Step 7（信号生成器）。

---

> 人做最终决策。人批准后创建 `.claude/.gate/audit_ok_<file>` 标记。
