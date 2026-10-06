# 交接简报：场所插件 × 分支统一 × demo

**日期：** 2026-10-05 · **写给：** 接手这项工作的下一个 agent · **来自：** 2026-10-01 至 10-04 的设计 session（Claude Code，session_01TrWt4ehRrR7e4TJ9XyFX2K）。
**一句话任务：** 把 Linqi 的几个分支和场所插件设计稿统一成一版，以做出 demo 为目标；决策和交互形式在 Claude Design 画布上。
**原则：** 这份简报只记事实、结论和待定项。机制以代码为准；意图以 `Kairos-Design.md` 为准；引用都带路径和行号，行号读自 `main @ a09f217`。
**状态（2026-10-05，operator 拍板）：** 这份简报的方案已被取代。operator 定了 demo 为主线：**现在站 C**（demo 以 `demo/` 子模块钉进树，PR #5；`face/` 与 `dsh/` 不调用它，两个产品互不接），**方向朝 A**（Kairos 经一行 MCP row 做 demo Account 的租客，在下一份 charter 里定）。§7 的 S0 被 PR #5 的落法取代：main + `feat/demo` + 子模块 bump 到 demo 的 main 头 `2d49602`；S1–S7 在下一份 charter 选定 A 或 B 之前不做。§3 的分支事实读自 10-03，10-05 的清理是：PR #1、#2、#3 关闭（paper-book 线暂存，分支保留为归档）、`feat/prediction-markets` 与 `feat/account-layer` 删除。§6 的 D1–D5、U1–U8 没有逐条答复；两种形状的五个冲突点（门在哪、谁签字、网络、每写一卡、账本）是下一份 charter 的议程。demo 当前的样子见 PR #5 与 demo 的 README。五个冲突点的完整记录、不冲突的部分和三种站法在 §12。

---

## 0. 交接物

| 物件 | 在哪 | 状态 |
|---|---|---|
| 设计画布（两页） | <https://claude.ai/artifact/2aXJoRzTzp5kDhMqCD8fLk> · 私有，operator 可从 Share 菜单分享 | v1 七块板（场所插件设计），v2 八块板（统一与 demo）。深底蓝金配色，照 Gravit 的 logo |
| 设计稿 v1 | `docs/superpowers/specs/2026-10-02-venue-plugins-design.md` · 分支 `docs/venue-plugins-design` · PR #4 | 已推送；**要改成 v2**，见 §7 S7 |
| 本简报 | `docs/superpowers/plans/2026-10-05-venue-plugins-unification-handoff.md` · 同一分支 | 已推送 |
| demo 的源码 | 子模块 `demo/` → `linqizhe07/buyer-agent-demo @ ae6a7ec`（`feat/demo` 分支）；同一内容也在本仓库 `origin/feat/prediction-markets`（无共同祖先，可 `git archive` 读） | 98 个测试全绿，见 §5 |
| 画布源文件 | 只在 artifact 里（`project/*.dc.html`、`project/canvas.json`）；用 Artifact 工具 `read` 取 | 这个 session 的 scratchpad 不会保留 |

## 1. 时间线：已经做了什么

1. **10-01 评估。** operator 的愿景：买方 agent 走进 Binance、Hyperliquid、Solana、NYSE 等卖方；agent 以 dsh 为底，要给它身份和钱包的 plugin。评估结论：接触一个场所 = 一行 dsh MCP row（`face/src/akshare.ts` 是模板）；plugin 不是一样东西而是三样：席位、身份、签名权；现 charter 明写"不是自动交易系统、不 hosted"，真钱与多用户要写下一份 charter。
2. **10-02 画布 v1 + 设计稿 v1。** 把 agent 当作人类投资者：身份、钱包、席位、账本、授权书五样东西各落到树上一个位置。manifest allow-list 合同；写路径；四个场所对照；五个决定 D1–D5。设计稿落成并推到 PR #4。
3. **10-03 配色** 改成 logo 的深底蓝金。
4. **10-03 比较 demo。** Linqi 的 `feat/demo` 挂了 buyer-agent-demo 子模块。它几乎就是设计稿的可运行版本，且多了授权书层、卡上参数哈希、哈希链账本和对账、钱包骨架与组合钱包。我跑了它的测试：10 个文件 98 个用例全绿，e2e 真的 spawn 完整 demo 跑完十一个场景。比较时发现**设计稿钉在 main，没看见 Linqi 九月的三条分支**（agentpay、Gate 3、paper book）。
5. **10-03/04 画布 v2。** operator 把 session 任务定为"统一 Linqi 的分支和设计稿，以 demo 为目标"。v2 八块板：盘点、统一地图、U1–U8 决定、十场景脚本、三张线框、施工顺序。
6. **待定。** D1–D5 与 U1–U8 都还没有 operator 的答复。

