"""Safety policy: URL allow-listing, consequential-action detection, human-intervention detection."""
from __future__ import annotations
import ipaddress, re
from urllib.parse import urlparse
import config

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Text on an element that implies a purchase/payment/irreversible action.
CONSEQUENTIAL = re.compile(
    r"\b(buy it now|buy now|place (?:your )?order|pay now|pay with|complete (?:purchase|order)|"
    r"confirm (?:purchase|order|payment)|submit order|checkout|check out|proceed to (?:checkout|payment)|"
    r"purchase|subscribe now|delete (?:account|my account)|place bid|commit to buy)\b", re.I)

CAPTCHA_MARKERS = re.compile(
    r"(captcha|are you a (?:human|robot)|verify you are (?:a )?human|unusual traffic|"
    r"security check|press (?:&|and) hold|checking your browser|access denied|bot detection|"
    r"pardon our interruption)", re.I)


def check_url(url: str, allow_local: bool = True) -> str:
    """Return a normalised URL or raise ValueError with a human-readable reason."""
    url = (url or "").strip()
    if not url:
        raise ValueError("No URL provided.")
    if "://" not in url:
        m = re.match(r"^([a-z][a-z0-9+.-]*):(?!\d+(?:/|$))", url, re.I)   # 'javascript:', 'data:', 'mailto:' (not host:port)
        if m:
            raise ValueError(f"Blocked URL scheme '{m.group(1).lower()}'. Only http/https is allowed.")
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"Blocked URL scheme '{p.scheme}'. Only http/https is allowed.")
    host = (p.hostname or "").lower()
    if not host:
        raise ValueError("URL has no host.")
    if any(host == d or host.endswith("." + d) for d in config.BLOCKED_DOMAINS):
        raise ValueError(f"Domain '{host}' is on the blocked list.")
    if host in LOCAL_HOSTS:
        if allow_local:
            return url
        raise ValueError("Local addresses are not allowed here.")
    try:
        ip = ipaddress.ip_address(host)
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved) and not config.ALLOW_PRIVATE_NETWORK:
            raise ValueError(f"Private network address '{host}' is blocked (set ALLOW_PRIVATE_NETWORK=true to allow).")
    except ValueError as e:
        if "blocked" in str(e):
            raise
    if host.endswith((".local", ".internal")) and not config.ALLOW_PRIVATE_NETWORK:
        raise ValueError(f"Internal hostname '{host}' is blocked.")
    return url


def is_consequential(text: str) -> bool:
    return bool(text and CONSEQUENTIAL.search(text))


def looks_blocked(page_text: str, title: str = "") -> str | None:
    """Return a reason string if the page seems to require human intervention (CAPTCHA, bot wall)."""
    sample = f"{title}\n{page_text[:3000]}"
    m = CAPTCHA_MARKERS.search(sample)
    # A real content page can mention 'captcha' in passing; only trust short, wall-like pages.
    if m and len(page_text) < 2500:
        return f"The site is showing a human-verification / access barrier (“{m.group(0)}”)."
    return None
