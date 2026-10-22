"""Page observation: a compact, structured snapshot of what is on screen right now."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

OBSERVE_JS = r"""
() => {
  const SEL = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=option],[role=tab],' +
              '[role=menuitem],[role=checkbox],[role=radio],[role=combobox],[role=listbox],[role=searchbox],[onclick],label';
  const PRICE = /(?:[$£€₹]|US\s?\$|Rs\.?)\s?\d[\d,]*(?:\.\d{1,2})?/;
  const out = []; let n = 0;
  document.querySelectorAll('[data-agent-id]').forEach(e => e.removeAttribute('data-agent-id'));
  for (const el of document.querySelectorAll(SEL)) {
    if (n >= 500) break;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
    const tag = el.tagName.toLowerCase();
    const txt = (el.innerText || el.value || '').replace(/\s+/g, ' ').trim().slice(0, 200);
    const labels = el.labels ? Array.from(el.labels).map(l => l.innerText.trim()).join(' ') : '';
    let box = el.closest('li,article,tr,[class*="item"],[class*="card"],[class*="result"],[class*="product"],[class*="grid"] > *') || el.parentElement;
    let ctx = box ? (box.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 400) : '';
    const pm = ctx.match(PRICE);
    const chrome = !!el.closest('header,nav,footer,[role=navigation],[role=banner],[role=contentinfo]');
    el.setAttribute('data-agent-id', String(n));
    out.push({id: n, tag, type: el.getAttribute('type') || '', role: el.getAttribute('role') || '',
      text: txt, label: (el.getAttribute('aria-label') || '') + ' ' + labels, title: el.getAttribute('title') || '',
      placeholder: el.getAttribute('placeholder') || '', name: el.getAttribute('name') || '', dom_id: el.id || '',
      href: tag === 'a' ? el.href : '', value: (tag === 'input' || tag === 'select' || tag === 'textarea') ? (el.value || '') : '',
      checked: !!el.checked, disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
      expanded: el.getAttribute('aria-expanded') || '', selected: el.getAttribute('aria-selected') || el.getAttribute('aria-checked') || el.getAttribute('aria-pressed') || '',
      in_chrome: chrome, cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120), haspopup: el.getAttribute('aria-haspopup') || '',
      overlay: !!el.closest('[role=dialog],[aria-modal=true],[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],[class*=gdpr i],[class*=modal i],[class*=overlay i]'), in_view: r.top < innerHeight && r.bottom > 0, y: Math.round(r.top + scrollY),
      ctx, price_text: pm ? pm[0] : '', sponsored: /\b(sponsored|promoted|ad)\b/i.test(ctx.slice(0, 80)),
      options: tag === 'select' ? Array.from(el.options).map(o => ({text: o.text.trim(), value: o.value, disabled: o.disabled})) : null});
    n++;
  }
  return out;
}
"""

STATE_JS = r"""() => ({
  url: location.href, title: document.title,
  text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim().slice(0, 20000),
  dialogs: document.querySelectorAll('[role=dialog],[aria-modal=true],dialog[open]').length,
  videos: Array.from(document.querySelectorAll('video')).map(v => ({ready: v.readyState, duration: v.duration || 0, time: v.currentTime, paused: v.paused, src: !!(v.currentSrc || v.src)})),
})"""


@dataclass
class Observation:
    url: str
    title: str
    text: str
    elements: list
    dialogs: int = 0
    videos: list = field(default_factory=list)

    def signature(self) -> str:
        return f"{self.url}|{len(self.text)}|{hash(self.text[:4000])}|{len(self.elements)}"


def observe(page) -> Observation:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    last = None
    for _ in range(3):  # tolerate in-flight navigations
        try:
            st = page.evaluate(STATE_JS)
            els = page.evaluate(OBSERVE_JS)
            return Observation(st["url"], st["title"], st["text"], els, st["dialogs"], st["videos"])
        except Exception as e:  # execution context destroyed during navigation
            last = e
            page.wait_for_timeout(600)
    raise RuntimeError(f"Could not observe page: {last}")


STOP = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "with", "at", "by", "from", "is", "it", "s"}
SYNONYMS = {
    "login": {"log in", "sign in", "signin", "login"}, "signin": {"log in", "sign in", "login"},
    "cart": {"cart", "basket", "bag", "trolley"}, "submit": {"submit", "send", "continue", "save", "go", "login", "sign in", "log in"},
    "search": {"search", "find", "go"}, "email": {"email", "e-mail", "mail"}, "username": {"username", "user name", "user", "login", "email"},
    "male": {"male"}, "female": {"female"},
}


def tokens(s: str) -> list[str]:
    s = re.sub(r"[’']s\b", "", s.lower())
    return [t for t in re.findall(r"[a-z0-9]+", s) if t not in STOP and (len(t) > 1 or t.isdigit())]


def haystack(el: dict) -> str:
    return " ".join(str(el.get(k, "")) for k in ("text", "label", "title", "placeholder", "name", "dom_id", "value")).lower()


def match_score(el: dict, phrase: str) -> float:
    """How well an element matches a natural-language description (higher is better)."""
    toks = tokens(phrase)
    if not toks:
        return 0.0
    hay = haystack(el)
    words = set(re.findall(r"[a-z0-9]+", hay))
    score = 0.0
    if phrase.lower().strip() in hay:
        score += 4
    for t in toks:
        opts = SYNONYMS.get(t, {t})
        if any((o in hay) if " " in o else (o in words) for o in opts):
            score += 3
        elif any(t in w or w in t for w in words if len(w) > 3):
            score += 1
    if score == 0:
        return 0.0
    text = (el.get("text") or el.get("label") or "").lower()
    if len(text) <= 3 * len(phrase) + 10:   # short, precise labels beat long paragraphs
        score += 1.5
    if el["tag"] in ("button", "a", "input") or el["role"] in ("button", "link"):
        score += 0.5
    if el.get("disabled"):
        score -= 3
    return score
