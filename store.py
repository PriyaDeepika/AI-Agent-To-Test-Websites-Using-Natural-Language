"""SQLite persistence for runs and steps (one short-lived connection per call; thread-safe)."""
from __future__ import annotations
import json, sqlite3, time, uuid
from contextlib import contextmanager
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, instruction TEXT NOT NULL, start_url TEXT, status TEXT NOT NULL, outcome TEXT, summary TEXT,
  planner TEXT, kind TEXT, pending TEXT, notes TEXT, created REAL, started REAL, finished REAL, report TEXT);
CREATE TABLE IF NOT EXISTS steps (
  run_id TEXT NOT NULL, idx INTEGER NOT NULL, action TEXT, description TEXT, params TEXT, status TEXT NOT NULL,
  detail TEXT, error TEXT, url TEXT, screenshot TEXT, evidence TEXT, selector TEXT, attempts INTEGER DEFAULT 0,
  started REAL, finished REAL, PRIMARY KEY (run_id, idx));
"""


@contextmanager
def conn():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def create_run(instruction, start_url, notes=None) -> str:
    rid = new_id()
    with conn() as c:
        c.execute("INSERT INTO runs (id,instruction,start_url,status,notes,created) VALUES (?,?,?,?,?,?)",
                  (rid, instruction, start_url, "queued", json.dumps(notes or []), time.time()))
    return rid


def update_run(rid, **kw):
    for k in ("pending", "notes", "report"):
        if k in kw and not isinstance(kw[k], (str, type(None))):
            kw[k] = json.dumps(kw[k])
    cols = ", ".join(f"{k}=?" for k in kw)
    with conn() as c:
        c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*kw.values(), rid))


def add_steps(rid, actions):
    with conn() as c:
        c.execute("DELETE FROM steps WHERE run_id=?", (rid,))
        for i, a in enumerate(actions):
            p = a.public()
            c.execute("INSERT INTO steps (run_id,idx,action,description,params,status) VALUES (?,?,?,?,?,?)",
                      (rid, i, a.action, a.description, json.dumps({"target": p["target"], "value": p["value"], **p["params"]}), "pending"))


def update_step(rid, idx, **kw):
    if "evidence" in kw and not isinstance(kw["evidence"], (str, type(None))):
        kw["evidence"] = json.dumps(kw["evidence"], default=str)
    cols = ", ".join(f"{k}=?" for k in kw)
    with conn() as c:
        c.execute(f"UPDATE steps SET {cols} WHERE run_id=? AND idx=?", (*kw.values(), rid, idx))


def _run(row):
    d = dict(row)
    for k in ("pending", "notes"):
        d[k] = json.loads(d[k]) if d.get(k) else (None if k == "pending" else [])
    d.pop("report", None)
    return d


def _step(row):
    d = dict(row)
    d["params"] = json.loads(d["params"]) if d.get("params") else {}
    d["evidence"] = json.loads(d["evidence"]) if d.get("evidence") else {}
    return d


def get_run(rid, with_steps=True):
    with conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if not r:
            return None
        d = _run(r)
        if with_steps:
            d["steps"] = [_step(s) for s in c.execute("SELECT * FROM steps WHERE run_id=? ORDER BY idx", (rid,))]
        return d


def get_report(rid):
    with conn() as c:
        r = c.execute("SELECT report FROM runs WHERE id=?", (rid,)).fetchone()
        return json.loads(r["report"]) if r and r["report"] else None


def list_runs(limit=100):
    with conn() as c:
        return [_run(r) for r in c.execute("SELECT * FROM runs ORDER BY created DESC LIMIT ?", (limit,))]


def delete_run(rid):
    with conn() as c:
        c.execute("DELETE FROM steps WHERE run_id=?", (rid,))
        c.execute("DELETE FROM runs WHERE id=?", (rid,))


def mark_interrupted():
    """Runs left 'running' by a crashed/stopped server can never finish; make that visible."""
    with conn() as c:
        c.execute("UPDATE runs SET status='failed', outcome='FAILED', summary='Interrupted: the server stopped while this run was in progress.' WHERE status IN ('queued','running','awaiting_user')")
