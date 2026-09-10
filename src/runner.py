import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "results"

from src.graph import build_graph

load_dotenv(REPO_ROOT / ".env")


class StepLogger(BaseCallbackHandler):
    """Log tool calls and results as the agent runs."""

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        name = serialized.get("name", "?")
        print(f"  -> {name}({input_str[:120]})")

    def on_tool_end(self, output, **kwargs) -> None:
        print(f"  <- {str(output)[:120]}")

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        for gen in response.generations:
            for g in gen:
                msg = getattr(g, "message", None)
                calls = getattr(msg, "tool_calls", []) if msg else []
                if not calls:
                    text = (g.text or "").strip()[:120]
                    if text:
                        print(f"  [thinking] {text}")


def _compare(expected: dict | None, actual: dict | None) -> None:
    if not expected or not actual:
        print("  [compare] missing expected or agent_output")
        return
    exp_msg = expected.get("next_message", {}) or {}
    act_msg = actual.get("next_message", {}) or {}
    for f in ["channel", "subject", "send_at"]:
        e, a = exp_msg.get(f), act_msg.get(f)
        print(f"  [{'OK ' if e == a else 'DIFF'}] {f}: expected={e!r}  got={a!r}")
    print(f"  [expected body] {(exp_msg.get('body') or '')[:120]}")
    print(f"  [agent   body] {(act_msg.get('body') or '')[:120]}")
    exp_a = expected.get("next_action", {}) or {}
    act_a = actual.get("next_action", {}) or {}
    print(f"  [{'OK ' if exp_a.get('type') == act_a.get('type') else 'DIFF'}] next_action.type: expected={exp_a.get('type')!r}  got={act_a.get('type')!r}")


def run(record: dict) -> dict:
    """Process a single input record through the agent graph.

    Args:
        record: A parsed JSON record with persona, consent, input, assertions,
                and thresholds fields.

    Returns:
        Dict with "output", "validation_errors", and "latency_ms".
    """
    app = build_graph()
    t0 = time.monotonic()
    final = app.invoke(
        {"messages": [], "input_record": record, "output": None,
         "validation_errors": [], "retry_count": 0, "llm_error": None},
        config={"callbacks": [StepLogger()]},
    )
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    errors = list(final.get("validation_errors", []))
    if final.get("llm_error") and final["llm_error"] not in errors:
        errors.append(final["llm_error"])
    max_latency = record.get("thresholds", {}).get("p95_latency_ms", float("inf"))
    if latency_ms > max_latency:
        errors.append(f"Latency {latency_ms}ms exceeded p95 threshold {max_latency}ms")
    return {
        "output": final.get("output"),
        "validation_errors": errors,
        "latency_ms": latency_ms,
    }


def run_file(input_path: Path, filter_id: str | None = None) -> list[dict]:
    """Run all (or one) records from an input file and return result rows.

    Args:
        input_path: Path to a JSON input file.
        filter_id: Optional task_id to run only one record.

    Returns:
        List of result dicts, one per record run.
    """
    with open(input_path) as f:
        records = json.load(f)
    if filter_id:
        records = [r for r in records if r["task_id"] == filter_id]

    rows = []
    for rec in records:
        print(f"\n=== {rec['task_id']} ===")
        result = run(rec)
        print("\n--- validation ---")
        print(f"  latency: {result['latency_ms']}ms")
        print(f"  errors:  {result['validation_errors'] or 'none'}")
        print("\n--- comparison ---")
        _compare(rec.get("expected"), result["output"])
        rows.append({
            "task_id": rec["task_id"],
            "agent_output": result["output"],
            "validation_errors": result["validation_errors"],
            "latency_ms": result["latency_ms"],
        })
    return rows


if __name__ == "__main__":
    # Usage:
    #   python -m src.runner                              # sample.json, first record only
    #   python -m src.runner sample.json                  # sample.json, first record only
    #   python -m src.runner sample.json all              # sample.json, all records
    #   python -m src.runner sample.json <task_id>        # sample.json, one record
    #   python -m src.runner sample_extended.json all     # extended, all records
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "sample.json"
    filter_arg = sys.argv[2] if len(sys.argv) > 2 else "prospect_welcome_day0"
    filter_id = None if filter_arg == "all" else filter_arg

    RESULTS_DIR.mkdir(exist_ok=True)
    output_path = RESULTS_DIR / (input_path.stem + "_results_3.json")

    rows = run_file(input_path, filter_id=filter_id)

    with open(output_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\n[results saved to {output_path}]")