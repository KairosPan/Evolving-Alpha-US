# youzi_web/features/decision/service.py
from youzi_web.data_access import list_runs, load_run, seed_harness, skill_plan


def cockpit_context(run: str | None, day: str | None) -> dict:
    runs = list_runs()
    run_id = run or (runs[0]["run_id"] if runs else None)
    report, meta = load_run(run_id) if run_id else (None, None)
    lr = report.hch_loop_report if report else None
    steps = lr.trajectory.steps if lr else []
    days = [s.date.isoformat() for s in steps]
    idx = next((i for i, s in enumerate(steps) if s.date.isoformat() == day), 0) if day else 0
    step = steps[idx] if steps else None
    cands = []
    if step is not None:
        h = seed_harness()
        for c in step.decision.candidates:
            cands.append({"cand": c, "plan": skill_plan(c.pattern, h),
                          "outcome": step.outcomes.get(c.code)})
    return {"runs": runs, "run_id": run_id, "meta": meta, "days": days,
            "day": (step.date.isoformat() if step else None), "step": step, "candidates": cands}
