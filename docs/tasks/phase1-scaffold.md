# Phase 1 — Bring Project In Line with CLAUDE.md

## Goal
Restructure the project so it matches the conventions defined in CLAUDE.md:
- Proper `docs/` scaffolding (PROGRESS.md, task files, learning notes)
- `src/` package layout replacing the flat `agent.py`
- `tests/` mirroring `src/`
- Code style: type hints, Google docstrings, Black/isort/ruff compliant, functions ≤ 40 lines

---

## Steps

- [x] Step 1 — Create `docs/` scaffolding: `PROGRESS.md`, `docs/tasks/phase1-scaffold.md`, `docs/learning/` subfolders, `src/`, `tests/`
- [x] Step 2 — Refactor `agent.py` into `src/` package: split into `state.py`, `tools.py`, `nodes.py`, `graph.py`, `runner.py`
- [~] Step 3 — Write `tests/` for each module in `src/` (skipped for now)
- [x] Step 4 — Add `pyproject.toml` with Black, isort, ruff config and project metadata
- [x] Step 5 — Write learning notes for this phase (project-notes + theory-notes)
- [x] Step 6 — Update CLAUDE.md Active Task pointer to this file
- [x] Step 7 — LLM provider factory (Anthropic + OpenAI) + .env config