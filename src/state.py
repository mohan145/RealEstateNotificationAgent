from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    input_record: dict
    output: dict | None
    validation_errors: list[str]
    retry_count: int
    llm_error: str | None