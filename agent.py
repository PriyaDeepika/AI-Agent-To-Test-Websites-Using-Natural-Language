from workflow import agent_workflow

def run_agent(instruction: str):

    state = {
        "instruction": instruction,
        "parsed_command": {},
        "structured_command": {},
        "playwright_code": "",
        "full_playwright_script": "",
        "execution_result": "",
        "report": {}
    }

    result = agent_workflow.invoke(state)

    return {
        "parsed_action": result["parsed_command"],
        "full_playwright_script": result["full_playwright_script"],
        "execution_result": result["execution_result"],
        "report": result["report"]
    }
