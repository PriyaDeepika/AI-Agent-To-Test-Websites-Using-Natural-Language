"""Report generation: JSON + self-contained HTML (screenshots embedded) + exportable Playwright script."""
from __future__ import annotations
import base64, html, json, time
from pathlib import Path
from urllib.parse import urlparse
import config, store

LOCAL = {"localhost", "127.0.0.1", "::1"}


def classify(run: dict) -> str:
    """real_website | local_regression — derived from the hosts actually visited, never asserted."""
    hosts = set()
    for s in run.get("steps", []):
        u = (s.get("evidence") or {}).get("url") or s.get("url")
        if u:
            hosts.add(urlparse(u).hostname or "")
    for s in run.get("steps", []):
        if s["action"] == "open" and s["params"].get("target"):
            hosts.add(urlparse(s["params"]["target"]).hostname or "")
    hosts.discard("")
    if not hosts:
        return "unknown"
    return "local_regression" if hosts <= LOCAL else "real_website"


def final_outcome(run: dict):
    """Derive the outcome strictly from step results — nothing is assumed to have succeeded."""
    steps = run["steps"]
    st = run["status"]
    if st == "cancelled":
        return "CANCELLED", "Run cancelled before completion."
    if st == "blocked":
        return "BLOCKED", run.get("summary") or "Stopped: human action was needed."
    if any(s["status"] == "failed" for s in steps) or st == "failed":
        return "FAILED", run.get("summary") or "A step failed."
    counts = {k: sum(1 for s in steps if s["status"] == k) for k in ("passed", "unverified", "pending", "running")}
    if counts["pending"] or counts["running"]:
        return "FAILED", "Run ended before all steps completed."
    if counts["unverified"]:
        return "INCONCLUSIVE", f"{counts['passed']} step(s) verified, {counts['unverified']} could not be machine-verified."
    return "PASSED", f"All {counts['passed']} steps executed and verified."


def build(run_id: str) -> dict:
    run = store.get_run(run_id)
    run["kind"] = classify(run)
    outcome, summary = final_outcome(run)
    run["outcome"], run["summary"] = outcome, summary
    report = {
        "run_id": run_id, "instruction": run["instruction"], "start_url": run["start_url"], "planner": run["planner"],
        "kind": run["kind"], "outcome": outcome, "summary": summary, "notes": run["notes"],
        "created": _iso(run["created"]), "started": _iso(run["started"]), "finished": _iso(run["finished"]),
        "duration_s": round((run["finished"] or time.time()) - (run["started"] or run["created"]), 1),
        "environment": {"headless": config.BROWSER_HEADLESS, "limits": {"max_actions": config.MAX_TOTAL_ACTIONS, "max_step_retries": config.MAX_STEP_RETRIES, "run_timeout_s": config.RUN_TIMEOUT_S}},
        "steps": [{k: s[k] for k in ("idx", "action", "description", "params", "status", "detail", "error", "url", "screenshot", "evidence", "attempts")} for s in run["steps"]],
    }
    return report


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)) if t else None


def to_html(report: dict, run_dir: Path | None = None) -> str:
    e = html.escape
    color = {"PASSED": "#1a7f4b", "FAILED": "#c0392b", "INCONCLUSIVE": "#b7791f", "BLOCKED": "#6b46c1", "CANCELLED": "#666"}.get(report["outcome"], "#444")
    kind_label = {"real_website": "Real website", "local_regression": "Local regression (demo pages)", "unknown": "Unknown"}[report["kind"]]
    rows = []
    for s in report["steps"]:
        img = ""
        if run_dir and s.get("screenshot") and (run_dir / s["screenshot"]).exists():
            b64 = base64.b64encode((run_dir / s["screenshot"]).read_bytes()).decode()
            img = f'<img alt="step {s["idx"] + 1} screenshot" src="data:image/png;base64,{b64}">'
        ev = json.dumps(s.get("evidence") or {}, indent=2, ensure_ascii=False, default=str)
        rows.append(f"""<section class="step {e(s['status'])}"><h3><span class="n">{s['idx'] + 1}</span> {e(s['description'])}
<span class="pill {e(s['status'])}">{e(s['status'])}</span></h3>
<p class="meta">{e(s['action'])} · {e(s.get('url') or '')}</p>
<p>{e(s.get('detail') or '')}</p>{('<p class="err">' + e(s['error']) + '</p>') if s.get('error') else ''}
<details><summary>Evidence</summary><pre>{e(ev)}</pre></details>{img}</section>""")
    notes = "".join(f"<li>{e(n)}</li>" for n in report.get("notes", []))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Test report {e(report['run_id'])}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1c1f24}}
h1{{font-size:1.4rem;margin:.2rem 0}}.badge{{display:inline-block;padding:.15rem .6rem;border-radius:4px;color:#fff;background:{color};font-weight:600}}
.meta{{color:#6a7280;font-size:.85rem;margin:.2rem 0}}.step{{border-left:3px solid #d0d5dd;padding:.4rem 1rem;margin:1rem 0;background:#fafbfc}}
.step.passed{{border-color:#1a7f4b}}.step.failed{{border-color:#c0392b}}.step.unverified{{border-color:#b7791f}}
.pill{{font-size:.7rem;text-transform:uppercase;padding:.1rem .4rem;border-radius:3px;background:#e4e7ec;margin-left:.4rem}}
.n{{display:inline-block;min-width:1.6rem;color:#6a7280}}img{{max-width:100%;border:1px solid #d0d5dd;margin-top:.5rem}}
pre{{background:#f1f3f5;padding:.6rem;overflow:auto;font-size:.8rem}}.err{{color:#c0392b}}h3{{font-size:1rem;margin:.2rem 0}}</style>
<h1>Web test report <span class="badge">{e(report['outcome'])}</span></h1>
<p class="meta">Run {e(report['run_id'])} · {e(kind_label)} · planner: {e(str(report['planner']))} · {report['duration_s']}s · {e(str(report['created']))}</p>
<p><strong>Instruction:</strong> {e(report['instruction'])}</p><p><strong>Result:</strong> {e(report['summary'])}</p>
{('<ul>' + notes + '</ul>') if notes else ''}{''.join(rows)}</html>"""
