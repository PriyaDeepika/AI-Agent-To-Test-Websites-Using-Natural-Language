from workflow import agent_workflow

def run_agent(instruction: str):
    if instruction.strip() == "":
        return {"status": "error", "message": "No instruction provided"}

    result = agent_workflow.invoke({
        "instruction": instruction,
        "parsed_command": {},
        "structured_command": {}
    })

    return {
        "status": "success",
        "parsed_action": result["parsed_command"],
        "full_playwright_script": result["full_playwright_script"],
        "execution_result": result["execution_result"]
    }
