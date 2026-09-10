import re
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool


@tool
def get_current_time(timezone: str) -> str:
    """Return current local time for a given IANA timezone."""
    return datetime.now(ZoneInfo(timezone)).isoformat()


@tool
def validate_consent(channel: str, consent: dict) -> dict:
    """Check whether the prospect has opted in to the given channel."""
    mapping = {
        "email": consent.get("email_opt_in", False),
        "sms": consent.get("sms_opt_in", False),
        "voice": consent.get("voice_opt_in", False),
    }
    permitted = mapping.get(channel, False)
    return {
        "permitted": permitted,
        "reason": f"{channel} opt-in is {'granted' if permitted else 'not granted'}",
    }


@tool
def check_fair_housing(body: str) -> dict:
    """Scan message body for fair housing violations."""
    forbidden = [
        "no children", "adults only", "no families", "christian",
        "english only", "no section 8", "ideal for singles", "perfect for couples",
    ]
    found = [f for f in forbidden if f.lower() in body.lower()]
    return {"passed": len(found) == 0, "violations": found}


@tool
def score_personalization(body: str, profile: dict) -> dict:
    """Score how many profile fields appear verbatim in the message body (0-1)."""
    matched = []
    for key, val in profile.items():
        if isinstance(val, str) and val.lower() in body.lower():
            matched.append(key)
        elif isinstance(val, list):
            if any(isinstance(i, str) and i.lower() in body.lower() for i in val):
                matched.append(key)
    score = round(min(len(matched) / max(len(profile), 1), 1.0), 2)
    return {"score": score, "matched_fields": matched}


@tool
def finalize_output(
    channel: str,
    send_at: str,
    body: str,
    cta: dict,
    next_action: dict,
    subject: str | None = None,
) -> dict:
    """Package the final message decision. Call once when all checks pass."""
    return {
        "next_message": {
            "channel": channel,
            "send_at": send_at,
            "subject": subject,
            "body": body,
            "cta": cta,
        },
        "next_action": next_action,
    }


TOOLS = [get_current_time, validate_consent, check_fair_housing, score_personalization, finalize_output]