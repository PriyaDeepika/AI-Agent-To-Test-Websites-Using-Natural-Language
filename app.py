import os, secrets
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory, Response, abort
import config, store, agent, reporter, llm_parser
from code_generator import generate_playwright_script
from demo import demo

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(16)
app.register_blueprint(demo)

EXAMPLES = [
    {"title": "eBay: women's Nike shoes → cart", "url": "https://www.ebay.com", "real": True,
     "text": "Search for Nike shoes for women, select a suitable product, choose size 8, add it to the cart, and verify that the correct item appears in the cart."},
    {"title": "YouTube: Linux tutorials", "url": "https://www.youtube.com", "real": True,
     "text": "Search for Linux administration tutorials, open a relevant video, and verify that it loads."},
    {"title": "Local shop: select size, add to cart", "url": f"{config.DEMO_BASE_URL}/demo/shop", "real": False,
     "text": "Search for Nike shoes for women, select a suitable product, choose size 8, add it to the cart, and verify that the correct item appears in the cart."},
    {"title": "Local login → dashboard", "url": f"{config.DEMO_BASE_URL}/demo/login", "real": False,
     "text": "Log in with username demo and password test1234, then verify that “Welcome back” is displayed."},
]


@app.route("/")
def index():
    return render_template("index.html")


# ---- legacy demo pages kept for backwards compatibility -------------------------------------------
@app.route("/login_page")
def login_page(): return render_template("login_page.html")
@app.route("/form_page")
def form_page(): return render_template("form_page.html")
@app.route("/success_page")
def success_page(): return render_template("success_page.html")


# ---- API ------------------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ok = Path(p.chromium.executable_path).exists()
    except Exception:
        ok = False
    return jsonify({"chromium_installed": ok, "llm_planner": llm_parser.available(), "headless": config.BROWSER_HEADLESS,
                    "limits": {"max_actions": config.MAX_TOTAL_ACTIONS, "retries": config.MAX_STEP_RETRIES, "timeout_s": config.RUN_TIMEOUT_S}})


@app.get("/api/examples")
def examples(): return jsonify(EXAMPLES)


@app.post("/api/plan")
def preview_plan():
    """Dry-run: parse the instruction into a validated plan without launching a browser."""
    import parser as rules
    from actions import validate_plan, PlanError
    import policy
    d = request.get_json(silent=True) or {}
    instruction, url = (d.get("instruction") or "").strip(), (d.get("url") or "").strip() or None
    if not instruction:
        return jsonify({"error": "Instruction is empty."}), 400
    try:
        url = policy.check_url(url) if url else None
        planner = "rules"
        try:
            plan, notes = llm_parser.parse_instruction_llm(instruction, url), []
            planner = "llm"
        except Exception:
            res = rules.parse(instruction, url)
            plan, notes = validate_plan(res.actions), list(res.notes)
            if res.unparsed:
                notes.append("Not understood (ignored): " + "; ".join(res.unparsed))
        return jsonify({"planner": planner, "notes": notes, "steps": [a.public() for a in plan]})
    except (ValueError, PlanError) as e:
        return jsonify({"error": str(e)}), 422


@app.post("/api/runs")
def create_run():
    data = request.get_json(silent=True) or {}
    try:
        rid = agent.start_run(data.get("instruction", ""), data.get("url"), headless=data.get("headless"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": rid}), 202


@app.get("/api/runs")
def runs(): return jsonify(store.list_runs())


@app.get("/api/runs/<rid>")
def run_detail(rid):
    r = store.get_run(rid) or abort(404)
    r["active"] = agent.is_active(rid)
    return jsonify(r)


@app.post("/api/runs/<rid>/respond")
def run_respond(rid):
    d = request.get_json(silent=True) or {}
    if not agent.respond(rid, bool(d.get("approved", True)), str(d.get("text", ""))):
        return jsonify({"error": "Run is not waiting for input."}), 409
    return jsonify({"ok": True})


@app.post("/api/runs/<rid>/cancel")
def run_cancel(rid):
    return (jsonify({"ok": True}) if agent.cancel(rid) else (jsonify({"error": "Run is not active."}), 409))


@app.delete("/api/runs/<rid>")
def run_delete(rid):
    if agent.is_active(rid): return jsonify({"error": "Run is still active."}), 409
    store.delete_run(rid)
    import shutil; shutil.rmtree(config.DATA_DIR / "runs" / rid, ignore_errors=True)
    return jsonify({"ok": True})


@app.get("/api/runs/<rid>/screenshots/<path:name>")
def screenshot(rid, name):
    d = (config.DATA_DIR / "runs" / rid).resolve()
    return send_from_directory(d, name)


def _report(rid):
    rep = store.get_report(rid)
    if rep is None: abort(404, "Report is not available until the run finishes.")
    return rep


@app.get("/api/runs/<rid>/report.json")
def report_json(rid):
    import json
    return Response(json.dumps(_report(rid), indent=2, ensure_ascii=False), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=report-{rid}.json"})


@app.get("/api/runs/<rid>/report.html")
def report_html(rid):
    return Response(reporter.to_html(_report(rid), config.DATA_DIR / "runs" / rid), mimetype="text/html",
                    headers={"Content-Disposition": f"attachment; filename=report-{rid}.html"})


@app.get("/api/runs/<rid>/script.py")
def script_py(rid):
    run = store.get_run(rid) or abort(404)
    return Response(generate_playwright_script(run["steps"]), mimetype="text/x-python",
                    headers={"Content-Disposition": f"attachment; filename=replay-{rid}.py"})


if __name__ == "__main__":
    store.mark_interrupted()
    app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False, threaded=True)
