from playwright.sync_api import sync_playwright

def execute_test(playwright_code: str):

    # If no meaningful actions were generated, FAIL immediately
    if not playwright_code.strip():
        return {
            "execution_result": "FAILED",
            "failure_reason": "No valid test actions were detected"
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=1000)
            page = browser.new_page()

            local_scope = {"page": page}

            for line in playwright_code.strip().splitlines():
                print("▶ ", line)
                exec(line, {}, local_scope)

            browser.close()

        # ✅ SUCCESS → ONLY PASSED
        return {
            "execution_result": "PASSED"
        }

    except Exception as e:
        # ❌ FAILURE → FAILED + reason
        return {
            "execution_result": "FAILED",
            "failure_reason": str(e)
        }