## 2. 这棵树的硬约束（接手前必读）

- 读 `Kairos-Design.md` §1–§2、§4 写地图、§5 债务、§6 规则、§7.3 不建的东西、§8 触发表；`AGENTS.md`；`CLAUDE.md` 的 Gotchas。
- **P1 wide hands, no self-keys**：agent 对自己运行时的权限为零，靠放置执行（`Kairos-Design.md:54`）。
- **Rule 2**：在能跑任意代码的那一层之下执行，否则承认门只是 prose。**Rule 4**：没演练过的 guard 视为坏的。**Rule 8**：内容没来之前别选 substrate。
- **§7.3**：no bespoke harness（dsh 是 runtime，face 只是宿主）、no hosted face、no multi-tenant / cryptographic / kernel-level machinery。
- **§8 触发**：在真实 harness home 里打开 `ALPACA_KIT_ENABLE_ORDERS` → 先做 D3（人工半场 order drill，`DEVELOPMENT.md` §10 第 1 项）；真钱意图 → §4 两道门、D1、D3、D8、换钥匙；第二个人或任何 hosted 部署 → "this charter is the wrong document; write the next one"（`Kairos-Design.md:292`）。
- **残差**（`DEVELOPMENT.md` §9）：R1 两道门只守工具面，`.env.alpaca` 在仓库根可被 shell 读；R2 Gate 2 是门不是容器；R3a 审批答复可从 workspace 经 loopback 伪造。
- **永不**：改 `data/pit/`、`bots/` 下任何东西、`docs/research/`；在真实 home 里打开 order flag；把 key 放进仓库根的 `.env.*` 当作新场所的身份。

## 3. 分支事实（2026-10-03 读自 origin）

| 分支 | 作者 · 日期 | 领先 main | 内容 | 关系 | 统一后 |
|---|---|---|---|---|---|
| `main @ a09f217` | KairosPan · 09-25 | 基线 | 跨市场 watchlist、AKShare row、Gravit 落地页三提交 | 落地页三提交不在 Linqi 线 | 保留 |
| `develop @ 4395536` | — | 落后 3 | 旧基线 | 三条 feat 线从它长出 | 统一落点；先快进到 main |
| `feat/payment` | linqizhe07 · 09-17..19 | 4 | agentpay 子模块（`payment/`，x402）、kairos-intro 页 | 被 bought-data 包含 | 不单独合 |
| `feat/bought-data` | linqizhe07 · 09-21 | 19 | `2026-09-20-agent-wallet-design.md`、`face/src/budgets.ts`（Gate 3）、`face/src/wallet.ts`、`/wallet`、`wallet_pay save_to`、`alpaca_kit/feeds/massive_files.py`、bought-data skill | 被 paper-book 包含 | 不单独合 |
| `feat/paper-book` | linqizhe07 · 09-22 | 24 | `alpaca_kit/paper/`（策略的模拟账户，放 workspace 之外）、`2026-09-22-paper-book-design.md`；charter 加 D16、D17；R-W1–R-W8、R-P1–R-P6 | 包含上两条；72 文件约 1.2 万行 | **统一基线** |
| `feat/demo` | linqizhe07 · 10-03 | 1 | 子模块 `demo/` + CLAUDE.md 一行 | 与 main 无冲突 | 子模块保留 |
| `feat/prediction-markets` | linqizhe07 · 10-03 | 无共同祖先 | buyer-agent-demo 自己的五个提交 | = 子模块指向的提交 | **不合**；删掉或改名为镜像 |
| `docs/venue-plugins-design` | 本 session · 10-02 | 1 | 设计稿 v1，PR #4 | 钉在 main | 改 v2 后 rebase 到统一基线 |

