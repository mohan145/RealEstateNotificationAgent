# Docker Compose — Theory Notes

## What is Docker Compose?

Docker Compose is a tool for defining and running **multi-container applications**. You describe all your services, networks, and volumes in a single `docker-compose.yml` file, then start everything with one command.

```
docker compose up
```

Without Compose, you'd manually run `docker run` for each container with all its flags — ports, env vars, volumes, networks. Compose replaces that with a declarative config file.

---

## Core Concepts

### Service
A service is one container definition. It maps roughly to "one process" — your agent, an MCP server, a database, a Redis cache.

### Network
Compose creates a private network for all services in the file. Services talk to each other by **service name** as the hostname — no IP addresses needed.

```
agent calls http://mcp-fair-housing:8000/  (not http://172.18.0.3:8000/)
```

### Volume
A named, persistent directory that survives container restarts. Used for databases, output files, model weights.

---

## File Structure

```yaml
version: "3.11"              # Compose file format version

services:
  service-name:              # you choose the name
    build: ./path            # build from Dockerfile
    image: python:3.11-slim  # OR use a pre-built image
    ports:
      - "host:container"     # expose to your machine
    environment:
      KEY: value             # env vars
    env_file:
      - .env                 # load from file
    volumes:
      - ./local:/container   # bind mount
      - named-vol:/data      # named volume
    depends_on:
      - other-service        # start order
    networks:
      - app-net

volumes:
  named-vol:

networks:
  app-net:
```

---

## NotifyBot Example: Agent + MCP Server

Imagine you've graduated `check_fair_housing` to a standalone MCP server (as discussed in `tools-vs-mcp-theory-notes.md`). You now have two processes:

1. **`agent`** — the LangGraph agent (`src/runner.py`)
2. **`mcp-fair-housing`** — the MCP server (`mcp_servers/fair_housing_server.py`) running over HTTP

### Directory layout

```
NotifyBot/
├── docker-compose.yml
├── .env
├── src/                        # agent code
├── mcp_servers/
│   ├── fair_housing/
│   │   ├── Dockerfile
│   │   └── server.py           # FastAPI + MCP
└── Dockerfile                  # agent Dockerfile
```

### Agent Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
COPY sample.json .

RUN pip install -e .

CMD ["python", "-m", "src.runner", "sample.json"]
```

### MCP Server Dockerfile

```dockerfile
# mcp_servers/fair_housing/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY server.py .

RUN pip install fastapi uvicorn mcp

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: "3.11"

services:

  mcp-fair-housing:
    build: ./mcp_servers/fair_housing
    ports:
      - "8000:8000"           # expose to host for debugging
    networks:
      - agent-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 5s
      timeout: 3s
      retries: 5

  agent:
    build: .
    env_file:
      - .env
    environment:
      LLM_PROVIDER: anthropic
      MCP_FAIR_HOUSING_URL: http://mcp-fair-housing:8000/mcp
    volumes:
      - ./sample.json:/app/sample.json   # hot-reload input data
      - ./output:/app/output             # persist results
    depends_on:
      mcp-fair-housing:
        condition: service_healthy       # wait for health check to pass
    networks:
      - agent-net

networks:
  agent-net:
    driver: bridge
```

---

## Key directives explained

### `build` vs `image`

```yaml
# Build from a local Dockerfile
build: ./path/to/dir

# OR pull a pre-built image from Docker Hub / registry
image: python:3.11-slim

# OR both — build locally but tag it
build: .
image: myregistry/notifybot:latest
```

### `ports`

```yaml
ports:
  - "8000:8000"   # host_port:container_port
  - "9000:8000"   # map container's 8000 to host's 9000
```

Without `ports`, the service is only reachable by other services on the same Compose network — not from your machine. Good for internal services that shouldn't be publicly exposed.

### `environment` vs `env_file`

```yaml
# Inline — visible in the compose file (fine for non-secrets)
environment:
  LLM_PROVIDER: anthropic
  LOG_LEVEL: info

# From file — keeps secrets out of the compose file
env_file:
  - .env
```

You can use both together. Inline `environment` overrides `env_file` values for the same key.

### `depends_on`

```yaml
# Basic — just controls start ORDER (doesn't wait for readiness)
depends_on:
  - mcp-fair-housing

# Better — waits for health check to pass before starting agent
depends_on:
  mcp-fair-housing:
    condition: service_healthy
```

`service_healthy` requires a `healthcheck` on the dependency. Without it, `depends_on` only guarantees the container *started*, not that the server inside it is *ready*.

### `healthcheck`

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 5s      # check every 5s
  timeout: 3s       # fail if no response in 3s
  retries: 5        # mark unhealthy after 5 failures
  start_period: 10s # grace period before checks count
```

### `volumes`

