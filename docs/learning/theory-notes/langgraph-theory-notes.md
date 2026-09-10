# LangGraph — Theory Notes

## What is LangGraph?

LangGraph is a library for building stateful, multi-step LLM applications as **directed graphs**. Each node in the graph is a Python function; edges define control flow. The graph runtime manages state, routing, and cycles.

It sits on top of LangChain but is architecturally independent — you can use it without any LangChain chains.

```
LangGraph = state machine + LLM nodes + tool nodes + conditional routing
```

---

## Core Concepts

### 1. State

State is a `TypedDict` (or Pydantic `BaseModel`) shared across all nodes. Every node receives the full state and returns a *partial update* — only the keys it changed.

```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # reducer-managed
    output: dict | None                       # last-write-wins
    errors: list[str]                         # last-write-wins
```

LangGraph merges partial updates into the full state between nodes. This is the **reducer pattern**.

---

### 2. Reducers

A reducer defines *how* a state key is updated when a node returns a new value.

**Default (no reducer) — last write wins:**
```python
output: dict | None
# Node returns {"output": {...}} → replaces the old value entirely
```

**`add_messages` reducer — append:**
```python
messages: Annotated[list, add_messages]
# Node returns {"messages": [new_msg]} → appended to existing list
# Deduplicates by message ID automatically
```

You can write custom reducers:
```python
from typing import Annotated

def merge_errors(existing: list, new: list) -> list:
    return existing + new

errors: Annotated[list[str], merge_errors]
```

---

### 3. Nodes

A node is any Python callable that takes `state` and returns a partial state dict.

```python
def my_node(state: AgentState) -> dict:
    # read from state
    record = state["input_record"]
    # do work
    result = process(record)
    # return only the keys you're updating
    return {"output": result}
```

Nodes **never mutate state directly** — they return updates. LangGraph applies them.

---

### 4. Edges

Three types of edges:

```python
# 1. Unconditional — always goes A → B
graph.add_edge("tools", "llm")

# 2. Conditional — router function decides
graph.add_conditional_edges("llm", router_fn, {
    "tools": "tools",
    "validate": "validate",
})

# 3. Entry point and END
graph.set_entry_point("llm")
graph.add_edge("validate", END)
```

`END` is a special sentinel — reaching it terminates the graph and returns final state.

---

### 5. Cycles (the ReAct loop)

LangGraph explicitly supports cycles, unlike LangChain's chains. This is what makes the ReAct (Reason + Act) loop possible:

```
llm → tools → llm → tools → llm → validate → END
```

The graph keeps looping until the routing function returns `"validate"` instead of `"tools"`.

Without cycles, you'd need to pre-define the number of tool calls — impossible for an agent.

---

## Graph Lifecycle

```python
# 1. Define
graph = StateGraph(AgentState)

# 2. Add nodes
graph.add_node("llm", llm_node)
graph.add_node("tools", ToolNode(TOOLS))
graph.add_node("validate", validate_node)

# 3. Wire edges
graph.set_entry_point("llm")
graph.add_conditional_edges("llm", should_continue, {...})
graph.add_edge("tools", "llm")
graph.add_edge("validate", END)

# 4. Compile — validates the graph, builds the runtime
app = graph.compile()

# 5. Invoke — runs the graph to completion
final_state = app.invoke({
    "messages": [],
    "input_record": record,
    "output": None,
    "validation_errors": [],
})
```

`compile()` validates that all referenced nodes exist, all edges are reachable, and the graph has at least one path to `END`. It returns a `CompiledGraph` — a runnable object.

---

## State Management In Depth

### Initial state

You pass the full initial state to `invoke()`. Every key must be present (or have a default). LangGraph does not infer defaults from TypedDict annotations — you must supply them.

```python
app.invoke({
    "messages": [],       # required — add_messages starts from empty list
    "input_record": {},   # required
    "output": None,       # required
    "validation_errors": [],  # required
})
```

### How updates flow

```
invoke(initial_state)
  │
  ▼
Node A runs → returns {"messages": [msg1]}
  │
  ▼  LangGraph merges: state["messages"] = add_messages([], [msg1]) = [msg1]
  │
  ▼
Node B runs → returns {"output": {...}, "messages": [msg2]}
  │
  ▼  LangGraph merges:
     state["messages"] = add_messages([msg1], [msg2]) = [msg1, msg2]
     state["output"] = {...}   (last-write-wins)
  │
  ▼
... continues until END
```

### State isolation between runs

Each `invoke()` call is independent. State is not shared between calls — `app` is stateless. To persist state across calls (e.g. multi-turn conversations), use a **checkpointer**.

---

## Checkpointers (Persistence)

A checkpointer saves state snapshots after every node, enabling:
- **Resume** — pick up where the graph left off after a crash
- **Multi-turn** — store conversation history between user messages
- **Time travel** — replay from any past checkpoint

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
app = graph.compile(checkpointer=checkpointer)

