from typing import TypedDict
from langgraph.graph import StateGraph
from llm_parser import parse_instruction_llm
from parser import parse_instruction
from code_generator import generate_playwright_code
from executor import execute_test
from reporter import generate_report


class AgentState(TypedDict):
    instruction: str
    parsed_command: list
    # structured_command: list
    playwright_code: str
    full_playwright_script: str
    execution_result: str
    report: dict

# ------------------NODES--------------------

def parser_node(state: AgentState):
    try:
        # Primary LLM parser
        parsed = parse_instruction_llm(state["instruction"])
    except Exception as e:
        print("⚠️ Gemini unavailable, using rule-based parser:", e)
        parsed = parse_instruction(state["instruction"])

    # 🔒 CRITICAL: always return valid state
    state["parsed_command"] = parsed
    return state



# def command_builder_node(state: AgentState):
#     structured = []

#     for cmd in state["parsed_command"]:
#         structured.append({
#             "action": cmd.get("action"),
#             "selector_type": "id",
#             "selector_value": cmd.get("target"),
#             "value": cmd.get("value")
#         })

#     state["structured_command"] = structured
#     return state

def code_generator_node(state: AgentState):
    action_line, full_script = generate_playwright_code(state["parsed_command"])
    state["playwright_code"] = action_line
    state["full_playwright_script"] = full_script
    return state

def executor_node(state: AgentState):
    state["execution_result"] = execute_test(state["playwright_code"])
    state["report"] = generate_report(state)
    return state

# ---------------LANGGRAPH WORKFLOW----------------

graph = StateGraph(AgentState)

graph.add_node("parser", parser_node, retry= False)
# graph.add_node("command_builder", command_builder_node)
graph.add_node("code_generator", code_generator_node)
graph.add_node("executor", executor_node)

graph.set_entry_point("parser")
graph.add_edge("parser", "code_generator")
# graph.add_edge("command_builder", "code_generator")
graph.add_edge("code_generator", "executor")

agent_workflow = graph.compile()
