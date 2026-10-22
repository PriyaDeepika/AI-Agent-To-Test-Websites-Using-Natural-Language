"""Structured, validated action schema. The agent never executes LLM-generated code:
plans are lists of these whitelisted actions, validated before anything runs."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional

# action -> (needs target, needs value)
ACTION_SPECS = {
    "open":          (True,  False),  # target = URL
    "search":        (False, True),   # value = query
    "click":         (True,  False),  # target = natural-language element description
    "type":          (True,  True),   # target = field description, value = text
    "select_option": (True,  False),  # target = control description ("size"), value = option (None -> ask user)
    "select_result": (False, False),  # target = kind: product | video | article | result
    "login":         (False, False),  # value = "username\npassword" (either may be empty)
    "add_to_cart":   (False, False),
    "apply_filter":  (True,  False),  # target = "price" | filter label; value = amount/label
    "press_key":     (False, True),
    "wait":          (False, False),
    "verify_text":   (False, True),   # value = text that must be present
    "verify_url":    (False, True),   # value = substring that must be in URL
    "verify_cart":   (False, False),  # selected item must appear in cart
    "verify_video":  (False, False),  # a video must be loaded/playing
    "verify_page":   (False, False),  # weak check: page loaded without error (reported as unverified)
}
VERIFY_ACTIONS = {a for a in ACTION_SPECS if a.startswith("verify_")}


class PlanError(ValueError):
    pass


@dataclass
class Action:
    action: str
    target: Optional[str] = None
    value: Optional[str] = None
    description: str = ""
    requires_confirmation: bool = False
    params: dict = field(default_factory=dict)  # e.g. {"max_price": 50}

    def to_dict(self):
        return asdict(self)

    def public(self):
        """Dict safe for display/storage (credentials masked)."""
        d = self.to_dict()
        if self.action == "login" and self.value:
            user, _, pw = self.value.partition("\n")
            d["value"] = f"{user} / {'••••••' if pw else '(no password)'}"
        return d


def validate_plan(raw: list, max_len: int = 40) -> list[Action]:
    if not isinstance(raw, list) or not raw:
        raise PlanError("Plan is empty.")
    if len(raw) > max_len:
        raise PlanError(f"Plan has {len(raw)} steps; the limit is {max_len}.")
    out = []
    for i, item in enumerate(raw, 1):
        if isinstance(item, Action):
            a = item
        elif isinstance(item, dict):
            known = {k: item.get(k) for k in ("action", "target", "value", "description")}
            a = Action(**{k: v for k, v in known.items() if v is not None},
                       requires_confirmation=bool(item.get("requires_confirmation")),
                       params=item.get("params") or {}) if known.get("action") else None
            if a is None:
                raise PlanError(f"Step {i}: missing 'action'.")
        else:
            raise PlanError(f"Step {i}: not an object.")
        if a.action not in ACTION_SPECS:
            raise PlanError(f"Step {i}: unsupported action '{a.action}'.")
        needs_t, needs_v = ACTION_SPECS[a.action]
        if needs_t and not a.target:
            raise PlanError(f"Step {i} ({a.action}): 'target' is required.")
        if needs_v and a.value in (None, ""):
            raise PlanError(f"Step {i} ({a.action}): 'value' is required.")
        for fld in ("target", "value", "description"):
            v = getattr(a, fld)
            if v is not None:
                if not isinstance(v, str):
                    setattr(a, fld, str(v))
                elif len(v) > 500:
                    raise PlanError(f"Step {i}: '{fld}' is too long.")
        if not a.description:
            a.description = default_description(a)
        out.append(a)
    return out


def default_description(a: Action) -> str:
    t, v = a.target, a.value
    return {
        "open": f"Open {t}",
        "search": f"Search for “{v}”",
        "click": f"Click {t}",
        "type": f"Type “{v}” into {t}",
        "select_option": f"Choose {('“' + v + '”') if v else 'an option'} for {t}",
        "select_result": f"Select a relevant {t or 'result'}",
        "login": "Log in",
        "add_to_cart": "Add the item to the cart",
        "apply_filter": f"Apply filter: {t}{(' ' + v) if v else ''}",
        "press_key": f"Press {v}",
        "wait": "Wait for the page to settle",
        "verify_text": f"Verify the page shows “{v}”",
        "verify_url": f"Verify the URL contains “{v}”",
        "verify_cart": "Verify the selected item is in the cart",
        "verify_video": "Verify a video has loaded",
        "verify_page": "Verify the page loaded without errors",
    }.get(a.action, a.action)
