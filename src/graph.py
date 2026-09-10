from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.nodes import llm_node, should_continue, validate_node, validate_should_retry
from src.state import AgentState
from src.tools import TOOLS


def build_graph() -> StateGraph:
    """
    Graph topology:
        llm -> (tools -> llm)* -> validate -> END         no errors
                                  validate -> llm -> ...  retry on errors (max 1)
    """
    graph = StateGraph(AgentState)

    graph.add_node("llm", llm_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_node("validate", validate_node)

    graph.set_entry_point("llm")
    graph.add_conditional_edges("llm", should_continue, {"tools": "tools", "validate": "validate"})
    graph.add_edge("tools", "llm")
    graph.add_conditional_edges("validate", validate_should_retry, {"llm": "llm", "end": END})

    return graph.compile()