```yaml
volumes:
  # Bind mount — syncs a local directory into the container
  - ./sample.json:/app/sample.json   # file
  - ./src:/app/src                   # directory (live reload)

  # Named volume — managed by Docker, persists across restarts
  - db-data:/var/lib/postgresql/data
```

Bind mounts are great for development (edit code locally, runs in container). Named volumes are better for data that shouldn't be tied to a local path.

### `networks`

```yaml
networks:
  agent-net:
    driver: bridge   # default — isolated virtual network
```

All services in the same network can reach each other by service name. Services in different networks can't communicate unless explicitly connected to both.

---

## Common Commands

```bash
# Start all services (build if needed, run in foreground)
docker compose up

# Start in background (detached)
docker compose up -d

# Rebuild images before starting (after code changes)
docker compose up --build

# Stop and remove containers (keeps volumes)
docker compose down

# Stop and remove containers AND volumes
docker compose down -v

# View logs for all services
docker compose logs -f

# View logs for one service
docker compose logs -f agent

# Run a one-off command in a service container
docker compose run agent python -m src.runner sample.json

# Open a shell in a running container
docker compose exec agent bash

# Check status of services
docker compose ps
```

---

## Development workflow with Compose

For active development, use a bind mount so code changes reflect immediately without rebuilding:

```yaml
services:
  agent:
    build: .
    volumes:
      - ./src:/app/src        # live code sync
    command: python -m src.runner sample.json
```

For production, bake code into the image (no bind mount) so the image is self-contained and portable.

---

## Secrets management in Compose

Never hardcode secrets in `docker-compose.yml` — it's usually committed to git.

**Option 1 — `.env` file (local dev)**
```yaml
env_file:
  - .env   # gitignored, contains real keys
```

**Option 2 — Docker secrets (production / Swarm)**
```yaml
services:
  agent:
    secrets:
      - anthropic_key
    environment:
      ANTHROPIC_API_KEY_FILE: /run/secrets/anthropic_key

secrets:
  anthropic_key:
    external: true   # pre-created with: docker secret create anthropic_key -
```

**Option 3 — Environment injection from CI/CD**
```bash
# In GitHub Actions / your deploy pipeline:
ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }} docker compose up -d
```

---

## Multi-stage builds (keeping images small)

```dockerfile
# Stage 1 — install deps
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --prefix=/install -e .

# Stage 2 — runtime only (no build tools)
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ src/
CMD ["python", "-m", "src.runner"]
```

The final image only contains what's needed to run — not pip, not build tools, not cached wheels.

---

## NotifyBot: stdio MCP vs HTTP MCP in Compose

The MCP server above uses HTTP (Streamable HTTP transport). But the original `mcp_deep_dive.md` shows MCP can also run over stdio (spawned as a subprocess).

| Transport | In Compose | How |
|-----------|-----------|-----|
| **stdio** | Not needed | Agent spawns server as a child process — both in same container |
| **HTTP** | Use Compose | Server is a separate container; agent connects over the network |

If your MCP server is stdio-based, it doesn't need its own container — run it in the same container as the agent, spawned via `MultiServerMCPClient`. Docker Compose only adds value when you have genuinely separate processes that need network isolation or independent scaling.

---

## When to use Docker Compose vs just Docker

| Situation | Use |
|-----------|-----|
| Single container app | `docker run` or `Dockerfile` only |
| App + database | Compose |
| App + MCP server (HTTP) | Compose |
| App + cache (Redis) + database + worker | Compose |
| Production at scale (many replicas, rolling deploys) | Kubernetes (Compose is for local / single-host) |

---

## Interview Q&A

**Q: What's the difference between `docker compose up` and `docker compose run`?**
A: `up` starts all services defined in the file and keeps them running. `run` starts a one-off container for a single service, runs a command, then exits — useful for migrations, scripts, or debugging.

**Q: Why does `depends_on` not guarantee the service is ready?**
A: `depends_on` only waits for the container process to start, not for the application inside to be ready (e.g. a web server binding its port). Use `condition: service_healthy` with a `healthcheck` to properly wait for readiness.

**Q: What's the difference between a bind mount and a named volume?**
A: A bind mount maps a specific path on your host into the container — you control the location. A named volume is managed entirely by Docker — Docker decides where data lives on disk. Named volumes are better for databases (portable, Docker manages cleanup); bind mounts are better for source code in development (you edit on host, runs in container).

**Q: How do services find each other in Compose?**
A: Compose creates a private DNS network. Each service's name becomes a hostname. `agent` can reach `mcp-fair-housing` at `http://mcp-fair-housing:8000` — no IP addresses or service discovery needed.

**Q: Can you use Docker Compose in production?**
A: Yes, for single-host deployments. For multi-host or high-availability setups, Kubernetes is the standard. Compose is often used in production for small services, internal tools, or self-hosted apps where you have one server and don't need orchestration.