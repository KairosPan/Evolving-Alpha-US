# K/M/p 种子知识库(Seed Knowledge Base)v1

> Harness 状态 `H=(p,G,K,M)` 的**种子**:从《轮回.docx》游资 playbook 抽取的结构化知识,供 Phase-0b 的注册表(registry)载入。**这是种子,不是定稿**——系统的 Refiner/协同学习会持续增删改它(自进化的核心)。

## 来源与生成
- 源:`轮回.docx`(文本 `/tmp/lunhui.txt`,1715 行)。
- 方式:6 路并行抽取器 + 覆盖度批判工作流(schema 校验、`source_lines` 行号可溯源)。
- 批判全文见 `_coverage_v1.md`(覆盖约 65%,已知缺口见下)。

## 文件
| 文件 | 内容 | 条数 | 对应蓝图 |
|---|---|---|---|
| `skills.json` | 技能 K:pattern 40 / failure_detector 13 / feature 4 | 57 | §6.3 |
| `memory.json` | 记忆 M:principle(口诀/禁忌)/ loss(失败教训+具名类比) | 21 | §6.5 |
| `doctrine.json` | doctrine p:分相位作战指导 + `immutable=true` 纪律红线 ×10 | 22 | §6.1 |
| `state_machine.json` | 情绪周期状态机(G_cycle 种子):7 相位 + transitions | 7 | §6.2 |

## 字段 schema(注册表契约)
- **skill**:`skill_id`(英文蛇形唯一)· `name_cn` · `type`(pattern/feature/failure_detector)· `applicable_regime[]` · `trigger` · `entry` · `exit_stop` · `taboo[]` · `depends_on[]` · `examples[]` · `source_lines[]` · `status`(active/incubating/dormant/retired)· `notes`。运行期再挂 `stats`(滚动胜率/盈亏比/oracle_gap,带 time×regime decay)。
- **memory**:`lesson_id` · `regime` · `pattern` · `outcome`(win/loss/principle)· `failure_signature` · `named_analog` · `lesson` · `source_lines[]`。
- **doctrine**:`section` · `regime`(相位或 all)· `immutable`(纪律红线=true,Refiner 不可改写)· `guidance` · `source_lines[]`。
- **state**:`phase` · `you_see[]` · `transitions[{to,signal}]` · `source_lines[]`。

## 规范化:相位词表(canonical regime vocabulary)
抽取出的 `applicable_regime`/`regime` 用词不统一(启动 vs 题材启动…)。**Phase-0b 的 loader 负责把变体归一到这 7 个 canonical 相位**(与 `state_machine.json` 的 `phase` 对齐):

`混沌冰点 · 修复启动 · 情绪回暖 · 题材启动 · 主升 · 震荡补涨 · 退潮`

归一映射(loader 实现):
`冰点|混沌|混沌期|情绪冰点 → 混沌冰点` · `修复|修复启动 → 修复启动` · `回暖|情绪回暖 → 情绪回暖` · `启动|题材启动|启动日 → 题材启动` · `主升|主升期 → 主升` · `震荡|补涨|震荡补涨|震荡期 → 震荡补涨` · `退潮|退潮期 → 退潮`。
另保留**生态标签**正交维度:`连板生态 · 容量生态 · 20cm生态 · 次新生态 · 超跌生态 · ST生态 · 北交生态`(不归入相位,单独索引)。
非相位的触发条件(如"情绪极值1500-""亏钱效应末期")**不应留在 regime 字段**——loader 归一时剔除并入 `trigger`。

## v1 已知缺口(交给 Refiner / 后续抽取补;不阻塞 Phase-0b)
**缺失模式**(待补 skills):上影线反包(1030-1040)· 新题材切换四类(82-94)· 多题材 A/B 线周末发酵(112-117)· 题材催化力度层级 国运>>政策>=产业>新闻>小作文(100-104)· 伴生(706-710)· 龙头 PK/卡位精细化(684-703)· 指数 K线/MACD 背离(1651-1684)· 生态周期识别规则(1693-1708)· 开拓者效应(1694-1697)· 新股/次新打法 5 类(1503-1580)· 转债隔夜预期(1591-1597)· 活口/半活口操作(82-86,273,308,663)· 竞价轮回预判关联首板(644-650)· 葵花宝典"尾盘次新跌停翘板"格(519-521)。
**精度问题**(待校订 source_lines):`anti_nuke_tail_blowup` 误并入中马传动退潮大长腿案例(972-976)· `dragon_second_wave` 跨技能重复引用 2进3 行号(1085-1087)· `fd_big_face_source` 遗漏定义行 376 · `w2s_weak_to_strong` 把"逆周期极致弱转强=顶级卖点"混入买入 notes(应独立为 detector)。
**状态机**:`题材启动` 缺 →退潮 直达路径;"唯一反弹"定位错误(属退潮内部,非震荡→主升)。
**命名**:`kht_*` 前缀含义不透明(建议 `gkbd_` 葵花宝典)· `w2s_strong_stronger` 名实不符(内容是"强更强",建议 `accel_strong_stronger`)。

> 这些缺口正是自进化系统该自己补的:Phase-1 后由 Refiner 从复盘 trajectory 增删改 K/M/p。v1 先求"骨架完整、可载入、可 CRUD"。
