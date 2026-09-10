
# NotifyBot — Design Document

## Problem

Build a context-aware messaging agent for residential property management. Given a structured input record (prospect or resident profile, consent flags, constraints, thresholds), the agent must decide:

- Whether to send a message
- Which channel to use (SMS, email, voice)
- What to say — personalized, compliant, on-brand
- When to send it
- What the follow-up action should be

The agent must not hardcode rules. All decisions must be inferred from the input data.

---

## High-Level Architecture

```
Input Record (JSON)
       |
       v
  [ LLM Node ]  <-----------------------------+
       |                                      |
       | tool calls?                          | retry with error feedback
       v                                      |
  [ Tool Node ]  -----> back to LLM           |
       |                                      |
       | finalize_output called               |
       v                                      |
  [ Validate Node ] -- errors found? ---------+
       |
       | no errors (or retry limit hit)
       v
     END
      |
      v
  results/sample_results.json
```

The agent is a **ReAct loop** (Reasoning + Acting) built on LangGraph. The LLM reasons, decides which tools to call, observes the results, and repeats until it calls `finalize_output`. After that, a deterministic validation layer checks hard constraints before exit.

---

## Component Breakdown

### `src/state.py` — Shared State

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # full conversation history
    input_record: dict                        # the raw input JSON
    output: dict | None                       # final structured output
    validation_errors: list[str]             # constraint violations
    retry_count: int                          # tracks validate->llm retries
