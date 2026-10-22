"""Export an *already executed* run as a standalone Playwright script (for display / re-running).
The script is generated from recorded, resolved selectors - the agent itself never exec()s generated code."""
from __future__ import annotations


def _q(s) -> str:
    return repr(str(s))


def generate_playwright_script(steps: list) -> str:
    body = []
    for s in steps:
        if s["status"] not in ("passed", "unverified"):
            continue
        a, p, sel = s["action"], s["params"], (s.get("evidence") or {})
        url, selector = None, None
        body.append(f"    # step {s['idx'] + 1}: {s['description']}")
        if a == "open":
            body.append(f"    page.goto({_q(p.get('target'))})")
        elif a == "search" and sel.get("query"):
            body.append(f"    page.fill({_q(s.get('selector') or 'input[type=search]')}, {_q(sel['query'])})\n    page.keyboard.press('Enter')")
        elif a == "type":
            body.append(f"    page.fill({_q(s.get('selector') or 'input')}, {_q(sel.get('value') or p.get('value'))})")
        elif a in ("click", "add_to_cart", "apply_filter") and s.get("selector"):
            body.append(f"    page.click({_q(s['selector'])})")
        elif a == "select_result" and sel.get("selected_title"):
            body.append(f"    page.get_by_role('link', name={_q(sel['selected_title'][:60])}).first.click()")
        elif a == "select_option" and sel.get("selected") and s.get("selector"):
            body.append(f"    page.select_option({_q(s['selector'])}, label={_q(sel['selected'])})")
        elif a == "verify_text":
            body.append(f"    assert {_q((p.get('value') or '').lower())} in page.inner_text('body').lower()")
        elif a == "verify_url":
            body.append(f"    assert {_q(p.get('value'))} in page.url")
        elif a == "login":
            body.append("    # login: credentials are intentionally not exported")
        else:
            body.append("    page.wait_for_timeout(500)  # (no direct script equivalent)")
        body.append("    page.wait_for_load_state('domcontentloaded')")
    return ("from playwright.sync_api import sync_playwright\n\n"
            "with sync_playwright() as p:\n    browser = p.chromium.launch(headless=False, slow_mo=300)\n    page = browser.new_page()\n"
            + "\n".join(body) + "\n    browser.close()\n")
