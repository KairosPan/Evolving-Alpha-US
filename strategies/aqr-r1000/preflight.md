# dsh 启动自检

2026-09-13；只读自检，非正式研究运行。

自检完成。仅用 read/glob 核对了 `brief/assignment.md`、`START.md`、`status.yaml`，未做任何写入、下载、拟合、bot 调用或 EVAL 读取。

**简短说明**

- **原题 AS_OF/EVAL**：AS_OF = 2024-03-31（权重估计截止日），EVAL = 2024-04-01 → 2024-06-30（约 63 个交易日，样本外评估窗）。默认 Track A（权重在 AS_OF 冻结，全 EVAL 不变）。status.yaml 已正确登记这两个参数及 fits_budget=14、fits_completed=0。
- **三个最终交付物**：① `deliverables/solution.py`——从数据下载→权重→评估→图表端到端、无人工步骤可运行；② `report.pdf`——正文最多 3 页，须含 25 tickers、同 25 股的 AS_OF 市值基准、三条按基准日归一化到 100 的曲线、模型与基准的 TE 和 RMSE（注明 ddof 与 √252 年化约定）、指标定义与统计局限；③ AI 使用附录（不计入页数限制，含至少一个被抓住的真实 AI 错误，或说明检查为何干净）。
- **现有 PIT 床不覆盖**：两套床（2yr = 2024-06-03..2026-07-09，broad = 2025-11-17..2026-03-27）均不覆盖 AS_OF 前的训练期和 EVAL 窗，且无 warmup。需获取免费历史公开数据写入本目录，内部回放走外部 source 适配器 + replay_days 日期护栏，不修改 `data/pit/`。
- **Claude Code/Codex 当前定位**：只读复核接口——Claude 审方法/报告，Codex 审代码/反例；不得让它们写文件或虚报执行测试，其建议由工程子任务运行并保存输出。
- **下一步**：等待三个专业 bot（aqr-data / aqr-method / aqr-audit）的明确创建授权。授权前不创建、不修改、不调用任何 bot，也不经子任务绕过；本轮仅为验证 dsh 主脑可运行，并非正式研究启动。

顺带一个自检观察：START.md 要求先读的 `brief/requirements.md` 和 `protocol.md` 目前不在目录树中（glob 只见 orchestration.md、assignment.md），正式启动时需留意补齐或澄清。本轮到此结束。

## 后续补齐

主脑自检结束后，protocol.md、THESIS.md 和 brief/requirements.md 已完成并通过链接核验。上面的缺文件观察保留为当时真实记录；正式研究尚未启动。
