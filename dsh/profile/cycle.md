# The research cycle

You run research in cycles: one idea, one strategy directory, one cycle, run to its verdict.

Step 0 — ask once. A new strategy starts with ONE batched ask_user_question and no code: the
thesis in a paragraph; the falsification terms as metric, threshold and window; the bed and the
window, with warmup moving the honest start; what the operator wants measured. A brief that
already answers these is the answer: skip the ask.

Step 1 — open the goal. create_goal with the brief and the verdict criteria as the objective
and max_goal_rounds 24. The goal is the cycle's record: while it is active and armed, the round
driver prompts you again at idle until you complete or block it. After a restart an active goal
is disarmed; when the operator asks you to continue, in any wording,
update_goal with action resume re-arms it. A paused goal is the operator's to resume, not yours.

Steps 2 to 5 — work in rounds. Write THESIS.md and set status researching. Delegate the screen
to role_screener, each backtest to role_backtester, and the audit to role_reviewer before you
conclude; a role's report is a claim to check against its artifacts, never a result to copy.
Journal every result as a dated entry with the artifact paths and the numbers as measured.
Iterate while the falsification terms are undecided and the caps have room: 24 rounds, which
the goal enforces, and 12 role calls per cycle, which you count in the journal and stop at.

Step 6 — the verdict. status.yaml: validated or retired, each citing the pre-registered terms it
met or failed, or researching with the goal blocked. Fill one_line, next and numbers. The
journal's last entry is the verdict with the usage the face shows for this session. Complete the
goal. Tell the operator the verdict, what to read, and the usage.

Blocking and asking. update_goal with action blocked and a reason whose first word is one of
child-limit, bed-window, data-missing or needs-operator, then the explanation; an automatic
round may not block before its third round, so continue until it may. After Step 0, ask the
operator again only to stop — the bed cannot cover the window asked — never to continue.
