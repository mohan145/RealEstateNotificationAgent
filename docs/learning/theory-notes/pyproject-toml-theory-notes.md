# pyproject.toml — Theory Notes

## What is pyproject.toml?

`pyproject.toml` is the single configuration file for modern Python projects, introduced across three PEPs:

| PEP | What it added |
|-----|--------------|
| PEP 517 (2017) | Defined a build system interface — how tools build a distribution |
| PEP 518 (2018) | Added `[build-system]` table to declare build dependencies |
| PEP 621 (2020) | Standardised `[project]` table for metadata (name, version, deps) |

Before this, projects spread config across `setup.py`, `setup.cfg`, `MANIFEST.in`, `tox.ini`, `.flake8`, `mypy.ini`. `pyproject.toml` collapses all of them.

---

## File Structure

```toml
[build-system]       # HOW to build a distribution package
[project]            # WHAT the package is (metadata + deps)
[project.optional-dependencies]  # extras (dev, test, docs)
[tool.black]         # Black formatter config
[tool.isort]         # isort config
[tool.ruff]          # ruff linter config
[tool.pytest.ini_options]  # pytest config
[tool.mypy]          # mypy config
```

Every `[tool.*]` section is owned by that tool — TOML ignores unknown tables, so tools only read their own section.

---

## [build-system]

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"
```

- `requires` — packages pip must install before it can build your project
- `build-backend` — the Python object pip calls to actually build the wheel/sdist

Common backends:

| Backend | Package | Use when |
|---------|---------|---------|
| `setuptools.backends.legacy:build` | `setuptools` | Default, most compatible |
| `hatchling.build` | `hatchling` | Modern, fast, no `setup.py` |
| `flit_core.buildapi` | `flit_core` | Pure Python libs, minimal config |
| `poetry.core.masonry.api` | `poetry-core` | If using Poetry |

---

## [project]

```toml
[project]
name = "notifybot"
version = "0.1.0"
description = "..."
requires-python = ">=3.11"
dependencies = [
    "langchain-anthropic",
    "langchain-openai",
]
```

### dependencies vs optional-dependencies

```toml
[project.optional-dependencies]
dev = ["black", "ruff", "pytest"]
docs = ["sphinx", "furo"]
```

Install with:
```bash
pip install -e .           # runtime only
pip install -e ".[dev]"    # + dev extras
pip install -e ".[dev,docs]"  # multiple extras
```

`-e` = editable install — the package points to your source directory, so changes take effect immediately without reinstalling.

### Version pinning strategy

| Style | Example | Use when |
|-------|---------|---------|
| Unpinned | `"requests"` | Libraries — let the user resolve |
| Lower bound | `"requests>=2.28"` | You need a specific feature |
| Exact | `"requests==2.31.0"` | Applications — reproducible deploys |
| Compatible | `"requests~=2.31"` | Allows patch updates only |

For an **application** (like NotifyBot), pin exactly in a lockfile (see Deployment section). For a **library**, use lower bounds only.

---

## [tool.black]

```toml
[tool.black]
line-length = 100
target-version = ["py311"]
```

Black is an *opinionated* formatter — it makes all style decisions for you. It rewrites:
- Trailing commas
- Quote style (prefers double quotes)
- Line wrapping
- Blank lines between functions/classes

Key principle: **Black is non-negotiable**. It doesn't have a config option for every preference — by design. The only knobs are `line-length` and `target-version`.

Run: `black src/`

---

## [tool.isort]

```toml
[tool.isort]
profile = "black"
line_length = 100
```

isort groups and sorts `import` statements into three sections:

```python
# 1. stdlib
import json
import os

# 2. third-party
from langchain_core.tools import tool

# 3. local
from src.state import AgentState
```

`profile = "black"` ensures isort's output is compatible with Black's formatting (they used to conflict on trailing commas in multi-line imports).

Run: `isort src/`

---

## [tool.ruff]

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = ["E501"]
```

Ruff is a Rust-based linter that replaces flake8, pylint, pyupgrade, and others. It is 10–100× faster than the tools it replaces.

### Rule sets

| Code | Origin | What it catches |
|------|--------|----------------|
| `E` | pycodestyle | Style errors (indentation, whitespace) |
| `F` | pyflakes | Logic errors (undefined names, unused imports) |
| `I` | isort | Import order (ruff can also sort imports itself) |
| `UP` | pyupgrade | Old Python syntax (`Union[X, Y]` → `X \| Y`) |
| `B` | flake8-bugbear | Common bugs and design issues |
| `SIM` | flake8-simplify | Suggests simpler code patterns |

`E501` (line too long) is ignored because Black already handles line length.

Run: `ruff check src/`
Auto-fix: `ruff check --fix src/`

---

## Deployment

### Local development

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install the package in editable mode with dev tools
pip install -e ".[dev]"

# 3. Copy and fill in env vars
cp .env.example .env
# Edit .env with your API keys

# 4. Run
python -m src.runner sample.json
```

---

### Reproducible deploys — lockfiles

`pyproject.toml` lists *constraints*, not exact versions. For reproducible deploys, generate a lockfile:

**pip-compile (pip-tools):**
```bash
pip install pip-tools
pip-compile pyproject.toml -o requirements.lock
# Deploy with:
pip install -r requirements.lock
```

**uv (modern, fast):**
```bash
pip install uv
uv lock          # generates uv.lock
uv sync          # installs exactly what's in the lock
```

---

### Docker deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

# Install deps (no dev extras)
RUN pip install -e .

# Env vars injected at runtime (never baked into image)
ENV LLM_PROVIDER=anthropic

CMD ["python", "-m", "src.runner", "sample.json"]
```

Pass secrets at runtime:
```bash
docker run \
  -e ANTHROPIC_API_KEY=sk-... \
  -v $(pwd)/data:/app/data \
  notifybot
```

**Never** `COPY .env` into a Docker image — baked secrets are a security incident waiting to happen.

---

### Environment variable management in production

| Approach | Tool | Use when |
|----------|------|---------|
| `.env` file | python-dotenv | Local dev only |
| Shell env | `export KEY=val` | CI/CD pipelines |
| Secret manager | AWS Secrets Manager, GCP Secret Manager | Production |
| Kubernetes secrets | `kubectl create secret` | K8s deployments |
| Docker secrets | `--secret` flag | Docker Swarm |

python-dotenv's `load_dotenv()` is a no-op if the env var is already set — so the same code works locally (reads `.env`) and in production (reads real env vars injected by the platform).

---

## Interview Q&A

**Q: What's the difference between `dependencies` in `[project]` and `requires` in `[build-system]`?**
A: `[build-system].requires` are packages needed to *build* the package (e.g. setuptools). `[project].dependencies` are packages needed to *run* it. They're installed at different times by pip.

**Q: When would you use `setup.py` instead of `pyproject.toml`?**
A: Only for very old projects or if you need dynamic version computation (e.g. reading version from git tags at build time). Modern setuptools supports dynamic fields in `pyproject.toml` via `[tool.setuptools.dynamic]`, so even that use case is mostly covered now.

**Q: What does editable install (`pip install -e .`) actually do?**
A: It creates a `.pth` file in `site-packages` that points to your source directory. Python's import system follows that pointer, so `import src` finds your actual source files. No copy is made — edits take effect immediately.

**Q: Why not just use `requirements.txt`?**
A: `requirements.txt` is a flat list with no metadata, no build system config, no tool config. It can't express extras, it doesn't encode the build backend, and it spreads config across multiple files. `pyproject.toml` is the standard for everything except final lockfiles (which are a separate concern).