**冲突事实**（`git merge-tree --write-tree`）：main + paper-book → `face/README.md`、`face/scripts/build-static.mjs`；paper-book + demo → 再加 `.gitmodules`（add/add）、`CLAUDE.md`；main + demo → 无。

## 4. 设计结论（画布 v1 + 设计稿 v1 的核心）

- **五样东西 → 树上的位置。** 身份 → dsh credential seam（`$DSH_HOME/.credentials.yaml`，按操作解析，spawn 环境 scrub；survey `docs/research/2026-08-22-deepseek-harness-dsh-survey.md:490,538,668-669`）。钱包 → agent 读不到的签名器。席位 → 每个场所一行 `dsh-mcp-client` row，带 manifest。账本 → `/account` 多场所只读汇总。授权书 → Gate 2 的卡在模型之上，场所侧 policy 在代码之下。
- **manifest 必须是 allow-list。** 今天的 Gate 2 只认 `ORDER_RAW_NAMES = ["place_order","cancel_order"]`（`face/src/orders.ts:33`）和描述里的 `(operator-gated)` 标记（`:38, :239`）。boot 审计只拒绝"带标记但名字不认识"的工具（`:270-278`，`boot.ts:364`）。第三方 server 的 `createOrder` 两样都没有 → **静默不受 gate**，face 照常启动。所以每个 row 的每个工具都要被 manifest 分类，未分类拒绝整行；write 名字在 mount 时注册进 Gate 2。
- **写路径（吸收 demo 后）：** intent → manifest 分类 → 授权书 → 审批卡 → 一次性 grant → 席位 / 签名器 → 场所 → 账本。
- **四个场所不同种。** NYSE 经 Alpaca，已建好，paper 账户本来就能交易加密现货；Binance key 分权限、关提币、绑 IP，CCXT 官方 MCP server 本地 stdio；Hyperliquid 主账户 approve 的 agent wallet 能下单不能提币、`validUntil` 场所侧强制；Solana 裸 keypair 即全权，要策略签名器，charter §7.3 把它推到下一份 charter。
- **PIT 不泛化。** 场所读是无 guard 的实时读，和 AKShare 同级（`AGENTS.md:12-18`），永不作 replay 证据；每个场所包自带读模型，只共享 guard 与 gate 合同。
- **Alpaca 的第一处美股假设：** MCP 的 `place_order` 不暴露 `time_in_force`（`alpaca_kit/mcp/tools.py:299-301`），库默认 `day`（`alpaca_kit/account.py:85-89`），加密单只收 gtc/ioc → 第一笔即被 422 拒。demo 的解法更好：manifest 的 `constraints` 改写参数并**再问一次卡**。

## 5. demo 的事实（buyer-agent-demo @ ae6a7ec）

- 独立 Node 22 / TypeScript 进程；四个场所全是本地模拟器（端口 4701–4704），策略签名器 4705，模拟钱包 4706，控制台 4800，钱包骨架 4810，组合钱包 4820；`$BUYER_HOME` 默认 `~/.buyer-agent-demo/`。
- `manifests/*.json`：`identity.ref`、`identity.kind`、`signer.kind`（in-plugin / external-policy-signer / none）、`tools.{read,write,deny}`、`card`、`sizing`、`constraints`、`venueErrors`。`src/contract/audit.ts` 四条规则：未分类整包拒绝；清单漂移拒绝；read 工具自称会写拒绝；write 全名进 gate allow-list。
- `src/agent/gate.ts` 照 Gate 2 的 decision / grant / guard 三件套，allow-list 从 manifest 长出。`src/agent/mandates.ts` 在卡之前检查用途、总额、单笔上限、品种、收款人、频率、有效期。`src/agent/agent.ts` 的 `execute()` 是整条写路径，每个拒绝是结构化的 `{ok:false, code, layer}`。`src/contract/env-scrub.ts`：子进程只带 `BUYER_CRED_REF`，按名字 scrub KEY/SECRET/TOKEN/PASSWORD。`src/agent/ledger.ts`：JSONL 哈希链，拒绝也是一行。
- 十一个场景：挂载；rogue 插件（藏 `sweepToColdWallet`）拒绝；跨场所读无卡；注资；Alpaca tif 改写再问；Hyperliquid agent key 过期；Binance 第三方 server 只配清单；Solana 签名器拒签；注入被授权书拦；提回与对账；总结。
- 它自己承认的边界：模拟器不是场所；门不是围栏（R1、R3a 它自己演了）；脚本 agent 不代表 LLM；钱包服务信任同一进程的卡结论。
- 它的 `回灌 Kairos` 表（README）把每块指回 face 接缝：manifests+mount → `akshare.ts` 模式；audit → `orders.ts` 的 `auditOrderTools` + `boot.ts` 拒绝启动；gate → `orders.ts` 三件套；mandates → `budgets.ts` Gate 3 与 agentpay 的 `mandateRejection`；env-scrub → dsh 的 `.credentials.yaml`；ledger → agentpay 的 JSONL 账本；场景 ✓/✗ → `face/README.md` 的 drill。
- 本机验证：`npm install && npm test` → 10 files, 98 tests passed, e2e 11 场景按序完成, exit 0。
- **没接进 dsh / face**：自带 MCP client、门、home；模拟器在 runner 进程内起（`src/runner/setup.ts`），没有单独的 serve 脚本。

