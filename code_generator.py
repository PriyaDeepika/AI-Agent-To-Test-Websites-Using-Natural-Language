def generate_playwright_code(commands: list):
    lines = []

    for cmd in commands:
        action = cmd["action"]
        selector = cmd.get("target")
        value = cmd.get("value")

        if action == "navigate":
            # 🔥 RESPECT TARGET PAGE
            if not selector:
                continue
            if selector.startswith("http://") or selector.startswith("https://"):
                lines.append(f"page.goto('{selector}')")
            else:
                lines.append(f"page.goto('http://127.0.0.1:5000/{selector}')")

        elif action == "type":
            if not selector or value is None:
                continue
            lines.append(f"page.wait_for_selector('#{selector}')")

            # 🔥 Handle dropdown separately
            if selector == "role_select":
                lines.append(f"page.select_option('#{selector}', '{value}')")
            else:
                lines.append(f"page.fill('#{selector}', '{value}')")

        elif action == "click":
            if not selector:
                continue
            lines.append(f"page.wait_for_selector('#{selector}')")
            lines.append(f"page.click('#{selector}')")

        # elif action == "search":
        #     query = value
        #     if not query:
        #         continue

        #     # allow page JS to settle
        #     lines.append("page.wait_for_timeout(2000)")

        #     # 🔹 site-aware but executor-safe search
        #     lines.append(
        #         "page.click("
        #         "\"input#search, "
        #         "input[aria-label='Search query'], "
        #         "ytd-searchbox input, "
        #         "input[name='q'], "
        #         "input[type='search'], "
        #         "input[aria-label*='Search']\""
        #         ")"
        #     )

        #     lines.append(f"page.keyboard.type('{query}', delay=100)")
        #     lines.append("page.keyboard.press('Enter')")

        elif action == "search":
            query = value
            if not query:
                continue

            # allow page to settle
            lines.append("page.wait_for_timeout(2000)")

            # 🔑 universal focus shortcut (works on YouTube, Google, etc.)
            lines.append("page.keyboard.press('/')")

            # type query
            lines.append(f"page.keyboard.type('{query}', delay=100)")

            # submit
            lines.append("page.keyboard.press('Enter')")


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
