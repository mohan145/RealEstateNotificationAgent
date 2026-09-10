import json
import os
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.llm import get_llm
from src.state import AgentState
from src.tools import TOOLS

SYSTEM_PROMPT = """You are an autonomous messaging agent for a residential property management company.

You will receive a prospect or resident record. Your job is to decide:
1. Whether to send a message
2. Which channel to use
3. What to say (personalized, compliant, on-brand)
4. When to send it
5. What the next action should be

Rules:
- Always include opt-out instructions in the message body.
- Never include raw PII (email addresses, phone numbers) in the message body.

EFFICIENCY — minimize round-trips by batching independent tool calls in a single turn:

Turn 1 (call all three in parallel):
  - validate_consent — confirm the channel is permitted
  - get_current_time — get current time in the prospect's timezone
  - check_fair_housing — pre-check an outline of the message you plan to send

Turn 2 (once you have the channel, time, and a draft body):
  - score_personalization — verify the draft meets the personalization threshold
  - If score >= threshold: call finalize_output in this same turn
  - If score < threshold: revise the body and call score_personalization again, then finalize_output

Never call tools one at a time when they can be called together.
Call finalize_output exactly once.
"""

_llm = None


class _GoogleQuotaError(RuntimeError):
    pass


def _get_llm():
    global _llm
    if _llm is None:
        _llm = get_llm(TOOLS)
    return _llm


def _is_google_quota_error(error: Exception) -> bool:
    if os.environ.get("LLM_PROVIDER", "anthropic").lower() != "google":
        return False
    status_code = getattr(error, "status_code", getattr(error, "code", None))
    details = str(error).lower()
    return status_code == 429 or "429" in details or "quota" in details or "resource exhausted" in details


def _invoke_llm(messages: list) -> object:
    try:
        return _get_llm().invoke(messages)
    except Exception as error:
        if not _is_google_quota_error(error):
            raise
        raise _GoogleQuotaError(
            "Google Gemini quota limit reached (HTTP 429). "
            "Please check your Google AI quota or try again later."
        ) from error


def llm_node(state: AgentState) -> dict:
    messages = list(state["messages"])
    try:
        if not messages:
            record_str = json.dumps(state["input_record"], indent=2)
            seed = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"Process this record:\n\n{record_str}"),
            ]
            return {"messages": seed + [_invoke_llm(seed)]}
        # On retry inject validation errors so the LLM knows what to fix
        errors = state.get("validation_errors", [])
        if errors:
            feedback = "Validation failed:\n" + "\n".join(f"- {e}" for e in errors)
            feedback += "\n\nRewrite the message body to fix these issues and call finalize_output again."
            messages = messages + [HumanMessage(content=feedback)]
        return {"messages": [_invoke_llm(messages)]}
    except _GoogleQuotaError as error:
        return {
            "messages": [AIMessage(content=str(error))],
            "llm_error": str(error),
            "validation_errors": [str(error)],
        }


def should_continue(state: AgentState) -> str:
    if state.get("llm_error"):
        return "end"
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    if any(getattr(m, "name", None) == "finalize_output" for m in state["messages"]):
        return "validate"
    return "validate"


def _extract_finalize_output(state: AgentState) -> dict | None:
    for msg in reversed(state["messages"]):
        if getattr(msg, "name", None) == "finalize_output":
            try:
                return json.loads(msg.content)
            except json.JSONDecodeError:
                return None
    return None


def _personalization_error(body: str, profile: dict, min_score: float) -> str | None:
    matched = []
    for key, val in profile.items():
        if isinstance(val, str) and val.lower() in body.lower():
            matched.append(key)
        elif isinstance(val, list):
            if any(isinstance(i, str) and i.lower() in body.lower() for i in val):
                matched.append(key)
    score = round(min(len(matched) / max(len(profile), 1), 1.0), 2)
    if score < min_score:
        return f"Personalization score {score} below threshold {min_score} (matched: {matched})"
    return None


def validate_node(state: AgentState) -> dict:
    output = _extract_finalize_output(state)
    if not output:
        return {"output": None, "validation_errors": ["finalize_output was never called"],
                "retry_count": state.get("retry_count", 0) + 1}

    body = output.get("next_message", {}).get("body", "")
    record = state["input_record"]
    constraints = record.get("assertions", {}).get("constraints", {})
    thresholds = record.get("thresholds", {})
    errors = []
    safety_count = 0

    if constraints.get("include_opt_out_instructions"):
        if "stop" not in body.lower() and "opt out" not in body.lower():
            errors.append("Missing opt-out instructions in body")
            safety_count += 1

    if constraints.get("no_pii_leak"):
        if re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", body):
            errors.append("PII leak: email address found in body")
            safety_count += 1
        if re.search(r"\b\d{10}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", body):
            errors.append("PII leak: phone number found in body")
            safety_count += 1

    if constraints.get("no_sensitive_discrimination"):
        for msg in state["messages"]:
            if getattr(msg, "name", None) == "check_fair_housing":
                try:
                    result = json.loads(msg.content)
                    violations = result.get("violations", [])
                    if violations:
                        errors.append(f"Fair housing violations: {violations}")
                        safety_count += len(violations)
                except json.JSONDecodeError:
                    pass

    max_violations = thresholds.get("safety_violations_max", 0)
    if safety_count > max_violations:
        errors.append(f"Safety violations {safety_count} exceeded max {max_violations}")

    min_score = thresholds.get("personalization_score_min",
                               float(os.environ.get("PERSONALIZATION_SCORE_MIN", "0.0")))
    profile = record.get("input", {}).get("profile", {})
    if profile and min_score > 0:
        err = _personalization_error(body, profile, min_score)
        if err:
            errors.append(err)

    return {"output": output, "validation_errors": errors,
            "retry_count": state.get("retry_count", 0) + 1}


def validate_should_retry(state: AgentState) -> str:
    retry_count = int(os.environ.get("RETRY_COUNT", "1"))
    if state.get("validation_errors") and state.get("retry_count", 0) <= retry_count:
        return "llm"
    return "end"