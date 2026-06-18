# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：过期文件归档 + 必读内容调整

### 步骤 1：建 archive 目录并移入过期文件

```bash
mkdir -p archive/设计文档 archive/测试报告 archive/审计记录

# 设计文档（被 system_audit.md 替代）
git mv 方向性讨论.md archive/设计文档/
git mv 进攻层失效分析.md archive/设计文档/

# 测试报告（已执行完毕，历史记录）
git mv 测试报告.md archive/测试报告/
git mv strateg_漏洞验证_20260612.md archive/测试报告/
git mv 新增测试方案.txt archive/测试报告/

# 审计记录
git mv 跨模型审计/全量审计-prompt.md archive/审计记录/
git mv 跨模型审计/公式验证报告.md archive/审计记录/
```

删除空目录 `跨模型审计/`。

### 步骤 2：CLAUDE.md 移除方向性讨论引用

```markdown
> **AI 核心指令**：任何新会话启动时，必须优先完整阅读本文件、
  `attribution/system_audit.md` 及 `.claude/rules/`
  下所有规则文件（按编号顺序加载）。本文件拥有最高解释权。
```

只保留 `system_audit.md`，去掉 `方向性讨论.md`。

### 步骤 3：10-context.md 加载分层图同步

```
CLAUDE.md（始终加载）
  └── attribution/system_audit.md（始终加载，系统审计）
  └── .claude/rules/（始终加载，按编号顺序）
        ├── 1-architecture.md
        ├── ...
        └── 12-project-log.md
  └── AGENTS.md / DESIGN.md（始终加载）
  └── archive/（历史文件，AI 在需要时自行读取）
```

### 步骤 4：更新 .claudeignore

确保 `archive/` 不在 ignore 中，让归档文件被 git 追踪。

### 步骤 5：提交

```bash
git add -A
git commit -m "v190-20260618-23: 归档 — 过期文件移至 archive/，必读简化为 system_audit + rules"
```

### 验收

- [ ] `archive/` 含三个子目录 + 7 个文件
- [ ] CLAUDE.md 必读引用仅含 `system_audit.md`
- [ ] 10-context.md 加载图与 CLAUDE.md 一致
- [ ] `跨模型审计/` 已删除
- [ ] 工作区干净
