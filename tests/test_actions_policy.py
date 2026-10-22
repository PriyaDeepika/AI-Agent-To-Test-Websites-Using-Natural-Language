import pytest
from actions import validate_plan, PlanError, Action
import policy


def test_validate_rejects_unknown_action_and_arbitrary_code():
    with pytest.raises(PlanError):
        validate_plan([{"action": "run_python", "value": "import os"}])
    with pytest.raises(PlanError):
        validate_plan([{"action": "eval", "target": "x"}])


def test_validate_requires_fields():
    with pytest.raises(PlanError):
        validate_plan([{"action": "click"}])
    with pytest.raises(PlanError):
        validate_plan([{"action": "search"}])
    with pytest.raises(PlanError):
        validate_plan([])


def test_validate_limits_length():
    with pytest.raises(PlanError):
        validate_plan([{"action": "wait"}] * 41)


def test_validate_fills_description():
    p = validate_plan([{"action": "search", "value": "boots"}])
    assert "boots" in p[0].description


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "ftp://x.com", "http://10.0.0.5/admin",
                                 "http://169.254.169.254/latest/meta-data", "http://192.168.1.1", "http://intranet.internal"])
def test_unsafe_urls_blocked(url):
    with pytest.raises(ValueError):
        policy.check_url(url)


def test_public_and_local_urls_ok():
    assert policy.check_url("ebay.com") == "https://ebay.com"
    assert policy.check_url("http://127.0.0.1:5000/x").startswith("http://127.0.0.1")


def test_local_can_be_disallowed():
    with pytest.raises(ValueError):
        policy.check_url("http://localhost:5000", allow_local=False)


@pytest.mark.parametrize("t", ["Buy it now", "Place your order", "Proceed to checkout", "Pay now", "Complete purchase"])
def test_consequential_detected(t):
    assert policy.is_consequential(t)


@pytest.mark.parametrize("t", ["Add to cart", "Search", "Sign in", "Size 8"])
def test_harmless_not_consequential(t):
    assert not policy.is_consequential(t)


def test_captcha_wall_detected_but_article_mentioning_it_is_not():
    assert policy.looks_blocked("Please verify you are human. CAPTCHA required.", "Security check")
    assert policy.looks_blocked("An article about captcha history. " * 200, "Blog") is None


def test_login_value_masked_in_public():
    a = Action("login", value="u\nhunter2")
    assert "hunter2" not in str(a.public())
