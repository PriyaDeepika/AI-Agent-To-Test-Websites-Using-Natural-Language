"""LOCAL REGRESSION tests: real Chromium, but against the bundled demo pages (/demo/*).
These prove the agent's mechanics; they are NOT evidence about real websites (see test_real_sites.py)."""
import pytest

pytestmark = pytest.mark.browser
SHOP_FLOW = "Search for Nike shoes for women, select a suitable product, choose size 8, add it to the cart, and verify that the correct item appears in the cart."


def statuses(r): return [s["status"] for s in r["steps"]]


@pytest.mark.parametrize("layout", ["select", "swatch", "dropdown"])
def test_shop_flow_all_option_layouts(run_agent, server, layout):
    r = run_agent(SHOP_FLOW, f"{server}/demo/shop?layout={layout}")
    assert r["outcome"] == "PASSED", [(s["description"], s["status"], s["error"]) for s in r["steps"]]
    assert r["kind"] == "local_regression"
    cart = r["steps"][-1]["evidence"]
    assert "Nike Air Zoom Pegasus" in cart["expected_title"] and cart["matched_words"]
    assert all(s["screenshot"] for s in r["steps"])


def test_blocking_cookie_overlay_is_dismissed(run_agent, server):
    r = run_agent(SHOP_FLOW, f"{server}/demo/shop?banner=full")
    assert r["outcome"] == "PASSED"


def test_js_delayed_results(run_agent, server):
    r = run_agent(SHOP_FLOW, f"{server}/demo/shop?delay=2500")
    assert r["outcome"] == "PASSED"


def test_vague_size_pauses_and_uses_answer(run_agent, server):
    r = run_agent("Search for Nike shoes for women, select a suitable product, choose the required size, add it to the cart, verify the item is in the cart",
                  f"{server}/demo/shop", answers={"input": "7"})
    assert [p["kind"] for p in r["_pauses"]] == ["input"] and "size" in r["_pauses"][0]["prompt"].lower()
    assert r["outcome"] == "PASSED" and "7" in r["steps"][3]["detail"]


def test_unavailable_size_asks_then_gives_up_after_three(run_agent, server):
    r = run_agent("Search for Nike shoes for women, select a suitable product, choose size 12, add it to the cart",
                  f"{server}/demo/shop", answers={"input": "9"})      # 9 is sold out for product 1
    assert r["outcome"] == "BLOCKED" and len(r["_pauses"]) == 3
    assert statuses(r)[-2:] == ["skipped", "skipped"]


def test_add_to_cart_without_size_fails_with_clear_reason(run_agent, server):
    r = run_agent("Search for Nike shoes for women, select a suitable product, add it to the cart", f"{server}/demo/shop")
    assert r["outcome"] == "FAILED" and "size" in r["steps"][-1]["error"].lower()


def test_purchase_requires_confirmation_and_decline_stops(run_agent, server):
    r = run_agent("Search for Nike shoes for women, select a suitable product, choose size 8, click Buy it now",
                  f"{server}/demo/shop", answers={"confirm": False})
    assert [p["kind"] for p in r["_pauses"]] == ["confirm"]
    assert r["outcome"] == "BLOCKED"
    assert not any("checkout" in (s["url"] or "") for s in r["steps"])      # never reached checkout


def test_captcha_wall_is_not_bypassed(run_agent, server):
    r = run_agent("Open the page and search for shoes", f"{server}/demo/captcha", answers={"human": False})
    assert r["outcome"] == "BLOCKED" and r["_pauses"][0]["kind"] == "human"
    assert all(s["status"] != "passed" for s in r["steps"])


def test_login_success_and_failure(run_agent, server):
    ok = run_agent('Log in with username demo and password test1234, then verify that "Welcome back" is displayed.', f"{server}/demo/login")
    assert ok["outcome"] == "PASSED"
    bad = run_agent('Log in with username demo and password nope, then verify that "Welcome back" is displayed.', f"{server}/demo/login")
    assert bad["outcome"] == "FAILED" and "rejected" in bad["steps"][1]["error"] and bad["steps"][2]["status"] == "skipped"
    assert "nope" not in str(bad["steps"]) and "test1234" not in str(ok["steps"])       # credentials never persisted


def test_missing_credentials_are_requested_not_invented(run_agent, server):
    r = run_agent('Log in, then verify that "Welcome back" is displayed.', f"{server}/demo/login")
    assert [p["field"] for p in r["_pauses"]][:1] == ["username"]


def test_http_500_is_reported_as_failure(run_agent, server):
    r = run_agent('Verify that the page shows "hello"', f"{server}/demo/broken")
    assert r["outcome"] == "FAILED" and "500" in r["steps"][0]["error"]


def test_failed_text_assertion(run_agent, server):
    r = run_agent('Verify that "this text is not here" is displayed', f"{server}/demo/shop")
    assert r["outcome"] == "FAILED"


def test_unmeasurable_claim_is_inconclusive_not_passed(run_agent, server):
    r = run_agent("Verify that the page looks professional", f"{server}/demo/shop")
    assert r["outcome"] == "INCONCLUSIVE" and r["steps"][-1]["status"] == "unverified"


def test_budget_is_enforced_when_site_has_no_filter(run_agent, server):
    r = run_agent("Search for women under $50, select a suitable product, choose size 8, add it to the cart, and verify the item is in the cart",
                  f"{server}/demo/shop")
    sel = [s for s in r["steps"] if s["action"] == "select_result"][0]
    assert "Puma" in sel["evidence"]["selected_title"]                    # the only women's item <= $50
    flt = [s for s in r["steps"] if s["action"] == "apply_filter"][0]
    assert flt["status"] == "unverified" and r["outcome"] == "INCONCLUSIVE"   # no filter UI -> honestly unverified


def test_no_item_within_budget_fails_clearly(run_agent, server):
    r = run_agent("Search for nike under $50, select a suitable product, choose size 8, add it to the cart", f"{server}/demo/shop")
    assert r["outcome"] == "FAILED"
    sel = [s for s in r["steps"] if s["action"] == "select_result"][0]
    assert sel["status"] == "failed" and "50" in sel["error"]
    assert [s["status"] for s in r["steps"] if s["action"] in ("add_to_cart",)] == ["skipped"]


def test_unsafe_start_url_rejected_before_browser(run_agent):
    import agent
    with pytest.raises(ValueError):
        agent.start_run("open it", "file:///etc/passwd")


def test_cancel_while_waiting(run_agent, server):
    import agent, store, time
    rid = agent.start_run("Open the page and search for shoes", f"{server}/demo/captcha")
    for _ in range(60):
        if store.get_run(rid, False)["status"] == "awaiting_user": break
        time.sleep(0.3)
    assert agent.cancel(rid)
    for _ in range(60):
        if store.get_run(rid, False)["status"] == "cancelled": break
        time.sleep(0.3)
    assert store.get_run(rid, False)["outcome"] == "CANCELLED"


def test_reports_downloadable(run_agent, server, client):
    r = run_agent(SHOP_FLOW, f"{server}/demo/shop")
    j = client.get(f"/api/runs/{r['id']}/report.json").get_json()
    assert j["outcome"] == "PASSED" and j["kind"] == "local_regression" and len(j["steps"]) == 6
    html = client.get(f"/api/runs/{r['id']}/report.html").get_data(as_text=True)
    assert "data:image/png;base64" in html and "PASSED" in html
    script = client.get(f"/api/runs/{r['id']}/script.py").get_data(as_text=True)
    assert "sync_playwright" in script and "page.goto" in script
    assert client.get(f"/api/runs/{r['id']}/screenshots/step-01.png").status_code == 200