## 6. 待拍板的决定（都还没答）

**D1–D5（画布 v1 第 07 板 / 设计稿 §11）**：D1 托管模式（建议 A 非托管）；D2 代码形态（建议 A 每场所一包）；D3 统一账本（原建议 A `/account` 只读汇总，比较 demo 后见 U4）；D4 第一个新场所（建议 A Hyperliquid testnet，C Alpaca 加密并行）；D5 真钱前谁回答卡（建议 A 带外设备）。

**U1–U8（画布 v2 第 13 板）**：

| # | 决定 | 建议 | 为什么 |
|---|---|---|---|
| U1 | 基线分支 | A：`feat/paper-book` 为基线，合 main 三个落地页提交，落到 `develop` | Linqi 线包含 Gate 3、D16、agentpay；cherry-pick 会丢历史 |
| U2 | 门的数量 | A：一道，Gate 2 留在 face，manifest 喂名字；demo 的 gate 退役 | §7.3 no bespoke harness；两道门两个进程就是 charter 拒绝的东西 |
| U3 | 授权书层 | A：移植 demo 的 `mandates.ts` 为 face 的 pre-execute 监听，文件放 `$DSH_HOME/face/mandates/`，不动 agentpay | 注入那一场靠它；B（泛化 Gate 3）留下一版 |
| U4 | 账本 | A：这版用 demo 的形状放 `$DSH_HOME/face/venues/ledger.jsonl`，`/account` 读它 | 三本账都是 JSONL 哈希链，行格式统一留下一版 |
| U5 | demo 界面 | A：face 的聊天卡、`/account`、插件面板 | control room 退役；线框在第 15–17 板 |
| U6 | demo 的 agent | A：Kairos 真 LLM；十一个脚本场景改成 operator 提示词清单；脚本版留作无头 drill | |
| U7 | 场所 | A：四个本地模拟器原样跑；不碰 testnet | testnet 要先过 spike S3 |
| U8 | 钱包与组合钱包 | A：不接 :4810 与 :4820；agentpay 的 `/wallet` 保留 | 会把下一份 charter 的题目提前拉进这版 |

**U2 与 U3 是这版的核心**，改起来要重做 face 接缝；其余事后可改。

## 7. 施工计划 S0–S7（画布 v2 第 18 板）

完成的定义：第 14 板的十个场景在 face 里由 Kairos 跑通；自动半场在 `FACE_SMOKE=1` 下全绿；手动半场有 operator 记的 PASS 行；`/account` 对账 4/4。S1、S3、S4 互相独立可并行；S2 等 S1 的 row 形状；S6 最后。分工只是建议。

