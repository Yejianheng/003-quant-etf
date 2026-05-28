# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：角色门禁增加 .claude/task/ 目录豁免

### 背景

上一轮回退了 `isRoleFileTarget`（role.json 自身豁免），但角色门禁变为无差别拦截。advisor 无法写 recommendation.md / direction.md——这是 CLAUDE.md 明确要求顾问履行的职责。

**正确方案**：角色门禁豁免 `.claude/task/` 目录。该目录只含协议文件（direction / outcome / recommendation），豁免它不会瓦解三权分立：
- advisor 仍无法写业务代码
- advisor 仍无法写 role.json（不在 task 目录）
- 单向锁完整：executor → advisor 成功，advisor → executor 被拦截

### 步骤

#### 步骤 0：确认当前状态

读取两个 Hook 文件，确认角色门禁位置：
- `pre_edit_file.js`：L21-37 角色门禁
- `pre_bash.js`：L100-116 角色门禁

#### 步骤 1：修改 pre_edit_file.js（保护区文件，需 audit）

在角色门禁判断中增加 task 目录豁免。在 L27 的 `if` 条件之前，增加判断：

```js
// 豁免：advisor 可写 .claude/task/ 目录（协议文件：direction/outcome/recommendation）
const isTaskFile = filePath.includes(".claude/task/");
if (!isTaskFile) {
```

并在 L35 的 `}` 之后增加闭合 `}`，使角色门禁不对 task 文件生效。

修改后的角色门禁结构：
```
if (role is advisor/consultant) {
  if (file is NOT in .claude/task/) {   ← 新增豁免判断
    block
  }
}
```

#### 步骤 2：修改 pre_bash.js（保护区文件，需 audit）

同上逻辑，在 pre_bash.js 的角色门禁中增加 task 目录豁免。

从 command 中提取文件路径来判断是否涉及 task 目录（Bash 没有 file_path 字段，需要解析命令）。如果命令涉及的文件路径全部在 `.claude/task/` 下，豁免角色门禁。

#### 步骤 3：验证

- advisor 角色 → 写 recommendation.md → 成功
- advisor 角色 → 写 direction.md → 成功
- advisor 角色 → 写业务代码 → 拦截
- advisor 角色 → 写 role.json → 拦截（单向锁保持）

### 约束

- 只豁免 `.claude/task/` 目录，不扩及其他路径
- 不修改 role.json 路径
- 单向锁机制不得退化

### 验收标准

- [ ] advisor 可写 `.claude/task/recommendation.md`
- [ ] advisor 可写 `.claude/task/direction.md`
- [ ] advisor 写 `src/` 下任意文件仍被拦截
- [ ] advisor 写 `.claude/role.json` 仍被拦截
- [ ] executor 写所有文件不受影响

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
