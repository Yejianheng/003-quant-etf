# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 执行纪律（强制）

**每步完成 → 验证通过 → 提交 → 再进行下一步。** 禁止批量执行后统一提交。

## 当前任务：三轮独立测试

---

### 步骤 1：Hook 角色门禁回归测试

#### 场景清单

```
基础路径：
  - executor Edit src/文件 → 放行
  - executor Write .claude/task/outcome.md → 放行

单向锁：
  - executor 写 role.json {"role":"advisor"} → 放行（时序窗口）
  - advisor 写 src/文件 → 拦截
  - advisor 写 .claude/task/recommendation.md → 放行（task 豁免）
  - advisor 写 .claude/task/direction.md → 放行
  - advisor 写 role.json {"role":"executor"} → 拦截（无法解锁）

边界：
  - 文件路径含 ".claude/task/" 但不以该前缀开头 → 防路径注入
  - 文件路径为空 → isTaskFile=false，走正常拦截
```

#### 执行

1. 写测试文件 `tests/test_role_gate.py`，用 monkeypatch 模拟 `process.exit` 和 `fs.readFileSync`，验证 pre_edit_file.js 角色门禁的所有分支
2. 跑测试 → 必须全红（测试文件新建，主逻辑尚未被测试覆盖，但因 Hook 是 JS 文件，Python 测试只能通过 subprocess 调用 node 间接验证）
3. 实际验证方式：创建测试脚本 `tests/test_role_gate.sh`，直接调用 node 模拟 Hook 输入，捕获退出码
4. 跑 → 全绿 → 提交

> **注意**：Hook 文件是 Node.js，测试方式需确认。如果是 JS 单元测试（如 `node -e` 或 jest），测试文件应在 `tests/` 下，文件名对应 `test_pre_edit_file.js`。

---

### 步骤 2：check_values.py offense_pool 校验测试

#### 场景清单

```
基础路径：
  - 合法 OFFENSE_POOL（6 源，各 1-3 候选，不重叠）→ exit 0

结构违规：
  - 缺少风险源 → exit 1 + "缺少风险源"
  - 多余风险源 → exit 1
  - 某源 candidates 为空 → exit 1 + "candidates 数量 0"
  - 某源 candidates > 3 → exit 1

重叠违规：
  - 候选 code 与 ETF_UNIVERSE 重叠 → exit 1 + "重叠"
  - code 非纯数字 → exit 1

边界：
  - OFFENSE_POOL 为 dict 但某源值为 str → exit 1
  - etf_universe.py 无 OFFENSE_POOL 变量 → exit 1
  - etf_universe.py 语法错误 → exit 1 + "AST错误"
```

#### 执行

1. 写 `tests/test_offense_pool_contract.py`
2. 测试用临时文件（`tmpdir` / `tmp_path`）构造各种违规 OFFENSE_POOL，调用 `check_values.py` 的 `check_offense_pool` 函数
3. 跑 → 全红 → 写主代码补全逻辑（如果有缺失）→ 全绿 → 提交

---

### 步骤 3：候选池分类映射表校验

#### 背景

`recommendation.md` 列出的 10 只候选 ETF，行业分类当前靠名称关键词推断。需确认分类与申万/中信标准一致。

#### 执行

1. 将 10 只候选的分类验证写入 `tests/test_candidate_classification.py`
2. 检查每只 ETF 的申万一级行业分类（通过 AKShare `fund_etf_info_sina` 或已缓存数据）
3. 与 `OFFENSE_POOL` 中分配的 6 类风险源逐一对照
4. 跑 → 全绿（或标记不匹配项）→ 提交

### 约束

- 每步独立提交，不跨步合并
- 旧测试安全带：每步跑全部测试，确认零回归
- 步骤 3 涉及网络请求，遵守分时限流（≥3s 间隔）

### 验收标准

- [ ] 步骤 1 测试全部通过 + 提交
- [ ] 步骤 2 测试全部通过 + 提交
- [ ] 步骤 3 测试全部通过 + 提交
- [ ] 全量测试零回归

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
