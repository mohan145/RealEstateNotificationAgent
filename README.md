# NotifyBot

A context-aware autonomous messaging agent for residential property management. Given a structured input record describing a prospect or resident, the agent decides whether to send a message, which channel to use, what to say, when to send it, and what follow-up action to take — all inferred from the data, no hardcoded rules.

---

## What it does

You give it a JSON record like this:

```json
{
  "task_id": "prospect_welcome_day0",
  "persona": "prospect",
  "consent": { "sms_opt_in": true, "email_opt_in": true },
  "channel_preferences": ["sms", "email"],
  "input": {
    "property_name": "Oak Ridge Apartments",
    "timezone": "America/Chicago",
    "profile": { "first_name": "Taylor", "city_interest": "Richardson, TX" }
  },
  "assertions": { "constraints": { "include_opt_out_instructions": true } },
  "thresholds": { "personalization_score_min": 0.85, "safety_violations_max": 0 }
}
```

And it produces:

```json
{
  "next_message": {
    "channel": "sms",
    "send_at": "2026-09-11T09:00:00-05:00",
    "body": "Hi Taylor, welcome to Oak Ridge Apartments! Tours are available this week...",
    "cta": { "type": "schedule_tour", "options": ["Thu", "Fri"] }
  },
  "next_action": { "type": "start_cadence", "name": "prospect_welcome_short_horizon" }
}
```

---

## Architecture

The agent is a **ReAct loop** built on LangGraph:

```
Input JSON
    |
    v
[ LLM Node ]  <-- retry with error feedback --+
    |                                          |
    | tool calls pending                       |
    v                                          |
[ Tool Node ]  --> results back to LLM         |
    |                                          |
    | finalize_output called                   |
    v                                          |
[ Validate Node ] -- errors found? ------------+
    |
    | clean (or retry limit hit)
    v
  END --> results/sample_results.json
```

The LLM reasons and calls tools in a loop until it commits by calling `finalize_output`. A deterministic validation layer then checks hard constraints. If validation fails the agent gets one retry with the specific errors injected into context.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full architecture, decisions, and tradeoffs. See [`docs/graph.png`](docs/graph.png) for the visual graph.

---

## Project structure

```
NotifyBot/
├── sample.json              # test cases with expected outputs
├── results/
│   └── sample_results.json  # agent outputs (written by runner, never touches sample.json)
├── src/
│   ├── state.py             # AgentState TypedDict
│   ├── tools.py             # 5 LangChain tools
│   ├── llm.py               # provider factory (Anthropic / OpenAI / Google)
│   ├── nodes.py             # llm_node, validate_node, routing functions
│   ├── graph.py             # LangGraph wiring
│   └── runner.py            # entrypoint, StepLogger callback, result writer
├── scripts/
│   └── draw_graph.py        # generates docs/graph.png offline (matplotlib)
├── docs/
│   ├── DESIGN.md            # architecture, decisions, tradeoffs
│   ├── graph.png            # visual agent graph
│   └── graph.mmd            # Mermaid source (VS Code / online viewers)
├── requirements.txt
└── .env                     # local config (not committed)
```

---

## Setup

**1. Clone and create a virtual environment**

```bash
git clone <repo>
cd NotifyBot
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure `.env`**

Copy the example and fill in your API key:

```
LLM_PROVIDER=anthropic          # anthropic | openai | google

ANTHROPIC_API_KEY=sk-...
ANTHROPIC_MODEL=claude-sonnet-4-6

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

GOOGLE_API_KEY=...
GOOGLE_MODEL=gemini-2.5-flash-lite

PERSONALIZATION_SCORE_MIN=0.0   # global fallback threshold
```

Only the key for your chosen provider needs to be filled in.

---

## Running the agent

**Run a single record (default)**

```bash
python -m src.runner
# or explicitly:
python -m src.runner sample.json prospect_welcome_day0
```

**Run all records in a file**

```bash
python -m src.runner sample.json all
```

**Run against a different input file**

```bash
python -m src.runner my_records.json all
```

Results are written to `results/<filename>_results.json`. The source file is never modified.

**Example output:**

```
=== prospect_welcome_day0 ===
  -> validate_consent({"channel": "sms", ...})
  <- {"permitted": true, "reason": "sms opt-in is granted"}
  -> get_current_time({"timezone": "America/Chicago"})
  <- 2026-09-11T09:00:00-05:00
  -> check_fair_housing({"body": "Hi Taylor..."})
  <- {"passed": true, "violations": []}
  -> score_personalization({"body": "Hi Taylor...", "profile": {...}})
  <- {"score": 1.0, "matched_fields": ["first_name", "city_interest"]}
  -> finalize_output({...})
  <- {"next_message": {...}, "next_action": {...}}

--- validation ---
  latency: 28860.0ms
  errors:  none

--- comparison ---
  [OK ] channel: expected='sms'  got='sms'
  [OK ] subject: expected=None  got=None
  [OK ] next_action.type: expected='start_cadence'  got='start_cadence'
```

---

## Tools

| Tool | What it does |
|---|---|
| `validate_consent` | Checks the prospect's opt-in for the chosen channel |
| `get_current_time` | Returns current local time in the prospect's timezone |
| `check_fair_housing` | Keyword scan for Fair Housing Act violations in the message body |
| `score_personalization` | Scores how many profile fields appear verbatim in the body (0–1) |
| `finalize_output` | Commits the final decision as structured JSON |

The system prompt instructs the LLM to batch independent tools in a single turn (`validate_consent + get_current_time + check_fair_housing` together), reducing a typical run from 6 LLM calls to 2–3.

---

## Validation

After `finalize_output` is called, `validate_node` checks all thresholds from the input record:

| Threshold | How it's checked |
|---|---|
| `personalization_score_min` | Verbatim profile field matching against the body |
| `safety_violations_max` | Counts PII leaks + missing opt-out + fair housing hits |
| `p95_latency_ms` | Wall-clock time measured in `runner.py` around `app.invoke()` |
| `reply_classification_f1_min` | Not implemented — requires a reply classifier model |

If validation fails, the agent gets one retry. The errors are injected as a `HumanMessage` so the LLM knows exactly what to fix.

---

## Generating the graph image

```bash
python scripts/draw_graph.py
```

Renders `docs/graph.png` fully offline using `matplotlib`. No network required (avoids corporate SSL interception of mermaid.ink).

---

## Input record format

Each record in the input JSON array follows this schema:

```
task_id             string   unique identifier
persona             string   prospect | resident
lifecycle_stage     string   new | open | stale | renewal_window | ...
consent             object   email_opt_in, sms_opt_in, voice_opt_in (bool)
channel_preferences array    ordered list of preferred channels
input               object   property_name, timezone, profile, move_date_target, ...
assertions          object   required_states, constraints (no_pii_leak, include_opt_out_instructions, ...)
thresholds          object   p95_latency_ms, personalization_score_min, safety_violations_max, ...
expected            object   ground truth next_message + next_action for comparison
```

---

## Known limitations

- **Latency:** Multi-tool LLM runs take 25–35s. The 2000ms `p95_latency_ms` threshold in the test data reflects a production SLA, not achievable on a free-tier API without streaming + dedicated infra.
- **`send_at` date:** `get_current_time` returns today's date. Expected values in `sample.json` are frozen in Dec 2025, so `send_at` will always diff.
- **Free tier quotas:** Each record costs ~5–6 LLM API calls. Anthropic and Google free tiers cap at 20 requests/day per model.
- **`reply_classification_f1_min`:** Not implemented — would require a separate classifier.