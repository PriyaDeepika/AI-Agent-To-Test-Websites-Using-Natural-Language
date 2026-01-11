def generate_playwright_code(command: dict):

    action = command["action"]
    selector = command["selector_value"]
    value = command["value"]

    if action == "navigate":
        action_line = "page.goto('http://localhost:5000/login_page')"

    elif action == "type":
        action_line = f"page.fill('#{selector}', '{value}')"

    elif action == "click":
        action_line = f"page.click('#{selector}')"

    else:
        action_line = "print('Unknown action')"

    # This is only for DISPLAY in UI
    full_script = f"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=1000)
    page = browser.new_page()
    page.goto("http://localhost:5000/login_page")
    page.wait_for_selector("#{selector}")
    {action_line}
    browser.close()
""".strip()

    return action_line, full_script
