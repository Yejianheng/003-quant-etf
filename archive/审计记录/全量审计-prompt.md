# 项目全量代码审计

你是一个铁面无私的代码审计专家。你的任务是对以下量化交易项目做全面审查。

## 审查维度

1. **策略逻辑一致性**：对照项目宪法中描述的策略机制，检查源码实现是否与文档一致，有无逻辑漏洞
2. **架构违规**：是否存在下层调用上层、展示层写业务逻辑、循环依赖
3. **安全漏洞**：硬编码凭证、注入风险、未校验的输入
4. **边界条件**：空值处理、除零保护、极端市场场景（如全跌停、涨跌停）
5. **回测正确性**：Look-Ahead Bias、幸存者偏差、执行延迟处理是否正确
6. **参数管理**：关键参数是否在配置文件中，是否存在魔法数字
7. **代码质量**：死代码、未使用变量、过度注释或缺少关键注释

## 输出格式

对每个审查维度输出：
- PASS / FAIL
- 如 FAIL：违规位置（文件+行号）、违反的具体规则、风险等级（高/中/低）、修复建议

最后输出总体评分（1-10）和 Top 5 最应该修复的问题。

---


========== CLAUDE.md ==========
# 003-quant-etf

> **AI 核心指令**：任何新会话启动时，必须优先完整阅读本文件、`方向性讨论.md` 及 `.claude/rules/` 下所有规则文件（按编号顺序加载）。本文件拥有最高解释权。

## 1. 项目目标

ETF 多资产动量轮动量化系统。利用动量因子驱动 ETF 轮动，AI 辅助纪律执行和标的筛选。两层结构：宽基防御层（趋势过滤 + 国债/逆回购兜底）+ 行业进攻层（截面动量排名）。硬约束最大回撤 20%。

> **当前阶段：方向性讨论。** 策略框架已有方向但大量细节未定，详见 `方向性讨论.md`。

## 2. 设计哲学

**本系统不追求全自动。** 核心矛盾——人不会代码因此必须依赖 AI 做技术判断——决策责任不可外包。窗口切换可以优化，人的决策环节不可替代。顾问提供建议、执行者动手、审计交叉验证，但最终批准权永远在人手里。这是刻意的设计约束，不是技术限制。

## 3. 协作原则

1. **禁止擅自生成**：未获需求细节前不写任何业务代码。新会话先问待攻克任务，索要源码/上下文后再给方案。
2. **单步输出**：每次回复只输出一个文件的一个步骤，完成后询问用户是否"继续"。
3. **意图包裹**：对代码执行操作的说明，必须写在代码块内部的注释中，禁止代码块外自然语言描述操作步骤。
4. **授权排雷**：重构前先汇报污染点及净化方案，未经同意禁止修改。
5. **新窗口门禁**：新会话启动后必须先执行 `git status`。若工作区不干净（有 modified / untracked / staged），禁止任何编码操作，必须先汇报并等待决策。
6. **防火墙自检**：收到任务后，对照架构防火墙表格逐文件判断是否触碰保护区。触碰则必须先执行 validate→audit 流程再动手。保护区文件需 audit 标记 + 令牌双重验证方可写入。
7. **审计令牌**：`@claude-override-approved` 仅存在于 `.claude/hooks/` 源码中（受保护目录），不在本文或 rules 文件中公开。令牌需配合 audit 标记使用，缺一不可。

## 4. 角色调度

新会话第一条消息匹配触发，只读指定文件、回复就位、停止。禁止额外操作。

**顾问角色第一步强制写 `.claude/role.json` → `{"role":"advisor"}`。执行角色无需操作 role 文件。Hook 从 `.claude/role.json` 读取角色，`"advisor"` 时仅放行 5 文件白名单。**

### 顾问 `^顾问$`

**永久原则：顾问在任何情况下都不直接修改业务代码。所有代码修改必须通过 direction.md → 执行窗口。**

0. 写 `.claude/role.json` → `{"role":"advisor"}`
1. 读 `.claude/next-session.md`
2. 读 `.claude/task/direction.md`
3. 读 `.claude/task/outcome.md`（如存在）
4. 读 `.claude/task/recommendation.md`（如存在）
5. `git status --porcelain`
6. 汇报：`顾问就位。当前阶段：[...] 工作区：[...] 待处理：[...]`
7. **自主判断**：有 outcome → 审查写 recommendation；direction 空有任务 → 立即写 direction；无任务 → 等待
   **写 direction 前检查**：涉及 .py/.ts/.tsx 文件时，确认测试文件存在。不存在则 direction 第一步为"建测试，跑红灯"。
8. **禁止**：改代码、清文件、跑 bash 写文件、生成 SVG/图表/非文档类产出

### 执行 `^执行$`
1. 读 `.claude/task/direction.md`
2. 空模板（含 `[待填写]`）→ 回复 `执行就位，等待顾问写入 direction.md。`
3. 有实际任务 → **立即执行，不询问确认。** 逐项完成，每项汇报进度。全部完成后写 outcome.md 并提示"请顾问窗口审查"。
4. 执行期间遵从 direction.md 全部约束，保护区文件必须先 validate→audit。

### 模型分工

| 角色 | 模型要求 | 说明 |
|------|---------|------|
| 顾问 | 最强推理模型 | 深度上下文 + 技术决策 |
| 执行 | 轻量快模型 | 精确执行，无需深度推理 |
| 审计 | 异构模型（与顾问不同厂商） | 交叉验证，防止同模型盲区 |

## 5. 规则索引

所有细则存放在 `.claude/rules/`，AI 按编号顺序加载：

| 文件 | 关注点 |
|------|--------|
| `.claude/rules/1-architecture.md` | 架构分层、三权分立、模块铁律 |
| `.claude/rules/2-coding-style.md` | 代码风格、命名规范、注释规范 |
| `.claude/rules/3-core-mechanism.md` | 核心业务机制（最难懂的 2-3 件事） |
| `.claude/rules/4-firewall.md` | 架构防火墙（受保护区文件清单） |
| `.claude/rules/5-infrastructure.md` | 基建约束（数据库/API/环境变量） |
| `.claude/rules/6-quality.md` | 质量保证、测试、构建要求 |
| `.claude/rules/7-git.md` | Git 提交规范、版本格式、禁区 |
| `.claude/rules/8-ui-design.md` | UI 设计规范、DESIGN.md 选型（前端项目适用） |
| `.claude/rules/9-ai-output.md` | AI 输出质量门禁（Plan→Code→Verify、反Slop、LLM契约） |
| `.claude/rules/10-context.md` | 上下文工程（.claudeignore、Session纪律、分层加载） |
| `.claude/rules/11-testing.md` | 测试规范（红灯检验、测试先于主代码、场景清单） |
| `.claude/rules/12-project-log.md` | 项目日志规范（调试记录格式、命名规范、记录时机） |

> 根文件超过 60 行时，将新增内容下沉到对应的 rules 文件，不要往根文件追加。


========== 方向性讨论.md ==========
# 方向性讨论

> 项目启动阶段的决策讨论记录。已定事项是后续 rules 填空的依据，未定事项按顺序逐一解决。

---

## 一、项目定位

ETF 多资产动量轮动量化系统。AI 辅助纪律执行和标的筛选，不追求全自动交易。量化核心价值：**选什么 + 什么时候换**。回测框架自研轻量，数据源 AKShare。

---

## 二、策略框架（双引擎结构）

```
防御层（Beta，70%）              进攻层（Alpha，30%）
─────────────────────           ─────────────────────
目标：活下来                      目标：增强收益
追求：低相关                      追求：高动量
核心：控制回撤、控制波动           核心：市场正在奖励谁
最怕：股债同跌、相关性失控         最怕：频繁换手、伪趋势
```

防御层负责稳定性，进攻层负责进攻性。两者优化目标相反（分散 vs 集中），失效模式独立，组合在一起才有意义。

**关键架构约束**：进攻层空仓时，释放的 30% 资金进入逆回购，**不回流防御层**。否则 Beta 从 70% 变成 100%，风险预算被污染，双引擎重新耦合——这是本系统最珍贵的职责分离结构，不可破坏。

### 完整决策链

```
买不买 ── 趋势强度（全系统统一）
    │     趋势强度 = 年化收益率 / 年化波动率
    │     年化收益率 = ln(P_t / P_{t-N}) × (252 / N)
    │     趋势强度 ≤ 0 → 排除
    │     趋势强度 > 0 → 进入候选
    │
买哪个 ── 防御层：目标权重 × clip(趋势强度 / 2, 0, 1)
    │     进攻层：20日 + 60日截面动量 → z-score → 综合排名 → Top3
    │
买多少 ── 目标波动率框架（Beta/Alpha 独立管理）
    │     防御层：独立计算 EWMA 协方差矩阵 → 70% 资金内缩放
    │     进攻层：独立计算 EWMA 协方差矩阵 → 30% 资金内缩放
    │     两层风险预算互不穿透，组合波动率为输出结果而非控制输入
    │     缩放系数 = 目标波动率 / 预测波动率
    │     容忍带：偏离不超过 ±1.5% 不操作
    │
钱去哪 ── 相关性熔断
    │     股票篮子 = 沪深300 + 创业板 + 纳指（等权合成）
    │     股票篮子 vs 国债 ETF，60 日相关性 → 5日 SMA 平滑
    │     平滑后 > 0 → 释放资金直进逆回购
    │
活下来 ── 回撤硬止损
          8% 告警 → 12% 减半 → 18% 清仓
```

### 五个不可替代的职责

| 模块 | 回答的问题 |
|------|-----------|
| 趋势强度 | 是否暴露风险 |
| 行业动量 | 市场正在奖励谁 |
| 目标波动率 | 暴露多少风险 |
| 相关性熔断 | 风险暴露在哪 |
| 回撤止损 | 风险失控怎么办 |

### 核心原则

不预测未来、不判断政策、不判断估值、不判断宏观。
只观察两件事：**市场正在奖励谁**，以及**当前应该承担多少风险**。

一个优秀的投资系统不是拥有最多规则，而是拥有最少但不可替代的规则。

---

### 防御层（Beta，70% 资金）

目标：不亏或少亏。硬约束最大回撤 20%。

| 标的 | 作用 |
|------|------|
| 沪深300 | A 股大盘 beta |
| 创业板 | A 股成长/中小盘 |
| 纳指 | 海外科技 beta，与 A 股低相关 |
| 黄金 | 避险资产，与股票接近零相关 |
| 国债 ETF | 防御资产，票息 + 负/零相关性 |
| 国债逆回购（GC001） | 极端情况兜底，现金等价物 |

> 目标权重是初配基准，最终仓位由目标波动率统一缩放。风险贡献才是真正的权重。

参考目标权重：沪深300 25% / 创业板 10% / 纳指 15% / 黄金 10% / 国债 ETF 40%

防御层工序（详见顶层决策链）：趋势强度过滤方向 → 目标权重 × clip(趋势强度 / 2, 0, 1.0) 得原始仓位 → 目标波动率统一缩放 → 相关性熔断修正资金路由 → 回撤硬止损兜底。

---

### 进攻层（Alpha，30% 资金）

目标：赚超额。截面动量排名选出当前最强的行业 ETF，纯动量单因子。

#### 候选池

行业池的作用不是"覆盖所有行业"，而是**提供足够独立的趋势来源**。它是趋势风险源筛选器，不是行业百科全书。

##### 三层架构：风险源稳定，ETF 可替换

```
风险源层（架构级，6 类固定，长期不变）
  │
  ├─ 消费 ──── 消费ETF候选池 ── 代表ETF
  ├─ 医药 ──── 医药ETF候选池 ── 代表ETF
  ├─ 金融 ──── 金融ETF候选池 ── 代表ETF         截面动量排名
  ├─ 周期资源 ─ 周期ETF候选池 ── 代表ETF   ─────────→  Top 3 持仓
  ├─ 科技成长 ─ 科技ETF候选池 ── 代表ETF
  └─ 军工 ──── 军工ETF候选池 ── 代表ETF

风险源层：架构稳定，不可随意增减。ETF 退化了只替换实现工具，不修改框架。
ETF 候选层：每类 1-3 只，共 ~12-20 只。ETF 只是风险源的实现工具，不是风险源本身。
最终轮动：6 只代表 ETF 之间做截面动量排名，选 Top 3 持仓。
```

> 行业轮动真正追求的不是 ETF 数量，而是有限数量的独立趋势来源。6 类风险源 + Top3 持仓已处于成熟行业轮动系统的合理区间。真正危险的是不断增加新主题 ETF——表面更丰富，实际全在押同一个市场风格。

##### 分类原则：按经济驱动因子，不是申万名称

```
错误方向：              正确方向：
半导体                   消费       ← 居民消费能力
电子                     医药       ← 人口老龄化、防御需求
计算机    同一科技       金融       ← 利率、信用扩张
通信      成长风险       周期资源   ← 经济周期、通胀
AI                       科技成长   ← 风险偏好、产业升级
                         军工       ← 政策、地缘风险
```

##### 一级分类（6 类，不拆分细行业）

| 分类 | 经济驱动因子 | 代表 ETF |
|------|-------------|---------|
| 消费 | 居民消费能力 | 消费ETF、食品饮料ETF |
| 医药 | 人口老龄化、防御需求 | 医药ETF |
| 金融 | 利率、信用扩张 | 证券ETF、银行ETF |
| 周期资源 | 经济周期、通胀 | 能源ETF、煤炭ETF、有色ETF |
| 科技成长 | 风险偏好、产业升级 | 科技ETF、半导体ETF |
| 军工 | 政策、地缘风险 | 军工ETF |

> 6-8 个已足够。超过 10 个后高度相关行业明显增加。宁可少，不要多。

##### 五项筛选机制

**机制 1：长期相关性过滤**
候选行业之间，3 年周收益率相关系数不得长期高于 0.7。若长期 > 0.7，视为同类风险资产，保留流动性更好者。

**机制 2：风险驱动差异化**
检查上涨原因是否不同。消费上涨（居民消费恢复）≠ 能源上涨（大宗商品涨价）≠ 科技上涨（风险偏好提升）。若上涨逻辑高度一致，不应同时纳入。

**机制 3：ETF 流动性门槛**
日均成交额长期稳定，避免冷门 ETF 流动性塌陷和大额滑点。

**机制 4：历史轮动性检查**
该行业是否真的参与轮动？若长期永远 Top1 或永远垫底，不具备轮动意义。

**机制 5：避免政策镜像行业**
地产、银行、建筑在很多时期本质同一政策链，同时纳入形成伪分散。

##### 可选扩展（谨慎）

海外科技、港股互联网、公用事业、红利——但必须先证明其风险来源与现有行业池不同。

> 行业间相关系数 0.7 作为硬规则。相关性是动态变化的但同类资产长期相关性稳定。

##### 行业映射流水线（Industry Mapping Pipeline）

从 1482 只 ETF 到 6 个风险源代表的完整执行路径。解决"原则有了但不知道怎么落地"的问题。

