from datetime import datetime

def generate_report(state: dict):
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "instruction": state["instruction"],
        "parsed_command": state["parsed_command"],
        "structured_command": state["structured_command"],
        "playwright_code": state["playwright_code"],
        "execution_result": state["execution_result"]
    }
