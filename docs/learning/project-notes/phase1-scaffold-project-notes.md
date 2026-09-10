# Phase 1 Scaffold — Project Notes

## What this phase did

Brought the NotifyBot project in line with the conventions in CLAUDE.md:

- Created the `docs/` scaffolding: `PROGRESS.md`, `docs/tasks/`, `docs/learning/`
- Split the flat `agent.py` into a proper `src/` package
- Added `pyproject.toml` with tooling config

## Package layout

```
src/
├── state.py    — AgentState TypedDict (shared graph state)
├── tools.py    — 5 @tool functions the LLM can call
├── nodes.py    — graph node functions + routing logic
├── graph.py    — graph wiring (build_graph)
└── runner.py   — public run() entry point + __main__
```

## Key design choices

**Why split by concern, not by layer?**
Each file has one job. `tools.py` has no graph knowledge; `graph.py` has no LLM knowledge. This makes each unit independently readable and (eventually) testable.

**Why is `_llm` at module level in `nodes.py`?**
`ChatAnthropic(...).bind_tools(...)` creates an HTTP client. Instantiating it inside `llm_node` would create a new client on every LLM call in the graph loop — wasteful and slow.

**Why extract `_extract_finalize_output`?**
`validate_node` would have exceeded 40 lines (CLAUDE.md limit) with that logic inline. Extracting it also makes the extraction logic independently testable later.

## Gotchas

- `src/` needs `__init__.py` for Python to treat it as a package (required for `from src.X import Y` to work).
- The original `agent.py` is still in the root — it's now superseded by `src/runner.py` but hasn't been deleted yet.
- `import re` was originally inside the function body in `validate_node` — moved to module top per convention.