**核心思想**：不是看 ETF 名称，是看底层指数成分的申万一级行业暴露。名称会漂移（"科技创新""新质生产力""数字经济"本质可能全是半导体+计算机），底层持仓不会说谎。

###### 第一步：资产池预过滤

目标：剔除不可交易资产。

| 过滤条件 | 目的 |
|---------|------|
| 非股票 ETF 剔除 | 排除债券/货币/QDII/商品 |
| 杠杆/反向 ETF 剔除 | 不适合动量策略 |
| 日均成交额 < 阈值 | 流动性底线 |
| 上市不足 252 日 | 至少 1 年历史数据 |
| 场外 ETF 剔除 | 不可交易所交易 |

结果：1482 → ~100-200 只。

###### 第二步：一级风险源映射

目标：把 ETF 映射到 6 类风险驱动类型。

**映射策略（两级，90% 自动化 + 10% 人工/半自动）**：

**第一级：名称关键词映射（处理 ~90%）**

ETF 名称天然暴露行业归属——"证券ETF"即金融、"医药ETF"即医药、 "芯片ETF"即科技。对 6 类风险源层面的粗分类，名称已足够可靠。实测：1535 只 ETF 预过滤+宽基排除后剩 1066 只，名称映射成功 480 只（消费 81/医药 80/金融 53/周期资源 86/科技成长 160/军工 20）。未映射的 586 只为策略/主题型 ETF（红利、央企、一带一路等）和漏网宽基——这些本就不该进入进攻池。

**第二级：申万成分验证（处理 ~10% 边缘案例）**

名称模糊的 ETF（如"数字经济""新质生产力""科创芯片"）通过 `index_component_sw` 抽取申万一级行业成分股 + 权重，按主导行业归属。已实测可用（数据源：申万研究所，非东方财富，不触发限流）。

> **数据源约束**：东方财富是唯一提供"ETF→跟踪指数代码→成分股列表"完整链路的源，但其 WAF 极不稳定。全自动申万暴露映射不可行。当前方案：名称粗分类 + 申万成分手动抽查，够用且不依赖东方财富。

| 风险源 | 名称关键词 | 申万一级行业（验证用） |
|--------|-------------|
| 消费 | 消费、食品饮料、酒、家电、农业、养殖、农牧、畜牧、旅游 | 食品饮料、家用电器、商贸零售、社会服务、农林牧渔 |
| 医药 | 医药、医疗、药、医械、中药、创新药、生物医药 | 医药生物 |
| 金融 | 证券、券商、银行、金融、保险、非银 | 银行、非银金融、房地产 |
| 周期资源 | 煤炭、有色、钢铁、化工、材料、能源、石油、稀土、矿业、资源 | 煤炭、石油石化、有色金属、钢铁、基础化工、建筑材料 |
| 科技成长 | 芯片、半导体、科创、电子、通信、计算机、软件、AI、人工智能、机器人、5G、信创、信息技术、数字经济 | 电子、计算机、通信、传媒 |
| 军工 | 军工、国防、军民、航空 | 国防军工 |

> 实测：1535 只 ETF 经预过滤+宽基排除后 1066 只，名称映射 480 只（45%），未映射的均为策略/主题/宽基——本不该进入进攻池。边缘案例（如"数字经济ETF"）通过申万成分抽样验证确认归属。

###### 第三步：单风险源代表选择

目标：每个风险源只保留 1-2 只代表 ETF。优先顺序：流动性 > 跟踪误差 > 成立时间 > 规模 > 费率。最终每个风险源保留最稳定的代表 ETF（如科技成长只保留科创 50 或芯片 ETF，不是 10 只科技 ETF 并存）。

###### 第四步：风险源重叠检查

验证不同分类之间是否真的不同。3 年周收益率相关系数长期 > 0.7 → 判定风险源重叠 → 只保留一个（如科技成长和港股互联网可能长期高度同步）。

###### 第五步：轮动有效性验证

检查该风险源是否真的参与轮动。长期永远垫底 / 长期永远 Top1 / 无明显状态切换 → 不具备轮动意义。行业轮动层需要"可轮动性"，不是"稳定优质资产"。

###### 第六步：最终行业池冻结

形成固定风险源池（消费、医药、金融、周期资源、科技成长、军工）。**后续只允许 ETF 替换，不允许频繁新增风险源。** 风险源层属于系统架构层，ETF 层属于实现层。否则行业池会不断膨胀，系统从"风险管理系统"退化为"热门 ETF 收集器"。

#### 动量指标

```
各窗口动量得分 = 该窗口对数收益率 = ln(P_t / P_{t-N})
```

20 日 + 60 日两个窗口，各自在截面上做 z-score 标准化后等权合成综合排名得分。

#### 调仓规则

- 每周检查一次行业动量排名
- 选综合得分前 3 只，等权配置
- **排名缓冲带**：持仓中任一只跌出前 5 → 触发卖出，换入当前前 3（买入门槛 3，卖出门槛 5，滞后带宽 2 名）
- 30 天内无触发 → 强制再平衡
- 候选 ETF 自身趋势强度 ≤ 0 → 移出候选池（绝对动量过滤）
- **极端兜底**：经过绝对动量过滤后，合格 ETF 不足 3 只 → 空缺仓位资金直进逆回购，宁缺毋滥

---

## 三、策略基准

多资产加权基准：沪深300 + 创业板 + 纳指 + 黄金 + 国债 ETF，按防御层目标权重配比，月度机械再平衡。逆回购不在基准内。

策略 vs 基准的差异 = 趋势强度的择时效果 + 行业动量的选股效果。

---

## 四、已定事项

1. **因子**：纯动量/趋势。估值因子不用
2. **池子必须包含**：纳指、黄金、国债 ETF、国债逆回购（GC001）
3. **宽基 A 股部分**：沪深300 + 创业板
4. **调仓**：信号驱动，不是日历驱动
5. **硬约束**：最大回撤不超过 20%
6. **两层资金权重**：防御层 70%，进攻层 30%
7. **行业层因子**：截面动量排名，单因子
8. **行业层动量窗口**：20 日 + 60 日双窗口等权合成
9. **行业层 K 值**：前 3 只，排名缓冲带（买入门槛前 3，卖出门槛跌出前 5）
10. **动量指标**：对数收益率 + z-score 截面标准化
11. **防御层机制**：趋势强度（买不买）→ 目标波动率（买多少）→ 相关性熔断（钱去哪）→ 回撤硬止损（兜底）
12. **目标波动率**：Beta/Alpha 独立管理，互不穿透。协方差 EWMA（λ=0.94）。具体目标波动率取值待回测确定
13. **回撤硬止损**：8% 告警（就位）→ 12% 减半 → 18% 清仓
14. **数据源**：AKShare
15. **回测**：自研轻量
16. **逆回购品种**：GC001
17. **可转债 ETF**：不考虑
18. **自动化边界**：层级 1/2/3 全自动，层级 4 实盘执行留人工闸

---

## 五、未定事项

- [ ] 防御层参考目标权重（目前提议 25/10/15/10/40，在目标波动率框架下风险贡献比名义权重更重要）
- [ ] 趋势强度窗口（60 日）和阈值（2）——等回测做参数敏感性扫描
- [ ] 目标波动率合意取值（8%/10%/12%）+ 波动率容忍带 ±1.5% 是否最优——等回测参数扫描
- [ ] 行业层候选 ETF 具体名单——等流动性/规模数据筛选
- [ ] 国债 ETF 具体标的（长久期 vs 短久期差异大，影响相关性熔断效果）
- [ ] 逆回购最短停留期（防频繁进出摩擦）
- [ ] 基准具体权重（名义权重 vs 风险贡献权重，两者是否需要区分）

---

## 六、策略验证标准流程

目标：验证策略是否具备逻辑有效性、参数稳健性、组合有效性、极端生存能力、样本外泛化能力、实盘可执行性。不追求最高收益率，优先追求长期稳定、风险可控、结果可重复、策略可执行。

---

### 阶段 1：逻辑验证（Module Validation）

**目的**：证明每个模块具有独立价值。如果移除该模块后系统变差，则模块有效。

| # | 对照测试 | 观察指标 |
|---|---------|---------|
| 1.1 | 趋势强度过滤 vs 无过滤（满仓持有） | 收益率、最大回撤、夏普比率 |
| 1.2 | 目标波动率缩放 vs 固定名义仓位 | 收益率、波动率、最大回撤 |
| 1.3 | 相关性熔断 vs 无熔断 | 股债同跌时期表现、极端回撤 |
| 1.4 | 回撤硬止损 vs 无止损 | 尾部风险控制、最大回撤 |
| 1.5 | 排名缓冲带 vs 无缓冲带（Top3 进出） | 换手率、交易次数、收益变化 |
| 1.6 | Beta/Alpha 独立风险预算 vs 全组合统一缩放 | 风险预算穿透程度、各层回撤独立性 |

**通过标准**：移除模块后收益下降或风险显著恶化。

---

### 阶段 2：参数验证（Parameter Validation）

**目的**：寻找稳定区间，不是寻找最优参数。参数小幅变化后系统仍有效 → 稳健；剧烈变化 → 过拟合。

| # | 参数 | 扫描范围 |
|---|------|---------|
| 2.1 | 趋势强度窗口 | 20 / 40 / 60 / 80 / 120 日 |
| 2.2 | 趋势强度阈值 | 1.0 / 1.5 / 2.0 / 2.5 / 3.0 |
| 2.3 | 行业截面动量窗口 | 20+60 / 20+80 / 40+120 |
| 2.4 | 行业排名 K 值 | Top2 / Top3 / Top4 / Top5 |
| 2.5 | 排名缓冲带宽 | 跌出 Top4 / 跌出 Top5 / 跌出 Top6 |
| 2.6 | Beta 目标波动率 | 8% / 10% / 12% |
| 2.7 | Alpha 目标波动率 | 15% / 20% / 25% |
| 2.8 | 波动率容忍带 | ±1.0% / ±1.5% / ±2.0% |
| 2.9 | 缩放频率 | 每日 / 每周 / 每月 / 偏离 >20% 才调 |
| 2.10 | 回撤止损线 | 10/15/18 / 12/15/18 / 12/18/20 |
| 2.11 | Alpha 资金比例 | 20% / 30% / 40% |
| 2.12 | 相关性熔断窗口 | 40 / 60 / 80 日 |
| 2.13 | 相关性熔断阈值 | 相关系数 0 / 0.1 / 0.2 |
| 2.14 | EWMA 半衰期 | 5 / 11 / 20 交易日 |
| 2.15 | 创业板权重 | 0% / 5% / 10%（当前）/ 15% |
| 2.16 | 防御层权重结构 | 不同 Beta 资产权重组合 |

**通过标准**：参数小幅变化后结果保持稳定。若结果剧烈变化，判定存在过拟合风险。

---

### 阶段 3：组合验证（Integration Validation）

**目的**：验证双引擎组合价值。联合组合的风险收益比应优于任一单独模块。

| # | 对照测试 | 观察指标 |
|---|---------|---------|
| 3.1 | 仅运行防御层（Beta Only） | 年化收益、波动率、最大回撤、夏普、卡玛 |
| 3.2 | 仅运行进攻层（Alpha Only） | 同上 |
| 3.3 | Beta + Alpha 联合运行 | 同上，对比 3.1 和 3.2 |
| 3.4 | 独立缩放 vs 统一缩放 | 收益/回撤差异、风险预算穿透程度 |

**通过标准**：联合组合的风险收益比优于任一单独模块。

---

### 阶段 4：压力测试（Stress Test）

**目的**：验证极端市场环境下的生存能力。系统必须在极端时期保持可控回撤，无结构性失效。

| # | 场景 | 年份 | 观察指标 |
|---|------|------|---------|
| 4.1 | A 股股灾 | 2015 | 最大回撤、仓位变化、止损触发次数、恢复时间 |
| 4.2 | 单边熊市 | 2018 | 趋势强度是否及时清仓、阴跌中的仓位变化 |
| 4.3 | 疫情冲击 | 2020 | V 型反转中的反应速度、仓位恢复节奏 |
| 4.4 | 全球股债双杀 | 2022 | 相关性熔断触发次数、资金路由是否正确 |
| 4.5 | Beta 全部趋势强度 ≤ 0 | 各极端年份 | 组合 100% 国债/逆回购时的表现和持续时间 |

**通过标准**：最大回撤可控，恢复能力正常，无结构性失效。

---

### 阶段 5：样本外验证（Out-of-Sample Validation）

**目的**：验证泛化能力。离开设计样本后仍有效 → 逻辑具备泛化能力，非过拟合产物。

```
开发样本：2013–2021（用于设计与调参）
验证样本：2022–2025（完全不参与设计）
```

| # | 对比维度 | 观察指标 |
|---|---------|---------|
| 5.1 | 开发期 vs 验证期 | 收益率、回撤、夏普比率 |
| 5.2 | 参数在验证期的表现 | 是否仍落在扫描的稳定区间内 |

**通过标准**：验证期表现与开发期方向一致，不存在明显失效。

---

### 阶段 6：模拟实盘（Paper Trading）

**目的**：验证回测能否转化为真实收益。周期至少 3 个月，推荐 6 个月至 1 年。

| # | 记录内容 | 对比 |
|---|---------|------|
| 6.1 | 每日信号、实际成交、滑点、手续费 | 理论收益 vs 实际收益 |
| 6.2 | 调仓频率、仓位变化、资金路由路径 | 与回测预期是否一致 |

**通过标准**：实盘结果与回测结果接近，策略具备落地能力。

---

### 门禁链（Gate Process）

```
逻辑有效 → 参数稳健 → 组合有效 → 极端可生存 → 样本外可泛化 → 实盘可执行
```

只有当前阶段通过，才允许进入下一阶段。任何阶段失败，返回上一阶段修正。

六个阶段全部通过后，策略完成从"理论框架"到"可投资系统"的转换。

---

---

## 七、自动化边界

四个层级，三个自动化，一个留给人。

| 层级 | 内容 | 自动化 | 说明 |
|------|------|:------:|------|
| 1 | 数据管线 | 全自动 | 每日 AKShare 拉取 → 清洗 → 存储 |
| 2 | 信号生成 | 全自动 | 趋势强度 → 截面动量 → 目标波动率 → 调仓清单 |
| 3 | 模拟执行 | 全自动 | Paper Trading，记录滑点/成交 |
| 4 | 实盘执行 | 人工闸 | 信号输出 → 人批准 → BrokerAPI 发送 |

信号生成是纯数学计算，人没有增值空间。实盘执行是最后一个闸——CLAUE.md 设计哲学"最终批准权永远在人手里"，不是技术限制，是刻意约束。

### 架构含义

回测和实盘跑同一套代码，唯一区别在出口：

```
信号生成（全自动）
  → 调仓清单
  → 人审
       ├─ 驳回 → 不改
       └─ 批准 → 执行
                  ├─ 回测模式：Recorder.log()
                  └─ 实盘模式：BrokerAPI.send()
```

