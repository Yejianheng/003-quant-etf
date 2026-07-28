# 执行指令

> 2026-07-28 | 提交当前工作区变更 + 验证三源交叉验证

## 步骤 0 — 提交当前变更

工作区包含 v214 三源交叉验证的全部实现（data_pipeline 拆源 + update_data 重写 + nav_chart/check_position 适配 + infrastructure.md 更新 + parquet 数据刷新）。

```bash
git add src/data_pipeline.py scripts/update_data.py scripts/nav_chart.py scripts/check_position.py .claude/rules/5-infrastructure.md .claude/task/direction.md .claude/task/recommendation.md data/159915.parquet data/510300.parquet data/511010.parquet data/513100.parquet data/518880.parquet data/position_state.json

git commit -m "v214-20260728: 数据核验改为三源交叉验证，取代人工Web核验"
```

## 步骤 1 — 验证

```bash
python scripts/update_data.py
```

预期：5 只 ETF 三源一致 → 自动入库，不触发 Web 核验。

若通过 → 写 outcome.md，提示顾问审查。

## 约束

- 不改策略计算逻辑
- 不改 parquet 数据格式
