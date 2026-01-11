from typing import TypedDict
from langgraph.graph import StateGraph
from parser import parse_instruction
from code_generator import generate_playwright_code
from executor import execute_test


class AgentState(TypedDict):
    instruction: str
    parsed_command: dict
    structured_command: dict
    playwright_code: str
    full_playwright_script: str
    execution_result: str

# ------------------NODES--------------------

def parser_node(state: AgentState):
    parsed = parse_instruction(state["instruction"])
    return {"parsed_command": parsed}

def command_builder_node(state: AgentState):
    parsed = state["parsed_command"]

    structured = {
        "action": parsed.get("action"),
        "selector_type": "id",
        "selector_value": parsed.get("target"),
        "value": parsed.get("value")
    }

    return {"structured_command": structured}

def code_generator_node(state: AgentState):
    action_line, full_script = generate_playwright_code(state["structured_command"])
    return {
        "playwright_code": action_line,
        "full_playwright_script": full_script
    }

def executor_node(state: AgentState):
    result = execute_test(state["playwright_code"])
    return {"execution_result": result}

# ---------------LANGGRAPH WORKFLOW----------------

graph = StateGraph(AgentState)

graph.add_node("parser", parser_node)
graph.add_node("command_builder", command_builder_node)
graph.add_node("code_generator", code_generator_node)
graph.add_node("executor", executor_node)

graph.set_entry_point("parser")
graph.add_edge("parser", "command_builder")
graph.add_edge("command_builder", "code_generator")
graph.add_edge("code_generator", "executor")

agent_workflow = graph.compile()
