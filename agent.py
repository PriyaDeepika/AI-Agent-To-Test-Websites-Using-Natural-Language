"""Run manager: starts runs on background threads and relays human responses."""
from __future__ import annotations
import threading
import config, store, policy
from executor import execute_run

_registry: dict = {}
_slots = threading.Semaphore(2)     # at most two concurrent browsers


def start_run(instruction: str, start_url: str | None = None, headless: bool | None = None) -> str:
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("Instruction is empty.")
    if len(instruction) > 2000:
        raise ValueError("Instruction is too long (2000 characters max).")
    if start_url and start_url.strip():
        start_url = policy.check_url(start_url.strip())
    else:
        start_url = None
    run_id = store.create_run(instruction, start_url)

    def _target():
        with _slots:
            execute_run(run_id, instruction, start_url, _registry, headless)

    threading.Thread(target=_target, daemon=True, name=f"run-{run_id}").start()
    return run_id


def respond(run_id: str, approved: bool, text: str = "") -> bool:
    rt = _registry.get(run_id)
    if not rt:
        return False
    rt.answer(approved, text)
    return True


def cancel(run_id: str) -> bool:
    rt = _registry.get(run_id)
    if not rt:
        return False
    rt.cancel.set()
    return True


def is_active(run_id: str) -> bool:
    return run_id in _registry


def run_agent(instruction: str, start_url: str | None = None, wait: bool = True, timeout: float = 300):
    """Convenience for scripts/tests: start a run and (optionally) block until it finishes."""
    import time
    rid = start_run(instruction, start_url)
    if wait:
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = store.get_run(rid, with_steps=False)
            if r["status"] not in ("queued", "running", "awaiting_user"):
                break
            time.sleep(0.5)
    return store.get_run(rid)
