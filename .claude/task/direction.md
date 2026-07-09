# 执行指令

> 2026-06-30 | 项目重组：004-quant-futures→005 + 新建 004-quant-stock

## 背景

进攻层（价值投资个股）确定为独立项目。现有 004-quant-futures 重编号为 005，腾出 004 给进攻层。

## 步骤

### 步骤 1 — 004-quant-futures → 005-quant-futures

```bash
cd "D:\AI项目"
mv 004-quant-futures 005-quant-futures
cd 005-quant-futures
```

修改 GitHub 远程 URL：
```bash
git remote set-url origin https://github.com/Yejianheng/005-quant-futures.git
```

项目内 `004` 引用替换为 `005`（README、CLAUDE.md 等）：
```bash
grep -r "004" --include="*.md" --include="*.json" -l | xargs sed -i 's/004/005/g'
```

提交：
```bash
git add -A && git commit -m "重命名：004→005"
```

### 步骤 2 — 新建 004-quant-stock

```bash
cd "D:\AI项目"
cp -r 003-quant-etf 004-quant-stock
cd 004-quant-stock
```

清理（进攻层不需要的）：

```
删除：
  data/                          # ETF 行情数据
  tests/test_execution_gap.py    # ETF 特定测试

清空：
  .claude/task/direction.md
  .claude/task/outcome.md
  .claude/task/recommendation.md
  .claude/next-session.md
```

保留：
- `.claude/hooks/` — 角色门禁 + 保护区 Hook
- `.claude/rules/` — 通用规范保留（3-core-mechanism.md 后续重写）
- `src/` — 回测引擎骨架保留
- `protected-files.json` / `protected-contracts.json`
- `.claude/role.json` → `{"role":"advisor"}`

### 步骤 3 — 修改项目标识

```
CLAUDE.md          → 项目名改为 004-quant-stock，描述改为"个股价值投资进攻层"
README.md          → 同步更新
.claude/rules/3-core-mechanism.md → 清空 ETF 内容，写"待进攻层设计填充"
```

GitHub 远程：
```bash
git remote set-url origin https://github.com/Yejianheng/004-quant-stock.git
```

### 步骤 4 — 写入进攻层备忘录

复制本项目的备忘录到新项目：
```bash
mkdir -p "D:\AI项目\004-quant-stock\attribution"
cp "D:\AI项目\003-quant-etf\.claude\memo\offense-layer-design.md" "D:\AI项目\004-quant-stock\attribution\offense-layer-design.md"
```

### 步骤 5 — 提交

```bash
cd "D:\AI项目\004-quant-stock"
git add -A
git commit -m "初始化：从 003-quant-etf 复制，进攻层价值投资个股独立项目"
```

## 约束

- 003-quant-etf 不动任何文件
- 原 004-quant-futures 仅重命名，内容不丢
- 每步提交，不跨步
