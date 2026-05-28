# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：回退 Hook 中 role.json 豁免逻辑

### 背景

上一轮执行实现了已驳回的豁免方案——pre_edit_file.js 和 pre_bash.js 中增加了 role.json 写入豁免。审计模型判定此举瓦解三权分立。

正确方案为**单向锁**：不加豁免，AI 能从 executor 锁成 advisor（写入时角色尚为 executor，放行），但无法反向解锁（已是 advisor，角色门禁拦截一切写入）。

### 步骤

#### 步骤 0：确认当前状态

读取两个 Hook 文件，确认豁免代码存在：
- `pre_edit_file.js` 第 23-25 行：`isRoleFileTarget` 判断 + 豁免注释
- `pre_bash.js` 第 102-104 行：同上

#### 步骤 1：回退 pre_edit_file.js（保护区文件，需 audit）

删除豁免逻辑三行：

```
// 删除:
// 豁免：写入 role.json 自身不受角色门禁限制（允许角色切换）
const isRoleFileTarget = filePath.endsWith("/.claude/role.json");
if (!isRoleFileTarget) {

// 同时删除对应的闭合 }
```

回退后角色门禁对**所有文件**一视同仁。

#### 步骤 2：回退 pre_bash.js（保护区文件，需 audit）

同上：删除 `isRoleFileTarget` 三行 + 闭合 `}`。

#### 步骤 3：验证

- executor 角色 → 写 role.json `{"role":"advisor"}` → 成功（此刻仍是 executor）
- 写入后 → 写任意其他文件 → Hook 拦截（单向锁生效）
- 写入后 → 再写 role.json `{"role":"executor"}` → Hook 拦截（无法解锁）
- 人手动改 role.json 为 executor → 恢复

### 约束

- 不碰路径（`.claude/role.json` 保留）
- 不碰 CLAUDE.md（步骤 0 指令保留）
- 仅删除豁免，不增不减其他逻辑

### 验收标准

- [ ] `pre_edit_file.js` 不含 `isRoleFileTarget`
- [ ] `pre_bash.js` 不含 `isRoleFileTarget`
- [ ] 单向锁生效：executor → advisor 成功，advisor → executor 被拦截

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