| 步 | 做什么 | 复用 / 新写 | 建议分工 |
|---|---|---|---|
| S0 git | develop 快进到 main → 合 `feat/paper-book`（解 README、build-static）→ 合 `feat/demo`（解 .gitmodules、CLAUDE.md）→ 设计稿 v2 rebase → 一次 PR 回 main；删掉或改名 `feat/prediction-markets` | 无 | Linqi |
| S1 face | `face/src/venues.ts`：读 manifest、mount 时按 demo 的四条规则审计、生成 `dsh-mcp-client` rows（照 `akshare.ts:13-36`，在 `boot.ts:177-179` 的 `marketPatches` 旁组合）、把 write 名字喂给 `orders.ts`（`ORDER_RAW_NAMES` 改成 boot 时填的集合）；未分类的 row 让 face 拒绝启动 | 移植 demo `src/contract/{manifest,audit}.ts`；manifest 加 `network`、`pit`、`ledger`；`network: mainnet` 一律拒绝 | 我 |
| S2 demo | demo 加 `venues:serve` 脚本单独起四个模拟器与签名器；face 以 rows 挂五个 seat server（`node --import tsx demo/src/plugins/<v>/server.ts`），env 只带 `BUYER_HOME`、`BUYER_VENUE`、`BUYER_VENUE_URL`、一条 `BUYER_CRED_REF` | 复用 demo `src/venues/`、`src/plugins/` | Linqi |
| S3 face | `face/src/mandates.ts`：pre-execute 监听排在 Gate 2 之前；mandate 文件 `$DSH_HOME/face/mandates/<venue>.json`；卡的 reason 行显示剩余额度与参数哈希 | 移植 demo `src/agent/mandates.ts`、`sizing.ts` | 我 |
| S4 face | `/account` 多场所只读汇总（`face/src/data.ts`、producer）；venue ledger 哈希链；对账四家；拒绝也是一行 | 移植 `src/agent/ledger.ts`、`reconcile.ts` | 我 |
| S5 dsh | `AGENTS.md` 一段（场所工具是无 PIT 的实时读）；`dsh/skills/mechanics` 一段；十个场景的 operator 提示词清单 | 新写 | 我 |
| S6 drill | 十个场景自动半场进 `FACE_SMOKE`；rogue 插件拒绝启动；手动半场 PASS 行写进 `face/README.md` | 改自 demo `test/e2e.test.ts`、`src/runner/beats/` | 共同 |
| S7 docs | 设计稿 v2 替换 PR #4 的 v1（吸收 Gate 3、demo、U 决定）；charter 新行；`CLAUDE.md` 地图；`DEVELOPMENT.md` §10 条目 | 新写 | 我 |

**不触发 D3**：这版的 Alpaca 是 demo 的模拟器席位，不是 `alpaca_kit` 的真 paper；真实 home 里 `ALPACA_KIT_ENABLE_ORDERS` 仍不开。真 paper 上的第一笔加密单是 demo 之后的下一步，先过 §10 第 1 项。

## 8. 技术要点与陷阱

- Gate 2 的两个锚：raw name 后缀匹配（`orders.ts:62`）与 `(operator-gated)` 标记（`:239-245`）；`hasApprovalGrant` 只认日志里这个 callId 这个工具名的 `allowed-once` 对（`:196`）；guard 在每次 allow 上单调评估（`boot.ts:332-356`）。
- registry 异步填充：dsh-mcp-client 首连失败也会 activate，boot 审计可能对着没填满的 registry（`orders.ts:224-227`）→ S1 的审计要在 row 报出工具表时做，不能只在 boot 做一次（spike S2）。
- bot 的 allow mask 已支持 `mcp__*__<raw>`（`face/plugins/bot.js:56-75`）；mask 是可见性不是权限（D12）。
- face 的 overlay 组合在最后并静默覆盖 operator patch 的同名 row（`face/README.md` "The profile"）。
- `describeOrder` 把模型可控文本截到 40 字符（`orders.ts`），新卡的 reason 行要守同样的边界。
- 凭据引用能否进 `dsh-mcp-client` row 的 `env` 由 seam 解析，还是只能由 operator patch 插值字面值：没验证（spike S1）；退路是 `$DSH_HOME/.env` 插值，仍在 workspace 之外。
- demo 的席位子进程靠 `BUYER_CRED_REF` 自己从 `$BUYER_HOME/credentials/<ref>.json` 读值；放进 face 时 `BUYER_HOME` 指到 `$DSH_HOME/face/venues/home`。
- 同一用户的 shell 能读别的进程的 `/proc/<pid>/environ`，放置挡不住；场所侧的不可提币与过期才是下层（设计稿 §14 R-V1）。
- 第三方 MCP server 是拿着凭据的第三方代码：按 commit 钉版本，像 AKShare 那样（`face/README.md` "AKShare MCP"）。

