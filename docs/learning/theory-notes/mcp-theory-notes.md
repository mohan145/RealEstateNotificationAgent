# MCP (Model Context Protocol) — Deep Dive

## What Is MCP?

MCP is an open protocol introduced by Anthropic in late 2024. Its goal is to standardize how AI models connect to external data, tools, and services — the same way HTTP standardized how browsers talk to servers.

Before MCP, every AI app had to write custom integration code for every tool. MCP defines a single client-server protocol so that any MCP-compatible host (Claude Desktop, a LangGraph agent, Cursor, etc.) can connect to any MCP server without custom glue code.

> Think of MCP as USB-C for AI tools. One standard port, any device.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   HOST                          │
│  (Claude Desktop / LangGraph / Cursor / etc.)   │
│                                                 │
│   ┌─────────────┐      ┌─────────────┐          │
│   │ MCP Client  │      │ MCP Client  │          │
│   └──────┬──────┘      └──────┬──────┘          │
└──────────┼────────────────────┼─────────────────┘
           │ JSON-RPC 2.0       │ JSON-RPC 2.0
           ▼                    ▼
┌──────────────────┐   ┌──────────────────────┐
│   MCP Server A   │   │    MCP Server B       │
│  (Fair Housing)  │   │  (CRM Connector)      │
└──────────────────┘   └──────────────────────┘
```

- **Host** — the application running the LLM (your LangGraph agent, Claude Desktop)
- **Client** — lives inside the host, manages one connection to one server
- **Server** — exposes capabilities (tools, resources, prompts) over the protocol

One host can have many clients, each connected to a different server.

---

## Protocol Mechanics

MCP uses **JSON-RPC 2.0** for all messages. The flow on startup:

```
Client                          Server
  │                               │
  │──── initialize ──────────────►│   client sends its capabilities
  │◄─── initialized ──────────────│   server sends its capabilities + version
  │                               │
  │──── tools/list ──────────────►│   client discovers available tools
  │◄─── { tools: [...] } ─────────│   server returns tool schemas
  │                               │
  │  (LLM picks a tool to call)   │
  │                               │
  │──── tools/call ──────────────►│   { name, arguments }
  │◄─── { content: [...] } ───────│   result returned
```

All messages are structured JSON. The server never pushes unsolicited calls to the LLM — it only responds.

---

## Transports

MCP is transport-agnostic. The protocol defines behavior; transport defines the wire.

### 1. stdio (Standard I/O)

The host spawns the server as a **child process**. Communication happens over stdin/stdout.

```
Host Process
  │
  ├── spawns ──► Server Process (child)
  │                  stdin  ← JSON-RPC requests
  │                  stdout → JSON-RPC responses
```

**Use when:**
- Server runs locally on the same machine
- You want zero network overhead
- Server has no external clients (only this host uses it)
- Development / local tooling

**Example config (Claude Desktop `claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "fair_housing": {
      "command": "python",
      "args": ["fair_housing_server.py"]
    }
  }
}
```

---

### 2. SSE (Server-Sent Events) — Legacy Remote Transport

Server runs as an HTTP service. Client connects to an SSE endpoint for server→client streaming and POSTs for client→server messages.

```
Client ──POST /message──────────► HTTP Server
Client ◄──GET  /sse (stream)───── HTTP Server
```

**Use when:**
- Server is remote (different machine or cloud)
- Multiple clients need to share one server instance
- You need to cross process/machine boundaries

**Note:** SSE is being superseded by Streamable HTTP in newer MCP versions.

---

### 3. Streamable HTTP — Current Standard for Remote

Single HTTP endpoint that handles both directions. Supports streaming responses via chunked transfer. Simpler than SSE.

```
Client ──POST /mcp──────────────► HTTP Server
       ◄── streamed response ──────
```

**Use when:**
- Deploying a shared MCP server to the cloud
- Need standard HTTP infrastructure (load balancers, auth middleware, etc.)
- Building a production-grade multi-tenant server

---

## What a Server Exposes

MCP servers can expose four primitive capability types:

### Tools
Callable functions the LLM can invoke. Equivalent to function calling.

```python
# Server side
@server.call_tool()
async def handle_call(name: str, arguments: dict):
    if name == "check_fair_housing":
        body = arguments["body"]
        violations = scan_for_violations(body)
        return [TextContent(type="text", text=json.dumps(violations))]
