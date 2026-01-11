from playwright.sync_api import sync_playwright

def execute_test(playwright_code: str):

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo = 1000)
        page = browser.new_page()

        page.goto("http://localhost:5000/login_page")

        # Wait for DOM to load
        page.wait_for_selector("#username_field", timeout=5000)

        # Make page available inside exec()
        local_scope = {"page": page}

        try:
            exec(playwright_code, {}, local_scope)
            status = "Test executed successfully"
        except Exception as e:
            status = f"Execution failed: {str(e)}"

        browser.close()

    return status