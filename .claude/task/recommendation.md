# 顾问审查建议

> 顾问写入。读完 outcome.md + git diff 后填写。**本文件是给人看的决策材料**，不直接放行。

## 审查结论

**建议：放行（附条件）**

## 分析

### 逻辑正确性

- `fetch_etf_daily`：AKShare → 中文列名映射为英文 → 日期设为 DatetimeIndex → 排序。逻辑正确。
- `save_to_parquet` / `load_from_parquet`：标准 pyarrow 读写，index 保留，往返测试 `assert_frame_equal` 通过。
- `etf_universe.py`：5 个防御层标的映射准确（510300/159915/513100/518880/511010）。

### 副作用评估

- 新建文件，未修改现有模块，零副作用。
- `data_pipeline.py` 未 import `ETF_UNIVERSE`，这是正确的——标的映射是上层（信号生成器）的职责，管线只负责拉取指定代码。

### 安全合规

- 未触碰 protected-files.json。
- 无硬编码凭证。
- 列名映射硬编码在 `data_pipeline.py` 中是合理的——这是 AKShare API 的响应格式，属于 API 适配层，不是配置项。

## 隐患

详见 `issues.md`，共 3 条：

| # | 隐患 | 重要性 | 计划 |
|---|------|--------|------|
| 1 | `except Exception` 太宽，静默吞所有异常 | 高 | Step 2 前统一规范 |
| 2 | 无日志机制 | 中 | Step 2 建最小 logging_config |
| 3 | `save_to_parquet` 不创建目录 | 低 | Step 7 加 `makedirs` |

## 驳回理由（如驳回）

（无。3 条隐患不影响 Step 1 合入，均计划在后续步骤解决。）

## 下一步

放行 → commit Step 1 → 顾问更新 direction.md 写入 Step 2。

---

> 人做最终决策。人批准后创建 `.claude/.gate/audit_ok_<file>` 标记。
