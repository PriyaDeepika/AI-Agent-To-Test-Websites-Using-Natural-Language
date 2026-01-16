from playwright.sync_api import sync_playwright

def detect_business_errors(page):
    errors = []

    # looks for any visible validation messages
    error_elements = page.locator(".error-text:visible")
    count = error_elements.count()

    for i in range(count):
        text = error_elements.nth(i).inner_text().strip()
        if text:
            errors.append(text)

    return errors


def execute_test(playwright_code: str):
    result = {
        "execution_result": "PASSED",
        "test_outcome": "BUSINESS_PASS",
        "failure_reason": None
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        page = browser.new_page()

        try:
            local_scope = {"page": page}

            for line in playwright_code.strip().splitlines():
                print("▶ ", line)
                exec(line, {}, local_scope)

        except Exception as e:
            # 🔴 Technical failure (Playwright error)
            result["execution_result"] = "FAILED"
            result["test_outcome"] = "TECHNICAL_FAIL"
            result["failure_reason"] = str(e)
            browser.close()
            return result

        # 🔥 BUSINESS VALIDATION (GENERIC)
        errors = detect_business_errors(page)

        if errors:
            result["test_outcome"] = "BUSINESS_FAIL"
            result["failure_reason"] = "; ".join(errors)

        browser.close()
        return result