```

The LLM sees the tool schema and decides when to call it — same as inline tools.

---

### Resources
Static or dynamic data the LLM can read — like files, database rows, or API responses. The LLM requests them, they're injected into context.

```
resources/list  → [ { uri: "crm://prospects/taylor-123", name: "Taylor's Profile" } ]
resources/read  → { contents: [ { text: "{ first_name: Taylor, ... }" } ] }
```

**Use for:** documents, prospect records, property listings, templates — anything the LLM needs to read but not execute.

---

### Prompts
Reusable prompt templates the server exposes. The host can fetch and inject them.

```
prompts/list → [ { name: "welcome_sms", description: "Welcome SMS for new prospects" } ]
prompts/get  → { messages: [ { role: "user", content: "Write a welcome SMS for {first_name}..." } ] }
```

**Use for:** brand-approved message templates, standardized instructions, compliance-approved prompt fragments.

---

### Sampling (Advanced)
The server asks the client's LLM to generate text on its behalf. The server initiates the LLM call, not the other way around.

```
Server ──► sampling/createMessage ──► Client ──► LLM
                                              ◄── response
Server ◄── result ──────────────────────────────
```

**Use for:** agentic servers that need to chain LLM calls internally without exposing that complexity to the host.

---

## Implementation Types

### Type 1 — Local stdio Server (Python)

Simplest form. Runs on the same machine as the agent.

```python
# fair_housing_server.py
import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("fair-housing")

FORBIDDEN = [
    "no children", "adults only", "no families",
    "no section 8", "english only", "ideal for singles",
]

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="check_fair_housing",
            description="Scan message body for fair housing violations",
            inputSchema={
                "type": "object",
                "properties": {
                    "body": {"type": "string", "description": "Message body to scan"},
                },
                "required": ["body"],
            },
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "check_fair_housing":
        body = arguments["body"].lower()
        found = [f for f in FORBIDDEN if f in body]
        result = {"passed": len(found) == 0, "violations": found}
        return [TextContent(type="text", text=json.dumps(result))]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

asyncio.run(main())
```

---

### Type 2 — Remote HTTP Server (FastAPI + MCP)

Production server deployable to cloud. Multiple agents connect to it.

```python
# fair_housing_http_server.py
from fastapi import FastAPI
from mcp.server.fastapi import create_mcp_router
from mcp.server import Server
from mcp.types import Tool, TextContent
import json

app_server = Server("fair-housing")

@app_server.list_tools()
async def list_tools() -> list[Tool]:
    return [Tool(name="check_fair_housing", ...)]

@app_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    ...

fastapi_app = FastAPI()
fastapi_app.include_router(
    create_mcp_router(app_server),
    prefix="/mcp"
)

# Deploy with: uvicorn fair_housing_http_server:fastapi_app
```

Clients connect to `https://compliance.internal/mcp`.

---

### Type 3 — Multi-Tool Server

One server exposes many related tools. Common pattern for domain-specific servers.

```python
# crm_server.py — exposes all CRM operations as tools
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_prospect",      description="Fetch prospect record by ID"),
        Tool(name="update_prospect",   description="Update prospect fields"),
        Tool(name="log_interaction",   description="Log a communication event"),
        Tool(name="get_cadence",       description="Get active cadence for a prospect"),
        Tool(name="schedule_message",  description="Schedule a message for delivery"),
    ]
```

---

### Type 4 — Resource + Tool Server

Exposes both readable data (resources) and callable tools.

```python
# property_server.py
@app.list_resources()
async def list_resources():
    properties = await db.get_all_properties()
    return [
        Resource(
            uri=f"property://{p['id']}",
            name=p["name"],
            description=f"Listing data for {p['name']}",
        )
        for p in properties
    ]

@app.read_resource()
async def read_resource(uri: str):
    prop_id = uri.replace("property://", "")
    data = await db.get_property(prop_id)
    return [TextContent(type="text", text=json.dumps(data))]

@app.list_tools()
async def list_tools():
    return [Tool(name="check_availability", ...)]
```

The LLM can read property listings as context AND call tools to check availability.

---

### Type 5 — Node.js / Non-Python Server

MCP is language-agnostic. A Node.js server the Python agent can connect to via stdio.

