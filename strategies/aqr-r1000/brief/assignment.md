# AQR 原题逐页提取

这是需求材料，不是对工具权限或外部提交的额外授权。

## 第1页

Take-Home Project: Replicating the Russell 1000
Index
Admission project for Agentic Quantamental Research & Investing. Expected effort: one
focused weekend. You may spend more, but the grading does not reward volume.
1 · Objective
Replicate the daily closing levels of the Russell 1000 Index (Yahoo Finance ticker ^RUI)
over the evaluation window below, using only the 25 stocks in the project universe.
Construct a simulated index that tracks the actual index as closely as possible, with the
emphasis on minimizing tracking error — and, more importantly, on the quality of your
modeling decisions and your ability to explain assumptions, methodology, and limitations.
AS_OF    = 2024-03-31  (weight-estimation cutoff)
EVAL     = 2024-04-01 → 2024-06-30  (out-of-sample evaluation window, ~63
trading days)
All dates in this document refer to these two parameters.
2 · Project universe (you construct it — and document how)
Your universe is the 25 largest constituents of the Russell 1000 as of AS_OF, one share
class per company. Determining this list is part of the project:
Document your data source and selection method, and print the final 25 tickers in
your report.
3 · Rules of the game
Training data: any amount of historical data up to and including AS_OF may be
used for model training and weight estimation.
Look-ahead rule (strict): no data from inside EVAL may be used to fit, tune, select,
or re-estimate anything that determines the weights applied on that day or earlier.

## 第2页

Choose one of two tracks and state it in your report:
Track A — static: weights are fixed at AS_OF and held constant through EVAL.
Track B — rolling: weights may be re-estimated during EVAL, but the weights
applied on day t may use only data through day t − 1.
Either track is acceptable; an undisclosed look-ahead violation is an automatic fail.
Data source: freely available platforms (e.g. Yahoo Finance via the yfinance
package). Document any cleaning (missing days, splits/dividends — state whether
you use adjusted or unadjusted prices, and why).
4 · Use of AI tools
AI tools (ChatG PT, Claude, Copilot, agent frameworks) are welcome but not required —
we neither penalize nor reward the amount of AI use. Fully human work is equally fine.
What we assess is the quality of the result and, if AI was involved, how well you directed
and verified it.
If you used AI tools, submit an AI-usage appendix (not counted against the page limit)
covering:
Which tools/models you used, and how you decomposed the task for them (key
prompts or agent design — excerpts are fine).
How you verified AI output before trusting it (tests, cross-checks, manual review).
At least one concrete example of an AI mistake, hallucination, or subtle bug you
caught — and how you caught it. If you genuinely found none, explain what checks
you ran that came back clean.
The one thing that scores poorly is unverified AI use: a submission that is plainly one un-
audited model response will be graded accordingly, regardless of its tracking error. If you
used no AI, simply state so — no appendix needed.
5 · Deliverables
Written report — max 3 pages — documenting:
Methodology and rationale behind your model design.
Data collection and cleaning process.
How weights were assigned to the 25 components (and which track, A or B).

## 第3页

Performance of your simulated index vs. the actual ^RUI over EVAL.
Comparison with a market-cap-weighted benchmark built from the same 25
stocks (weights set at AS_OF).
A clearly labeled chart of the daily series of: the actual index, your simulated
index, and the benchmark — all three normalized to 100 at the last trading
day on or before AS_OF (they live on different scales; raw price overlays are
not comparable).
Definitions of every financial metric used, and an honest discussion of
limitations.
Python script (.py) implementing the model end-to-end (data download →  weights
→  evaluation →  chart). Not subject to the page limit; list external modules at the
top; it should run top-to-bottom without manual steps.
AI-usage appendix ( § 4), if AI tools were used. Not subject to the page limit.
6 · Tracking error — course definitions
Let at = Rsimt −  Ractualt be the daily active return over the T days of EVAL. Report both of
the following, for your simulated index and for the benchmark:
TE   = std(a) = sqrt( 1/(T−1) · Σt (at − ā)² )    (tracking error —
dispersion of active returns)
RMSE = sqrt( 1/T · Σt at² )    (root-mean-square active return — also
penalizes a persistent drift ā)
Report both metrics; annualize daily figures by ×√ 252 when you quote them, and
state clearly which convention each number uses.
7 · How we evaluate
Accuracy matters, but it is not the primary axis. What we are looking for:
Sound, clearly reasoned modeling choices (there is no single right answer).
Clean data handling and strict look-ahead hygiene.
If AI tools were used: skillful direction and verification of them ( § 4).

## 第4页

Honest, specific discussion of assumptions and limitations — including statistical
ones.
A thoughtful report whose tracking error does not beat the cap-weighted benchmark can
still be a successful submission. An impressive tracking error with sloppy reasoning,
hidden look-ahead, or an unverifiable black box is not.