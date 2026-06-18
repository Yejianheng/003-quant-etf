# 上下文工程

## 核心原则

CLAUDE.md / rules 只写 AI 从代码库自己发现不了的东西。
工具配置（build/test/lint 命令）从 `package.json` 可发现 → 不写。
代码风格从 ESLint/Prettier 配置可发现 → 不写。
目录结构 AI 可自行探索 → 不写。
环境变量从 `.env.example` 可发现 → 不写。

冗余上下文：+20% token 消耗，-3% 任务成功率。

## .claudeignore（必须配置）

排除噪声目录，防止其内容消耗上下文 token：

```
node_modules/
.venv/
dist/
build/
.next/
.turbo/
*.lock
*.min.js
*.min.css
coverage/
public/assets/
*.png
*.jpg
*.gif
*.svg
*.ico
*.woff2
generated/
__pycache__/
*.pyc
```

## Session 纪律

- 一个会话一个任务：40 条消息覆盖 3 个功能的效果 < 3 个独立会话各 15 条消息。
- AI 开始循环或自相矛盾时 → 使用 `/compact` 压缩上下文，而不是继续追加解释。
- 新会话启动必须先 `git status`，工作区不干净禁止编码操作。

## 上下文分层加载

```
CLAUDE.md（≤40 行，始终加载）
  └── attribution/system_audit.md（始终加载）
  └── .claude/rules/（始终加载，按编号顺序）
        ├── 1-architecture.md
        ├── 2-coding-style.md
        ├── ...
        └── 12-project-log.md
  └── AGENTS.md / DESIGN.md（始终加载）
  └── docs/architecture/*.md（AI 在需要时自行读取）
  └── archive/（按需加载，仅当任务明确引用时）
```

- 根文件只做导航，不堆内容。
- 规则文件按关注点拆分，一个文件管一件事。
- 子目录可放独立 CLAUDE.md（如 `frontend/CLAUDE.md`），AI 在该目录工作时自动加载，避免前端规则污染后端任务。**子目录 CLAUDE.md 第一行必须是 `@../CLAUDE.md`**，确保根目录安全规则（保护区清单、Hook 配置、宪法）始终生效。@claude-override-approved

## 验证

新项目配置完成后，输入 `/memory` 确认所有规则文件出现在加载列表中。
准则：没列出 = 没生效。
