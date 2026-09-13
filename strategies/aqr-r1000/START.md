# AQR room 启动简报

由 Codex 根据 operator 的“创建一下跑一下”请求整理。Operator 已明确授权本次创建三个 bot；宿主已创建并将它们加入本频道，无需 dsh 再创建或修改 bot。正式发送状态与会话身份以 room.json 为准。

请在本 room 完成 AQR Russell 1000 复制课程项目。你是 dsh 主脑。先读当前目录 brief/assignment.md、brief/requirements.md、protocol.md、THESIS.md；完整编排参考仓库根 docs/aqr-room-orchestration.md。项目目录是当前 strategies/aqr-r1000，不使用原设计中的 projects/ 路径。原题PDF在 brief/aqr_takehome-project.pdf。

这份启动brief已回答新策略所需的目标、证伪条件、数据窗口和指标，不要重复询问这些。AS_OF=2024-03-31，EVAL=2024-04-01..2024-06-30，默认Track A。目标是当日Russell1000前25大公司各一个股类的指数复制；没有历史名单或市值证据时，先查源，不用今日名单补齐。两套现有PIT床均不覆盖。可获取免费历史公开数据并写到本项目，内部回放使用外部source适配器和replay_days的日期护栏；不修改data/pit/。这是模拟指数，不声称实际成交回测。

立即开始第一轮 parallel dispatch 给 aqr-data、aqr-method、aqr-audit，围绕数据来源/方法/前视审计独立审题。说明尚未取数和未看EVAL结果。dispatch返回后结束当前turn，等待round-end唤醒；不把轮次结束当项目完成。先说明实际分歧，再作主脑裁决。

随后用两个原生临时工程子任务分别实现数据管线和在合成数据上开发模型/评估模块；每个任务约束独占文件范围、输入版本、验收条件和不读取EVAL。你负责solution.py集成、实验账本和报告。已有agent_claude和agent_codex是只读咨询接口：Claude审方法/报告，Codex审代码/反例，不能让它们写文件或虚报执行测试。由工程任务运行其建议并保存输出。

默认预算4个lambda×3个pre-EVAL时间折，共12次候选拟合，预检查与AS_OF refit各1次，总14次。训练窗与lambda选择遵循protocol.md。不得下载/读取EVAL收益或绩效来选名单、调参、换Track或追加模型。冻结股票池、数据清洗、方法、权重和评估代码之后，才运行最终EVAL。实际数据缺失须显式阻断/披露，不静默缩窗、补零或改权重。

先跑独立合成oracle与未来数据扰动测试，重点验证首日03-28到04-01、TE的ddof=1、RMSE、sqrt252年化、拆股和股息、25个唯一公司与标签对齐。审计角色提独立期望值，工程角色执行；不得把设计的测试故障编造成真实AI错误。

room最多3轮、10条bot消息，按3+2+3发言安排；每次读取剩余额度，round-end/子任务通知不重置配额，不伪造operator消息。只有真正缺失的信息或未获授权的事项才请求operator；普通实现选择自主推进。没有胜过市值基准可以诚实交付，数据证据和前视错误未解决不得宣称成功。

交付 deliverables/solution.py（从下载到权重、评估与图表能端到端运行并可移植）、正文最多3页的report.pdf和AI使用附录。报告必须列25 tickers、同25股AS_OF市值基准、三条以基准交易日100归一化曲线、模型与基准的TE和RMSE、指标定义及统计局限。保留失败实验、真实AI错误与修复记录。不要自动向外部提交。按阶段更新status.yaml与journal.md，提交自己的文件，不修改其他策略、现有bots或安装profile。
