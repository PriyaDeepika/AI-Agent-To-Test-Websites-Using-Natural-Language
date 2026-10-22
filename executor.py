"""Owns the Chromium session for one run and drives the LangGraph workflow to completion."""
from __future__ import annotations
import time, traceback
from playwright.sync_api import sync_playwright
import config, store, reporter
from runtime import RunRuntime, RunAbort
from workflow import agent_workflow


def execute_run(run_id: str, instruction: str, start_url: str | None, registry: dict, headless: bool | None = None):
    store.update_run(run_id, status="running", started=time.time())
    final = {}
    rt = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=config.BROWSER_HEADLESS if headless is None else headless,
                                        slow_mo=config.BROWSER_SLOW_MO_MS)
            ctx = browser.new_context(viewport={"width": 1366, "height": 860}, locale="en-US")
            page = ctx.new_page()
            page.set_default_timeout(config.ACTION_TIMEOUT_MS)
            page.set_default_navigation_timeout(config.NAV_TIMEOUT_MS)
            rt = RunRuntime(run_id, page, [])
            registry[run_id] = rt
            try:
                final = agent_workflow.invoke(
                    {"instruction": instruction, "start_url": start_url},
                    config={"configurable": {"rt": rt}, "recursion_limit": 1500})
            except RunAbort as a:
                final = {"status": a.status, "message": a.message}
                _mark_remaining(run_id, rt, a.status)
            finally:
                try:
                    rt.screenshot("final.png")
                except Exception:
                    pass
                browser.close()
    except Exception as e:  # launch failures, unexpected crashes
        final = {"status": "failed", "message": f"Unexpected error: {type(e).__name__}: {str(e)[:300]}"}
        traceback.print_exc()
    finally:
        registry.pop(run_id, None)
        _finish(run_id, final)


def _mark_remaining(run_id, rt, status):
    run = store.get_run(run_id)
    for s in run["steps"]:
        if s["status"] == "running":
            store.update_step(run_id, s["idx"], status="failed" if status != "cancelled" else "skipped", error="Interrupted")
        elif s["status"] == "pending":
            store.update_step(run_id, s["idx"], status="skipped")


def _finish(run_id, final):
    status = final.get("status", "failed")
    run = store.get_run(run_id)
    for s in run["steps"]:            # steps never reached are skipped, not passed
        if s["status"] in ("pending", "running"):
            store.update_step(run_id, s["idx"], status="skipped")
    store.update_run(run_id, status={"running": "done"}.get(status, status), summary=final.get("message"), finished=time.time())
    rep = reporter.build(run_id)
    outcome = rep["outcome"]
    terminal = {"PASSED": "passed", "INCONCLUSIVE": "inconclusive", "FAILED": "failed", "BLOCKED": "blocked", "CANCELLED": "cancelled"}[outcome]
    store.update_run(run_id, status=terminal, outcome=outcome, summary=rep["summary"] if not final.get("message") or outcome in ("PASSED", "INCONCLUSIVE") else final["message"],
                     kind=rep["kind"], report=rep)
    rep["summary"] = store.get_run(run_id, with_steps=False)["summary"]
    store.update_run(run_id, report=rep)
