# youzi_web/features/research/service.py
from youzi_web.data_access import harness_view, list_runs, load_run, seed_harness


def get_seed_harness_view() -> dict:
    return harness_view(seed_harness())


def run_context(run: str | None):
    runs = list_runs()
    run_id = run or (runs[0]["run_id"] if runs else None)
    report, meta = load_run(run_id) if run_id else (None, None)
    return {"runs": runs, "run_id": run_id, "meta": meta, "report": report}
