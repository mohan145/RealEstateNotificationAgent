# Project: Refer to problem_statement.txt

## Core Behaviour
- At the START of every session, read `docs/PROGRESS.md` before doing anything else.
- Always split work into phases. Read the active task file to find the current phase and next unchecked step.
- Work on ONE step at a time. Announce the step and wait for confirmation before starting.
- Never move to the next step automatically — always stop, report what was done, and wait.
- After completing each step:
  - Update `docs/PROGRESS.md` with what was done, any decisions made and why, and what's next.
  - Check off the completed step in the task file.

## Decisions Log
- When any significant decision is made (library choice, architecture, approach), log it in `docs/PROGRESS.md` under a "Decisions" section with the reason.
- If a better approach is found later, log why the previous decision was changed — don't just overwrite.

## Coding Style
- Python 3.11+
- Type hints on all functions
- Black for formatting, isort for imports, ruff for linting
- Google-style docstrings on all public functions
- Never use bare `except:` — always catch specific exceptions
- Functions under 40 lines — extract if longer
- Tests for every new module in `tests/` mirroring the `src/` structure


## Active Task
@docs/tasks/phase1-scaffold.md 