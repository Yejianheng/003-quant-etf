# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 背景

顾问窗口通过 `python scripts/daily_signal.py` 绕过 Bash 门禁——命令无文件路径，`extractPaths` 返回空数组，`taskPaths.length === 0` 直接放行。审计 2 次驳回（第 1 次正则安全风险、第 2 次角色误判）。放弃正则方案，用模板已验证的数组方案。

## 任务

### 步骤 1：用模板覆盖 pre_bash.js

```bash
cp "d:/AI项目/000-guard-mcp/项目开始规范/001-新项目模板/.claude/hooks/pre_bash.js" "d:/AI项目/003-quant-etf/.claude/hooks/pre_bash.js"
```

模板使用 `ADVISOR_READONLY_CMDS` 数组 + `startsWith` 前缀匹配。无正则，无注入面。

### 步骤 2：validate

```bash
node d:/AI项目/000-guard-mcp/build/cli.js validate "模板 ADVISOR_READONLY_CMDS 数组方案覆盖，封堵顾问 Bash 绕过" --files .claude/hooks/pre_bash.js
```

### 步骤 3：audit

```bash
node d:/AI项目/000-guard-mcp/build/cli.js audit ".claude/hooks/pre_bash.js" "d:/AI项目/003-quant-etf/.claude/hooks/pre_bash.js"
```

### 步骤 4：提交

```bash
git log --oneline -1  # 取最新序号，<序号> = 最新序号 + 1
git add .claude/hooks/pre_bash.js .claude/task/direction.md
git commit -m "v<序号>-20260611: 模板 pre_bash.js 覆盖，ADVISOR_READONLY_CMDS 数组封堵顾问 Bash 绕过"
```

### 步骤 5：清理

direction.md 恢复模板（`[待填写]`）。

---

## 验证

- 顾问角色 `git status` 放行
- 顾问角色 `python scripts/daily_signal.py` 被拦截
- 执行者角色不受影响
- 全量测试零回归

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