## 9. Spikes（开工前先验）

S1 凭据引用进 MCP row 的 env；S2 row 工具表何时可审计、拒绝后能否卸载；S3 Hyperliquid testnet 的 agent approval 流程（只在 U7-B 时需要）；S4 CCXT MCP 的 write 工具名与交易开关（只在接真 CCXT 时需要，这版用 demo 的模拟 server）；S5 Alpaca paper 加密单 `day` 被拒、`gtc` 成交（demo 之后的下一步）。

## 10. 不要做的事

- 不要并排跑 demo 的 gate 和 face 的 Gate 2（U2-B）。
- 不要把 `feat/prediction-markets` 合进任何分支。
- 不要在真实 harness home 里打开 `ALPACA_KIT_ENABLE_ORDERS`；不要把任何 key 写进仓库根的 `.env.*` 当新场所身份。
- 不要动 `bots/`、`data/pit/`、`docs/research/`、`dsh/skills/style-kairos/`。
- 不要为了统一先抽一个通用 venue Protocol 或新建 ledger 服务（Rule 8；U4、D2）。
- 不要把 demo 的钱包骨架与组合钱包接进这版（U8-A）。
- 画布改动：用 Artifact 工具先 `read` 再 publish，编辑器会重新序列化文件，直接重发旧副本会被拒。

## 11. 给下一个 agent 的开场提示词

> 先读本简报顶部的「状态」行，再读 `Kairos-Design.md` §1–§2、§7.3、§8，`AGENTS.md`，`CLAUDE.md`。operator 的决定（2026-10-05）是：**现在站 C，方向朝 A**。不要按 §7 施工：S0 已由 PR #5 落地，S1–S7 等下一份 charter。先读 PR #5 和 `demo/` 的 README（回灌 Kairos 表），再读设计稿 v1（PR #4）的 §4、§5、§11。画布 <https://claude.ai/artifact/2aXJoRzTzp5kDhMqCD8fLk> 是当时的图，不是现在的计划。下一个文档任务是下一份 charter：议程是两种形状的五个冲突点（门在哪、谁签字、网络、每写一卡、账本，记录在本简报 §12），A 和 B 是它要选的两种形状。任何真钱、testnet 或 mainnet 的事，以及任何把 demo 接进 face 的事，都先停下来问。

## 12. 冲突记录：v1 的形状 vs demo 的形状（2026-10-05）

operator 的决定：**现在站 C**，两个产品互不接；**方向朝 A**。要接的时候回到这一节，先把 12.1 的五个点定了再动代码。这一节只记事实和分歧，不做决定。demo 的事实读自 `linqizhe07/buyer-agent-demo @ 2d49602`（PR #5 钉的那个提交）的 README 与它的 PR #3–#5 说明；v1 的事实读自设计稿 `docs/superpowers/specs/2026-10-02-venue-plugins-design.md`。

### 12.1 真正冲突的五个点（不能都要）