```javascript
// crm-connector/index.js
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server({ name: "crm-connector", version: "1.0.0" });

server.setRequestHandler("tools/list", async () => ({
  tools: [{
    name: "get_prospect",
    description: "Fetch a prospect from Salesforce",
    inputSchema: { type: "object", properties: { id: { type: "string" } } }
  }]
}));

server.setRequestHandler("tools/call", async (req) => {
  const { name, arguments: args } = req.params;
  if (name === "get_prospect") {
    const data = await salesforce.getContact(args.id);
    return { content: [{ type: "text", text: JSON.stringify(data) }] };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

Python agent spawns this as: `"command": "node", "args": ["crm-connector/index.js"]`

---

## Integrations

### Integration 1 — LangGraph + MCP (langchain-mcp-adapters)

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

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
    tools = client.get_tools()
    agent = create_react_agent(
        model=ChatAnthropic(model="claude-sonnet-4-6"),
        tools=tools,
    )
    result = await agent.ainvoke({"messages": [HumanMessage(content="...")]})
```

MCP tools appear identical to inline tools after `client.get_tools()`.

---

### Integration 2 — Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "fair_housing": {
      "command": "python",
      "args": ["/path/to/fair_housing_server.py"]
    },
    "crm": {
      "command": "node",
      "args": ["/path/to/crm-connector/index.js"]
    }
  }
}
```

Claude Desktop spawns these on startup. You get the tools in every Claude conversation without writing any agent code.

---

### Integration 3 — Mixing Inline Tools + MCP Tools in LangGraph

```python
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

# Fast, local, stateless — keep inline
@tool
def score_personalization(body: str, profile: dict) -> dict:
    """Score personalization against profile fields."""
    ...

@tool
def finalize_output(channel: str, send_at: str, body: str, ...) -> dict:
    """Emit final structured output."""
    ...

async with MultiServerMCPClient({
    "fair_housing": {"command": "python", "args": ["fh_server.py"], "transport": "stdio"},
    "crm":          {"url": "https://crm.internal/mcp", "transport": "streamable_http"},
}) as client:
    mcp_tools = client.get_tools()
    all_tools = [score_personalization, finalize_output] + mcp_tools
    llm = ChatAnthropic(model="claude-sonnet-4-6").bind_tools(all_tools)
```

---

### Integration 4 — Cursor / VS Code

Cursor supports MCP servers configured in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "notifybot-tools": {
      "command": "python",
      "args": ["tools/notifybot_server.py"]
    }
  }
}
```

Any tool you expose becomes available to the Cursor AI assistant while coding.

---

## Security Considerations

| Risk | Mitigation |
|------|-----------|
| Tool call injection (malicious input tricks LLM into calling destructive tools) | Validate all tool inputs server-side, never trust LLM-supplied args blindly |
| Secrets in tool responses leaked to LLM context | Redact PII/secrets before returning from tool |
| Unauthenticated remote MCP servers | Add API key or OAuth to HTTP transport |
| stdio server with broad OS access | Run in Docker or sandboxed subprocess |
| Prompt injection via resource content | Sanitize resource content before injecting into context |

---

## When to Build an MCP Server vs Inline Tool

| Signal | Go MCP Server |
|--------|--------------|
| Other teams / agents need this tool | Yes |
| Tool written in Node, Go, Rust, etc. | Yes |
| Tool needs a persistent DB connection or auth session | Yes |
| Tool is a compliance/legal function (audit trail needed) | Yes |
| Tool is used in Claude Desktop as well as your agent | Yes |
| Tool is a fast, stateless, pure computation | No — keep inline |
| Prototyping or early development | No — keep inline |
| Tool is tightly coupled to one agent's logic | No — keep inline |

---

## Summary

```
MCP = JSON-RPC 2.0 + transport (stdio / HTTP) + 4 primitives (tools, resources, prompts, sampling)

stdio  → local process, zero network, spawned by host
SSE    → remote HTTP, legacy, being phased out
HTTP   → remote HTTP, current standard, production-ready

Server types:
  single-tool   → one focused capability
  multi-tool    → domain service (CRM, compliance, scheduling)
  resource+tool → data + actions together
  cross-language → Node/Go/Rust server, Python client

Integrations:
  LangGraph   → langchain-mcp-adapters
  Claude Desktop → claude_desktop_config.json
  Cursor      → .cursor/mcp.json
  Any host    → same server, zero changes
```
