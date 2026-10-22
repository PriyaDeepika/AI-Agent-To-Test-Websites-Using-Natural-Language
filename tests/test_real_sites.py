"""REAL-WEBSITE tests. Opt-in:  RUN_REAL_SITE_TESTS=1 pytest -m real_site -s
Outcomes are reported honestly: PASSED = verified success; BLOCKED = the site demanded human verification / blocked
automation (xfail, never counted as a pass); anything else fails. Results are appended to data/real_site_results.json."""
import json, os, socket, time
import pytest
import config

pytestmark = pytest.mark.real_site


def _online(host="www.ebay.com"):
    try:
        socket.create_connection((host, 443), timeout=5).close(); return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _guard():
    if os.getenv("RUN_REAL_SITE_TESTS") != "1":
        pytest.skip("set RUN_REAL_SITE_TESTS=1 to run real-website tests")
    if not _online():
        pytest.skip("no outbound internet access from this machine")


def _record(name, r):
    p = config.DATA_DIR / "real_site_results.json"
    data = json.loads(p.read_text()) if p.exists() else []
    data.append({"test": name, "run_id": r["id"], "outcome": r["outcome"], "summary": r["summary"], "when": time.strftime("%F %T")})
    p.write_text(json.dumps(data, indent=2))


def _judge(name, r):
    _record(name, r)
    if r["outcome"] == "BLOCKED":
        pytest.xfail(f"blocked by the site / needs human: {r['summary']}")
    assert r["outcome"] == "PASSED", (r["outcome"], r["summary"], [(s["description"], s["status"], s["error"]) for s in r["steps"]])
    assert r["kind"] == "real_website"


def test_ebay_womens_nike_shoes_to_cart(run_agent):
    r = run_agent("Open eBay, search for Nike shoes for women, select a suitable product, choose size 8, add it to the cart, and verify that the correct item appears in the cart.",
                  answers={"input": "8"}, timeout=240)
    _judge("ebay_cart", r)


def test_youtube_linux_tutorial_loads(run_agent):
    r = run_agent("Open YouTube, search for Linux administration tutorials, open a relevant video, and verify that it loads.", timeout=180)
    _judge("youtube_video", r)


def test_wikipedia_search_and_verify(run_agent):
    r = run_agent('Open https://www.wikipedia.org, search for Linux kernel, open a relevant result, and verify that "Linux" is displayed.', timeout=180)
    _judge("wikipedia_search", r)
