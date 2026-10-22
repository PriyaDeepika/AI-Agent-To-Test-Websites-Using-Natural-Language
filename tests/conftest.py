import os, socket, tempfile, threading, time
import pytest

# Configure BEFORE importing project modules (config reads env at import time).
_tmp = tempfile.mkdtemp(prefix="agent-tests-")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]
os.environ.update({"DATA_DIR": _tmp, "DB_PATH": os.path.join(_tmp, "t.db"), "BROWSER_HEADLESS": "true",
                   "DEMO_BASE_URL": f"http://127.0.0.1:{PORT}", "GEMINI_API_KEY": "", "RUN_TIMEOUT_S": "120",
                   "USER_RESPONSE_TIMEOUT_S": "30", "MAX_STEP_RETRIES": "1"})

import config, store, agent  # noqa: E402
from app import app as flask_app  # noqa: E402

BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="session")
def server():
    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", PORT, flask_app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield BASE
    srv.shutdown()


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture(scope="session")
def run_agent(server):
    """run(instruction, url, answers={'input':'7','confirm':False,'human':False}) -> finished run dict.
    Answers are keyed by pause kind; the helper records every pause it saw in run['_pauses']."""
    def run(instruction, url=None, answers=None, timeout=120):
        answers = answers or {}
        rid = agent.start_run(instruction, url)
        pauses, t0 = [], time.time()
        while time.time() - t0 < timeout:
            r = store.get_run(rid, with_steps=False)
            if r["status"] == "awaiting_user":
                p = r["pending"]; pauses.append(p)
                a = answers.get(p["kind"], True if p["kind"] != "input" else "")
                if p["kind"] == "input":
                    agent.respond(rid, bool(a), str(a))
                else:
                    agent.respond(rid, bool(a))
                time.sleep(0.4)
            elif r["status"] not in ("queued", "running"):
                break
            else:
                time.sleep(0.3)
        out = store.get_run(rid)
        out["_pauses"] = pauses
        return out
    return run
