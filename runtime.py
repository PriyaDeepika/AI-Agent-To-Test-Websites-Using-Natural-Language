"""Per-run runtime: browser handles, shared context, screenshots, and human-in-the-loop pauses."""
from __future__ import annotations
import threading, time
from pathlib import Path
import config
import store


class RunAbort(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


class RunRuntime:
    def __init__(self, run_id: str, page, actions: list):
        self.run_id, self.page, self.actions = run_id, page, actions
        self.ctx: dict = {}              # shared memory between steps: query, selected_item, options, max_price ...
        self.obs = None
        self.cancel = threading.Event()
        self._answer: dict | None = None
        self._answered = threading.Event()
        self.started = time.time()
        self.total_actions = 0
        self.dir = Path(config.DATA_DIR) / "runs" / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    # -- browser ---------------------------------------------------------------
    def adopt_page(self, page):
        self.page = page
        try:
            page.bring_to_front()
            page.set_default_timeout(config.ACTION_TIMEOUT_MS)
            page.set_default_navigation_timeout(config.NAV_TIMEOUT_MS)
        except Exception:
            pass

    def screenshot(self, name: str) -> str | None:
        try:
            self.page.screenshot(path=str(self.dir / name), full_page=False, timeout=8000)
            return name
        except Exception:
            return None

    # -- limits ----------------------------------------------------------------
    def check_limits(self):
        if self.cancel.is_set():
            raise RunAbort("cancelled", "Run cancelled by the user.")
        if time.time() - self.started > config.RUN_TIMEOUT_S:
            raise RunAbort("failed", f"Run exceeded the {config.RUN_TIMEOUT_S}s time limit.")
        if self.total_actions >= config.MAX_TOTAL_ACTIONS:
            raise RunAbort("failed", f"Run exceeded the limit of {config.MAX_TOTAL_ACTIONS} actions.")

    # -- human in the loop -----------------------------------------------------
    def ask_user(self, pending: dict) -> dict:
        self._answer = None
        self._answered.clear()
        store.update_run(self.run_id, status="awaiting_user", pending=pending)
        deadline = time.time() + config.USER_RESPONSE_TIMEOUT_S
        while time.time() < deadline:
            if self.cancel.is_set():
                raise RunAbort("cancelled", "Run cancelled by the user.")
            if self._answered.wait(0.5):
                store.update_run(self.run_id, status="running", pending=None)
                return self._answer or {}
        raise RunAbort("blocked", "Timed out waiting for a human response.")

    def answer(self, approved: bool, text: str = ""):
        self._answer = {"approved": bool(approved), "text": text or ""}
        self._answered.set()