回测引擎的 Recorder 预留 `execute()` 接口，回测时写日志，实盘时替换实现。上游信号生成逻辑不变。

---

## 八、风险源新增准入框架

> 代码已冻结（v1.0）。只在发现新的长期独立风险源时才讨论新增资产。

### 设计原则

本系统配置的是风险源，不是资产。新增 ETF 不是目标。只有"新风险源 + 能提升组合效率"才允许进入。

现有五个风险源：中国经济（沪深300）、全球科技创新（纳指）、利率（国债ETF）、通胀/避险（黄金）、流动性（逆回购）。

### 准入门禁（五层，全部通过方可纳入）

#### 第一层：驱动独立性

该资产的涨跌是否由现有风险源无法解释？

判断标准：若资产表现主要由现有风险源决定 → 淘汰。存在独立驱动逻辑 → 进入下一层。

```
淘汰案例：
  红利ETF → 本质是中国权益风险（与沪深300 高度重叠）
  中证500 → 同上

通过案例：
  黄金 → 驱动是通胀/货币信用/避险，与权益不同
```

#### 第二层：长期相关性 + 极端市场独立性

它与现有风险源是否长期低相关？在危机中是否独立？

测试方法：滚动 3/5/10 年相关系数 vs 沪深300、纳指、国债、黄金，**显式包含危机子窗口**（2015 股灾、2018 熊市、2020 疫情、2022 加息）。

| 相关系数 | 结论 |
|----------|------|
| > 0.70 | 同风险源，淘汰 |
| 0.40-0.70 | 存疑 |
| < 0.40 | 可接受 |
| < 0.20 | 优秀 |

```
淘汰案例：
  红利ETF vs 沪深300：0.7-0.9（牛市同涨、熊市同跌，无独立表现）

通过案例：
  黄金 vs 沪深300：0.0-0.3（2022 股票跌、黄金涨，独立表现）
```

#### 第三层：长期存在性

该风险源是否可能持续 10 年以上？

要求：能给出 10 年甚至数十年以上的持续存在逻辑。

```
通过：利率风险（数百年）、黄金（数千年）、全球科技创新（数十年）
淘汰：AI 概念 ETF（主题行情）、短期热点行业
```

#### 第四层：可投资性

是否存在稳定、低成本、长期可交易的载体？

要求：ETF 可获取、流动性充足、长期存在、数据可获得、可纳入回测框架。否则即使风险源成立也不进入。

#### 第五层：组合贡献测试

加入后是否不损害现有系统？

测试：原组合 vs 新增后组合，全量回测对比。准入标准：**加入后 Sharpe 不跌破 1.0 且最大回撤不突破 18%**。

> 注意：现有防御层 Sharpe 1.23 已很高，新资产很难显著提升任一单项。准入标准设为"不显著恶化"而非"必须改善"，防止门槛过窄导致永远无法纳入新风险源。

### 禁止纳入的理由

```
✗ 收益率更高
✗ 最近表现更好
✗ 行业更热门
✗ ETF 数量更多
```

### 候选观察清单

以下风险源满足"独立驱动 + 长期存在"，待 ETF 流动性成熟后评估：

| 风险源 | 独立驱动逻辑 | 当前障碍 |
|--------|------------|---------|
| 数字资产 | 货币信用替代，与所有传统资产接近零相关 | 国内 ETF 受限，海外 BTC ETF 可通过但渠道不成熟 |
| AI 基础设施 | 算力供应链独立于消费/金融周期 | 纯度不够（掺杂消费电子），需观察专用 ETF |
| 全球电力网络 | 公用事业属性，与科技/金融周期错位 | 国内 ETF 规模偏小 |
| 新型能源体系 | 政策驱动逻辑，与经济周期不一致 | 标的分散，缺乏纯能源转型 ETF |

---

## 九、参考材料

- Moskowitz, Ooi & Pedersen (2012). "Time Series Momentum." *JFE*. — 时间序列动量开山之作，趋势信号 = sign(12月收益)，波动率缩放仓位
- Hurst, Ooi & Pedersen (2017). "A Century of Evidence on Trend-Following Investing." *JPM*. — 1880-2016 全周期验证，组合层目标波动 10%
- Hoffstein / Newfound Research (2019). "Fragility Case Study: Dual Momentum GEM." — 单参数脆弱性批评，ensemble 方案
- 招商证券 (2025). "行业动量策略的改进与ETF组合落地." — A 股行业动量实证：龙头股动量 IC 6.65%，择时后超额 ~12%
- 开源证券 (2024). "行业轮动3.0：范式、模型迭代与ETF轮动应用." — ETF 轮动组合年化 25.5%，信息比率 0.90
- 知乎文章：《一套跑通 2012–2025 的 ETF 多因子策略》（1.pdf 已存档）— 动量+多资产 ETF 轮动可行性验证


========== .claude/rules/1-architecture.md ==========
# 架构分层与模块铁律

## 三权分立（单向依赖，禁止循环）

- **协议/契约层**（[填入目录，如 /types, /interfaces]）：只定义类型和接口，禁止包含业务逻辑。
- **业务/中台层**（[填入目录，如 /services, /controllers]）：负责核心逻辑，禁止直接操作 UI 或向 C 端暴露未鉴权接口。
- **展现/消费层**（[填入目录，如 /components, /views]）：只负责渲染/展示，禁止在此层直接连接数据库或处理复杂算法。

```
消费层 ←──调用── 中台层 ←──依赖── 协议层
   ↑              ↑              ↑
  UI 渲染      业务编排       类型定义
```

## 模块铁律

- 单文件不得超过 [X] 行，超过必须拆分（hook / util / component 各拆独立文件）。
- 每个文件一个职责，禁止不经判断就往已有文件里塞新逻辑。
- LLM Prompt 是独立文件（`prompts/` 目录），禁止硬编码在业务代码中。
- 配置文件是唯一入口，禁止在业务代码中硬编码 API Key / URL / ID。
- 字段名变更必须同步更新所有引用处。


========== .claude/rules/2-coding-style.md ==========
# 代码风格与注释规范

## 语言规范

- 前端示例：必须使用 React Hooks，禁用 Class Components；样式必须使用 Tailwind。
- 后端示例：禁止使用全局变量；所有数据库查询必须使用 ORM，严禁拼接 SQL。

## 命名规范

- 文件名：[kebab-case]
- 类名/组件名：[PascalCase]
- 函数/变量：[camelCase]
- 常量：[UPPER_SNAKE_CASE]

## 注释规范（强制）

### 全量注释
所有代码必须包含注释。每个函数、类、关键逻辑块必须有注释说明其用途。

### 修改记录
每次对文件的修改，必须在文件**最前方**添加修改记录：
```js
// [2026-05-14] 修改：将 fetch 改为 axios，统一请求拦截
// [2026-05-13] 新增：用户登录模块，接入 OAuth 2.0
```

- 格式：`// [YYYY-MM-DD] 操作类型：简述`
- 操作类型：`新增` / `修改` / `修复` / `删除` / `重构`
- 按时间倒序排列，最新修改在最前。
- 超过 10 条记录时，保留最近 10 条，旧记录归档到文件末尾或删除。


========== .claude/rules/3-core-mechanism.md ==========
# 核心业务机制

## 实盘策略：50/50 A/B 组合（v186 确立）

> **50% A（无 sf, beta=0.10）+ 50% B（sf+0.08），各自独立运行，不调仓。defense_ratio = 1.00，进攻层完全搁置。**

### 为什么是组合而不是单一策略

| | 纯A 无sf | 纯B sf+0.08 | **50/50 组合** |
|---|---|---|---|
| Sharpe | 1.017 | 1.206 | **1.108** |
| 年化 | 11.72% | 9.05% | **10.47%** |
| 最大回撤 | -13.91% | -7.45% | **-9.66%** |
| 2018 | -8.6% | -3.6% | **-6.2%** |

纯 B Sharpe 最高但牛市被 sf 拖累收益。纯 A 收益最高但回撤最大。50/50 取两者之长——低波动时享受 A 的满仓，高波动时获得 B 的保护。不调仓自带"牛熊自动切换权重"。

### 等效单策略

A 和 B 持有同一批 ETF，只是仓位乘数不同。组合总仓位等效乘数：

```
combined_mult = (dd_mult + final_mult) / 2
              = (dd_mult + min(sf, dd_mult)) / 2
```

- **低波动（sf >= dd_mult）**：combined_mult = dd_mult，跟 A 一样满仓
- **高波动（sf < dd_mult）**：combined_mult = (dd_mult + sf) / 2，居于 A/B 之间

> 不需要跑两个账户。一个策略改乘数公式即可复现。

### 资产池（5 只 ETF）

| 名称 | 代码 | 角色 |
|------|------|------|
| 沪深300 | 510300 | A 股大盘 beta |
| 创业板 | 159915 | A 股成长/中小盘 |
| 纳指 | 513100 | 海外科技 beta |
| 黄金 | 518880 | 通胀/避险对冲 |
| 国债ETF | 511010 | 债券防御收益 |

### 六步决策链（每交易日执行）

**Step 1 — 趋势过滤（`trend_strength.py`）**

对每只 ETF 计算 `trend_strength = 年化收益率 / 年化波动率`（窗口 40 天）。`trend_strength > 0` 的 ETF 标记为 "active"，进入等权池。趋势为负的 ETF 被剔除。

> 因此组合持有的 ETF 数量在 0~5 之间动态变化。全部为负时空仓。

**Step 2 — 等权分配（`signal_generator.py`）**

active ETF 等权分配：`weight_i = 1 / N_active`。

**Step 3 — EWMA 波动率缩放（`target_volatility.py`）**

计算 active ETF 池的 EWMA 协方差矩阵（λ=0.94, 窗口 252 天）→ 组合预测波动率 → `scaling_factor = 0.08 / predicted_vol`。若 `|predicted - 0.08| ≤ 0.012` 则 sf=1.0（等比容忍带 = beta×15%）。

> sf 仅缩仓不加仓（被 `final_multiplier = min(sf, dd_mult)` 截断）。防御层最终乘数 `combined_mult = (dd_mult + min(sf, dd_mult)) / 2`。

**Step 4 — 股债相关性熔断（`correlation_circuit_breaker.py`）**

计算股票篮子（沪深300+创业板+纳指等权）与国债ETF 的 60 日滚动 Pearson 相关系数，经 5 日 SMA 平滑。**平滑值 > 0 则触发熔断** → 全部资金转入逆回购（年化 2%，零权益仓位）。

> 这是最强防线。Ablation 测试：关闭熔断 ΔSharpe -0.85。

**Step 5 — 回撤硬止损（`drawdown_stop.py`）**

| 回撤幅度 | 级别 | 仓位乘数 |
|---------|------|---------|
| < 8% | normal | 1.0 |
| 8% ~ 12% | warning | 1.0 |
| 12% ~ 18% | halve | 0.5 |
| ≥ 18% | liquidate | 0.0 |

**Step 6 — 资金路由（`portfolio_manager.py`）**

- 熔断触发 → positions = {}，全部 repo
- 正常 → 防御池 = total × defense_ratio × combined_mult → 按 target_weights 分配
  - `combined_mult = (dd_mult + final_mult) / 2 = (dd_mult + min(sf, dd_mult)) / 2`
- 进攻池（offense_pool）= total × (1 - defense_ratio) = 0（因 defense_ratio=1.00）→ 进 repo
- 剩余零钱 → repo

### 关键参数（8 个入 Hook 保护）

```
trend_window = 40        # 趋势计算窗口
ewma_lambda = 0.94       # EWMA 衰减因子 (RiskMetrics)
target_vol_beta = 0.08   # 防御层目标波动率（v184 边际换率最优）
target_vol_alpha = 0.20  # 进攻层目标波动率（搁置中）
defense_ratio = 1.00     # 防御资金占比（1.00=纯防御）
corr_threshold = 0.0     # 股债相关性熔断阈值
drawdown [0.08, 0.12, 0.18]  # 回撤三级阈值
vol_tolerance = 0.012    # Vol Target 容忍带（= beta×15%，等比缩放）
```

### 策略特点总结

- **A/B 组合**：50% 无 sf（满仓涨）+ 50% sf+0.08（缩仓防），不调仓，牛熊自动切换权重
- **动态持仓**：不是固定 5 只等权。趋势过滤剔除弱势 ETF，可能持有 0-5 只。
- **仓位缩放**：波动率 > 8% 时 B 端缩仓，A 端满仓，组合居于中间
- **极端避险**：股债同涨时全部清仓进逆回购。
- **硬回撤止损**：回撤 ≥ 18% 强制清仓。
- **进攻层零权重**：defense_ratio=1.00 意味着进攻层完全不参与。
- **理论地板**：~ -2.0 Sharpe（涨跌停 + T+1 + 18% 止损 + sf 半保护锁死尾部）

### 进攻层状态

已搁置。截面动量在 A 股行业 ETF 上不成立（Sharpe -0.15~0.23），时间序列动量改善至 0.69 但仍跑输纯防御 1.23。混合和条件性激活均跑输纯防御。当前防御/进攻比例硬编码为 100/0。

### 关键文件

| 文件 | 职责 |
|------|------|
| `src/signal_generator.py` | 六步编排，信号生成总入口 |
| `src/trend_strength.py` | Step 1: 趋势强度 + 确认 |
| `src/target_volatility.py` | Step 3: EWMA 协方差 + 波动率缩放 |
| `src/correlation_circuit_breaker.py` | Step 4: 股债相关性熔断 |
| `src/drawdown_stop.py` | Step 5: 回撤硬止损 |
| `src/portfolio_manager.py` | Step 6: 资金路由 |
| `src/backtest_engine.py` | 日循环回测引擎 + 参数扫描 |
| `src/etf_universe.py` | ETF 代码映射 |

### 执行延迟（execution_lag）— 新窗口必须了解

回测引擎支持两种执行模式：

| 参数 | 含义 | 现实可行性 | Sharpe | 总收益 | 回撤 |
|------|------|-----------|--------|--------|------|
| `execution_lag=0` | 当日收盘价算信号 → 当日收盘价成交 | **物理不可能**（同一瞬间既计算又成交） | ~1.19 | ~358% | -13.4% |
| `execution_lag=1` | T-1 日收盘价算信号 → T 日收盘价成交 | **现实可行**（盘后跑信号，次日执行） | ~1.02 | ~275% | -13.9% |

**ΔSharpe ≈ 0.17**：差值来自信号含当日收盘价带来的 1 日先知优势（趋势突破当日即可成交，延迟一日错过首日收益）。

**T+1 组合策略 Sharpe 1.108 仍远超三基准**（沪深300/创业板/纳指），策略未失效。T+0 的 1.19 是理论上限。

**当前默认**：`run_backtest()` 默认 `execution_lag=0`。`nav_chart.py` 和 `check_position.py` 使用 `execution_lag=1`。图表为 T+1 真实可执行数据。

