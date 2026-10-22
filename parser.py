"""Rule-based natural-language -> structured plan. No LLM or API key required.

Produces goal-level actions (search, select_result, add_to_cart, verify_cart ...) rather than
site-specific selectors; the browser layer resolves them against the live page."""
from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from actions import Action, validate_plan
import config
import policy

SITES = {
    "youtube": "https://www.youtube.com", "ebay": "https://www.ebay.com", "amazon": "https://www.amazon.com",
    "google": "https://www.google.com", "duckduckgo": "https://duckduckgo.com", "bing": "https://www.bing.com",
    "wikipedia": "https://www.wikipedia.org", "github": "https://github.com", "reddit": "https://www.reddit.com",
    "stackoverflow": "https://stackoverflow.com", "hacker news": "https://news.ycombinator.com",
}
LOCAL_PAGES = {"login page": "login_page", "form page": "form_page", "success page": "success_page",
               "shop": "shop", "demo shop": "shop", "store": "shop"}
LOCAL_DEFAULT_FIELD = {"login_page": "username", "form_page": "name"}

VERBS = r"verify|check|ensure|confirm|assert|validate|make sure|open|go|visit|launch|navigate|browse|search|look|find|log|login|sign|select|choose|pick|click|tap|press|hit|type|enter|fill|input|write|add|put|apply|set|submit|send|wait|play|watch|buy"
SPLIT_RE = re.compile(
    r"\s*(?:,\s*(?:and\s+)?(?:then\s+)?|\s+and\s+then\s+|\s+then\s+|;\s*|\.\s+(?=[A-Za-z])|\s+and\s+(?=(?:" + VERBS + r")\b))\s*",
    re.I)
BUDGET_RE = re.compile(r"\b(?:under|below|less than|up to|max(?:imum)?(?: price)?(?: of)?|within)\s*(?:a\s+budget\s+of\s*)?[$£€₹]?\s*(\d[\d,]*(?:\.\d+)?)", re.I)
VAGUE_BUDGET_RE = re.compile(r"\b(?:under|below|within|up to)\s+(?:a|the|your)?\s*(?:specified|given|set|certain|defined)?\s*budget\b", re.I)
URL_RE = re.compile(r"(https?://[^\s,]+|(?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|app|co|in|edu|gov|uk)(?:/[^\s,]*)?)", re.I)
QUOTED_RE = re.compile(r"[\"“'‘]([^\"”'’]+)[\"”'’]")
SIZE_RE = re.compile(r"\b(?:size\s*)?(\d{1,2}(?:\.\d)?|xxs|xs|s|m|l|xl|xxl|xxxl|small|medium|large)\b", re.I)
VAGUE_VALUE = re.compile(r"\b(required|appropriate|suitable|correct|right|available|needed|desired|relevant)\b", re.I)


@dataclass
class ParseResult:
    actions: list
    unparsed: list
    notes: list


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" .,;:\"'")


def _site_url(text: str):
    low = text.lower()
    for name, url in SITES.items():
        if re.search(rf"\b{re.escape(name)}(?:\.com)?\b", low):
            return url
    m = URL_RE.search(text)
    if m:
        u = m.group(1).rstrip(".,)")
        return u if u.lower().startswith("http") else "https://" + u
    return None


def _split_budget(query: str):
    """-> (clean query, numeric max price or None, whether a budget was mentioned without an amount)."""
    max_price = None
    m = BUDGET_RE.search(query)
    if m:
        max_price = float(m.group(1).replace(",", ""))
        query = BUDGET_RE.sub("", query)
    vague = bool(VAGUE_BUDGET_RE.search(query)) and max_price is None
    query = VAGUE_BUDGET_RE.sub("", query)
    return _clean(query), max_price, vague


