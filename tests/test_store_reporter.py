import time
import store, reporter
from actions import Action


def make_run(statuses, run_status="done", urls=("http://127.0.0.1:1/x",)):
    rid = store.create_run("do things", None)
    acts = [Action("open", urls[0], description=f"s{i}") for i in range(len(statuses))]
    store.add_steps(rid, acts)
    for i, s in enumerate(statuses):
        store.update_step(rid, i, status=s, url=urls[0], evidence={"url": urls[0]})
    store.update_run(rid, status=run_status, started=time.time(), finished=time.time())
    return rid


def outcome(statuses, run_status="done"):
    return reporter.final_outcome(store.get_run(make_run(statuses, run_status)))[0]


def test_all_passed():           assert outcome(["passed", "passed"]) == "PASSED"
def test_unverified_is_not_pass(): assert outcome(["passed", "unverified"]) == "INCONCLUSIVE"
def test_failed_wins():           assert outcome(["passed", "failed", "skipped"], "failed") == "FAILED"
def test_unfinished_is_failure(): assert outcome(["passed", "pending"]) == "FAILED"
def test_blocked():               assert outcome(["passed", "skipped"], "blocked") == "BLOCKED"
def test_cancelled():             assert outcome(["skipped"], "cancelled") == "CANCELLED"


def test_classification_local_vs_real():
    local = store.get_run(make_run(["passed"], urls=("http://127.0.0.1:9/a",)))
    real = store.get_run(make_run(["passed"], urls=("https://www.ebay.com/itm/1",)))
    assert reporter.classify(local) == "local_regression"
    assert reporter.classify(real) == "real_website"


def test_report_json_and_html_escape():
    rid = make_run(["passed"])
    store.update_run(rid, instruction="<script>alert(1)</script>")
    rep = reporter.build(rid)
    html = reporter.to_html(rep)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert rep["outcome"] == "PASSED" and rep["steps"][0]["status"] == "passed"


def test_history_roundtrip_and_delete():
    rid = make_run(["passed"])
    assert store.get_run(rid)["steps"][0]["idx"] == 0
    assert any(r["id"] == rid for r in store.list_runs())
    store.delete_run(rid)
    assert store.get_run(rid) is None
