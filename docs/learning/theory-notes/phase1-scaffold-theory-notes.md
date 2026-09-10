# Phase 1 Scaffold — Theory Notes

## Python package structure

A directory becomes a Python package when it contains `__init__.py`. Without it, `from src.tools import TOOLS` raises `ModuleNotFoundError`.

`__init__.py` can be empty (as here) or used to re-export symbols to simplify import paths.

**Flat module vs package — when to split:**
- One file is fine for prototypes and scripts
- Split into a package when: you have >3 logical concerns, you want per-module tests, or you need to import subsets independently

## pyproject.toml

Introduced in PEP 517/518. Replaces `setup.py` + `setup.cfg` + `tox.ini` + `.flake8` with a single file.

```toml
[build-system]        # how to build a distribution
[project]             # metadata (name, version, deps)
[tool.black]          # black config
[tool.isort]          # isort config
[tool.ruff]           # ruff config
[tool.pytest.ini_options]  # pytest config (when added)
```

## Black vs isort vs ruff

| Tool | Job |
|------|-----|
| Black | Opinionated code formatter — rewrites whitespace, quotes, trailing commas |
| isort | Sorts and groups import statements |
| ruff | Fast linter (replaces flake8, pylint, pyupgrade) — catches bugs and style issues |

They're complementary: Black formats, ruff flags, isort organizes imports. Run order: isort → black → ruff (ruff just reports, doesn't reformat).

## TypedDict

`TypedDict` defines a dict with a fixed set of typed keys. Unlike `dataclass`, it's still a plain dict at runtime — no overhead, no attribute access syntax.

```python
class AgentState(TypedDict):
    messages: list
    output: dict | None
```

LangGraph requires `TypedDict` (or `BaseModel`) for state because it needs to merge partial updates from nodes: a node can return `{"messages": [...]}` and LangGraph merges it into the full state.

## The `Annotated[list, add_messages]` pattern

```python
messages: Annotated[list, add_messages]
```

`add_messages` is a LangGraph reducer — it tells the graph how to combine the existing `messages` list with a node's returned `messages`. Without it, each node's return would **replace** the list; with `add_messages`, it **appends**.

## Interview Q&A

**Q: Why use TypedDict over a dataclass for graph state?**
A: LangGraph merges partial state dicts from nodes. A TypedDict is a plain dict, so merging is natural (`{**old, **new}`). A dataclass would require custom merge logic.

**Q: What does `bind_tools` do?**
A: It attaches tool schemas (name, description, JSON input schema) to the LLM client. When the LLM is invoked, those schemas are sent as part of the request so the model knows it can emit structured tool calls.

**Q: Why keep `_llm` at module level rather than constructing it per call?**
A: `ChatAnthropic` creates an HTTP client with connection pooling. Constructing it per call would leak connections and add latency. Module-level instantiation gives you one client for the lifetime of the process.