# thread_id groups checkpoints into a "conversation"
config = {"configurable": {"thread_id": "user-123"}}
result = app.invoke(initial_state, config=config)

# Next call resumes from last checkpoint for this thread_id
result2 = app.invoke({"messages": [new_msg]}, config=config)
```

Checkpointers available: `SqliteSaver`, `PostgresSaver`, `MemorySaver` (in-memory, for testing).

---

## ToolNode

`ToolNode` is a pre-built node that executes tool calls from the last LLM message:

```python
from langgraph.prebuilt import ToolNode

graph.add_node("tools", ToolNode(TOOLS))
```

Internally it:
1. Reads `tool_calls` from `state["messages"][-1]`
2. Dispatches each call to the matching tool function
3. Wraps results as `ToolMessage` objects
4. Returns `{"messages": [tool_msg_1, tool_msg_2, ...]}`

The `add_messages` reducer appends these to the message history, so the LLM sees them on the next iteration.

---

## `create_react_agent` vs Custom Graph

LangGraph provides a shortcut:

```python
from langgraph.prebuilt import create_react_agent

app = create_react_agent(model=llm, tools=TOOLS)
```

This builds the standard `llm → tools → llm` loop automatically.

**Use `create_react_agent` when:**
- You just need a basic ReAct loop
- No custom validation, routing, or state needed

**Build a custom graph when (NotifyBot's case):**
- You need a custom `validate` node after tool calls
- You need custom routing logic (e.g. `finalize_output` routes differently than other tools)
- You need custom state fields beyond `messages`
- You want fine-grained control over the loop termination condition

---

## Streaming

LangGraph supports streaming node outputs as they happen:

```python
# Stream final state deltas
for chunk in app.stream(initial_state):
    print(chunk)  # {"llm": {"messages": [...]}}

# Stream token-by-token from LLM nodes
for chunk in app.stream(initial_state, stream_mode="messages"):
    print(chunk)
```

Useful for building chat UIs where you want to show responses as they're generated.

---

## Parallel Nodes (Fan-out / Fan-in)

LangGraph supports running nodes in parallel using `Send`:

```python
from langgraph.types import Send

def fan_out(state):
    # Send each record to the same node in parallel
    return [Send("process_record", {"record": r}) for r in state["records"]]

graph.add_conditional_edges("start", fan_out)
```

Results are collected and merged back into state automatically.

---

## Common Patterns

### Pattern 1 — ReAct Agent (this project)
```
llm → [tools → llm]* → validate → END
```

### Pattern 2 — Reflection
```
generate → critique → [revise → critique]* → END
```
LLM generates, then a second LLM call critiques, loops until quality passes.

### Pattern 3 — Multi-agent
```
orchestrator → [agent_A | agent_B | agent_C] → aggregator → END
```
Supervisor dispatches subtasks to specialised agents in parallel.

### Pattern 4 — Human-in-the-loop
```
llm → human_review → [approve → END | reject → llm]
```
Graph pauses at `human_review`, waits for external input, then resumes.

---

## LangGraph vs Alternatives

| Framework | Model | Strengths | Weaknesses |
|-----------|-------|-----------|------------|
| LangGraph | Stateful graph | Cycles, persistence, fine control | More boilerplate than simple chains |
| LangChain LCEL | Functional pipeline | Simple chains, composable | No cycles, limited state |
| CrewAI | Role-based agents | Easy multi-agent setup | Less control over routing |
| AutoGen | Conversational agents | Microsoft ecosystem | Chat-centric, less graph control |
| Raw API | None | Maximum control | You build everything yourself |

LangGraph is the right choice when you need **cycles + state + conditional routing** — exactly what a ReAct agent requires.

---

## Interview Q&A

**Q: Why does LangGraph use a graph instead of a chain?**
A: Chains are DAGs — they can't loop. Agents need to loop (call tools, observe results, decide next step) an unknown number of times. A graph with cycles models this naturally.

**Q: What's the difference between `add_messages` and a plain list in state?**
A: A plain list uses last-write-wins — a node returning `{"messages": [x]}` would *replace* the entire history with just `[x]`. `add_messages` appends instead, and deduplicates by message ID, so history accumulates correctly.

**Q: How does LangGraph know when to stop?**
A: When a routing function returns `END`, or when an unconditional edge leads to `END`. There's no automatic timeout — you must design termination into the graph.

**Q: What happens if two parallel nodes update the same state key?**
A: The reducer for that key is called with both updates. For `add_messages`, both message lists are merged. For last-write-wins keys, the result is non-deterministic — design parallel nodes to write to different keys.

**Q: Can LangGraph be used without LangChain?**
A: Yes. LangGraph only requires `langchain-core` for base types (`BaseMessage`, `BaseChatModel`). You don't need LangChain chains, retrievers, or memory. Many teams use LangGraph with raw Anthropic/OpenAI SDK calls wrapped in thin adapters.