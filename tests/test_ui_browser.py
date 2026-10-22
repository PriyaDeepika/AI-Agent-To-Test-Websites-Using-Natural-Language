"""Drives the actual web UI in Chromium: plan preview, run, live timeline, result banner."""
import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.browser


def test_ui_preview_run_and_history(server):
    q = "Search for Nike shoes for women, select a suitable product, choose size 8, add it to the cart, and verify that the correct item appears in the cart."
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1360, "height": 900}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(server + "/")
        pg.fill("#instruction", q); pg.fill("#url", server + "/demo/shop")
        pg.click("#planBtn")
        pg.wait_for_selector("#timeline .step", timeout=5000)
        assert pg.locator("#timeline .step").count() == 6 and pg.locator("#timeline .step.passed").count() == 0
        pg.click("#runBtn")
        pg.wait_for_selector("#resultBanner.PASSED", timeout=90000)
        assert pg.locator("#timeline .step.passed").count() == 6
        assert "Local regression" in pg.inner_text("#resultBanner")
        with pg.expect_download() as d:
            pg.click("text=JSON report")
        assert d.value.suggested_filename.endswith(".json")
        pg.click(".nav[data-view=history]")
        pg.wait_for_selector("#historyBody tr.row")
        assert "PASSED" in pg.inner_text("#historyBody")
        assert errs == []
        b.close()


def test_ui_shows_error_for_bad_url(server):
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto(server + "/"); pg.fill("#instruction", "open it"); pg.fill("#url", "file:///etc/passwd"); pg.click("#runBtn")
        pg.wait_for_selector("#formError:not([hidden])"); assert "scheme" in pg.inner_text("#formError")
        b.close()
