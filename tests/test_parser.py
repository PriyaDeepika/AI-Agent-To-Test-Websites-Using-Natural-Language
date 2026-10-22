import parser as P
from actions import validate_plan, PlanError
import pytest

EBAY = "Open eBay, search for Nike shoes for women, select a suitable product, choose the required size, add it to the cart, and verify that the correct item appears in the cart."


def kinds(text, url=None):
    r = P.parse(text, url)
    return [(a.action, a.target, a.value) for a in r.actions], r


def test_ebay_instruction_becomes_goal_level_plan():
    steps, r = kinds(EBAY)
    assert [s[0] for s in steps] == ["open", "search", "select_result", "select_option", "add_to_cart", "verify_cart"]
    assert steps[0][1] == "https://www.ebay.com"
    assert steps[1][2] == "Nike shoes for women"
    assert steps[2][1] == "product"
    assert steps[3] == ("select_option", "size", None)     # vague -> must ask the user later
    assert any("ask you" in n for n in r.notes)


def test_explicit_size_is_extracted():
    steps, _ = kinds("choose size 8, add it to the cart")
    assert ("select_option", "size", "8") in steps


def test_youtube_video_verification():
    steps, _ = kinds("Open YouTube, search for Linux administration tutorials, open a relevant video, and verify that it loads.")
    assert [s[0] for s in steps] == ["open", "search", "select_result", "verify_video"]
    assert steps[2][1] == "video"


def test_budget_extracts_price_filter_and_param():
    r = P.parse("Search for running shoes under $50 on amazon")
    names = [a.action for a in r.actions]
    assert names == ["open", "search", "apply_filter"]
    assert r.actions[1].value == "running shoes" and r.actions[1].params["max_price"] == 50
    assert r.actions[2].value == "50.0"


def test_vague_budget_asks_for_amount():
    r = P.parse("Search for products under a specified budget", "https://example.com")
    f = [a for a in r.actions if a.action == "apply_filter"][0]
    assert f.target == "price" and f.value is None


def test_login_credentials_and_masking():
    r = P.parse("Log in with username alice and password s3cret", "https://example.com")
    a = [x for x in r.actions if x.action == "login"][0]
    assert a.value == "alice\ns3cret"
    assert "s3cret" not in str(a.public())


def test_quoted_text_gives_hard_verification_and_vague_gives_weak():
    s, _ = kinds('verify that "Welcome back" is displayed', "https://example.com")
    assert ("verify_text", None, "Welcome back") in s
    s, r = kinds("verify that the dashboard looks right", "https://example.com")
    assert s[-1][0] == "verify_page" and any("unverified" in n for n in r.notes)


def test_consequential_click_flagged():
    r = P.parse("click Buy it now", "https://example.com")
    assert r.actions[-1].requires_confirmation


def test_legacy_form_phrase_still_works():
    r = P.parse("fill the form with name as Bob email as b@x.com male student submit")
    assert [a.action for a in r.actions][:3] == ["open", "type", "type"]
    assert any(a.action == "select_option" and a.value == "student" for a in r.actions)


def test_gibberish_yields_no_plan():
    r = P.parse("blorp flibber zonk")
    assert r.unparsed and not r.actions
    with pytest.raises(PlanError):
        validate_plan(r.actions)


def test_open_the_page_does_not_create_empty_click():
    r = P.parse("Open the page and search for shoes", "https://example.com")
    assert all(a.action != "click" for a in r.actions)
