# Tools vs MCP Servers

## 1. LangChain / LangGraph Tools

### What they are

A tool is a Python function decorated with `@tool` (or defined via `StructuredTool`) that the LLM can call during its reasoning loop. The function lives **in the same process** as your agent.

```python
from langchain_core.tools import tool

@tool
def validate_consent(channel: str, consent: dict) -> dict:
    """Check whether a channel is permitted."""
    return {"permitted": consent.get(f"{channel}_opt_in", False)}
```

LangChain extracts the name, description, and JSON schema from the function signature and docstring, then passes that schema to the LLM. The LLM emits a tool call (structured JSON), your code executes the function, and the result is appended to the message history.

### Lifecycle

```
LLM emits tool_call JSON
       │
       ▼
ToolNode deserializes args
       │
       ▼
Python function runs (in-process)
       │
       ▼
Result appended as ToolMessage
       │
       ▼
LLM sees result, continues reasoning
```

### Key characteristics

| Property | Value |
|----------|-------|
| Where it runs | Same process as the agent |
| Language | Python only |
| Defined by | You, inline in the agent codebase |
| Discoverable at runtime | No — must be explicitly passed to the LLM |
| Reusable across agents | Only via import |
| Deployment unit | Your agent app |
| Transport | None — direct function call |
| Schema source | Docstring + type hints |

---

## 2. MCP Servers (Model Context Protocol)

### What they are

MCP is an open protocol (by Anthropic) that standardizes how LLMs discover and call external capabilities. An MCP server is a **separate process** (or remote service) that exposes tools, resources, and prompts over a defined transport. The agent connects to it as a client.

```
┌─────────────────────┐        stdio / SSE / HTTP        ┌──────────────────────┐
│   LangGraph Agent   │ ◄──────────────────────────────► │    MCP Server        │
│   (MCP client)      │    JSON-RPC 2.0 messages          │    (separate process)│
└─────────────────────┘                                   └──────────────────────┘
```

The server advertises its tools via a `tools/list` response. The client fetches that list at startup and hands the schemas to the LLM — same as inline tools from the LLM's perspective. When the LLM calls a tool, the client sends a `tools/call` JSON-RPC request to the server and returns the result.

### Transports

| Transport | Use case |
|-----------|----------|
| `stdio` | Local process — agent spawns server as subprocess, communicates over stdin/stdout |
| `SSE` (Server-Sent Events) | Remote server over HTTP — agent connects to a URL |
| `Streamable HTTP` | Newer standard, replaces SSE for most remote cases |

### Example: connecting LangGraph to an MCP server

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

async with MultiServerMCPClient({
    "fair_housing": {
        "command": "python",
        "args": ["fair_housing_server.py"],
        "transport": "stdio",
    },
    "crm": {
        "url": "https://crm.internal/mcp",
        "transport": "streamable_http",
    },
}) as client:
    tools = client.get_tools()  # returns LangChain-compatible tool objects
    llm = ChatAnthropic(model="claude-sonnet-4-6").bind_tools(tools)
```

From the agent's perspective, MCP tools look identical to inline tools after loading.

### What an MCP server exposes

- **Tools** — callable functions (like inline tools)
- **Resources** — data the LLM can read (files, DB rows, docs)
- **Prompts** — reusable prompt templates
- **Sampling** — the server can ask the client's LLM to generate text (advanced)

---

## 3. Side-by-Side Comparison

| Dimension | LangChain Tool | MCP Server |
|-----------|---------------|------------|
| **Process boundary** | Same process | Separate process or remote service |
| **Language** | Python only | Any language (Python, Node, Go, Rust…) |
| **Reusability** | Import only | Any MCP-compatible client can connect |
| **Discovery** | Hardcoded in agent | Dynamic — `tools/list` at runtime |
| **Transport overhead** | None (function call) | Serialization + IPC or network round-trip |
| **Versioning** | Agent redeploy | Server can be versioned independently |
| **Auth / isolation** | Shared process memory | Process / network boundary |
| **Tooling ecosystem** | LangChain only | Claude Desktop, Cursor, any MCP client |
| **Startup cost** | None | Server process must be running |
| **State** | Stateless by default | Can hold persistent connections (DB, APIs) |

---

## 4. When to Use Which

### Use inline LangChain tools when:

- The logic is simple and tightly coupled to your agent
- You only have one agent consuming these tools
- You want zero transport overhead (latency matters)
- The tool is pure computation (timestamp formatting, scoring, JSON shaping)
- Prototyping — inline is faster to iterate

### Use an MCP server when:

- The capability is shared across multiple agents or apps (Claude Desktop, another team's agent, etc.)
- The tool is written in a different language (e.g., a Go service, a Node.js CRM connector)
- The tool needs persistent state or long-lived connections (database pool, authenticated API session)
- You want to version and deploy the tool independently from the agent
- The tool has heavy dependencies you don't want in the agent's process
- You are building something that should work with the broader MCP ecosystem

---

## 5. Using Both Together

You can mix inline tools and MCP tools in the same LangGraph agent. The LLM sees them identically.

```python
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

@tool
def score_personalization(body: str, profile: dict) -> dict:
    """Local fast heuristic — inline tool."""
    ...

async with MultiServerMCPClient({
    "fair_housing": {"command": "python", "args": ["fh_server.py"], "transport": "stdio"},
}) as client:
    mcp_tools = client.get_tools()           # tools from MCP server
    all_tools = [score_personalization] + mcp_tools
    llm = ChatAnthropic(model="claude-sonnet-4-6").bind_tools(all_tools)
```

### Recommended split for this project (NotifyBot)

| Tool | Where |
|------|-------|
| `get_current_time` | Inline — pure util, no deps |
| `validate_consent` | Inline — simple dict check |
| `score_personalization` | Inline — fast heuristic |
| `finalize_output` | Inline — output shaping |
| `check_fair_housing` | MCP server — could be a shared compliance service used by multiple agents, potentially powered by a fine-tuned classifier with its own dependencies |

---

## Summary

> **Inline tools = fast, local, agent-specific.**
> **MCP servers = portable, language-agnostic, independently deployable.**

Start with inline tools. Graduate a tool to an MCP server when it needs to be shared, independently versioned, or written outside Python.