**历史**：早期 Look-Ahead Bias 验证时 T+1 数据因现金泄漏 bug（repo_cash 取值错误）被压至 Sharpe 0.02。修复后 T+1 恢复至 1.02（commit `17aea9e` → `f88bcd6`）。此后未切换默认值，保持 T+0。


========== .claude/rules/4-firewall.md ==========
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


========== .claude/rules/5-infrastructure.md ==========
# 基建与环境约束

## 数据库

- 所有表结构变更必须通过 Migration 脚本执行，严禁直接 `ALTER TABLE`。
- 禁止在业务代码中拼接 SQL 字符串。
- [其他数据库约束]

## 第三方服务

- 调用外部 API 必须包裹在 `try-catch` 中。
- 必须统一使用 [指定的请求库/代理模块]。
- [其他第三方约束]

## 环境变量

- 新增环境变量必须同步在 `.env.example` 中记录。
- 禁止在非配置文件中硬编码凭证。
- [其他环境约束]


========== .claude/rules/6-quality.md ==========
# 质量保证与测试

## 回测输出要求（强制）@claude-override-approved

每次回测输出必须包含**同期三基准对比表**：

| 指标 | 策略 | 沪深300 | 创业板 | 纳指 |
|------|------|--------|--------|------|
| 总收益 | | | | |
| 年化 | | | | |
| 波动率 | | | | |
| Sharpe | | | | |
| 最大回撤 | | | | |

- 所有标的必须使用**同一时间段**（共同交易日起止一致），禁止跨期对比。
- 基准数据源：沪深300（`ak.stock_zh_index_daily`）、创业板（`399006`）、纳指（513100 ETF 或 `ak.index_us_stock_sina`）。
- 验收标准：策略 Sharpe > 全部三个基准才算跑赢，允许收益低于创业板但 Sharpe/回撤必须更优。

## 测试要求

- 核心逻辑修改需同步更新/新增测试用例。
- 测试框架：[Jest / PyTest / 其他]

## 构建要求

- 提交代码前，必须确保本地运行构建/类型检查零报错。
- 构建命令：`[npm run build / npx tsc --noEmit / 其他]`
- Lint 命令：`[eslint / ruff / 其他]`

## AI 质量门禁

- LLM 输出失败降级策略：[重试次数 + temperature 调整]
- 人工介入条件：[何时标记 status=review]


========== .claude/rules/7-git.md ==========
# Git 协作规范

## 提交规范

- 格式：`v{全局序号}-{YYYYMMDD}: 描述`
- 同日多推：`v{全局序号}-{YYYYMMDD}-{当日序号}: 描述`
- 示例：`v9-20260513: 新增用户认证模块` / `v9-20260513-1: 修复 token 刷新`

## 禁区

- 禁止 force push。
- 禁止 amend 已推送的 commit。
- 未获用户明确指令，禁止执行 `git push`。


========== .claude/rules/8-ui-design.md ==========
# UI 设计规范（前端项目）

## DESIGN.md 优先

