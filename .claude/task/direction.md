# 执行指令

> 2026-11-13 | v234：提交 11-12 数据 + 仓位状态，清理工作区，推送

## 步骤 1 — 忽略角色标记文件

在 `.gitignore` 末尾追加一行：

```
.claude/role.json
```

理由：`role.json` 是会话瞬态文件（顾问/执行 Step 0 写入，Stop hook `clear_role.sh`
清除），不应进入版本库。当前工作区 `?? .claude/role.json` 即此文件。

## 步骤 2 — 提交

```bash
git add .gitignore data/159915.parquet data/510300.parquet data/511010.parquet data/513100.parquet data/518880.parquet data/raw/159915.parquet data/raw/510300.parquet data/raw/511010.parquet data/raw/513100.parquet data/raw/518880.parquet data/position_state.json .claude/next-session.md .claude/task/direction.md .claude/task/outcome.md .claude/task/recommendation.md
git commit -m "v234-20261113: 提交 2026-11-12 数据更新 + 仓位状态（熔断解除→100% 国债ETF），清理 v214 遗留任务文件"
```

## 步骤 3 — 推送

```bash
git push
```

用户已明确授权推送。

## 步骤 4 — 验证

`git status --porcelain` 必须无输出。

## 约束

- 本次无源码改动，不涉及任何保护区文件，无需 validate→audit。
- 数据文件为 2026-11-12 夜间三源核验产物，禁止手工改写任何数值。
- 提交前确认 `git status` 中不出现 `.py` 文件的修改；若出现，停止并报告。
