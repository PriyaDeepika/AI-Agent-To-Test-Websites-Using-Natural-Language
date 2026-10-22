"""Generic, site-agnostic browser skills. Each skill resolves a goal-level action against the *live* page
(observe -> act -> verify) and returns an Outcome, or raises NeedsUser / StepFailed."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse
import config
import policy
from observer import observe, match_score, tokens, Observation


class NeedsUser(Exception):
    """Execution must pause for a human: confirmation, missing input, or CAPTCHA."""
    def __init__(self, prompt, kind="input", field="value", options=None, secret=False):
        super().__init__(prompt)
        self.prompt, self.kind, self.field, self.options, self.secret = prompt, kind, field, options or [], secret


class StepFailed(Exception):
    def __init__(self, message, recoverable=True):
        super().__init__(message)
        self.recoverable = recoverable


@dataclass
class Outcome:
    status: str                      # passed | unverified
    detail: str = ""
    evidence: dict = field(default_factory=dict)
    selector: str = ""               # best-effort stable selector, used for script export


NAV_JUNK = re.compile(r"\b(sign ?in|log ?in|register|help|contact|my ebay|sell|privacy|terms|cookie|feedback|advertis|see all|shop by|categor|sort|filter|watchlist|notification|account|feedback|skip to|about us|customer service|gift card)\b", re.I)
ITEM_HREF = re.compile(r"/itm/|/dp/|/gp/product|/product|/p/|/item|/ip/|/listing|/pd/|/sku|/prd|/products/", re.I)
VIDEO_HREF = re.compile(r"/watch\?v=|/video|/videos/", re.I)
CART_WORDS = r"(?:cart|basket|bag|trolley)"
EMPTY_CART = re.compile(r"(?:your\s+(?:shopping\s+)?" + CART_WORDS + r"\s+is\s+empty|no items in (?:your )?" + CART_WORDS + r"|" + CART_WORDS + r"\s+is empty)", re.I)
PRICE_NUM = re.compile(r"(\d[\d,]*(?:\.\d{1,2})?)")


# ---------------------------------------------------------------- helpers
def selector_hint(el: dict) -> str:
    if el.get("dom_id"):
        return f"#{el['dom_id']}"
    if el.get("name"):
        return f'{el["tag"]}[name="{el["name"]}"]'
    t = (el.get("text") or el.get("label") or "").strip()
    if t and len(t) < 60:
        return f'text="{t}"'
    return el["tag"]


def loc(rt, el):
    return rt.page.locator(f'[data-agent-id="{el["id"]}"]').first


def settle(page, ms=1500):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=ms + 1500)
    except Exception:
        pass
    page.wait_for_timeout(250)


def safe_click(rt, el, timeout=None):
    l = loc(rt, el)
    timeout = timeout or config.ACTION_TIMEOUT_MS
    try:
        l.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    before_pages = len(rt.page.context.pages)
    try:
        l.click(timeout=timeout)
    except Exception as first:
        try:   # bounded fallback: DOM click (works through some overlays); still a real user-level element
            l.evaluate("e => e.click()")
        except Exception:
            raise StepFailed(f"Could not click “{(el.get('text') or el.get('label') or el['tag'])[:60]}”: {str(first).splitlines()[0][:140]}")
    rt.page.wait_for_timeout(300)
    if len(rt.page.context.pages) > before_pages:      # link opened a new tab: follow it
        rt.adopt_page(rt.page.context.pages[-1])
    settle(rt.page)


def need_clear(obs: Observation):
    reason = policy.looks_blocked(obs.text, obs.title)
    if reason:
        raise NeedsUser(reason + " I will not try to bypass it. Solve it in the browser window (run non-headless), then click Continue.",
                        kind="human", field="human")


def numeric_price(s: str):
    m = PRICE_NUM.search(s or "")
    try:
        return float(m.group(1).replace(",", "")) if m else None
    except ValueError:
        return None


def title_of(el: dict) -> str:
    t = el.get("text") or el.get("title") or el.get("label") or ""
    return re.sub(r"\s+", " ", t).strip()


def cart_count(obs: Observation):
    best = None
    for el in obs.elements:
        hay = f"{el['label']} {el['title']} {el['href']} {el['dom_id']} {el['cls']}".lower()
        if re.search(CART_WORDS, hay):
            m = re.search(r"\b(\d{1,3})\b", f"{el['text']} {el['label']}")
            if m:
                best = max(best or 0, int(m.group(1)))
    return best


def dismiss_overlays(rt):
    """Best-effort: close cookie / consent banners (never touches purchase-like controls)."""
    order = ["reject all", "decline", "no thanks", "not now", "got it", "close", "dismiss", "accept all", "accept", "i agree", "agree", "ok"]
    try:
        obs = observe(rt.page)
    except Exception:
        return False
    cands = [e for e in obs.elements if e["overlay"] and e["tag"] in ("button", "a") or e["overlay"] and e["role"] == "button"]
    for want in order:
        for e in cands:
            t = (e["text"] or e["label"]).strip().lower()
            if t == want or t.startswith(want + " ") and len(t) < 28:
                if policy.is_consequential(t):
                    continue
                try:
                    loc(rt, e).click(timeout=2500)
                    rt.page.wait_for_timeout(400)
                    return True
                except Exception:
                    continue
    return False


# ---------------------------------------------------------------- skills
def do_open(rt, obs, a):
    try:
        url = policy.check_url(a.target)
    except ValueError as e:
        raise StepFailed(str(e), recoverable=False)
    try:
        resp = rt.page.goto(url, wait_until="domcontentloaded", timeout=config.NAV_TIMEOUT_MS)
    except Exception as e:
        raise StepFailed(f"Navigation to {url} failed: {str(e).splitlines()[0][:200]}")
    settle(rt.page)
    status = resp.status if resp else None
    dismiss_overlays(rt)
    new = observe(rt.page)
    need_clear(new)
    if status and status >= 400:
        raise StepFailed(f"{url} responded with HTTP {status}.", recoverable=status >= 500)
    if not new.title and len(new.text) < 20:
        raise StepFailed("The page loaded but is empty.")
    return Outcome("passed", f"Loaded “{new.title or url}”" + (f" (HTTP {status})" if status else ""),
                   {"url": new.url, "title": new.title, "http_status": status})


def _search_input(obs):
    best, best_s = None, 0
    for el in obs.elements:
        if el["tag"] not in ("input", "textarea") and el["role"] not in ("searchbox", "combobox"):
            continue
        if el["type"] in ("password", "hidden", "checkbox", "radio", "submit", "button", "file", "email") or el["disabled"]:
            continue
        hay = f"{el['label']} {el['placeholder']} {el['name']} {el['dom_id']} {el['title']} {el['cls']}".lower()
        s = 0
        if el["type"] == "search" or el["role"] == "searchbox":
            s += 5
        if re.search(r"search|query|keyword|find|lookup", hay):
            s += 4
        if el["name"] in ("q", "k", "s", "query", "search_query", "_nkw", "field-keywords"):
            s += 3
        if el["role"] == "combobox":
            s += 1
        if el["in_chrome"]:
            s += 1
        if re.search(r"login|password|user|email|newsletter|zip|postal", hay):
            s -= 6
        if s > best_s:
            best, best_s = el, s
    return best if best_s >= 4 else None


def do_search(rt, obs, a):
    q = a.value
    box = _search_input(obs)
    if not box:   # maybe the search field is behind an icon
        btn = max((e for e in obs.elements if e["tag"] in ("button", "a") or e["role"] == "button"),
                  key=lambda e: match_score(e, "search"), default=None)
        if btn and match_score(btn, "search") >= 3:
            safe_click(rt, btn)
            obs = observe(rt.page)
            box = _search_input(obs)
    if not box:
        raise StepFailed("No search box found on this page.")
    before_url, before_text = obs.url, obs.text
    l = loc(rt, box)
    try:
        l.click(timeout=4000)
        l.fill(q, timeout=4000)
    except Exception:
        try:
            l.click(timeout=3000)
            rt.page.keyboard.type(q, delay=40)
        except Exception as e:
            raise StepFailed(f"Could not type into the search box: {str(e).splitlines()[0][:120]}")
    rt.page.keyboard.press("Enter")
    settle(rt.page, 3000)
    new = observe(rt.page)
    need_clear(new)
    qt = [t for t in tokens(q) if len(t) > 2] or tokens(q)
    hits = [t for t in qt if t in new.text.lower()]
    changed = new.url != before_url or new.text != before_text
    if not changed:
        raise StepFailed("Submitting the search did not change the page.")
    if qt and len(hits) < max(1, len(qt) // 2):
        raise StepFailed(f"Search submitted but results do not mention the query terms (found {hits or 'none'} of {qt}).")
    rt.ctx["query"] = q
    return Outcome("passed", f"Searched for “{q}”; results mention {len(hits)}/{len(qt)} query terms.",
                   {"url": new.url, "query": q, "matched_terms": hits}, selector_hint(box))


def do_select_result(rt, obs, a):
    kind = (a.target or "result").lower()
    query = rt.ctx.get("query") or ""
    qt = [t for t in tokens(query) if len(t) > 2]
    max_price = rt.ctx.get("max_price")
    skip = set(rt.ctx.get("rejected_hrefs", []))
    here = urlparse(obs.url).path
    scored = []
    for el in obs.elements:
        if el["tag"] != "a" or not el["href"] or el["href"].startswith(("javascript:", "mailto:")) or "#" in el["href"].split("?")[0][-1:]:
            continue
        if el["href"] in skip or el["disabled"]:
            continue
        t = title_of(el)
        if len(t) < 10 or NAV_JUNK.search(t[:60]) or (el["in_chrome"] and kind != "result"):
            continue
        if urlparse(el["href"]).path == here and "?" not in el["href"]:
            continue
        hay = f"{t} {el['label']} {el['title']}".lower()
        hits = [x for x in qt if x in hay]
        s = 2.0 * len(hits)
        structural = (kind == "product" and bool(ITEM_HREF.search(el["href"]))) or (kind == "video" and bool(VIDEO_HREF.search(el["href"])))
        if qt and not hits and not structural:     # the site's own search already vouches for structurally valid item/video links
            continue
        if kind == "product":
            s += 4 if ITEM_HREF.search(el["href"]) else 0
            s += 2 if el["price_text"] else 0
        elif kind == "video":
            s += 5 if VIDEO_HREF.search(el["href"]) else (-2 if "/shorts/" in el["href"] else -4)
        else:
            s += 1 if not el["in_chrome"] else 0
        price = numeric_price(el["price_text"])
        if max_price is not None and price is not None and price > float(max_price):
            continue
        if el["sponsored"]:
            s -= 1.5
        s -= el["y"] / 6000
        scored.append((s, el, t, price))
    if not scored:
        raise StepFailed(f"No suitable {kind} found among the visible results" + (f" (matching “{query}”" + (f", ≤ {max_price}" if max_price else "") + ")" if query else "") + ".")
    scored.sort(key=lambda x: -x[0])
    s, el, t, price = scored[0]
    before_url = obs.url
    safe_click(rt, el)
    new = observe(rt.page)
    need_clear(new)
    sig = [w for w in tokens(t) if len(w) > 3][:8]
    hits = [w for w in sig if w in new.text.lower()]
    if new.url == before_url or (sig and not hits):
        rt.ctx.setdefault("rejected_hrefs", []).append(el["href"])
        try:
            rt.page.go_back(wait_until="domcontentloaded", timeout=8000)
        except Exception:
            pass
        raise StepFailed(f"Opened “{t[:60]}” but it did not load as expected (URL unchanged or title words missing); will try the next candidate.")
    m = re.search(r"(\d{9,})", el["href"])
    rt.ctx["selected_item"] = {"title": t, "href": el["href"], "price": el["price_text"] or None,
                               "item_id": m.group(1) if m else None, "kind": kind}
    rt.ctx["rejected_hrefs"] = []
    return Outcome("passed", f"Opened “{t[:90]}”" + (f" ({el['price_text']})" if el["price_text"] else ""),
                   {"selected_title": t, "price": el["price_text"] or None, "from_url": before_url, "url": new.url,
                    "page_title": new.title, "candidates_considered": len(scored)}, selector_hint(el))


def _choose_native(options, val):
    v = val.lower().strip()
    ok = [(i, o) for i, o in enumerate(options) if not o["disabled"] and not re.match(r"^\s*(select|choose|please|-)", o["text"], re.I)]
    for pred in (lambda t: t == v, lambda t: t.startswith(v) and not re.match(r"[\d.]", t[len(v):len(v) + 1] or "x"),
                 lambda t: re.search(rf"(?<![\d.]){re.escape(v)}(?![\d.])", t) is not None):
        for i, o in ok:
            if pred(o["text"].lower()):
                return i, o
    return None, None


def do_select_option(rt, obs, a):
    ctrl, val = a.target.lower(), a.value
    # discover what is selectable, so the user can be asked a precise question when needed
    selects = [e for e in obs.elements if e["tag"] == "select" and match_score(e, ctrl) >= 3]
    avail = [o["text"] for e in selects for o in (e["options"] or []) if not o["disabled"] and not re.match(r"^\s*(select|choose|please|-)", o["text"], re.I)]
    if val is None:
        raise NeedsUser(f"Which {ctrl} should I choose?" + (f" Available on this page: {', '.join(avail[:15])}." if avail else ""),
                        field="value", options=avail[:15])
    for e in selects:
        i, o = _choose_native(e["options"] or [], val)
        if o is not None:
            l = loc(rt, e)
            try:
                l.select_option(value=o["value"], timeout=4000) if o["value"] else l.select_option(index=i, timeout=4000)
            except Exception as ex:
                raise StepFailed(f"Could not select “{o['text']}”: {str(ex).splitlines()[0][:120]}")
            chosen = l.evaluate("e => e.options[e.selectedIndex] ? e.options[e.selectedIndex].text.trim() : ''")
            if chosen.lower() != o["text"].lower():
                raise StepFailed(f"Selected value reads back as “{chosen}”, expected “{o['text']}”.")
            rt.ctx.setdefault("options", {})[ctrl] = val
            return Outcome("passed", f"{ctrl.title()} set to “{chosen}”", {"selected": chosen, "available": avail[:15]}, selector_hint(e))
    if selects:
        raise NeedsUser(f"“{val}” is not available for {ctrl}. Available: {', '.join(avail[:15]) or 'none listed'}. Which should I choose?",
                        field="value", options=avail[:15])
    # buttons / radios / swatches whose container mentions the control name
    vre = re.compile(rf"^(?:{re.escape(val)})$|(?<![\d.]){re.escape(val)}(?![\d.])", re.I)
    cands = [e for e in obs.elements if e["tag"] in ("button", "label", "a", "input") or e["role"] in ("radio", "option", "button")]
    cands = [e for e in cands if not e["disabled"] and re.search(rf"\b{re.escape(ctrl)}\b", e["ctx"].lower() + " " + e["label"].lower())
             and (vre.fullmatch((e["text"] or e["label"] or e["value"]).strip()) or (len(e["text"]) < 20 and vre.search(e["text"] or "")))]
    if cands:
        e = sorted(cands, key=lambda x: len(x["text"]))[0]
        safe_click(rt, e)
        new = observe(rt.page)
        again = [x for x in new.elements if (x["text"] or x["label"]).strip() == (e["text"] or e["label"]).strip()]
        on = any(x["checked"] or x["selected"] in ("true", "checked") or re.search(r"\b(selected|active|checked|chosen)\b", x["cls"]) for x in again)
        rt.ctx.setdefault("options", {})[ctrl] = val
        return Outcome("passed" if on else "unverified",
                       f"Clicked {ctrl} “{val}”" + ("" if on else " (page does not expose a selected state, so this could not be read back)"),
                       {"selected": val, "read_back": on}, selector_hint(e))
    # custom dropdown: open the trigger for this control, then pick the option
    trig = [e for e in obs.elements if (e["role"] in ("combobox", "listbox", "button") or e["haspopup"] or e["tag"] == "button")
            and re.search(rf"\b{re.escape(ctrl)}\b", (e["label"] + " " + e["ctx"][:120]).lower()) and not e["disabled"]]
    trig.sort(key=lambda x: -match_score(x, ctrl))
    for t in trig[:3]:
        safe_click(rt, t)
        o2 = observe(rt.page)
        opts = [x for x in o2.elements if (x["role"] in ("option", "menuitem", "radio") or x["tag"] == "li" or x["tag"] == "a" or x["tag"] == "button")
                and not x["disabled"] and vre.search((x["text"] or x["label"]).strip()) and len((x["text"] or x["label"])) < 40]
        if opts:
            pick = sorted(opts, key=lambda x: len(x["text"]))[0]
            safe_click(rt, pick)
            o3 = observe(rt.page)
            confirmed = bool(re.search(rf"(?<![\d.]){re.escape(val)}(?![\d.])", " ".join(x["text"] for x in o3.elements if x["role"] in ("combobox", "button", "listbox"))))
            rt.ctx.setdefault("options", {})[ctrl] = val
            return Outcome("passed" if confirmed else "unverified", f"Opened the {ctrl} dropdown and picked “{val}”" + ("" if confirmed else " (selection could not be read back)"),
                           {"selected": val, "read_back": confirmed}, selector_hint(pick))
        try:
            rt.page.keyboard.press("Escape")
        except Exception:
            pass
    raise StepFailed(f"No {ctrl} control offering “{val}” was found on this page.")


def do_add_to_cart(rt, obs, a):
    rx = re.compile(r"add\s+(?:item\s+)?to\s+(?:my\s+|your\s+)?" + CART_WORDS, re.I)
    cands = [e for e in obs.elements if rx.search(f"{e['text']} {e['label']} {e['value']}") and not e["disabled"]
             and not policy.is_consequential(e["text"])]
    if not cands:
        raise StepFailed("No “Add to cart” control found on this page.")
    e = sorted(cands, key=lambda x: (not x["in_view"], x["y"]))[0]
    before = cart_count(obs)
    before_text = obs.text.lower()
    safe_click(rt, e)
    new = observe(rt.page)
    need_clear(new)
    low = new.text.lower()
    err = re.search(r"(please (?:select|choose)[^.]{0,60}|select (?:a|an|your) (?:size|colou?r|option|variant)[^.]{0,40}|required[^.]{0,40}(?:size|option))", low)
    if err and err.group(0) not in before_text:
        raise StepFailed(f"The site requires an option before adding to cart: “{err.group(0)[:100]}”. Add a ‘choose size …’ step to the instruction.", recoverable=False)
    signals = []
    if re.search(CART_WORDS, urlparse(new.url).path, re.I) and new.url != obs.url:
        signals.append("navigated to a cart page")
    after = cart_count(new)
    if after is not None and (before is None or after > before):
        signals.append(f"cart badge {before or 0} → {after}")
    conf = re.search(r"(added to (?:your |my )?" + CART_WORDS + r"|(?:item|items|product)s? (?:has|have|was|were)? ?(?:been )?added|in your " + CART_WORDS + r"|view (?:cart|basket|bag)|go to (?:cart|basket|bag)|continue shopping)", low)
    if conf and conf.group(0) not in before_text:
        signals.append(f"page says “{conf.group(0)}”")
    rt.ctx["add_clicked"] = True
    if signals:
        return Outcome("passed", "Add to cart confirmed: " + "; ".join(signals), {"signals": signals, "url": new.url}, selector_hint(e))
    return Outcome("unverified", "Clicked “Add to cart” but the page showed no confirmation signal; the cart check will decide.",
                   {"url": new.url}, selector_hint(e))


def do_verify_cart(rt, obs, a):
    cur = obs
    if not re.search(CART_WORDS, urlparse(cur.url).path, re.I):
        links = [e for e in cur.elements if re.search(CART_WORDS, f"{e['href']} {e['label']} {e['text']} {e['title']}", re.I)
                 and not re.search(r"add\s+to", f"{e['text']} {e['label']}", re.I) and (e["tag"] == "a" or e["role"] in ("link", "button"))]
        links.sort(key=lambda x: (not re.search(r"/" + CART_WORDS, x["href"], re.I), not x["in_chrome"]))
        if links:
            safe_click(rt, links[0])
        else:
            origin = f"{urlparse(cur.url).scheme}://{urlparse(cur.url).netloc}"
            try:
                rt.page.goto(origin + "/cart", wait_until="domcontentloaded", timeout=config.NAV_TIMEOUT_MS)
                settle(rt.page)
            except Exception as e:
                raise StepFailed(f"Could not open the cart: {str(e).splitlines()[0][:120]}")
        cur = observe(rt.page)
    need_clear(cur)
    text = cur.text
    item = rt.ctx.get("selected_item")
    if EMPTY_CART.search(text[:3000]):
        raise StepFailed("The cart page reports that the cart is empty.", recoverable=False)
    excerpt = text[:400]
    if not item:
        return Outcome("unverified", "A cart page was opened, but no product was selected earlier in this run, so contents cannot be compared.",
                       {"url": cur.url, "cart_excerpt": excerpt})
    low = text.lower()
    toks = [t for t in tokens(item["title"]) if len(t) > 2][:12]
    hits = [t for t in toks if t in low]
    id_hit = bool(item.get("item_id") and (item["item_id"] in " ".join(e["href"] for e in cur.elements) or item["item_id"] in text))
    ratio = len(hits) / len(toks) if toks else 0
    if not (id_hit or ratio >= 0.6):
        raise StepFailed(f"The cart does not appear to contain “{item['title'][:70]}” (matched {len(hits)}/{len(toks)} title words). Cart shows: {excerpt[:200]}", recoverable=False)
    if hits:
        i = low.find(hits[0])
        excerpt = text[max(0, i - 80): i + 320]
    opt_note = ""
    for k, v in (rt.ctx.get("options") or {}).items():
        opt_note += f" {k.title()} “{v}” " + ("is visible in the cart." if re.search(rf"(?<![\d.]){re.escape(v.lower())}(?![\d.])", low) else "was not visible in the cart text (not verified).")
    return Outcome("passed", f"Cart contains “{item['title'][:80]}” (" + ("item id match" if id_hit else f"{len(hits)}/{len(toks)} title words") + ")." + opt_note,
                   {"url": cur.url, "expected_title": item["title"], "matched_words": hits, "item_id_match": id_hit, "cart_excerpt": excerpt.strip()})


def do_login(rt, obs, a):
    user, _, pw = (a.value or "\n").partition("\n")
    pwd_field = next((e for e in obs.elements if e["type"] == "password"), None)
    texts = [e for e in obs.elements if e["tag"] == "input" and e["type"] in ("", "text", "email", "tel") and not e["disabled"]]
    scored = sorted(texts, key=lambda e: -match_score(e, "username email login account user"))
    ufield = scored[0] if scored and match_score(scored[0], "username email login account user") >= 2 else (texts[0] if texts else None)
    if not ufield and not pwd_field:
        raise StepFailed("No login form was found on this page.")
    if ufield and not user:
        raise NeedsUser("Login requires a username / email. Enter test credentials (they are never stored in reports).", field="username")
    if pwd_field and not pw:
        raise NeedsUser("Login requires a password.", field="password", secret=True)
    before = obs
    try:
        if ufield:
            loc(rt, ufield).fill(user, timeout=4000)
        if pwd_field:
            loc(rt, pwd_field).fill(pw, timeout=4000)
    except Exception as e:
        raise StepFailed(f"Could not fill the login form: {str(e).splitlines()[0][:120]}")
    btns = [e for e in obs.elements if (e["tag"] in ("button", "input", "a") or e["role"] == "button") and not e["disabled"]
            and re.search(r"log ?in|sign ?in|submit|continue|enter", f"{e['text']} {e['label']} {e['value']}", re.I)
            and not re.search(r"forgot|sign ?up|register|create", f"{e['text']} {e['label']}", re.I)]
    btns.sort(key=lambda e: (e["type"] != "submit", not e["in_view"]))
    if btns:
        safe_click(rt, btns[0])
    else:
        rt.page.keyboard.press("Enter")
        settle(rt.page)
    new = observe(rt.page)
    need_clear(new)
    err = re.search(r"(invalid[^.]{0,50}|incorrect[^.]{0,50}|wrong (?:password|username)[^.]{0,30}|login failed|try again|doesn.t match[^.]{0,30}|unable to (?:log|sign))", new.text, re.I)
    if err and err.group(0).lower() not in before.text.lower():
        raise StepFailed(f"Login was rejected by the site: “{err.group(0)[:100]}”.", recoverable=False)
    still_form = any(e["type"] == "password" for e in new.elements)
    if new.url != before.url or (pwd_field and not still_form):
        return Outcome("passed", f"Login submitted; page changed to “{new.title or new.url}”.", {"url": new.url, "title": new.title, "user": user})
    return Outcome("unverified", "Login form submitted but no clear success signal (URL/form unchanged).", {"url": new.url})


def do_apply_filter(rt, obs, a):
    t = a.target.lower()
    if "price" in t or "budget" in t:
        if a.value is None:
            raise NeedsUser("What is the maximum price / budget?", field="value")
        mx = float(re.sub(r"[^\d.]", "", a.value) or 0)
        rt.ctx["max_price"] = mx          # enforced when choosing results, regardless of site UI
        inputs = [e for e in obs.elements if e["tag"] == "input" and e["type"] in ("", "text", "number", "tel") and re.search(r"max|to\b|upper|maximum|price", f"{e['label']} {e['placeholder']} {e['name']} {e['dom_id']}", re.I)
                  and re.search(r"max|to\b|upper|price", f"{e['label']} {e['placeholder']} {e['name']} {e['dom_id']}", re.I)]
        inputs.sort(key=lambda e: (not re.search(r"max|upper|to\b", f"{e['label']} {e['placeholder']} {e['name']} {e['dom_id']}", re.I)))
        if inputs:
            before = obs.signature()
            try:
                l = loc(rt, inputs[0]); l.fill(f"{mx:g}", timeout=4000)
            except Exception as ex:
                raise StepFailed(f"Could not fill the price filter: {str(ex).splitlines()[0][:100]}")
            rt.page.keyboard.press("Enter")
            settle(rt.page, 2500)
            new = observe(rt.page)
            if new.signature() != before:
                return Outcome("passed", f"Applied max price {mx:g} via the site’s price filter.", {"url": new.url, "max_price": mx}, selector_hint(inputs[0]))
        under = []
        for e in obs.elements:
            m = re.search(r"under\s*[$£€₹]?\s*(\d[\d,]*)", f"{e['text']} {e['label']}", re.I)
            if m and (e["tag"] == "a" or e["role"] in ("link", "button", "checkbox")):
                under.append((float(m.group(1).replace(",", "")), e))
        ok = sorted([u for u in under if u[0] >= mx], key=lambda u: u[0])
        if ok:
            safe_click(rt, ok[0][1])
            return Outcome("passed", f"Clicked the site filter “{ok[0][1]['text'][:40]}”.", {"url": rt.page.url, "max_price": mx}, selector_hint(ok[0][1]))
        return Outcome("unverified", f"No price-filter control found; max price {mx:g} will still be enforced when a result is chosen.", {"max_price": mx})
    cands = sorted([e for e in obs.elements if match_score(e, a.target) >= 3 and (e["tag"] in ("a", "button", "input", "label") or e["role"] in ("checkbox", "link", "button"))],
                   key=lambda e: -match_score(e, a.target))
    if not cands:
        raise StepFailed(f"No filter matching “{a.target}” was found.")
    before = obs.signature()
    safe_click(rt, cands[0])
    new = observe(rt.page)
    return Outcome("passed" if new.signature() != before else "unverified", f"Applied filter “{(cands[0]['text'] or a.target)[:50]}”.", {"url": new.url}, selector_hint(cands[0]))


def do_click(rt, obs, a):
    scored = sorted(((match_score(e, a.target), e) for e in obs.elements), key=lambda x: -x[0])
    scored = [(s, e) for s, e in scored if s >= 3]
    if not scored:
        raise StepFailed(f"No element matching “{a.target}” was found.")
    top = scored[0][0]
    e = sorted([x for x in scored if x[0] >= top - 0.01], key=lambda x: (not x[1]["in_view"], x[1]["y"]))[0][1]
    label = (e["text"] or e["label"] or a.target).strip()
    if (a.requires_confirmation or policy.is_consequential(label) or policy.is_consequential(a.target)) and not a.params.get("confirmed"):
        raise NeedsUser(f"The next action clicks “{label[:60]}”, which may complete a purchase, payment or other consequential action. Allow it?",
                        kind="confirm", field="confirm")
    before = obs
    safe_click(rt, e)
    new = observe(rt.page)
    need_clear(new)
    if e["type"] in ("radio", "checkbox"):
        now = next((x for x in new.elements if x["dom_id"] == e["dom_id"] and x["name"] == e["name"] and x["value"] == e["value"]), None)
        ok = bool(now and now["checked"])
        return Outcome("passed" if ok else "unverified", f"Clicked “{label[:60]}”" + (" (now checked)" if ok else ""), {"url": new.url}, selector_hint(e))
    if new.signature() != before.signature():
        return Outcome("passed", f"Clicked “{label[:60]}”; page changed.", {"url": new.url, "title": new.title}, selector_hint(e))
    return Outcome("unverified", f"Clicked “{label[:60]}” but no change was observed on the page.", {"url": new.url}, selector_hint(e))


def do_type(rt, obs, a):
    fields = [e for e in obs.elements if (e["tag"] in ("input", "textarea")) and e["type"] not in ("hidden", "checkbox", "radio", "submit", "button", "file") and not e["disabled"]]
    scored = sorted(((match_score(e, a.target), e) for e in fields), key=lambda x: -x[0])
    if scored and scored[0][0] >= 3:
        e = scored[0][1]
    elif re.fullmatch(r"input field|field|input|box", a.target, re.I) and fields:
        e = fields[0]
    else:
        raise StepFailed(f"No input field matching “{a.target}” was found.")
    l = loc(rt, e)
    try:
        l.fill(a.value, timeout=4000)
    except Exception as ex:
        raise StepFailed(f"Could not type into “{a.target}”: {str(ex).splitlines()[0][:120]}")
    got = l.input_value()
    if got != a.value:
        raise StepFailed(f"Field value reads back as “{got}”, expected “{a.value}”.")
    shown = "••••" if e["type"] == "password" else a.value
    return Outcome("passed", f"Typed “{shown}” into {a.target}.", {"field": a.target, "value": shown}, selector_hint(e))


def do_press_key(rt, obs, a):
    rt.page.keyboard.press(a.value)
    settle(rt.page)
    new = observe(rt.page)
    return Outcome("passed" if new.signature() != obs.signature() else "unverified", f"Pressed {a.value}.", {"url": new.url})


def do_wait(rt, obs, a):
    rt.page.wait_for_timeout(1000)
    settle(rt.page)
    return Outcome("passed", "Waited for the page to settle.", {"url": rt.page.url})


def _poll(rt, fn, seconds=6):
    last = None
    for _ in range(int(seconds * 2) + 1):
        last = observe(rt.page)
        got = fn(last)
        if got:
            return last, got
        rt.page.wait_for_timeout(500)
    return last, None


def do_verify_text(rt, obs, a):
    want = a.value.lower()
    new, found = _poll(rt, lambda o: want in o.text.lower())
    if not found:
        raise StepFailed(f"Expected text “{a.value}” was not found on {new.url}.", recoverable=False)
    i = new.text.lower().find(want)
    return Outcome("passed", f"Found “{a.value}” on the page.", {"url": new.url, "snippet": new.text[max(0, i - 60): i + len(want) + 100]})


def do_verify_url(rt, obs, a):
    want = a.value.lower()
    new, found = _poll(rt, lambda o: want in o.url.lower())
    if not found:
        raise StepFailed(f"URL is {new.url}, which does not contain “{a.value}”.", recoverable=False)
    return Outcome("passed", f"URL contains “{a.value}”.", {"url": new.url})


def do_verify_video(rt, obs, a):
    def ok(o):
        return next((v for v in o.videos if v["src"] and (v["ready"] >= 2 or v["duration"] > 0)), None)
    new, v = _poll(rt, ok, seconds=14)
    if not v:
        raise StepFailed("No video element with loaded media was found on the page.", recoverable=False)
    return Outcome("passed", f"A video is loaded (duration {v['duration']:.0f}s, readyState {v['ready']}, {'paused' if v['paused'] else 'playing'}).",
                   {"url": new.url, "title": new.title, "video": v})


def do_verify_page(rt, obs, a):
    new = observe(rt.page)
    need_clear(new)
    if re.match(r"\s*(404|page not found|error|something went wrong)", new.text[:80], re.I):
        raise StepFailed("The page appears to show an error.", recoverable=False)
    return Outcome("unverified", f"Page loaded without an error, but this check is not machine-verifiable: “{a.description}”. Marked unverified, not passed.",
                   {"url": new.url, "title": new.title, "page_excerpt": new.text[:300]})


SKILLS = {
    "open": do_open, "search": do_search, "select_result": do_select_result, "select_option": do_select_option,
    "add_to_cart": do_add_to_cart, "verify_cart": do_verify_cart, "login": do_login, "apply_filter": do_apply_filter,
    "click": do_click, "type": do_type, "press_key": do_press_key, "wait": do_wait, "verify_text": do_verify_text,
    "verify_url": do_verify_url, "verify_video": do_verify_video, "verify_page": do_verify_page,
}
