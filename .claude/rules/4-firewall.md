# 架构防火墙

以下文件是项目的"骨架"，误改会导致系统瘫痪。修改前必须执行完整审核协议。

保护区清单见项目根 `protected-files.json`（**唯一事实源**）。Hook 从该文件读取，人只需维护这一处。

> 新增保护区文件：只改 `protected-files.json`。Hook 和本文自动同步。禁止在 Hook 脚本或本文中重复硬编码文件名。

## 三层拦截

| 层 | 配置/代码 | Hook | 拦截什么 |
|------|---------|------|------|
| Bash 文件保护 | `pre_bash.js` 硬编码 + `protected-files.json` 动态合并 | PreToolUse (`pre_bash.js`) | Bash 写/删保护区文件，关闭 Bash 绕过路径 |
| 文件级 | `protected-files.json` | PreToolUse (`pre_edit_file.js`) | Edit/Write 是否触碰保护区文件 |
| 内容级 | `protected-contracts.json` | PostToolUse (`post-edit-audit.sh`) + `check_values.py` | 改了已确认的常量值 / 写了禁止模式 |

### Bash 文件保护（第一道防线）

- 拦截对保护区文件的写/删操作：`>`、`>>`、`rm`、`tee`、`dd of=`、`truncate`、`cp`、`mv`
- 硬编码保护 `protected-files.json`、`protected-contracts.json`、`check_values.py`、`.claude/hooks/`、`.claude/.gate/`
- 保护区清单从 `protected-files.json` 动态合并（硬编码 + JSON 只增不减）
- Bash 写保护区文件 → 无条件拦截（exit 2），强制走 Edit/Write + audit 流程

### 文件级（protected-files.json）

- `protected_files`：准确文件名匹配
- `protected_dirs`：目录前缀匹配
- `protected-files.json`、`protected-contracts.json`、`check_values.py` 自保护
- 条目**只增不减**

### 内容级（protected-contracts.json）

- **values**：已验证的常量，修改即拦截
- **patterns**：禁止出现的危险模式
- 配合 `check_values.py` AST 值级校验（Python 零依赖）
- 两层任意一层触发 → 走审核协议

## 审核协议

修改保护区文件的完整流程：

```
执行者要改保护区文件
      │
      ▼
调 CLI validate ── 规则合规 + 测试门禁
      │
      ▼
调 CLI audit ── 提交修改意图 + 拟写代码给异构审计模型
      │
      ▼
审计模型输出报告
      │
      ├── PASS → 结果写入 outcome.md
      │
      ├── 驳回（第 1-2 次）→ 按审计意见修，重走 audit
      │
      └── 驳回（第 3 次）→ 停止提交审计，输出分歧报告
                            │
                            ├── 人采纳审计意见 → 修完走令牌放行
                            └── 人判定过度拦截 → 直接令牌放行
      
      执行者写 outcome.md（含 audit 报告 + diff 摘要 + 改动理由）
                │
                ▼
      人审阅 → 批准/驳回
                │
                ├── 批准 → 创建 .claude/.gate/audit_ok_<file> 标记
                │           │
                │           ▼
                │     执行者用 @claude-override-approved 令牌 Edit
                │           │
                │           ▼
                │     Hook 双重验证：令牌 + audit 标记（缺一拦截）
                │           │
                │           ├── 标记有效（<30min，文件匹配）→ 删除标记，放行
                │           └── 标记缺失/过期/不匹配 → 拦截
                │
                └── 驳回 → 更新 direction.md，执行者重做
```

## 令牌说明

`@claude-override-approved` 仅存在于 `.claude/hooks/` 源码中（受保护目录）。
不在 CLAUDE.md、rules 文件或任何 AI 可读文件中公开。
新会话无法通过阅读项目文档获知令牌值。

## 操作步骤

0. **校验**：运行 CLI validate，通过后再走下面流程
1. **审计**：运行 CLI audit 提交异构盲审
2. **报告**：执行者写 outcome.md（含 audit 报告 + diff 摘要 + 改动理由）
3. **批准**：人审阅后批准。批准后创建 `.claude/.gate/audit_ok_<file>` 标记（有效期 30 分钟，一次性使用）
4. **修改**：执行者用令牌执行 Edit/Write。Hook 双重验证（令牌 + 有效 audit 标记）
5. **验证**：完成后立即运行构建/类型检查，确认零错误
6. **违反后果**：跳过 audit 直接用 Bash → pre_bash.js 拦截。跳过 audit 直接用 Edit → 无令牌拦截。有令牌无 audit 标记 → pre_edit_file.js 拦截
