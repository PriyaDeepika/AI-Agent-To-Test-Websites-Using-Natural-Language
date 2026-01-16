def generate_playwright_code(commands: list):
    lines = []

    for cmd in commands:
        action = cmd["action"]
        selector = cmd.get("selector_value")
        value = cmd.get("value")

        if action == "navigate":
            # 🔥 RESPECT TARGET PAGE
            lines.append(
                f"page.goto('http://localhost:5000/{selector}')"
            )

        elif action == "type":
            lines.append(f"page.wait_for_selector('#{selector}')")

            # 🔥 Handle dropdown separately
            if selector == "role_select":
                lines.append(f"page.select_option('#{selector}', '{value}')")
            else:
                lines.append(f"page.fill('#{selector}', '{value}')")

        elif action == "click":
            lines.append(f"page.wait_for_selector('#{selector}')")
            lines.append(f"page.click('#{selector}')")

    action_block = "\n".join(lines)

    # For DISPLAY ONLY (not execution)
    full_script = f"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=800)
    page = browser.new_page()
    {action_block}
    browser.close()
""".strip()

    return action_block, full_script
