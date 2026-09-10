# NotifyBot — Progress Log

## Session: 2026-09-08

### Current Phase
Phase 1 — Bring Project In Line with CLAUDE.md
Active task file: `docs/tasks/phase1-scaffold.md`

---

### Completed Steps

#### Step 1 — Create docs/ scaffolding
**What was done:**
- Created `docs/`, `docs/tasks/`, `docs/learning/project-notes/`, `docs/learning/theory-notes/`
- Created `docs/PROGRESS.md` (this file)
- Created `docs/tasks/phase1-scaffold.md` defining all Phase 1 steps
- Created `src/` and `tests/` directories (empty, to be populated in Steps 2–3)

**Decisions:**
- Split Phase 1 into 6 steps to match the one-step-at-a-time workflow
- Chose to refactor `agent.py` into 5 modules in `src/` (state, tools, nodes, graph, runner) — mirrors the logical separation already visible in the file's section comments
- `tests/` will mirror `src/` structure exactly per CLAUDE.md

**Next:** ~~Step 2~~ → see below

---

#### Step 2 — Refactor `agent.py` into `src/` package
**What was done:**
- Created `src/__init__.py`, `src/state.py`, `src/tools.py`, `src/nodes.py`, `src/graph.py`, `src/runner.py`
- `state.py` — `AgentState` TypedDict only
- `tools.py` — all 5 `@tool` functions + `TOOLS` list; added Google docstrings and cleaned up formatting
- `nodes.py` — `llm_node`, `should_continue`, `validate_node`; extracted `_extract_finalize_output` helper to keep `validate_node` under 40 lines; moved `import re` out of function body
- `graph.py` — `build_graph()` only; no business logic
- `runner.py` — `run()` + `__main__` entrypoint; original `agent.py` can now be deleted or kept as legacy

**Decisions:**
- Extracted `_extract_finalize_output` as a private helper — `validate_node` was approaching 40 lines with it inline
- `_llm` instantiated at module level in `nodes.py` (not inside `llm_node`) — avoids re-creating the client on every graph invocation
- `import re` moved to module top in `nodes.py` — bare `import` inside a function body is a code smell

**Next:** ~~Step 3 skipped~~ → Step 4

---

#### Step 3 — Tests
Skipped by user decision. Tests directory exists but is empty.

---

#### Step 4 — `pyproject.toml`
**What was done:**
- Created `pyproject.toml` with project metadata, runtime deps, and dev extras
- Configured Black (line-length 100, py311), isort (black profile), ruff (E/F/I/UP/B/SIM rules)

**Decisions:**
- line-length 100 (not 88) — agent prompts and JSON strings make 88 feel tight
- ruff replaces flake8 + pylint for linting; Black handles formatting separately

**Next:** ~~Step 5~~ → Step 6

---

#### Step 5 — Learning notes
**What was done:**
- `docs/learning/project-notes/phase1-scaffold-project-notes.md` — package layout, key design choices, gotchas
- `docs/learning/theory-notes/phase1-scaffold-theory-notes.md` — TypedDict, Annotated reducers, pyproject.toml, Black/isort/ruff, interview Q&A

---

#### Step 6 — Fix CLAUDE.md Active Task pointer
**What was done:**
- Updated `CLAUDE.md` `## Active Task` from placeholder to `@docs/tasks/phase1-scaffold.md`

---

#### Step 7 — LLM provider factory + env config
**What was done:**
- Created `src/llm.py` — `get_llm(tools)` factory; reads `LLM_PROVIDER` env var, dispatches to `_build_anthropic` or `_build_openai`
- Updated `src/nodes.py` — replaced hardcoded `ChatAnthropic(...)` with `get_llm(TOOLS)`
- Created `.env.example` — documented all env vars with defaults
- Created `.env` — local config file (not committed); keys left blank for user to fill
- Created `.gitignore` — excludes `.env`, `__pycache__`, `.venv`, `dist`
- Updated `pyproject.toml` — added `langchain-openai` and `python-dotenv` to dependencies
- Updated `src/runner.py` — calls `load_dotenv()` at startup

**Decisions:**
- Provider selection via `LLM_PROVIDER` env var (not a CLI flag) — keeps the interface uniform whether running as a script or imported as a library
- `langchain-openai` imported lazily inside `_build_openai` — avoids import error if the package isn't installed and the user is only using Anthropic
- Same pattern for `langchain-anthropic` in `_build_anthropic` — symmetric and consistent
- `load_dotenv()` in `runner.py` (not in `llm.py`) — the runner is the entrypoint; library code shouldn't have side effects like loading env files

---

#### Step 8 — Learning docs expansion
**What was done:**
- `docs/learning/theory-notes/pyproject-toml-theory-notes.md` — full deep dive: PEP history, every table, Black/isort/ruff config, deployment patterns (local, Docker, lockfiles, secret management), interview Q&A
- `docs/learning/theory-notes/langgraph-theory-notes.md` — full deep dive: state, reducers, nodes, edges, cycles, checkpointers, ToolNode, streaming, parallel nodes, common patterns, comparison with alternatives, interview Q&A
- `docs/learning/project-notes/langgraph-project-notes.md` — how LangGraph is specifically used in NotifyBot: graph topology, state field rationale, why custom graph over `create_react_agent`, router logic, validate_node design, gotchas
- `docs/learning/theory-notes/mcp-theory-notes.md` — moved from `mcp_deep_dive.md` (root) into learning structure; original deleted

---

### Decisions Log

| Decision | Reason |
|----------|--------|
| Split `agent.py` into `state.py`, `tools.py`, `nodes.py`, `graph.py`, `runner.py` | The file already has clear section comments for each; splitting makes each unit independently testable |
| Keep all tools as inline LangChain tools (not MCP) | `tools_vs_mcp.md` documents this as the right call for this stage — only `check_fair_housing` is a candidate for MCP later |
| Use `pyproject.toml` (not `setup.py`) | Modern standard for Python 3.11+ projects; supports Black, isort, ruff config in one file |