```

`messages` uses LangGraph's `add_messages` reducer — each node appends to the list rather than replacing it, so the full conversation history is always available.

---

### `src/tools.py` — Agent Tools

Five tools the LLM can call:

| Tool | Purpose |
|---|---|
| `validate_consent` | Checks channel opt-in from the consent block |
| `get_current_time` | Returns current local time in the prospect's timezone |
| `check_fair_housing` | Keyword scan for Fair Housing Act violations |
| `score_personalization` | Scores how many profile fields appear verbatim in the body |
| `finalize_output` | Packages the final decision into structured JSON |

`finalize_output` is a tool (not free-form text) so the output is always structured and machine-readable. The LLM is forced to commit to exact field values rather than describing what it would do.

---

### `src/llm.py` — Provider Factory

Reads `LLM_PROVIDER` from `.env` and returns a tool-bound model. Supported: `anthropic`, `openai`, `google`. Provider packages are imported lazily so the project works without all three installed.

---

### `src/nodes.py` — Graph Nodes

**`llm_node`**
Invokes the LLM with the full message history. On the first call it seeds the conversation with the system prompt and the input record. On retry (after validation failure) it appends a `HumanMessage` containing the specific errors so the LLM knows exactly what to fix.

**`should_continue`**
Conditional edge after `llm_node`. Routes to `tools` if the last message contains tool calls, to `validate` if `finalize_output` has been called.

**`validate_node`**
Deterministic constraint checker. Runs after `finalize_output`:
- Opt-out instructions present in body
- No PII (email/phone regex)
- Fair housing violations (from `check_fair_housing` tool results in history)
- Safety violations count vs `safety_violations_max` threshold
- Personalization score vs `personalization_score_min` threshold

Increments `retry_count` on every run.

**`validate_should_retry`**
If errors exist and `retry_count <= 1`, routes back to `llm_node` with error feedback injected. Otherwise exits to `END`. Max 1 retry to cap API usage.

---

### `src/graph.py` — Graph Wiring

```
__start__ -> llm
llm -> tools          (conditional: tool calls pending)
llm -> validate       (conditional: finalize_output called)
tools -> llm          (back-edge, the ReAct loop)
validate -> llm       (conditional: errors + retry available)
validate -> END       (conditional: clean or retry limit hit)
```

---

### `src/runner.py` — Entrypoint

- Builds the graph and invokes it with `app.invoke()`
- Attaches a `StepLogger` callback handler that prints tool calls and results live
- Measures wall-clock latency and checks it against `p95_latency_ms`
- Writes results to `results/<input_stem>_results.json` without modifying the source file
- Prints a side-by-side diff of `expected` vs `agent_output` for each record

---

## Key Decisions & Tradeoffs

### 1. LangGraph over a raw loop

**Decision:** Use LangGraph's `StateGraph` instead of a hand-written `while` loop.

**Reason:** LangGraph gives us checkpointing, streaming, and a visual graph for free. The graph topology is also explicit — you can see exactly which edges exist and what triggers each transition.

**Tradeoff:** Adds a dependency and learning curve. A raw loop would be 30 lines of code. LangGraph is the right call once the graph has conditional branches and retry logic.

---

### 2. `finalize_output` as a tool

**Decision:** The agent commits its decision by calling a `finalize_output` tool rather than emitting free-form text.

**Reason:** Structured output. The tool forces the LLM to provide exact values for `channel`, `send_at`, `body`, `cta`, and `next_action`. The validate node can then check these fields deterministically.

**Tradeoff:** The LLM needs one extra round-trip to call the tool vs just responding with JSON. Acceptable given the reliability gain.

---

### 3. Validation as a separate graph node

**Decision:** Constraint checking lives in `validate_node`, not inside `llm_node`.

**Reason:** The LLM cannot reliably enforce its own constraints — it may miss a PII leak or forget opt-out text even when instructed. A deterministic code layer after the fact is the only reliable gate.

**Tradeoff:** If validation fails and the retry also fails, the run exits with errors rather than silently passing bad output. This is the correct behaviour — surfacing failures is better than hiding them.

---

### 4. Retry loop with max 1 retry

**Decision:** On validation failure, inject error feedback into the conversation and re-run the LLM once.

**Reason:** Gives the agent a chance to fix deterministic errors (PII leak, missing opt-out). Without this, a single bad word choice would fail the entire run with no recovery.

**Tradeoff:** Doubles the API call count on failure. Cap at 1 retry to stay within free-tier quotas and keep latency bounded.

---

### 5. System prompt batching instruction

**Decision:** The system prompt explicitly tells the LLM to batch `validate_consent`, `get_current_time`, and `check_fair_housing` in a single turn.

**Reason:** LLMs default to calling tools one at a time. Each round-trip costs ~5-8s of latency and one API call. Batching reduces a 6-call run to ~2-3 calls.

**Tradeoff:** The model has to draft the message body before `check_fair_housing` runs (to have something to scan). This is acceptable — the validate node re-checks fair housing violations from the tool result in message history regardless.

---

### 6. Provider factory with lazy imports

**Decision:** `llm.py` imports `langchain_anthropic`, `langchain_openai`, `langchain_google_genai` lazily inside each builder function.

**Reason:** The project should work if only one provider package is installed. A top-level import would crash on startup if any package is missing.

**Tradeoff:** Slightly less obvious import structure. Worth it for install flexibility.

---

### 7. Results written to separate file

**Decision:** `runner.py` writes output to `results/<stem>_results.json` instead of modifying the input file.

**Reason:** The input files (`sample.json`) are the ground truth. Overwriting them with agent output conflates the test data with test results.

**Tradeoff:** Two files to manage instead of one. Clear separation of concerns outweighs the minor inconvenience.

---

## Threshold Enforcement

| Threshold | Enforced | Where |
|---|---|---|
| `personalization_score_min` | Yes | `validate_node` — verbatim profile field matching |
| `safety_violations_max` | Yes | `validate_node` — counts PII + opt-out + fair housing hits |
| `p95_latency_ms` | Yes | `runner.py` — wall-clock time around `app.invoke()` |
| `reply_classification_f1_min` | No | Would need a reply classifier model — known gap |

---

## Known Limitations

- **Latency:** A multi-tool LLM run takes 25-35s end-to-end. The 2000ms threshold in the test data reflects a production SLA that would require streaming + faster infra, not a research prototype.
- **`send_at` date:** `get_current_time` returns today's date. Expected values in `sample.json` are hardcoded to Dec 2025. This will always diff — the agent behaviour is correct, the test data is frozen in time.
- **`reply_classification_f1_min`:** Not implemented. Scoring whether a message would elicit the right reply requires a separate classifier.
- **Free tier quotas:** Each record costs ~5-6 LLM API calls. Both Anthropic and Google free tiers cap at 20 requests/day per model.