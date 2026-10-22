"""LangGraph state machine:  plan → observe → act → verify → (recover → observe) … → report.

Graph state is small and serialisable; live objects (browser page, shared ctx) live in RunRuntime,
which is passed through config["configurable"]["rt"]."""
from __future__ import annotations
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
import config as settings
import store, policy
from actions import validate_plan, PlanError, VERIFY_ACTIONS
from observer import observe
from runtime import RunAbort
from skills import SKILLS, NeedsUser, StepFailed, dismiss_overlays, settle
import parser as rule_parser
import llm_parser


class AgentState(TypedDict, total=False):
    instruction: str
    start_url: Optional[str]
    cursor: int
    attempts: int
    status: str            # running | failed | cancelled | blocked | done
    message: str
    pending: Optional[dict]
    error: Optional[dict]
    outcome: Optional[dict]
    planner: str
    notes: list
    plan_len: int
    asks: int


def _rt(config):
    return config["configurable"]["rt"]


# ------------------------------------------------------------------ nodes
def plan_node(state: AgentState, config):
    rt = _rt(config)
    planner, notes = "rules", []
    plan = None
    if llm_parser.available():
        try:
            plan = llm_parser.parse_instruction_llm(state["instruction"], state.get("start_url"))
            planner = "llm"
        except Exception as e:
            notes.append(f"LLM planner unavailable or invalid output ({str(e)[:90]}); used the rule-based parser.")
    if plan is None:
        res = rule_parser.parse(state["instruction"], state.get("start_url"))
        notes += res.notes
        if res.unparsed:
            notes.append("Not understood (ignored): " + "; ".join(f"“{u}”" for u in res.unparsed))
        try:
            plan = validate_plan(res.actions)
        except PlanError as e:
            msg = f"I could not turn that instruction into a plan: {e} Try phrasing like “Open eBay, search for …, select a product, add it to the cart, verify the cart”, or set GEMINI_API_KEY for complex instructions."
            store.update_run(rt.run_id, notes=notes, planner=planner)
            return {"status": "failed", "message": msg, "planner": planner, "notes": notes}
    # policy: validate every URL in the plan before anything runs
    for a in plan:
        if a.action == "open":
            try:
                a.target = policy.check_url(a.target)
            except ValueError as e:
                return {"status": "failed", "message": f"Plan rejected by safety policy: {e}", "planner": planner, "notes": notes}
    rt.actions[:] = plan
    store.add_steps(rt.run_id, plan)
    store.update_run(rt.run_id, planner=planner, notes=notes)
    return {"cursor": 0, "attempts": 0, "plan_len": len(plan), "status": "running", "planner": planner, "notes": notes, "pending": None, "error": None}


def observe_node(state: AgentState, config):
    rt = _rt(config)
    rt.check_limits()
    store.update_step(rt.run_id, state["cursor"], status="running", started=_now_if_new(rt, state["cursor"]))
    try:
        rt.obs = observe(rt.page)
    except Exception as e:
        # Blank tab before the first navigation is fine for 'open'
        if rt.actions[state["cursor"]].action != "open":
            return {"error": {"message": f"Could not observe the page: {e}", "recoverable": True}, "pending": None}
        rt.obs = None
    if rt.obs is not None and rt.actions[state["cursor"]].action != "open":
        reason = policy.looks_blocked(rt.obs.text, rt.obs.title)
        if reason:
            return {"pending": {"kind": "human", "field": "human", "options": [], "secret": False,
                                "prompt": reason + " I will not try to bypass it. Resolve it in the browser window (run non-headless), then click Continue."}}
    return {"pending": None, "error": None}


def act_node(state: AgentState, config):
    rt = _rt(config)
    a = rt.actions[state["cursor"]]
    rt.total_actions += 1
    try:
        out = SKILLS[a.action](rt, rt.obs, a)
        return {"outcome": {"status": out.status, "detail": out.detail, "evidence": out.evidence, "selector": out.selector}, "error": None, "pending": None}
    except NeedsUser as n:
        return {"pending": {"kind": n.kind, "field": n.field, "options": n.options, "secret": n.secret, "prompt": n.prompt}, "outcome": None, "error": None}
    except StepFailed as f:
        return {"error": {"message": str(f), "recoverable": f.recoverable}, "outcome": None, "pending": None}
    except Exception as e:   # Playwright timeouts, closed pages, etc.
        text = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
        return {"error": {"message": f"{type(e).__name__}: {text}", "recoverable": "closed" not in text.lower()}, "outcome": None, "pending": None}