涉及前端 UI 时，必须从 [awesome-design-md](https://github.com/Yejianheng/awesome-design-md) 选取一个 DESIGN.md 放入项目根目录（73 个品牌可选，如 ClickHouse / Linear / Airbnb）。

选定后 AI 自动按该色彩/字体/组件规范生成 UI，禁止脱离 DESIGN.md 自由发挥视觉风格。

## 前端环境

- 框架：[Next.js / Vite / 其他]
- 样式：[Tailwind / CSS Modules / 其他]
- 组件库：[有/无]


========== .claude/rules/9-ai-output.md ==========
# AI 输出质量门禁

## Plan → Test(红灯) → Code → Test(绿灯) → Verify 五段式（强制）

每次编码任务必须按此管线执行：

```
Plan（先想）→ Test(红灯) → Code（再写）→ Test(绿灯) → Verify（后验）
```

### Plan：写代码前必须校验方案

1. 分析代码库后，给出逐步实施计划
2. **强制**：运行 CLI 校验——`node d:/AI项目/000-guard-mcp/build/cli.js validate "<意图>" --files <文件列表>`
3. 校验通过 → 列出将修改/创建的每个文件 → 等用户认可
4. 校验不通过 → 根据报告调整方案，重试

### Test(红灯)：先写测试，必须全红

> 详见 `11-testing.md` "红灯检验（强制）"。此段是管线的硬锚点，不可跳过。

1. 列出测试场景（自然语言）→ 用户审
2. 写测试代码 → 跑 → 必须全红（主代码还没写，测试应全部失败）
3. 全绿 ⚠ → 测试有鬼，必须解释并重写

### Code：手术级修改

- 只改必须改的代码，不顺手重构无关部分。
- 最小实现：不添加未被要求的功能、抽象层、工具函数。
- 每步只输出一个文件，完成后等待用户"继续"。

### Test(绿灯)：主代码让测试变绿

1. 主代码写完后跑全部测试 → 必须全绿
2. 新测试绿 + 旧测试不红（旧测试是安全带——改搜索不能把登录搞崩）
3. 汇报：哪些红了变绿、哪些旧测试也过了

### Verify：代码写完后必须自检

- 运行构建/类型检查（`npx tsc --noEmit` / `npm run build`），零报错是提交前提。
- 检查是否引用了不存在的 API / 函数 / 导入路径（幻觉检测）。
- 检查是否有未使用的变量 / 导入 / 死代码。

## 反 Slop 清单（AI 代码自检）

以下模式出现即为红色信号，必须在提交前自行清除：

| 反模式 | 检测方法 |
|--------|---------|
| 过度注释显而易见逻辑 | `// 设置 x 为 1` 类注释直接删除 |
| 为不可能的情况做防御性处理 | 在 `try-catch` 里捕获了不会抛出的异常 |
| 过早抽象 | 为仅用一次的代码创建 helper/util |
| 给未改动代码补文档 | 仅改 5 行逻辑却带来了 20 行 docstring |
| PR 描述塞满文件引用 | 描述应解释"为什么"而非列出改了什么文件 |
| 硬编码值出现在非配置文件中 | grep 数字/字符串常量，应在 config 或 constants 中 |

## LLM 输出契约

所有调用 LLM 的模块必须定义结构化输出契约：

- 定义 JSON Schema（必填字段、类型、枚举值）。
- 解析失败 → temperature 降低 → 重试 1 次 → 仍失败标记人工介入。
- Prompt 是独立文件，存放在 `prompts/` 目录，禁止硬编码在业务代码中。
- 受控词汇表是独立配置文件，Prompt 和业务代码均引用它，禁止两处分别维护。

## 修改记录（强制）

> 详见 `2-coding-style.md` 同名章节。此处不再赘述。


========== .claude/rules/10-context.md ==========
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
  └── .claude/rules/（始终加载，按编号顺序）
        ├── 1-architecture.md
        ├── 2-coding-style.md
        ├── ...
        └── 12-project-log.md
  └── AGENTS.md / DESIGN.md（始终加载）
  └── docs/architecture/*.md（AI 在需要时自行读取）
```

- 根文件只做导航，不堆内容。
- 规则文件按关注点拆分，一个文件管一件事。
- 子目录可放独立 CLAUDE.md（如 `frontend/CLAUDE.md`），AI 在该目录工作时自动加载，避免前端规则污染后端任务。**子目录 CLAUDE.md 第一行必须是 `@../CLAUDE.md`**，确保根目录安全规则（保护区清单、Hook 配置、宪法）始终生效。

## 验证

新项目配置完成后，输入 `/memory` 确认所有规则文件出现在加载列表中。
准则：没列出 = 没生效。


========== .claude/rules/11-testing.md ==========
# 测试规范

## 核心原则

测试代码和主代码是两个东西，物理隔离，互不污染。

| | 测试代码 | 主代码 |
|------|---------|------|
| 存放位置 | `tests/` 目录 | `src/` 或业务目录 |
| 谁来写 | AI 先写 | AI 后写 |
| 什么时候变 | 需求变了才变 | 每次改代码都可能变 |
| 版本跟着谁 | 需求 | 实现 |
| 作用 | 验收标准（标尺） | 实际干活 |

## 红灯检验（强制）

**一个没红过的测试 = 假测试。**

```
AI 写完测试 → 立刻跑一次
  ↓
红了 ✅                     绿了 ❌
（主代码还没写，           （代码没写就绿了，
  测试正确检测到缺失）        测试有鬼，AI 必须解释并重写）
  ↓
AI 写主代码，让测试变绿
  ↓
全绿 → 汇报给用户审
```

用户只需要看汇报里有没有"第一次就绿"的测试。有就追问，没有就审场景。

## 工作流

```
1. 用户提需求
2. AI 列出测试场景（自然语言）→ 用户审
3. AI 写测试代码 → 跑 → 必须全红
4. AI 写主代码 → 跑 → 必须全绿
5. AI 汇报：哪些红了变绿、哪些旧测试也过了（安全带）
```

## 测试场景清单

AI 必须在写代码前列出：

```
基础路径：
  - 正常输入 → 正常输出

边界：
  - 空值 / 极限值 / 边界值

异常：
  - 网络挂了 / 服务端挂了 / 格式不对
```

用户审的是这些场景，不是代码。场景靠业务常识就能判断。

## 修改已有功能

```
需求要改 → 测试先改（新期望）
         → 主代码跟着改（新实现）
         → 跑全部测试
         → 新测试必须绿 + 旧测试不能红
```

旧测试是安全带——改搜索功能不能把登录搞崩。

## 测试文件命名

```
tests/
├── test_模块名.py        # 一个模块一个测试文件
├── test_xxx.py
└── ...
```

禁止：测试代码写在主代码文件里。禁止：主代码 import 测试文件。

## 步进执行纪律（强制）

多步骤任务必须逐步执行，禁止批量跑完再统一提交。

```
步骤 1 → 写测试 → 跑 → 全红 → 写代码 → 全绿 → git commit
  ↓
步骤 2 → 写测试 → 跑 → 全红 → 写代码 → 全绿 → git commit
  ↓
步骤 3 → ...
```

**为什么**：一步一提交确保每次提交都是可回退的原子增量。批量执行后统一提交 = 一个大黑箱，出了问题无法精确定位到哪一步引入的。

**每步提交前**：必须跑全量测试（新测试绿 + 旧测试不红），确认零回归。


========== .claude/rules/12-project-log.md ==========
# 项目日志规范

调试过程是项目知识资产的核心组成部分。每次排查结束后必须记录，防止经验流失、避免重复踩坑。

## 日志位置与命名

- 存放于项目根目录 `项目日志/`。
- 按日期命名：`yyyy-mm-dd.md`（如 `2026-05-17.md`）。
- 同一天多次调试追加到同一文件。

## 记录格式

每次调试/问题排查结束后，在当天日志文件中追加一条记录：

```markdown
## hh:mm — 问题简述

**现象**：<具体报错/异常行为，附关键堆栈或截图>

**排查路径**：
1. <假设A → 验证方法 → 成立/排除>
2. <假设B → 验证方法 → 成立/排除>

**根因**：<最终定位的原因，精确到文件+行号>

**修复**：<采用的方案，涉及文件列表>

**教训**：<下次如何避免，或可复用的排查技巧>
```

## 记录时机

- 任何需要超过 3 轮排查的问题，必须记录。
- 修复提交后立即记录，趁记忆新鲜。
- 最终未修好的问题，记录"阻塞点"和"后续待办"。

## AI 会话使用

- 新会话启动时，检查 `项目日志/` 最近 3 天记录，了解近期问题背景。
- 遇到同类现象，优先检索历史日志中的"教训"条目，避免重复排查。


========== protected-files.json ==========
{
  "_说明": "@claude-override-approved 架构防火墙保护区清单 — Hook PreToolUse 唯一事实源。新增文件只改此 JSON，4-firewall.md 自动同步引用。",
  "_自保护": "protected-files.json、protected-contracts.json、check_values.py 自身也在保护区内，防止攻击者先改清单再改核心文件。",
  "_Bash保护": "pre_bash.js 硬保护 .claude/hooks/ 和 .claude/.gate/ 目录，Bash 不可写/删。",
  "protected_files": [
    "CLAUDE.md",
    "方向性讨论.md",
    "测试报告.md",
    "新增测试方案.txt",
    "src/config.py",
    "src/signal_generator.py",
    "src/backtest_engine.py",
    "src/trend_strength.py",
    "src/target_volatility.py",
    "src/correlation_circuit_breaker.py",
    "src/drawdown_stop.py",
    "src/portfolio_manager.py",
    "src/recorder.py",
    "src/benchmark.py",
    ".claude/settings.json",
    "protected-files.json",
    "protected-contracts.json",
    "check_values.py"
  ]@claude-override-approved,
  "protected_dirs": [
    "prompts/",
    ".claude/rules/",
    ".claude/hooks/",
    "技术隐患/"
  ]
}


========== protected-contracts.json ==========
{
  "_说明": "内容级保护清单 — Hook PostToolUse 读取。values = 已确认的常量不许改；patterns = 禁止出现的写法；offense_pool = 进攻层候选池结构校验（方向性讨论硬约束）。",
  "values": [
    {"file": "src/signal_generator.py", "key": "trend_window", "value": "40", "reason": "7点全量扫描最优(30-50窄带唯一存活窗口)，样本外验证通过，跨时间段稳定"},
    {"file": "src/signal_generator.py", "key": "ewma_lambda", "value": "0.94", "reason": "RiskMetrics标准"},
    {"file": "src/signal_generator.py", "key": "target_vol_beta", "value": "0.08", "reason": "防御层8%目标波动（v184扫描最优，0.06→0.08边际换率1.05，前后半Sharpe均>0.85）"},
    {"file": "src/signal_generator.py", "key": "target_vol_alpha", "value": "0.20", "reason": "进攻层20%目标波动"},
    {"file": "src/signal_generator.py", "key": "defense_ratio", "value": "1.00", "reason": "纯防御最优，混合不如"},
    {"file": "src/drawdown_stop.py", "key": "dd_threshold_halve", "value": "0.08", "reason": "回撤≥8%减半仓位，三级阈值第一级"},
    {"file": "src/drawdown_stop.py", "key": "dd_threshold_warning", "value": "0.12", "reason": "回撤≥12%警告，三级阈值第二级"},
    {"file": "src/drawdown_stop.py", "key": "dd_threshold_liquidate", "value": "0.18", "reason": "回撤≥18%清仓，三级阈值第三级"},
    {"file": "src/signal_generator.py", "key": "corr_threshold", "value": "0.0", "reason": "相关性熔断阈值，ΔSharpe +0.85（最强模块），篡改可废掉最强防线"},
    {"file": "src/signal_generator.py", "key": "vol_tolerance", "value": "0.012", "reason": "Vol Target容忍带±1.2%（= beta×15%，等比缩放）"}
  ],
  "patterns": [
    {"pattern": "abs_dd < 0\\.0[0-7]\\b", "reason": "drawdown_stop: 禁止将halve阈值降到0.08以下（削弱风控）"},
    {"pattern": "abs_dd < 0\\.09\\b", "reason": "drawdown_stop: 禁止将阈值改为0.09（偏离已验证值）"},
    {"pattern": "abs_dd < 0\\.1[0-1]\\b", "reason": "drawdown_stop: 禁止将阈值改为0.10或0.11（偏离已验证值）"},
    {"pattern": "abs_dd < 0\\.1[3-7]\\b", "reason": "drawdown_stop: 禁止将阈值改为0.13-0.17（偏离已验证值）"},
    {"pattern": "abs_dd < 0\\.(19|[2-9]\\d)\\b", "reason": "drawdown_stop: 禁止将清仓阈值升至0.19以上（放大回撤风险）"}
  ],
  "offense_pool": {
    "file": "src/etf_universe.py",
    "_说明": "方向性讨论 — 进攻层三层架构硬约束：6 类固定风险源，每类 1-3 只候选 ETF，不与防御层重叠。",
    "required_sources": ["消费", "医药", "金融", "周期资源", "科技成长", "军工"],
    "min_candidates": 1,
    "max_candidates": 3,
    "defensive_var": "ETF_UNIVERSE"
  }
}


========== check_values.py ==========
"""
模块归属：工具层 / 内容级防篡改校验
职责：读取 protected-contracts.json，校验目标文件是否保留已确认常量、不含禁止模式
用法：python check_values.py <target_file> <contracts_json>
退出码：0=合规, 1=违规
依赖：protected-contracts.json
"""
import json
import re
import ast
import sys
import os


def load_contracts(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_values(target: str, contracts: dict) -> list[str]:
    basename = os.path.basename(target)
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    violations = []
    for entry in contracts.get("values", []):
        if os.path.basename(entry.get("file", "")) != basename:
            continue
        expected = entry.get("value", "")
        if expected not in content:
            violations.append(
                f"[常量篡改] {basename}: {entry.get('key', '?')}"
                f" 预期值 '{expected[:60]}' 丢失"
                f" — {entry.get('reason', '')[:80]}"
            )
    return violations


def check_patterns(target: str, contracts: dict) -> list[str]:
    basename = os.path.basename(target)
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    violations = []
    for entry in contracts.get("patterns", []):
        pattern = entry.get("pattern", "")
        try:
            if re.search(pattern, content):
                violations.append(
                    f"[禁止模式] {basename}: {pattern[:60]}"
                    f" — {entry.get('reason', '')[:80]}"
                )
        except re.error:
            violations.append(f"[模式错误] 正则无效: {pattern[:60]}")
    return violations


def check_offense_pool(target: str, contracts: dict) -> list[str]:
    """校验 src/etf_universe.py 的 OFFENSE_POOL 符合方向性讨论三层架构硬约束"""
    pool_cfg = contracts.get("offense_pool", {})
    target_file = pool_cfg.get("file", "")
    if os.path.basename(target) != os.path.basename(target_file):
        return []
    try:
        with open(target, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return ["[AST错误] 无法解析 etf_universe.py"]
    violations = []

    # 查找 OFFENSE_POOL 和 ETF_UNIVERSE 的 AST 节点
    offense_assign = None
    defense_assign = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "OFFENSE_POOL":
                    offense_assign = node
                if isinstance(t, ast.Name) and t.id == pool_cfg.get("defensive_var", "ETF_UNIVERSE"):
                    defense_assign = node

    if offense_assign is None:
        return ["[OFFENSE_POOL] 在 etf_universe.py 中未找到"]

    # 提取 OFFENSE_POOL 字典
    try:
        pool = ast.literal_eval(offense_assign.value)
    except (ValueError, TypeError):
        return ["[OFFENSE_POOL] 无法解析为静态字典，禁止使用变量拼接"]

    if not isinstance(pool, dict):
        return [f"[OFFENSE_POOL] 必须为 dict，实际为 {type(pool).__name__}"]

    required = pool_cfg.get("required_sources", [])
    min_c = pool_cfg.get("min_candidates", 1)
    max_c = pool_cfg.get("max_candidates", 3)

    # 检查风险源名称完全匹配
    actual_sources = set(pool.keys())
    expected_sources = set(required)
    if actual_sources != expected_sources:
        missing = expected_sources - actual_sources
        extra = actual_sources - expected_sources
        if missing:
            violations.append(f"[OFFENSE_POOL] 缺少风险源: {missing}")
        if extra:
            violations.append(f"[OFFENSE_POOL] 多余风险源: {extra}")

    # 检查每风险源结构
    all_offense_codes = set()
    for source_name in actual_sources:
        entry = pool.get(source_name, {})
        if not isinstance(entry, dict):
            violations.append(f"[OFFENSE_POOL] {source_name}: 值必须为 dict，实际 {type(entry).__name__}")
            continue
        code = entry.get("code", "")
        candidates = entry.get("candidates", [])
        if not isinstance(code, str) or not code.isdigit():
            violations.append(f"[OFFENSE_POOL] {source_name}: code 必须为纯数字字符串")
        if not isinstance(candidates, list):
            violations.append(f"[OFFENSE_POOL] {source_name}: candidates 必须为 list")
        else:
            n = len(candidates)
            if n < min_c or n > max_c:
                violations.append(f"[OFFENSE_POOL] {source_name}: candidates 数量 {n}，要求 {min_c}-{max_c}")
            for c in candidates:
                if isinstance(c, str) and c.isdigit():
                    all_offense_codes.add(c)

    # 检查与防御层重叠
    if defense_assign is not None:
        try:
            defense = ast.literal_eval(defense_assign.value)
            if isinstance(defense, dict):
                defense_codes = set(v for v in defense.values() if isinstance(v, str) and v.isdigit())
                overlap = all_offense_codes & defense_codes
                if overlap:
                    violations.append(f"[OFFENSE_POOL] 候选 ETF 代码与 ETF_UNIVERSE 重叠: {overlap}")
        except (ValueError, TypeError):
            pass

    return violations


def check_ast_constants(target: str, contracts: dict) -> list[str]:
    basename = os.path.basename(target)
    if not basename.endswith(".py"):
        return []
    try:
        with open(target, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return []
    const_assigns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    try:
                        val = ast.literal_eval(node.value)
                        const_assigns[t.id] = str(val)
                    except (ValueError, TypeError):
                        pass
    violations = []
    for entry in contracts.get("values", []):
        if os.path.basename(entry.get("file", "")) != basename:
            continue
        key = entry.get("key", "")
        var_name = key.split(".", 1)[0]
        if var_name in const_assigns:
            expected = entry.get("value", "")
            if expected not in const_assigns[var_name]:
                violations.append(
                    f"[AST篡改] {basename}:{var_name}"
                    f" 预期含'{expected}'"
                    f" — {entry.get('reason', '')[:80]}"
                )
    return violations


def main():
    if len(sys.argv) < 2:
        print("用法: python check_values.py <target_file> [contracts_json]")
        sys.exit(0)
    target = sys.argv[1]
    contracts_path = sys.argv[2] if len(sys.argv) > 2 else "protected-contracts.json"
    if not os.path.exists(target) or not os.path.exists(contracts_path):
        sys.exit(0)
    contracts = load_contracts(contracts_path)
    violations = []
    violations.extend(check_values(target, contracts))
    violations.extend(check_patterns(target, contracts))
    violations.extend(check_ast_constants(target, contracts))
    violations.extend(check_offense_pool(target, contracts))
    if violations:
        for v in violations:
            print(v)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()


========== src/__init__.py ==========
# [2026-05-26] 新增：src 包初始化


========== src/backtest_engine.py ==========
# [2026-05-30] 修复：parameter_scan scalar_metrics 排除 _recorder/benchmark_* 序列，避免 CSV 字段超限
# [2026-05-30] 修复：repo_cash 改为残差计算（现金守恒）+ 首日直接执行避免空仓期 — T+1 现金泄漏
# [2026-05-30] 新增：execution_lag 参数（0=当日成交，1=T+1成交）— Look-Ahead Bias 验证
# [2026-05-29] 修改：修正回测起始日（≥防御全部就位）+ 清盘恢复机制（repo 利息 + 状态追踪）
# [2026-05-29] 修改：run_backtest 日期从交集改为并集 + 动态 ETF 接入 + union_dates/get_available_etfs
# [2026-05-28] 修改：run_backtest 传递 defense_ratio；parameter_scan 支持 checkpoint 持久化
# [2026-05-27] 新增：回测引擎 — 日循环驱动 + 参数扫描入口

import csv
import itertools
import os
import numpy as np
import pandas as pd

from src.signal_generator import DEFENSE_NAMES, generate_signal
from src.portfolio_manager import allocate_capital
from src.recorder import init_recorder, record_daily, get_records_df
from src.benchmark import compute_benchmark, compute_single_benchmark

REPO_ANNUAL_RATE = 0.02


def union_dates(prices: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """返回所有 ETF 日期 index 的并集（非交集），按升序排列。"""
    date_sets = [set(df.index) for df in prices.values() if len(df) > 0]
    if not date_sets:
        return pd.DatetimeIndex([])
    all_dates = sorted(set.union(*date_sets))
    return pd.DatetimeIndex(all_dates)


def get_available_etfs(
    prices: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    min_history: int = 120,
) -> list[str]:
    """返回指定日期有数据且历史 ≥ min_history 的 ETF 名称列表。"""
    available = []
    for name, df in prices.items():
        if len(df) == 0:
            continue
        if date not in df.index:
            continue
        # 该 ETF 在 date 之前（含）的数据天数
        hist = (df.index <= date).sum()
        if hist >= min_history:
            available.append(name)
    return available


def run_backtest(
    prices: dict[str, pd.DataFrame],
    initial_capital: float = 1_000_000,
    params: dict | None = None,
    min_days: int = 120,
    execution_lag: int = 0,
    slippage_bps: float = 0.0,
    commission_rate: float = 0.0,
) -> dict:
    """运行完整回测。

    prices: {标的名: OHLCV DataFrame}，所有 DataFrame 需对齐到同一日期范围。
    initial_capital: 初始资金。
    params: 传给 generate_signal 的参数。
    min_days: 最少需要的数据天数（trend_window + corr_window + sma_window 缓冲）。
    execution_lag: 0=信号当日成交（当前），1=T+1成交（修正 Look-Ahead Bias）。
    slippage_bps: 双边滑点（bp），买入 close*(1+s/10000)，卖出 close*(1-s/10000)。
    commission_rate: 佣金费率（如 0.00025 = 万2.5），按换手额收取。

    返回绩效指标 dict，含 records_df 和 benchmark_nav。
    """
    # 1. 日期范围：所有标的 index 的并集（动态 ETF 接入）
    dates = union_dates(prices)

    # 1b. 截断到防御 ETF 全部就位之后
    defense_starts = []
    for name in DEFENSE_NAMES:
        if name in prices and len(prices[name]) > 0:
            defense_starts.append(prices[name].index.min())
    if defense_starts:
        defense_start = max(defense_starts)
        dates = dates[dates >= defense_start]

    if len(dates) <= min_days:
        raise ValueError(
            f"防御全就位后交易日不足：需要 > {min_days} 天，实际 {len(dates)} 天"
        )

    # 2. 初始状态
    nav = float(initial_capital)
    positions: dict[str, float] = {}
    repo_cash = float(initial_capital)
    recorder = init_recorder()
    # 清盘恢复状态追踪
    prev_drawdown_level = "normal"
    liquidation_nav: float | None = None
    # T+1 执行：存储上一日的 alloc，当日执行
    pending_alloc: dict | None = None

    nav_values = np.full(len(dates), float(initial_capital))
    nav_series = pd.Series(nav_values, index=dates, dtype=float)

    # 3. 日循环
    for t in range(min_days, len(dates)):
        today = dates[t]

        # repo 现金日利息（年化 2% / 252）
        repo_cash *= (1.0 + REPO_ANNUAL_RATE / 252.0)

        # 估值：昨日持仓按今日收盘价重估
        if positions:
            nav = sum(
                positions.get(name, 0.0) * prices[name].loc[today, "close"]
                for name in positions
                if name in prices and today in prices[name].index
            )
            nav += repo_cash

        # 更新 nav_series
        nav_series.iloc[t] = nav

        # 动态 ETF 接入：只传入当日有数据且满足 min_history 的 ETF
        available_names = get_available_etfs(prices, today, min_history=min_days)
        visible_prices = {name: prices[name].loc[:today] for name in available_names}
        signal = generate_signal(visible_prices, nav_series.iloc[: t + 1], params)
        defense_ratio = (params or {}).get("defense_ratio", 0.70)

        # 清盘恢复机制：持续监控 drawdown，回到 halve 阈值以下则恢复
        current_level = signal["drawdown_stop"]["level"]
        current_dd = signal["drawdown_stop"]["drawdown"]
        if prev_drawdown_level == "liquidate":
            if current_level != "liquidate":
                # drawdown 已自然回落到 halve/warning/normal → 恢复
                pass  # signal 已包含正确的 level/multiplier
            elif liquidation_nav is not None and current_dd > -0.12:
                # repo 利息让 nav 回升，drawdown 已 < 12% → 强制恢复 halve
                signal["drawdown_stop"]["level"] = "halve"
                signal["drawdown_stop"]["position_multiplier"] = 0.5
                signal["execution"]["final_multiplier"] = min(
                    signal["defense"]["scaling_factor"], 0.5
                )
                signal["execution"]["funds_to_repo"] = False
        if current_level == "liquidate" and prev_drawdown_level != "liquidate":
            liquidation_nav = nav
        prev_drawdown_level = current_level

        alloc = allocate_capital(signal, nav, defense_ratio=defense_ratio)

        # 调仓：目标金额 → 股数（含滑点 + 佣金）
        if execution_lag == 0:
            exec_day = today
            exec_alloc = alloc
        else:
            if pending_alloc is None:
                exec_alloc = alloc
            else:
                exec_alloc = pending_alloc
            pending_alloc = alloc
            exec_day = today

        prev_positions = positions.copy()
        positions = {}
        total_commission = 0.0
        if exec_alloc is not None:
            for name, target_dollar in exec_alloc["positions"].items():
                if name not in prices or exec_day not in prices[name].index:
                    continue
                price = prices[name].loc[exec_day, "close"]
                if price <= 0:
                    continue
                # 买卖方向 → 执行价
                current_value = prev_positions.get(name, 0.0) * price
                if target_dollar > current_value:
                    exec_price = price * (1.0 + slippage_bps / 10000.0)
                else:
                    exec_price = price * (1.0 - slippage_bps / 10000.0)
                positions[name] = target_dollar / exec_price
                # 佣金按换手额
                turnover = abs(target_dollar - current_value)
                total_commission += turnover * commission_rate
        # repo_cash 总是残差（现金守恒，扣除佣金）
        positions_value = sum(
            positions.get(name, 0.0) * prices[name].loc[exec_day, "close"]
            for name in positions
            if name in prices and exec_day in prices[name].index
        )
        repo_cash = nav - positions_value - total_commission

        # 日记录（含持仓明细，供 Golden Dataset 使用）
        pos_detail = {name: positions.get(name, 0.0) * prices[name].loc[exec_day, "close"]
                      for name in positions
                      if name in prices and exec_day in prices[name].index}
        record_daily(
            recorder, str(today.date()), nav, signal, alloc["positions"],
            positions_detail=pos_detail,
        )

    # 4. 绩效指标
    records_df = get_records_df(recorder)
    final_nav = float(records_df["nav"].iloc[-1]) if len(records_df) > 0 else float(initial_capital)
    total_return = (final_nav - initial_capital) / initial_capital

    # 日收益率 → 年化指标
    daily_nav = records_df["nav"].values
    daily_returns = np.diff(daily_nav) / daily_nav[:-1]
    n_trading_days = len(records_df)

    if n_trading_days >= 2:
        annual_return = (final_nav / initial_capital) ** (252 / n_trading_days) - 1
        annual_volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(252))
        sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0.0
    else:
        annual_return = 0.0
        annual_volatility = 0.0
        sharpe_ratio = 0.0

    # 回撤
    running_max = np.maximum.accumulate(daily_nav)
    drawdowns = (daily_nav - running_max) / running_max
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    calmar_ratio = annual_return / abs(max_drawdown) if abs(max_drawdown) > 0 else 0.0

    # 5. 基准
    benchmark_nav = compute_benchmark(prices)
    final_benchmark_nav = float(benchmark_nav.iloc[-1])
    benchmark_return = final_benchmark_nav - 1.0

    benchmark_300 = compute_single_benchmark(prices, "沪深300")
    benchmark_chinext = compute_single_benchmark(prices, "创业板")
    benchmark_nasdaq = compute_single_benchmark(prices, "纳指")

    return {
        "records_df": records_df,
        "_recorder": recorder,
        "benchmark_nav": benchmark_nav,
        "benchmark_300": benchmark_300,
        "benchmark_chinext": benchmark_chinext,
        "benchmark_nasdaq": benchmark_nasdaq,
        "final_nav": final_nav,
        "final_benchmark_nav": final_benchmark_nav,
        "total_return": total_return,
        "benchmark_return": benchmark_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar_ratio,
    }


def parameter_scan(
    prices: dict[str, pd.DataFrame],
    param_grid: dict[str, list],
    initial_capital: float = 1_000_000,
    min_days: int = 120,
    checkpoint_path: str | None = None,
) -> list[dict]:
    """参数扫描入口。

    param_grid: {"trend_window": [40, 60, 80], "target_vol_beta": [0.08, 0.10, 0.12], ...}
    checkpoint_path: 可选 CSV 路径，每完成一个组合追加写入，支持断点续扫。

    对每个参数组合调用 run_backtest，返回按 Sharpe 降序排列的结果列表。
    每个元素 = {**params_combo, **绩效指标}（不含 records_df / benchmark_nav）。
    """
    keys = list(param_grid.keys())
    value_lists = list(param_grid.values())
    combinations = list(itertools.product(*value_lists))

    # 断点续扫：读取已完成组合
    completed: set[tuple] = set()
    if checkpoint_path and os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed.add(tuple(row[k] for k in keys))

    results: list[dict] = []
    header_written = bool(completed)  # 已有文件 → 表头已存在
    for combo in combinations:
        params = dict(zip(keys, combo))
        # 跳过已完成组合
        if checkpoint_path:
            param_tuple = tuple(str(params[k]) for k in keys)
            if param_tuple in completed:
                continue

        bt = run_backtest(
            prices,
            initial_capital=initial_capital,
            params=params,
            min_days=min_days,
        )
        scalar_metrics = {
            k: v
            for k, v in bt.items()
            if k not in ("records_df", "benchmark_nav", "_recorder",
                         "benchmark_300", "benchmark_chinext", "benchmark_nasdaq")
        }
        results.append({**params, **scalar_metrics})

        # checkpoint 写入
        if checkpoint_path:
            row = {**{k: str(v) for k, v in params.items()}, **scalar_metrics}
            os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
            mode = "a" if header_written else "w"
            with open(checkpoint_path, mode, newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if not header_written:
                    writer.writeheader()
                    header_written = True
                writer.writerow(row)

    # 合并内存结果与 checkpoint 已有数据用于排序
    if checkpoint_path and os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", newline="") as f:
            all_rows = list(csv.DictReader(f))
        all_results = []
        for row in all_rows:
            entry = {}
            for k, v in row.items():
                try:
                    entry[k] = float(v)
                except (ValueError, TypeError):
                    entry[k] = v
            all_results.append(entry)
        all_results.sort(key=lambda r: float(r.get("sharpe_ratio", 0)), reverse=True)
        return all_results

    results.sort(key=lambda r: r["sharpe_ratio"], reverse=True)
    return results


========== src/benchmark.py ==========
# [2026-05-28] 新增：compute_single_benchmark — 单标的买入持有净值
# [2026-05-27] 新增：基准计算 — 买入持有基准组合净值曲线

import numpy as np
import pandas as pd

BENCHMARK_WEIGHTS = {
    "沪深300": 0.25,
    "创业板": 0.10,
    "纳指": 0.15,
    "黄金": 0.10,
    "国债ETF": 0.40,
}


def compute_benchmark(
    prices: dict[str, pd.DataFrame],
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """计算基准组合净值曲线（买入持有近似）。

    prices: {标的名: OHLCV DataFrame}，同 signal_generator 格式。
    weights: 基准权重，默认 BENCHMARK_WEIGHTS。
    返回: 基准净值 Series，index=DatetimeIndex，起始值=1.0。

    月度再平衡摩擦成本约 2-4bp/月，对长期回测结果影响 <0.5%，不做模拟。
    """
    w = weights if weights is not None else BENCHMARK_WEIGHTS

    # 只使用 prices 中实际存在的标的
    available = [name for name in w if name in prices]
    if not available:
        raise ValueError("prices 中无任何基准标的，无法计算基准净值")
    # 归一化可用权重
    total_w = sum(w[name] for name in available)
    active_weights = {name: w[name] / total_w for name in available}

    # 提取每个标的收盘价 → 日对数收益率
    daily_returns = pd.DataFrame({
        name: np.log(prices[name]["close"] / prices[name]["close"].shift(1))
        for name in available
    }).dropna()

    # 篮子日收益率 = Σ(weight_i × return_i)
    basket_return = sum(active_weights[name] * daily_returns[name] for name in available)

    # 累积净值（首日=1.0）
    first_date = prices[available[0]].index[0]
    nav_values = np.exp(basket_return.cumsum())
    nav = pd.Series(1.0, index=prices[list(w.keys())[0]].index, dtype=float)
    nav.loc[basket_return.index] = nav_values
    nav.name = "benchmark_nav"

    return nav


def compute_single_benchmark(
    prices: dict[str, pd.DataFrame],
    name: str,
) -> pd.Series | None:
    """计算单个标的的买入持有净值曲线（起始值 1.0）。

    prices: {标的名: OHLCV DataFrame}。
    name: 目标标的名称。
    返回: 净值 Series（index=DatetimeIndex, 起始=1.0），标的不存在返回 None。
    """
    if name not in prices:
        return None
    close = prices[name]["close"]
    nav = close / close.iloc[0]
    nav.name = f"benchmark_{name}"
    return nav


========== src/config.py ==========
# [2026-05-26] 新增：配置入口，读取环境变量
"""
模块归属：业务层 / 配置入口
职责：读取环境变量，提供全局配置常量
用法：from src.config import DASHSCOPE_API_KEY, DATA_DIR
"""
import os

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DATA_DIR = os.getenv("AKSHARE_DATA_DIR", "./data")


========== src/correlation_circuit_breaker.py ==========
# [2026-05-27] 新增：相关性熔断模块 — 股债滚动相关性 + SMA 熔断判断

import numpy as np
import pandas as pd


def stock_basket_returns(stock_prices: dict[str, pd.Series]) -> pd.Series:
    """
    计算股票篮子等权日对数收益率。
    stock_prices: {"沪深300": Series, "创业板": Series, "纳指": Series}，
      每个 Series index=日期 DatetimeIndex，values=close 价格。
    返回: 日对数收益率 Series（等权平均），index=日期。
    """
    # 每只 ETF 独立计算日对数收益率
    returns = {}
    for name, prices in stock_prices.items():
        returns[name] = np.log(prices / prices.shift(1))
    df = pd.DataFrame(returns)
    # 按日期横向等权平均（skipna：某 ETF 某日缺数据不拖垮整体）
    basket = df.mean(axis=1, skipna=True)
    return basket.dropna()


def rolling_correlation(series_a: pd.Series, series_b: pd.Series, window: int = 60) -> pd.Series:
    """
    滚动 Pearson 相关系数。
    series_a, series_b: 两个等长日收益率 Series，index 对齐。
    window: 滚动窗口（交易日数）。
    返回: 滚动相关系数 Series，index=日期，长度 < window 的位置为 NaN。
    """
    return series_a.rolling(window).corr(series_b)


def correlation_circuit_breaker(
    stock_prices: dict[str, pd.Series],
    bond_prices: pd.Series,
    corr_window: int = 60,
    sma_window: int = 5,
    threshold: float = 0.0,
) -> dict:
    """
    相关性熔断判断。
    返回: {
        "triggered": bool,          # 是否触发熔断
        "smoothed_corr": float,     # 最新平滑相关性
        "raw_corr": float,          # 最新原始 60 日相关性（调试用）
    }
    """
    # 1. 股票篮子日收益率
    stock_rets = stock_basket_returns(stock_prices)
    # 2. 债券日对数收益率
    bond_rets = np.log(bond_prices / bond_prices.shift(1)).dropna()
    # 日期对齐（中美交易日不同，取交集）
    common_idx = stock_rets.index.intersection(bond_rets.index)
    stock_aligned = stock_rets.loc[common_idx]
    bond_aligned = bond_rets.loc[common_idx]
    # 数据不足检查
    if len(common_idx) < corr_window + sma_window:
        return {"triggered": False, "smoothed_corr": 0.0, "raw_corr": 0.0}
    # 3. 滚动相关性
    roll_corr = rolling_correlation(stock_aligned, bond_aligned, corr_window)
    # 4. SMA 平滑
    smoothed = roll_corr.rolling(sma_window).mean()
    # 取最新值
    raw_corr = float(roll_corr.dropna().iloc[-1])
    smoothed_corr = float(smoothed.dropna().iloc[-1])
    # 5. 熔断判断
    triggered = smoothed_corr > threshold
    return {"triggered": triggered, "smoothed_corr": smoothed_corr, "raw_corr": raw_corr}


========== src/cross_sectional_momentum.py ==========
# [2026-05-27] 新增：截面动量模块 — momentum_score / cross_sectional_zscore / composite_momentum

import numpy as np
import pandas as pd


def momentum_score(prices: pd.DataFrame, window: int) -> pd.Series:
    """计算单窗口动量得分（对数收益率）。prices: 多资产收盘价。window: 回看窗口。"""
    result = {}
    for col in prices.columns:
        series = prices[col].dropna()
        if len(series) < window:
            result[col] = np.nan
        else:
            p_start = series.iloc[-window]
            p_end = series.iloc[-1]
            result[col] = np.log(p_end / p_start)
    return pd.Series(result, name=f"momentum_{window}d")


def cross_sectional_zscore(scores: pd.Series) -> pd.Series:
    """截面上 z-score 标准化。公式: (x - mean) / std(ddof=1)。NaN 输入 → NaN 输出。"""
    mean = scores.mean()
    std = scores.std(ddof=1)
    if std == 0 or pd.isna(std):
        result = scores.copy()
        result[~result.isna()] = 0.0
        return result
    return (scores - mean) / std


def composite_momentum(prices: pd.DataFrame, window_short: int = 20, window_long: int = 60) -> pd.Series:
    """双窗口截面动量合成。20 日 + 60 日 z-score 等权，按得分降序排列。"""
    s20 = momentum_score(prices, window_short)
    z20 = cross_sectional_zscore(s20)
    s60 = momentum_score(prices, window_long)
    z60 = cross_sectional_zscore(s60)
    composite = (z20 + z60) / 2
    composite = composite.dropna()
    if composite.empty:
        return pd.Series(dtype=float)
    return composite.sort_values(ascending=False)


========== src/data_pipeline.py ==========
# [2026-06-12] 新增：拆分/除权自动检测与修正（跌幅>50%触发，前复权）
# [2026-05-27] 新增：数据管线 — AKShare → Parquet
# [2026-05-27] 修改：save_to_parquet 自动创建目录（技术隐患 #3）
# [2026-05-27] 修改：fetch_etf_daily 加代理绕过 + 重试 + 异常分类

import os
import time
import pandas as pd
import akshare as ak
from src.logging_config import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # 秒，指数退避: 2s → 4s → 8s


def _patch_requests_no_proxy():
    """Monkey-patch requests.Session 强制不走系统代理（VPN 残留 127.0.0.1:7890）。"""
    import requests
    _original_init = requests.Session.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        self.trust_env = False

    requests.Session.__init__ = _patched_init


_patch_requests_no_proxy()


def fetch_etf_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """从 AKShare 拉取单只 ETF 日线，返回 pandas DataFrame。code: ETF 代码，如 "510300"."""
    for attempt in range(_MAX_RETRIES):
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )
        except Exception as e:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"AKShare 调用失败 (code={code}, attempt={attempt + 1}/{_MAX_RETRIES}): "
                f"{type(e).__name__}: {e}"
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(delay)
            else:
                logger.error(
                    f"AKShare 重试 {_MAX_RETRIES} 次后仍失败 (code={code})，返回空 DataFrame。"
                    f"可能原因：网络不可达 / 东方财富限流 / VPN 干扰。"
                )
                return pd.DataFrame()
            continue

        # AKShare 调用成功
        if df is None or df.empty:
            logger.info(f"AKShare 返回空数据 (code={code}, {start_date}~{end_date})，"
                        f"可能是非交易日区间")
            return pd.DataFrame()

        # 中文列名 → 英文
        df = df.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
            }
        )
        cols = ["date", "open", "high", "low", "close", "volume"]
        available = [c for c in cols if c in df.columns]
        df = df[available]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df = df.sort_index()

        # 拆分/除权检测：单日跌幅 > 50%，自动前复权修正
        close = df["close"]
        daily_ret = close.pct_change()
        split_mask = daily_ret < -0.50
        if split_mask.any():
            for split_date in daily_ret[split_mask].index:
                pre = close.loc[:split_date].iloc[-2]  # 拆前最后一天
                post = close.loc[split_date]            # 拆后第一天
                ratio = pre / post
                logger.warning(
                    f"检测到拆分 (code={code}, date={str(split_date)[:10]}): "
                    f"拆前 close={pre:.3f}, 拆后 close={post:.3f}, "
                    f"比例 1:{ratio:.2f}，自动前复权修正"
                )
                pre_mask = df.index < split_date
                for col in ["open", "high", "low", "close"]:
                    df.loc[pre_mask, col] = df.loc[pre_mask, col] / ratio

        return df

    return pd.DataFrame()


def save_to_parquet(df: pd.DataFrame, path: str) -> None:
    """写入 Parquet，保留 index。自动创建目标目录。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_parquet(path, index=True)


def load_from_parquet(path: str) -> pd.DataFrame:
    """从 Parquet 读取 DataFrame，含 index。"""
    return pd.read_parquet(path)


========== src/drawdown_stop.py ==========
# [2026-05-28] 修改：drawdown_stop 支持自定义阈值参数
# [2026-05-27] 新增：回撤硬止损模块 — compute_drawdown + drawdown_stop

import pandas as pd


def compute_drawdown(portfolio_values: pd.Series) -> pd.Series:
    """
    计算滚动回撤序列。
    portfolio_values: 组合净值 Series，index=日期 DatetimeIndex，按时间升序。
    返回: 回撤 Series（负小数，如 -0.12 表示回撤 12%），index 同输入。
    公式: (value - running_max) / running_max
    """
    running_max = portfolio_values.expanding().max()
    drawdown = (portfolio_values - running_max) / running_max
    drawdown.name = portfolio_values.name
    return drawdown


def drawdown_stop(drawdown: float, thresholds: list[tuple[float, float]] | None = None) -> dict:
    """
    根据当前回撤返回止损信号。
    drawdown: 当前回撤值（负小数，如 -0.12 表示回撤 12%）。
    thresholds: 可选自定义阈值 [(abs_dd_boundary, position_multiplier), ...]，
                如 [(0.08, 1.0), (0.12, 0.5), (0.18, 0.0)]。
                传入 None 时使用默认四级阈值。
    返回: {"level": ..., "position_multiplier": ...}
    """
    abs_dd = abs(drawdown)

    if thresholds is None:
        if abs_dd < 0.08:
            return {"level": "normal", "position_multiplier": 1.0}
        elif abs_dd < 0.12:
            return {"level": "warning", "position_multiplier": 1.0}
        elif abs_dd < 0.18:
            return {"level": "halve", "position_multiplier": 0.5}
        else:
            return {"level": "liquidate", "position_multiplier": 0.0}

    multiplier = 1.0
    for boundary, mult in thresholds:
        if abs_dd < boundary:
            multiplier = mult
            break
    else:
        multiplier = thresholds[-1][1]

    if multiplier >= 1.0:
        level = "normal"
    elif multiplier >= 0.5:
        level = "halve"
    else:
        level = "liquidate"

    return {"level": level, "position_multiplier": multiplier}


========== src/etf_universe.py ==========
# [2026-05-29] 重构：OFFENSE_POOL 主题去重——二级主题（芯片/半导体/酒/电池）排除，换宽基一级风险源 ETF
# [2026-05-29] 重构：OFFENSE_POOL 三层架构（风险源层 + ETF 候选层 + 代表 ETF），旧 10 只作废
# [2026-05-28] 新增：OFFENSE_POOL — 进攻层行业 ETF 候选池
# [2026-05-27] 新增：ETF 代码映射 — 防御层标的

# 防御层标的 → ETF 代码（上交所/深交所）
ETF_UNIVERSE = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

# 进攻层候选池 — 三层架构（方向性讨论 §二-进攻层-候选池）
# 风险源层：6 类经济驱动因子（架构级，长期不变）
# ETF 候选层：每类 1-3 只（实现层，ETF 退化可替换）
# 代表 ETF：每类 1 只（截面动量轮动使用，选流动性最佳者）
# 最终轮动：6 代表 ETF → 截面动量排名 → Top K 等权持仓
# 禁止：芯片/半导体/电池/AI/机器人/算力等二级主题 ETF 进入主轮动池
OFFENSE_POOL = {
    "消费": {
        "code": "159928",
        "name": "消费ETF汇添富",
        "candidates": [
            {"code": "159928", "name": "消费ETF汇添富"},
            {"code": "159865", "name": "养殖ETF国泰"},
        ],
    },
    "医药": {
        "code": "512010",
        "name": "医药ETF易方达",
        "candidates": [
            {"code": "512010", "name": "医药ETF易方达"},
            {"code": "512170", "name": "医疗ETF华宝"},
            {"code": "159992", "name": "创新药ETF银华"},
        ],
    },
    "金融": {
        "code": "512880",
        "name": "证券ETF国泰",
        "candidates": [
            {"code": "512880", "name": "证券ETF国泰"},
            {"code": "512000", "name": "券商ETF鹏华"},
            {"code": "512800", "name": "银行ETF鹏华"},
        ],
    },
    "周期资源": {
        "code": "512400",
        "name": "有色金属ETF南方",
        "candidates": [
            {"code": "512400", "name": "有色金属ETF南方"},
            {"code": "515220", "name": "煤炭ETF国泰"},
            {"code": "159870", "name": "化工ETF鹏华"},
        ],
    },
    "科技成长": {
        "code": "515000",
        "name": "科技ETF华夏",
        "candidates": [
            {"code": "515000", "name": "科技ETF华夏"},
            {"code": "515880", "name": "通信ETF国泰"},
        ],
    },
    "军工": {
        "code": "512660",
        "name": "军工ETF国泰",
        "candidates": [
            {"code": "512660", "name": "军工ETF国泰"},
            {"code": "512710", "name": "军工龙头ETF富国"},
            {"code": "512680", "name": "军工ETF广发"},
        ],
    },
}


def build_candidate_pool():
    """扫描全市场 ETF，返回行业候选池代码列表。
    网络不可达时返回空列表而非崩溃。
    """
    try:
        codes = []
        for entry in OFFENSE_POOL.values():
            codes.append(entry["code"])
        return codes
    except Exception:
        return []


========== src/logging_config.py ==========
# [2026-05-27] 新增：日志模块 — 统一 logger 配置

import logging
import os


def get_logger(name: str) -> logging.Logger:
    """返回统一配置的 logger。格式：时间 | 级别 | 名称 | 消息，输出到 stdout 和 logs/app.log"""
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    # stdout handler
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # file handler — 自动创建 logs/ 目录
    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("logs/app.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 禁止 propagate 到 root logger，避免重复输出
    logger.propagate = False

    return logger


========== src/portfolio_manager.py ==========
# [2026-06-12] 修复：sf 生效 — position_multiplier → final_multiplier（v184 验证通过）
# [2026-05-27] 新增：组合管理器 — 信号→仓位转换层，资金路由

def allocate_capital(
    signal: dict,
    total_capital: float,
    defense_ratio: float = 0.70,
) -> dict:
    """根据信号分配资金，输出每只标的的精确持仓金额。"""
    # 1. 基础资金池
    defense_pool = total_capital * defense_ratio
    offense_pool = total_capital * (1 - defense_ratio)

    # 2. 总仓位乘数 = min(sf, drawdown_multiplier)，已在 signal_generator 计算
    final_mult = signal["execution"]["final_multiplier"]
    defense_pool *= final_mult
    offense_pool *= final_mult

    # 3. 相关性熔断 → 全部资金进逆回购
    if signal["circuit_breaker"]["triggered"]:
        return {
            "date": signal["date"],
            "total_capital": total_capital,
            "positions": {},
            "defense_total": 0.0,
            "offense_total": 0.0,
            "repo_amount": total_capital,
            "exposure": 0.0,
            "exposure_ratio": 0.0,
        }

    positions: dict[str, float] = {}
    repo_amount = 0.0

    # 4. 防御层分配
    for name, weight in signal["defense"]["target_weights"].items():
        positions[name] = defense_pool * weight

    # 5. 进攻层分配（空仓 → 进逆回购，不回流防御层）
    offense_weights = signal["offense"]["target_weights"]
    if offense_weights:
        for name, weight in offense_weights.items():
            positions[name] = offense_pool * weight
    else:
        repo_amount += offense_pool

    # 6. 汇总（剩余零钱进逆回购）
    exposure = sum(positions.values())
    repo_amount += total_capital - exposure - repo_amount
    # 等价于 repo_amount = total_capital - exposure

    return {
        "date": signal["date"],
        "total_capital": total_capital,
        "positions": positions,
        "defense_total": defense_pool,
        "offense_total": offense_pool if offense_weights else 0.0,
        "repo_amount": repo_amount,
        "exposure": exposure,
        "exposure_ratio": exposure / total_capital,
    }


========== src/recorder.py ==========
# [2026-05-30] 修改：record_daily 新增 positions_detail 可选参数 — Golden Dataset
# [2026-05-30] 修改：日记录新增 scaling_factor / predicted_vol — Vol Target 触发审计
# [2026-05-27] 新增：Recorder — 回测日记录器，记录每天组合状态和信号

import pandas as pd


def init_recorder() -> dict:
    """初始化空记录器。"""
    return {"records": [], "positions_detail": []}


def record_daily(
    recorder: dict,
    date: str,
    nav: float,
    signal: dict,
    positions: dict[str, float],
    positions_detail: dict[str, float] | None = None,
) -> None:
    """追加一条日记录到 recorder["records"]（in-place 修改）。"""
    exposure = sum(positions.values())
    repo_amount = nav - exposure

    offense_top = [item["name"] for item in signal["offense"]["rankings"]]
    position_names = list(positions.keys())

    record = {
        "date": date,
        "nav": nav,
        "exposure": exposure,
        "repo_amount": repo_amount,
        "final_multiplier": signal["execution"]["final_multiplier"],
        "circuit_breaker_triggered": signal["circuit_breaker"]["triggered"],
        "drawdown_level": signal["drawdown_stop"]["level"],
        "drawdown": signal["drawdown_stop"]["drawdown"],
        "n_positions": len(position_names),
        "position_names": ";".join(position_names),
        "defense_active": ";".join(signal["defense"]["active"]),
        "offense_top": ";".join(offense_top),
        "scaling_factor": signal["defense"]["scaling_factor"],
        "predicted_vol": signal["defense"].get("predicted_vol", 0.0),
        "defense_count": len(signal["defense"]["active"]),
    }
    recorder["records"].append(record)

    if positions_detail is not None:
        detail = {"date": date}
        detail.update(positions_detail)
        recorder["positions_detail"].append(detail)


def get_records_df(recorder: dict) -> pd.DataFrame:
    """将 records 列表转为 DataFrame，date 列设为 DatetimeIndex。"""
    df = pd.DataFrame(recorder["records"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


========== src/signal_generator.py ==========
# [2026-06-12] 修改：target_vol_beta 0.10→0.08（v184 扫描最优）
# [2026-05-30] 修改：defense 返回新增 predicted_vol — Vol Target 触发审计
# [2026-05-29] 新增：vol_scaling_enabled 参数 — ablation 开关，关闭后固定等权不缩放
# [2026-05-29] 新增：trend_filter_enabled 参数 — ablation 开关，关闭后防御/进攻全仓等权
# [2026-05-29] 修改：进攻层切换为时间序列动量 — 取消截面排名，price>MA 即通过等权
# [2026-05-29] 新增：进攻层绝对趋势过滤 — price > MA(trend_window) 才进入截面排名
# [2026-05-28] 修改：trend_threshold/defense_ratio 参数化、进攻层波动率缩放、drawdown_stop 自定义阈值
# [2026-05-27] 新增：信号生成器 — Step 2-6 编排层，回测引擎与实盘执行共用入口

import numpy as np
import pandas as pd

from src.trend_strength import trend_strength, trend_confirmation
from src.target_volatility import ewma_covariance, portfolio_volatility, scaling_factor
from src.correlation_circuit_breaker import correlation_circuit_breaker
from src.drawdown_stop import compute_drawdown, drawdown_stop

DEFENSE_NAMES = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]

# [2026-05-29] 修改：trend_window 60→40（阶段2跨12年扫描最优）、defense_ratio 0.70→1.00（纯防御最优）
DEFAULT_PARAMS = {
    "trend_window": 40,
    "momentum_short": 20,
    "momentum_long": 60,
    "offense_top_k": 3,
    "target_vol_beta": 0.08,
    "target_vol_alpha": 0.20,
    "vol_tolerance": 0.012,  # = target_vol_beta * 15%，等比缩放
    "ewma_lambda": 0.94,
    "corr_window": 60,
    "corr_sma_window": 5,
    "corr_threshold": 0.0,
    "trend_threshold": 0.0,
    "trend_confirmation_method": "trend_strength",
    "trend_filter_enabled": True,
    "vol_scaling_enabled": True,
    "covariance_method": "ewma",
    "drawdown_thresholds": None,
    "defense_ratio": 1.00,
}


def generate_signal(
    prices: dict[str, pd.DataFrame],
    portfolio_value: pd.Series,
    params: dict | None = None,
) -> dict:
    """编排 Step 2-6 模块，生成当日调仓信号。"""
    p = {**DEFAULT_PARAMS, **(params or {})}

    # 1. 提取各资产收盘价
    close = {name: df["close"] for name, df in prices.items()}

    # 2. 防御层趋势强度
    trend_strengths = {}
    for name in DEFENSE_NAMES:
        if name in close:
            trend_strengths[name] = trend_strength(close[name], window=p["trend_window"])
    if p.get("trend_filter_enabled", True):
        method = p.get("trend_confirmation_method", "trend_strength")
        active = [
            name for name in DEFENSE_NAMES
            if name in close and trend_confirmation(close[name], method=method, window=p["trend_window"])
        ]
    else:
        active = [name for name in DEFENSE_NAMES if name in close]

    # 3. 防御层目标波动率（等权参考权重）
    predicted_vol = 0.0
    if active:
        active_close = pd.DataFrame({name: close[name] for name in active})
        raw_weights = np.ones(len(active)) / len(active)
        if p.get("vol_scaling_enabled", True):
            cov = ewma_covariance(active_close, lambda_=p["ewma_lambda"],
                                   method=p.get("covariance_method", "ewma"))
            predicted_vol = portfolio_volatility(raw_weights, cov)
            sf = scaling_factor(p["target_vol_beta"], predicted_vol, p["vol_tolerance"])
        else:
            sf = 1.0
        defense_target_weights = dict(zip(active, raw_weights))
    else:
        sf = 1.0
        defense_target_weights = {}

    # 4. 进攻层时间序列动量（price > MA → 通过，等权分配）
    offense_names = [name for name in close if name not in DEFENSE_NAMES]
    offense_weights = {}
    rankings = []
    if offense_names:
        if p.get("trend_filter_enabled", True):
            trend_filtered = []
            for name in offense_names:
                series = close[name]
                if len(series) >= p["trend_window"]:
                    ma = series.rolling(window=p["trend_window"]).mean()
                    if series.iloc[-1] > ma.iloc[-1]:
                        trend_filtered.append(name)
            if trend_filtered:
                offense_weights = {name: 1.0 / len(trend_filtered) for name in trend_filtered}
                rankings = [{"name": name} for name in trend_filtered]
        else:
            # 趋势过滤关闭 → 全仓等权
            offense_weights = {name: 1.0 / len(offense_names) for name in offense_names}
            rankings = [{"name": name} for name in offense_names]

    # 4b. 进攻层目标波动率缩放（与防御层对称）
    if offense_weights:
        if p.get("vol_scaling_enabled", True):
            selected_close = pd.DataFrame({name: close[name] for name in offense_weights})
            offense_w_array = np.array(list(offense_weights.values()))
            offense_cov = ewma_covariance(selected_close, lambda_=p["ewma_lambda"],
                                           method=p.get("covariance_method", "ewma"))
            offense_pred_vol = portfolio_volatility(offense_w_array, offense_cov)
            sf_alpha = scaling_factor(p["target_vol_alpha"], offense_pred_vol, p["vol_tolerance"])
            offense_weights = {name: w * sf_alpha for name, w in offense_weights.items()}

    # 5. 相关性熔断
    stock_basket = {name: close[name] for name in ["沪深300", "创业板", "纳指"] if name in close}
    bond_close = close.get("国债ETF")

    if stock_basket and bond_close is not None:
        cb = correlation_circuit_breaker(
            stock_basket, bond_close,
            corr_window=p["corr_window"],
            sma_window=p["corr_sma_window"],
            threshold=p["corr_threshold"],
        )
    else:
        cb = {"triggered": False, "smoothed_corr": 0.0}

    # 6. 回撤硬止损
    dd_series = compute_drawdown(portfolio_value)
    current_dd = float(dd_series.iloc[-1])
    ds = drawdown_stop(current_dd, thresholds=p.get("drawdown_thresholds"))

    # 7. execution 汇总
    if cb["triggered"]:
        final_multiplier = 0.0
        funds_to_repo = True
    else:
        final_multiplier = min(sf, ds["position_multiplier"])
        funds_to_repo = False

    return {
        "date": str(portfolio_value.index[-1].date()),
        "defense": {
            "trend_strengths": trend_strengths,
            "active": active,
            "target_weights": defense_target_weights,
            "scaling_factor": sf,
            "predicted_vol": predicted_vol,
        },
        "offense": {
            "rankings": rankings,
            "target_weights": offense_weights,
        },
        "circuit_breaker": {
            "triggered": cb["triggered"],
            "smoothed_corr": cb["smoothed_corr"],
        },
        "drawdown_stop": {
            "level": ds["level"],
            "position_multiplier": ds["position_multiplier"],
            "drawdown": current_dd,
        },
        "execution": {
            "final_multiplier": final_multiplier,
            "funds_to_repo": funds_to_repo,
        },
    }


========== src/target_volatility.py ==========
# [2026-05-29] 修改：ewma_covariance 新增 method 参数 — "ewma"/"historical" ablation 开关
# [2026-05-27] 新增：目标波动率模块 — EWMA 协方差矩阵 / 组合波动率 / 仓位缩放系数

import numpy as np
import pandas as pd


def ewma_covariance(prices: pd.DataFrame, lambda_: float = 0.94, window: int = 252,
                    method: str = "ewma") -> pd.DataFrame:
    """加权的年化协方差矩阵。prices: 多资产收盘价 DataFrame。lambda_: 衰减因子（仅 method="ewma"）。window: 历史窗口。method: "ewma" 或 "historical"。"""
    recent = prices.iloc[-window:]
    log_returns = np.log(recent / recent.shift(1)).dropna()
    T = len(log_returns)
    if T < 2:
        n = len(prices.columns)
        return pd.DataFrame(np.zeros((n, n)), index=prices.columns, columns=prices.columns)

    if method == "historical":
        weights = np.ones(T) / T
    else:
        # EWMA 权重：w_t = (1-λ) × λ^(T-1-t)，最新观测权重最大
        raw_weights = np.array([(1 - lambda_) * lambda_ ** (T - 1 - t) for t in range(T)])
        weights = raw_weights / raw_weights.sum()

    assets = prices.columns
    n = len(assets)
    rets = log_returns.values  # shape (T, n)

    # EWMA 加权均值
    means = np.average(rets, axis=0, weights=weights)

    # EWMA 加权协方差
    centered = rets - means  # (T, n)
    cov = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            cov[i, j] = np.sum(weights * centered[:, i] * centered[:, j])

    # 年化
    cov *= 252
    return pd.DataFrame(cov, index=assets, columns=assets)


def portfolio_volatility(weights: np.ndarray, cov_matrix: pd.DataFrame) -> float:
    """组合预测波动率 = sqrt(w^T Σ w)。"""
    w = np.asarray(weights, dtype=float)
    sigma = cov_matrix.values
    var = w @ sigma @ w
    return float(np.sqrt(max(var, 0.0)))


def scaling_factor(target_vol: float, predicted_vol: float, tolerance: float = 0.015) -> float:
    """仓位缩放系数，含容忍带。|predicted - target| ≤ tolerance → 1.0。predicted ≤ 0 → 1.0。"""
    if predicted_vol <= 0:
        return 1.0
    if abs(predicted_vol - target_vol) <= tolerance:
        return 1.0
    return target_vol / predicted_vol


========== src/trend_strength.py ==========
# [2026-05-27] 新增：趋势强度模块 — 年化收益率/年化波动率/趋势强度

import numpy as np
import pandas as pd


def annualized_return(prices: pd.Series, window: int = 60) -> float:
    """计算年化收益率。公式：ln(P_t / P_{t-N}) × (252 / window)"""
    if len(prices) < window:
        return 0.0
    recent = prices.iloc[-window:]
    p_start = recent.iloc[0]
    p_end = recent.iloc[-1]
    return np.log(p_end / p_start) * (252 / window)


def annualized_volatility(prices: pd.Series, window: int = 60) -> float:
    """计算年化波动率。公式：std(日对数收益率, ddof=1) × √252"""
    if len(prices) < 2:
        return 0.0
    if len(prices) > window:
        prices = prices.iloc[-window:]
    log_returns = np.log(prices / prices.shift(1)).dropna()
    if len(log_returns) < 2:
        return 0.0
    return float(np.std(log_returns, ddof=1) * np.sqrt(252))


def trend_strength(prices: pd.Series, window: int = 60) -> float:
    """计算趋势强度 = 年化收益率 / 年化波动率。数据不足或波动率为 0 返回 0.0。"""
    if len(prices) < window:
        return 0.0
    ann_ret = annualized_return(prices, window)
    ann_vol = annualized_volatility(prices, window)
    if ann_vol == 0.0:
        return 0.0
    return ann_ret / ann_vol


def trend_confirmation(prices: pd.Series, method: str = "trend_strength", window: int = 40) -> bool:
    """趋势确认机制开关——用指定方法判断是否处于上升趋势。

    method:
      - "trend_strength": 趋势强度 > 0（当前默认）
      - "price_ma": close > MA(window)
      - "dual_ma": MA(window//2) > MA(window)
      - "ma_slope": MA(window) 斜率 > 0（今日 > window 日前）
      - "breakout": close > 最高价(window)
    """
    if len(prices) < window:
        return False

    if method == "trend_strength":
        return trend_strength(prices, window) > 0.0

    elif method == "price_ma":
        ma = prices.rolling(window=window).mean()
        return bool(prices.iloc[-1] > ma.iloc[-1])

    elif method == "dual_ma":
        short_window = max(window // 2, 2)
        ma_short = prices.rolling(window=short_window).mean()
        ma_long = prices.rolling(window=window).mean()
        return bool(ma_short.iloc[-1] > ma_long.iloc[-1])

    elif method == "ma_slope":
        ma = prices.rolling(window=window).mean().dropna()
        if len(ma) < 2:
            return False
        return bool(ma.iloc[-1] > ma.iloc[0])

    elif method == "breakout":
        highest = prices.shift(1).rolling(window=window).max()
        return bool(prices.iloc[-1] > highest.iloc[-1])

    else:
        return trend_strength(prices, window) > 0.0


========== src/visualization.py ==========
# [2026-05-28] 新增：三基准线（沪深300/创业板/纳指）渲染到 NAV 图表
# [2026-05-27] 修复：回撤图去掉 reverse:true（负值应向下）
# [2026-05-27] 修复：benchmark 同起点归一化
# [2026-05-27] 修复：NAV 归一化 + benchmark 日期对齐 + Calmar 格式
# [2026-05-27] 新增：HTML 回测可视化报告 — Chart.js CDN + 内嵌 JSON

import json
import os
import numpy as np
import pandas as pd


def generate_report(result: dict, output_path: str = "./reports/backtest_report.html") -> str:
    """生成独立 HTML 回测可视化报告。result: run_backtest() 返回值。"""

    records_df = result.get("records_df", pd.DataFrame())
    benchmark_nav = result.get("benchmark_nav", pd.Series(dtype=float))

    has_data = len(records_df) > 0

    # 提取日期和净值序列
    if has_data:
        dates = [str(d.date()) for d in records_df.index]
        nav_raw = records_df["nav"].values
        # Bug1 修复：归一化到起点 1.0，与基准同比例尺
        nav_list = (nav_raw / nav_raw[0]).tolist()
        running_max = np.maximum.accumulate(nav_raw)
        drawdown_list = ((nav_raw - running_max) / running_max * 100).tolist()
        # Bug2 修复：benchmark 对齐到 records_df 日期范围，并归一化到同一起点
        bench_aligned = benchmark_nav.reindex(records_df.index)
        if bench_aligned.isna().any():
            bench_aligned = bench_aligned.ffill()
        bench_list = (bench_aligned / bench_aligned.iloc[0]).tolist()

        # 三基准对齐
        def _align_benchmark(series, idx):
            if series is None or len(series) == 0:
                return []
            aligned = series.reindex(idx)
            if aligned.isna().any():
                aligned = aligned.ffill()
            return (aligned / aligned.iloc[0]).tolist()

        bench_300_list = _align_benchmark(result.get("benchmark_300"), records_df.index)
        bench_chinext_list = _align_benchmark(result.get("benchmark_chinext"), records_df.index)
        bench_nasdaq_list = _align_benchmark(result.get("benchmark_nasdaq"), records_df.index)
    else:
        dates, nav_list, drawdown_list = [], [], []
        bench_list, bench_300_list, bench_chinext_list, bench_nasdaq_list = [], [], [], []

    # 标量指标
    def pct(v):
        return f"{v * 100:.2f}%" if isinstance(v, (int, float)) else v

    annual_return = result.get("annual_return", 0)
    calmar = result.get("calmar_ratio", 0)
    # Bug3 修复：年化收益为负时 Calmar 无参考意义，显示 N/A
    if annual_return < 0:
        calmar_str = "N/A"
    else:
        calmar_str = f"{calmar:.3f}"

    metrics = {
        "总收益": pct(result.get("total_return", 0)),
        "年化收益": pct(annual_return),
        "年化波动": pct(result.get("annual_volatility", 0)),
        "Sharpe": f"{result.get('sharpe_ratio', 0):.2f}",
        "最大回撤": pct(result.get("max_drawdown", 0)),
        "Calmar": calmar_str,
    }

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 动量轮动 — 回测报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js">
</script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f5f5f5; color: #333; padding: 24px; }}
h1 {{ text-align: center; margin-bottom: 24px; font-size: 22px; }}
.cards {{ display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; margin-bottom: 32px; }}
.card {{ background: #fff; border-radius: 8px; padding: 16px 24px; min-width: 140px;
         text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.card .value {{ font-size: 24px; font-weight: 700; color: #1a1a2e; }}
.card .label {{ font-size: 12px; color: #888; margin-top: 4px; }}
.chart-container {{ max-width: 960px; margin: 0 auto 32px; background: #fff;
                    border-radius: 8px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.chart-container h2 {{ font-size: 16px; margin-bottom: 12px; color: #555; }}
.empty-notice {{ text-align: center; color: #999; padding: 60px 0; }}
</style>
</head>
<body>
<h1>ETF 动量轮动 — 回测报告</h1>

<div class="cards">
{"".join(f'<div class="card"><div class="value">{v}</div><div class="label">{k}</div></div>' for k, v in metrics.items())}
</div>

{"<div class=\"empty-notice\">无回测数据</div>" if not has_data else f"""
<div class="chart-container">
  <h2>净值曲线（策略 vs 基准）</h2>
  <canvas id="navChart"></canvas>
</div>
<div class="chart-container">
  <h2>回撤曲线</h2>
  <canvas id="ddChart"></canvas>
</div>
"""}

<script>
const dates = {json.dumps(dates)};
const navData = {json.dumps(nav_list)};
const benchData = {json.dumps(bench_list)};
const bench300Data = {json.dumps(bench_300_list)};
const benchChinextData = {json.dumps(bench_chinext_list)};
const benchNasdaqData = {json.dumps(bench_nasdaq_list)};
const ddData = {json.dumps(drawdown_list)};

const blue = '#3366cc';
const orange = '#ff6600';
const red = '#dc3912';

if (dates.length > 0) {{
  // NAV 叠加图
  new Chart(document.getElementById('navChart'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{
          label: '策略净值',
          data: navData,
          borderColor: blue,
          backgroundColor: 'rgba(51,102,204,0.05)',
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.1,
        }},
        {{
          label: '基准净值(5ETF篮子)',
          data: benchData,
          borderColor: orange,
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
          tension: 0.1,
          borderDash: [5, 3],
        }},
        {{
          label: '沪深300',
          data: bench300Data,
          borderColor: '#ff6384',
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
          tension: 0.1,
          borderDash: [2, 2],
        }},
        {{
          label: '创业板',
          data: benchChinextData,
          borderColor: '#36a2eb',
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
          tension: 0.1,
          borderDash: [2, 2],
        }},
        {{
          label: '纳指',
          data: benchNasdaqData,
          borderColor: '#4bc0c0',
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
          tension: 0.1,
          borderDash: [2, 2],
        }},
      ],
    }},
    options: {{
      responsive: true,
      animation: false,
      plugins: {{ legend: {{ position: 'top' }} }},
      scales: {{
        x: {{ display: true, ticks: {{ maxTicksLimit: 12 }} }},
        y: {{ display: true, ticks: {{ callback: v => v.toFixed(2) }} }},
      }},
    }},
  }});

  // 回撤图
  new Chart(document.getElementById('ddChart'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: '回撤 (%)',
        data: ddData,
        borderColor: red,
        backgroundColor: 'rgba(220,57,18,0.08)',
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
        tension: 0.1,
      }}],
    }},
    options: {{
      responsive: true,
      animation: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ display: true, ticks: {{ maxTicksLimit: 12 }} }},
        y: {{
          display: true,
          ticks: {{ callback: v => v + '%' }},
          max: 0,
        }},
      }},
    }},
  }});
}}
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path