def parse(text: str, start_url: str | None = None) -> ParseResult:
    original = text.strip()
    actions: list[Action] = []
    unparsed: list[str] = []
    notes: list[str] = []
    state = {"opened": False, "local": None, "last_query": None}

    def add(action, target=None, value=None, desc="", **params):
        a = Action(action=action, target=target, value=value, description=desc, params={k: v for k, v in params.items() if v is not None})
        a.requires_confirmation = policy.is_consequential(f"{target or ''} {value or ''} {desc}")
        actions.append(a)

    def open_url(url, desc=""):
        add("open", url, desc=desc or f"Open {url}")
        state["opened"] = True

    legacy = _legacy_form(original)
    if legacy:
        return ParseResult(legacy, [], ["Interpreted as a local demo-form instruction."])

    if start_url:
        try:
            open_url(policy.check_url(start_url))
        except ValueError as e:
            notes.append(str(e))

    for clause in [c for c in SPLIT_RE.split(original) if c and c.strip()]:
        c = _clean(clause)
        low = c.lower()
        c_nov = re.sub(r"^(?:and|then|also|next|finally|after that)\s+", "", c, flags=re.I)
        low = c_nov.lower()

        # ---------- verification ----------
        m = re.match(r"(?:verify|check|ensure|confirm|assert|validate|make sure)(?:\s+that)?\s+(.*)", c_nov, re.I)
        if m:
            rest = m.group(1)
            q = QUOTED_RE.search(rest)
            if re.search(r"\b(cart|basket|bag|trolley)\b", rest, re.I):
                add("verify_cart")
            elif re.search(r"load|play|start|open", rest, re.I) and (re.search(r"\bvideo\b", rest, re.I) or (actions and actions[-1].action == "select_result" and actions[-1].target == "video")):
                add("verify_video")
            elif re.search(r"\burl\b", rest, re.I):
                um = QUOTED_RE.search(rest) or re.search(r"contains?\s+(\S+)", rest, re.I)
                if um:
                    add("verify_url", value=um.group(1))
                else:
                    add("verify_page", desc=f"Verify: {rest}")
            elif q:
                add("verify_text", value=q.group(1))
            else:
                add("verify_page", desc=f"Verify: {rest}")
                notes.append(f"“{rest}” cannot be machine-checked precisely; it will be reported as unverified. Put the expected text in quotes for a hard check.")
            continue

        # ---------- result selection (before generic open/click) ----------
        m = re.match(r"(?:open|select|choose|pick|click(?: on)?|play|watch|go to)\s+(?:a|an|the|one|any)?\s*(?:(?:suitable|relevant|first|top|matching|good|best|appropriate|right|most relevant)\s+)*(product|item|listing|result|video|article|link)s?\b", c_nov, re.I)
        if m:
            kind = {"product": "product", "item": "product", "listing": "product", "video": "video"}.get(m.group(1).lower(), "result")
            add("select_result", kind)
            continue

        # ---------- login ----------
        if re.search(r"\b(log ?in|sign ?in)\b", low) and not re.match(r"(?:open|go to|visit)\b.*\bpage\b", low):
            user = pw = ""
            um = re.search(r"(?:username|user(?:name)?|email)\s*(?:is|=|:|as)?\s*['\"]?([^\s,'\"]+)", c_nov, re.I) or re.search(r"(?:log ?in|sign ?in)\s+(?:with|as)\s+['\"]?([^\s,'\"]+)", c_nov, re.I)
            pm = re.search(r"password\s*(?:is|=|:|as)?\s*['\"]?([^\s,'\"]+)", c_nov, re.I)
            if um and um.group(1).lower() not in ("the", "provided", "test", "my", "valid"):
                user = um.group(1)
            if pm and pm.group(1).lower() not in ("the", "provided", "test", "my"):
                pw = pm.group(1)
            if not user and not state["opened"] and not start_url:
                open_url(f"{config.DEMO_BASE_URL}/login_page", "Open local demo login page")
                state["local"] = "login_page"
            add("login", value=f"{user}\n{pw}", desc="Log in" + (f" as {user}" if user else " (credentials will be requested if required)"))
            continue

        # ---------- add to cart ----------
        if re.search(r"\b(add|put|place)\b.*\b(cart|basket|bag|trolley)\b", low):
            add("add_to_cart")
            continue

        # ---------- option selection ----------
        m = re.match(r"(?:select|choose|pick|set)\s+(?:the\s+|a\s+|an\s+)?(?:(?:required|correct|appropriate|suitable|right|available|needed)\s+)?(size|colou?r|quantity|qty|variant|option|storage|capacity)\b\s*(?:to|as|of|=|:)?\s*(.*)", c_nov, re.I)
        if m:
            ctrl, rest = m.group(1).lower(), _clean(m.group(2))
            qv = QUOTED_RE.search(c_nov)
            value = qv.group(1) if qv else None
            if not value and rest and not VAGUE_VALUE.search(rest):
                sm = SIZE_RE.search(rest)
                value = sm.group(1) if sm and ctrl == "size" else (rest or None)
            if not value and not VAGUE_VALUE.search(c_nov) and re.search(r"size\s*\d", c_nov, re.I):
                value = re.search(r"size\s*(\S+)", c_nov, re.I).group(1)
            add("select_option", ctrl, value)
            if value is None:
                notes.append(f"No specific {ctrl} given; the run will pause and ask you which {ctrl} to choose.")
            continue
        m = re.match(r"(?:select|choose|pick)\s+(?:in\s+)?size\s*(\S+)", c_nov, re.I)
        if m:
            add("select_option", "size", m.group(1))
            continue

        # ---------- filters ----------
        m = re.match(r"(?:apply|set|use|add)\s+(?:the\s+|a\s+|some\s+)?(.*(?:filter|price|budget).*)", c_nov, re.I)
        if m:
            rest = m.group(1)
            bm = BUDGET_RE.search(rest)
            if bm or re.search(r"price|budget", rest, re.I):
                add("apply_filter", "price", str(float(bm.group(1).replace(",", ""))) if bm else None)
            else:
                lab = _clean(re.sub(r"\b(?:filters?|for|by)\b", "", rest, flags=re.I))
                if not lab and any(a.action == "apply_filter" for a in actions):
                    notes.append("Generic “apply filters” skipped: the price filter was already planned. Name a specific filter (e.g. “filter by brand Nike”) to add more.")
                else:
                    add("apply_filter", lab or "filter", None)
            continue

        # ---------- open / navigate ----------
        m = re.match(r"(?:open|go to|go for|go on|visit|launch|navigate to|browse to|load|head to)\s+(?:the\s+)?(.+)", c_nov, re.I)
        if m:
            rest = _clean(m.group(1))
            local = next((v for k, v in LOCAL_PAGES.items() if k in rest.lower()), None)
            url = _site_url(rest)
            if local and not url:
                open_url(f"{config.DEMO_BASE_URL}/{local}", f"Open local demo page /{local}")
                state["local"] = local
            elif url:
                if not (len(actions) == 1 and actions[0].action == "open" and urlparse(actions[0].target).netloc == urlparse(url).netloc):
                    open_url(url)
                    state["local"] = None
            elif state["opened"] or start_url:
                tgt = re.sub(r"\b(?:page|section|tab|website|site|url)\b", "", rest, flags=re.I).strip()
                if tgt:
                    add("click", tgt, desc=f"Navigate to “{rest}”")
                else:
                    notes.append(f"“{c}” refers to the current page; no navigation needed.")
            elif re.fullmatch(r"(?:the )?(?:page|website|site|url)", rest, re.I):
                notes.append(f"“{c}” refers to the target URL; no separate step needed.")
            elif re.fullmatch(r"[A-Za-z0-9-]+", rest):
                open_url(f"https://www.{rest.lower()}.com", f"Open {rest} (guessed https://www.{rest.lower()}.com)")
                notes.append(f"Site “{rest}” is not known; guessed www.{rest.lower()}.com. Provide a full URL for certainty.")
            else:
                unparsed.append(clause)
            continue

        # ---------- search ----------
        m = re.match(r"(?:search|look up|look for|find|browse)\s+(?:for\s+)?(.+?)(?:\s+(?:on|in|at)\s+(?:the\s+)?([A-Za-z.]+))?$", c_nov, re.I)
        if m:
            q_raw, site = m.group(1), m.group(2)
            site_url = _site_url(site) if site else None
            if site_url and not state["opened"]:
                open_url(site_url)
            elif site and not site_url:
                q_raw = f"{q_raw} {site}"
            q, max_price, vague = _split_budget(q_raw)
            q = re.sub(r"^(?:for\s+)", "", q, flags=re.I)
            if not q:
                unparsed.append(clause)
                continue
            if not state["opened"]:
                notes.append("No website specified: provide a target URL or say e.g. “Open eBay”.")
            add("search", value=q, max_price=max_price)
            state["last_query"] = q
            if vague:
                add("apply_filter", "price", None, desc="Apply the budget filter (amount will be requested)")
            elif max_price is not None:
                add("apply_filter", "price", str(max_price), desc=f"Apply max price filter ≤ {max_price:g}")
            continue

        # ---------- type / fill ----------
        m = re.match(r"(?:type|enter|fill(?: in)?|input|write)\s+(.+?)\s+(?:in|into|to|on)\s+(?:the\s+)?(.+)", c_nov, re.I)
        if m:
            val = _clean(m.group(1))
            qv = QUOTED_RE.search(m.group(1))
            add("type", _clean(m.group(2)), qv.group(1) if qv else val)
            continue
        m = re.match(r"(?:type|enter|input|write)\s+(.+)", c_nov, re.I)
        if m:
            qv = QUOTED_RE.search(m.group(1))
            field = LOCAL_DEFAULT_FIELD.get(state["local"] or "", "input field")
            add("type", field, qv.group(1) if qv else _clean(m.group(1)))
            continue

        # ---------- click / press ----------
        m = re.match(r"(?:click|tap|hit|press)\s+(?:on\s+)?(?:the\s+)?(.+)", c_nov, re.I)
        if m:
            rest = _clean(m.group(1))
            if re.fullmatch(r"(?:enter|return|tab|escape|esc|space)(?: key)?", rest, re.I):
                add("press_key", value=rest.split()[0].capitalize())
            else:
                add("click", re.sub(r"\b(?:button|link)\b", "", rest, flags=re.I).strip() or rest, desc=f"Click “{rest}”")
            continue

        if re.match(r"(?:submit|send)\b", low):
            add("click", "submit", desc="Click submit")
            continue
        if re.match(r"wait\b", low):
            add("wait")
            continue
        unparsed.append(clause)

    return ParseResult(actions, unparsed, notes)


def _legacy_form(text: str):
    """Backwards-compatible handling of the original local-demo form phrases."""
    low = text.lower()
    if not (("form" in low or "fill" in low) and re.search(r"name as|email as", low)):
        return None
    acts = [Action("open", f"{config.DEMO_BASE_URL}/form_page", description="Open local demo form page")]
    nm = re.search(r"name as (\w+)", text, re.I)
    em = re.search(r"email as ([\w@.+-]+)", text, re.I)
    if nm:
        acts.append(Action("type", "name", nm.group(1)))
    if em:
        acts.append(Action("type", "email", em.group(1)))
    if re.search(r"\bfemale\b", low):
        acts.append(Action("click", "female"))
    elif re.search(r"\bmale\b", low):
        acts.append(Action("click", "male"))
    for role in ("student", "developer", "tester"):
        if role in low:
            acts.append(Action("select_option", "role", role))
            break
    if "submit" in low:
        acts.append(Action("click", "submit"))
        acts.append(Action("verify_url", value="success_page"))
    return acts


def parse_instruction(text: str, start_url: str | None = None) -> list:
    """Compatibility wrapper: returns the validated list of Actions."""
    res = parse(text, start_url)
    return validate_plan(res.actions)