def wait_user_node(state: AgentState, config):
    rt = _rt(config)
    p = state["pending"]
    asks = state.get("asks", 0) + 1
    if p["kind"] == "input" and asks > 3:
        return {"status": "blocked", "pending": None,
                "message": f"Stopped at step {state['cursor'] + 1}: still no usable value after 3 requests ({p['prompt'][:120]})"}
    if p["kind"] == "human" and asks > 3:
        return {"status": "blocked", "pending": None,
                "message": f"Stopped at step {state['cursor'] + 1}: the site still shows a human-verification barrier after 3 attempts. I do not bypass CAPTCHAs or access controls."}
    ans = rt.ask_user(p)
    a = rt.actions[state["cursor"]]
    if p["kind"] in ("confirm", "human") and not ans.get("approved"):
        reason = "You declined the confirmation." if p["kind"] == "confirm" else "The human-verification step was not completed."
        return {"status": "blocked", "message": f"Stopped at step {state['cursor'] + 1}: {reason}", "pending": None}
    if p["kind"] == "confirm":
        a.params["confirmed"] = True
    elif p["kind"] == "input":
        text = (ans.get("text") or "").strip()
        if not text:
            return {"status": "blocked", "message": "No value was provided for the requested input.", "pending": None}
        if p["field"] == "username":
            a.value = f"{text}\n{(a.value or '').partition(chr(10))[2]}"
        elif p["field"] == "password":
            a.value = f"{(a.value or '').partition(chr(10))[0]}\n{text}"
        else:
            a.value = text
    return {"pending": None, "error": None, "asks": asks}


def verify_node(state: AgentState, config):
    rt = _rt(config)
    i, out = state["cursor"], state["outcome"]
    shot = rt.screenshot(f"step-{i + 1:02d}.png")
    ev = dict(out["evidence"])
    ev.setdefault("url", rt.page.url)
    store.update_step(rt.run_id, i, status=out["status"], detail=out["detail"], screenshot=shot, url=rt.page.url,
                      evidence=ev, selector=out["selector"], attempts=state.get("attempts", 0), finished=_now())
    return {"cursor": i + 1, "attempts": 0, "asks": 0, "outcome": None}


def recover_node(state: AgentState, config):
    rt = _rt(config)
    i, err, attempts = state["cursor"], state["error"], state.get("attempts", 0)
    a = rt.actions[i]
    hard = (not err["recoverable"]) or attempts >= settings.MAX_STEP_RETRIES or a.action in VERIFY_ACTIONS and attempts >= 1
    shot = rt.screenshot(f"step-{i + 1:02d}-{'failed' if hard else 'retry'}.png")
    if hard:
        store.update_step(rt.run_id, i, status="failed", error=err["message"], screenshot=shot, url=rt.page.url,
                          attempts=attempts, finished=_now())
        return {"status": "failed", "message": f"Step {i + 1} failed: {err['message']}", "error": None}
    # bounded recovery strategies, escalating with each attempt
    store.update_step(rt.run_id, i, error=f"Attempt {attempts + 1} failed: {err['message']} — recovering…", attempts=attempts + 1)
    try:
        dismiss_overlays(rt)
        if attempts == 0:
            rt.page.mouse.wheel(0, 600)
            rt.page.wait_for_timeout(800)
        else:
            if a.action != "open":
                try:
                    rt.page.reload(wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
            rt.page.wait_for_timeout(1500)
        settle(rt.page)
    except Exception:
        pass
    return {"attempts": attempts + 1, "error": None}


def report_node(state: AgentState, config):
    return {}


# ------------------------------------------------------------------ routing
def _now():
    import time; return time.time()


def _now_if_new(rt, idx):
    return _now()


def after_plan(state):
    return "observe" if state.get("status") == "running" else "report"


def after_observe(state):
    if state.get("pending"):
        return "wait_user"
    return "recover" if state.get("error") else "act"


def after_act(state):
    if state.get("pending"):
        return "wait_user"
    return "recover" if state.get("error") else "verify"


def after_wait(state):
    return "report" if state.get("status") in ("blocked", "failed", "cancelled") else "observe"


def after_verify(state):
    return "observe" if state["cursor"] < state["plan_len"] else "report"


def after_recover(state):
    return "report" if state.get("status") == "failed" else "observe"


def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [("plan", plan_node), ("observe", observe_node), ("act", act_node), ("wait_user", wait_user_node),
                     ("verify", verify_node), ("recover", recover_node), ("report", report_node)]:
        g.add_node(name, fn)
    g.set_entry_point("plan")
    g.add_conditional_edges("plan", after_plan, {"observe": "observe", "report": "report"})
    g.add_conditional_edges("observe", after_observe, {"wait_user": "wait_user", "recover": "recover", "act": "act"})
    g.add_conditional_edges("act", after_act, {"wait_user": "wait_user", "recover": "recover", "verify": "verify"})
    g.add_conditional_edges("wait_user", after_wait, {"report": "report", "observe": "observe"})
    g.add_conditional_edges("verify", after_verify, {"observe": "observe", "report": "report"})
    g.add_conditional_edges("recover", after_recover, {"report": "report", "observe": "observe"})
    g.add_edge("report", END)
    return g.compile()


agent_workflow = build_graph()