| # | 点 | v1 设计稿（face 侧） | demo @ 2d49602 | 为什么不能都要 |
|---|---|---|---|---|
| C1 | 门在哪 | face 的 Gate 2 是全树唯一的卡生产者（`face/src/orders.ts`），manifest 只喂写工具名（设计稿 §4.3） | 自己的门（`src/agent/gate.ts`）+ 授权书（`src/agent/mandates.ts`）+ Account 层的支出 / 交易额度（`src/portfolio/account/state.ts`），Conservative / Aggressive 两档 | 两道门两个进程，就是 `Kairos-Design.md` §7.3「no bespoke harness」和本简报 U2-B 否掉的东西；接了就只能留一道 |
| C2 | 谁签字 | 人在 face 上点卡，答复进会话日志（`allowed-once`）；真正的边界在场所侧（agent key 不能提币、`validUntil`）；签名器「不建」（设计稿 §6.4、§12） | owner 是浏览器里的 P-256 设备钥匙，每条指令是带 nonce 的 EIP-712 签名信封；批卡 = owner 对卡哈希的签名，放行时重查（`src/portfolio/account/sign.ts`、`exchange.ts`） | 这正是设计稿 D5-A 和残差 R3a 要的答案，也正是 charter §7.3 写明不建的 cryptographic machinery；要么接受签名协议并改 charter，要么留在点卡加场所侧约束 |
| C3 | 网络 | paper / testnet；manifest 里 `network: mainnet` 一律拒绝（设计稿 §4.1） | 主网真账户（ccxt 覆盖的交易所、Alpaca、Kalshi、Robinhood、Polymarket、六条 EVM 链上的浏览器钱包、MetaMask）；真实下单**默认开**，`--read-only` 才关，`--live-cap` 单笔默认 $100 | 「拒绝 mainnet」和「默认开」不能同时成立；接了就要选 fence 是哪一种 |
| C4 | 每写一卡 | charter P5：每次写停一张卡 | Aggressive 模式：额度内 agent 直接下单、直接动钱，不出卡 | 这是 P5 本身；Aggressive 进 face 就要改 charter |
| C5 | 账本 | `/account` 只读汇总，不存东西（设计稿 D3-A、§8） | 多本哈希链 JSONL（agent ledger、account ledger）+ statement + 对账；签名信封嵌在账本行里 | 可以并存一阵，长期只能有一本真账；demo 的形状就是设计稿 D3-B 推迟的「有存储的账本」 |

另一处分歧，不算冲突但要知道：demo 为比价和拆单抽了统一的场所形状（`markets / market / place / cancel / status`，`src/portfolio/live/trade.ts`），设计稿按 Rule 8 说第二个场所出现前不抽 Protocol。

### 12.2 不冲突的部分

- demo 的插件合同就是设计稿 §4：manifest allow-list、挂载审计四条规则、`intent → 授权书 → 卡 → grant → 场所 → 账本`。demo 在四个模拟器上把这一层验证了（十一个场景，`test/e2e.test.ts`）。这一层没有取舍。
- demo 的资金面（每个场所的出入金门、在途资金、地址簿冷静期、agent 子账户 float、经 LI.FI 的跨链、x402 / MPP / AP2 付款）设计稿没有，是加法。
- 设计稿的 face / dsh 接法 demo 没有：MCP row 组合（`face/src/akshare.ts` 模式）、credential seam、bot mask、`AGENTS.md` 一段。demo README 的「回灌 Kairos」表把这些列为目标，一条没做。纯互补。

### 12.3 三种站法

| 站法 | 做什么 | 代价 | 设计稿 v1 的去向 |
|---|---|---|---|
| A · Kairos 做 Account 的租客 | face 一行 MCP row 接 demo 的 `portfolio:mcp`，agent key 由 owner 授权；owner 在 Account 页批卡；Gate 2 不再看场所写入 | 两个审批面（Alpaca paper 仍在 face 出卡）；两个 home；charter 必须重写，C2、C3、C4 全触发 | §4.3 的 Gate 2 喂名作废；§7 的 PIT 立场和 §4.5 的 bot mask 仍适用 |
| B · demo 的件搬进 face | 本简报 S1–S4：manifest 审计、授权书、账本移植进 `face/src`；Gate 2 仍是唯一的门，demo 的门退役；签名协议不要或重做 | 重写已有的东西；Kairos 长期停在 paper / testnet；Linqi 的 Account 线和 face 分叉 | 原样成立 |
| C · 两个产品，先不接 | 现状：demo 以 `demo/` 钉在树里（PR #5），谁也不调用谁；设计稿留作 face 侧接法的记录 | 没有共享的门、账本、凭据；Kairos 仍只有 Alpaca paper 一个席位 | 记录 |

### 12.4 什么时候回来这一节

- Kairos 真的需要第二个场所的时候：先在 12.1 上选 A 或 B，再动代码。
- 任何真钱之前：先写下一份 charter（`Kairos-Design.md` §8 最后一行），C1–C5 就是它的议程。
- 再 bump `demo/` 之前：读 demo 那次 PR 的说明，知道又有多少能动真钱的代码进树；2d49602 起 demo 默认开着真实下单。
- demo 自己承认没有一把真钥匙用过（README「诚实边界」）：Kairos 接过去并不比它的 Alpaca paper 席位更真，所以 Rule 8 的「内容来之前别选 substrate」在这里仍然成立。
