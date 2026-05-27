# 顾问审查建议

> 顾问写入。读完 outcome.md + git diff 后填写。**本文件是给人看的决策材料**，不直接放行。

## 审查结论

**建议：放行**

## 分析

### 逻辑正确性

决策链 7 步编排完整且优先级正确：

1. close 提取 → 2. 趋势强度过滤（ts>0 → active）→ 3. 目标波动率缩放（等权 → EWMA cov → scaling_factor）→ 4. 截面动量排名（offense 候选 → top K）→ 5. 相关性熔断（股债相关性 → triggered）→ 6. 回撤止损（current dd → level+multiplier）→ 7. execution 汇总。

关键优先级（line 91-96）：
- 熔断触发 → `final_multiplier=0, funds_to_repo=True`（覆盖一切）
- 否则 → `min(scaling_factor, position_multiplier)`（取保守值）

正确。

### 边界处理

- active 为空 → sf=1.0, 空权重，不崩溃。
- 无 offense 候选 → 空 rankings/weights，不崩溃。
- 缺股票篮子或国债 → 熔断默认不触发，不崩溃。
- 参数全部可配，`{**DEFAULT_PARAMS, **(params or {})}` 合并模式安全。

### 副作用评估

- 新建文件，零修改现有模块。
- 纯编排，不实现算法。调用链清晰可追溯。
- 测试覆盖 4 条集成路径（全绿/趋势过滤/熔断覆盖/止损覆盖），与单元测试互补无重叠。

### 安全合规

- 未触碰 protected-files.json。
- 无硬编码凭证。
- 默认参数与方向性讨论一致。

## 驳回理由（如驳回）

（无）

## 下一步

放行 → commit Step 7 → 更新 direction.md 写入 Step 8（组合管理器）。

---

> 人做最终决策。人批准后创建 `.claude/.gate/audit_ok_<file>` 标记。
