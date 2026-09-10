# LangGraph — Project Notes (NotifyBot)

## How LangGraph is used in this project

NotifyBot uses a custom LangGraph StateGraph to implement a ReAct (Reason + Act) loop that processes messaging records end-to-end.

---

## Graph topology

```
input_record
     │
     ▼
  [llm]  ◄──────────────────────┐
     │                          │
     │ tool_calls present?       │
     ├── yes (not finalize) ──► [tools]
     │                          │
     │ finalize_output called?   │
     └── yes ──────────────────► [validate] ──► END
     │
     └── no tool_calls ────────► [validate] ──► END
```

The loop runs until the LLM calls `finalize_output` or produces no tool calls.

---

## State fields and why each exists

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # full conversation history
    input_record: dict                        # the raw input — read-only by convention
    output: dict | None                       # populated by validate_node
    validation_errors: list[str]              # populated by validate_node
```

- `messages` uses `add_messages` so each node appends rather than replacing history
- `input_record` is set once at `invoke()` time and never written by any node — treated as read-only context
- `output` and `validation_errors` are written only by `validate_node` at the very end

---

## Why a custom graph instead of `create_react_agent`

`create_react_agent` gives you `llm → tools → llm` but no post-processing. NotifyBot needs:

1. A **custom validate node** that runs constraint checks (opt-out, PII) after `finalize_output`
2. **Custom routing** — `finalize_output` routes to `validate` while all other tool calls route back to `llm`
3. **Custom state fields** (`output`, `validation_errors`) that a pre-built agent doesn't know about

---

## The `should_continue` router

```python
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        for call in last.tool_calls:
            if call["name"] == "finalize_output":
                return "validate"
        return "tools"
    return "validate"
```

Key behaviour: if the LLM calls `finalize_output` alongside other tools in the same response, we still route to `validate` — `finalize_output` is treated as terminal.

---

## How ToolNode works in this graph

`ToolNode(TOOLS)` is wired at the `"tools"` node. When the LLM emits tool calls, ToolNode:
1. Finds the matching function by name in `TOOLS`
2. Calls it with the LLM-supplied arguments
3. Wraps the return value as a `ToolMessage` and appends it to `messages`

The LLM sees all tool results on the next iteration and continues reasoning.

---

## validate_node design

`validate_node` is the only node that writes to `output` and `validation_errors`. It:
1. Calls `_extract_finalize_output` to pull the `finalize_output` result from message history
2. Checks `no_pii_leak` constraint with regex
3. Checks `include_opt_out_instructions` constraint

It does **not** loop back to the LLM on failure — it just records errors in `validation_errors`. The caller (`run()`) surfaces those errors in the return value. A future improvement could re-route to `llm` with the error as feedback.

---

## Gotchas

- **`invoke()` requires all state keys** — TypedDict annotations don't provide defaults. Omitting any key causes a KeyError inside the graph.
- **`_llm` at module level in `nodes.py`** — constructed once when the module is imported. This means the provider is chosen at import time, not at call time. If `LLM_PROVIDER` changes after import, the old LLM instance is reused. Restart the process to pick up env changes.
- **`finalize_output` result lives in `messages`** — not in a dedicated state key. `_extract_finalize_output` scans message history in reverse to find it. This is intentional: ToolNode writes all tool results to messages, so that's the canonical location.
- **No checkpointer** — each `run()` call is fully stateless. Records are processed independently with no shared history.