"""Build the agent graph and save a detailed PNG to docs/graph.png.

Renders fully offline using matplotlib — no network required.

Outputs:
    docs/graph.png  — detailed PNG diagram
    docs/graph.mmd  — Mermaid source (for VS Code / online viewers)
    docs/graph.txt  — ASCII fallback
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

from src.graph import build_graph  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"

BG        = "#12121F"
NODE_LLM  = "#1565C0"
NODE_TOOL = "#E65100"
NODE_VAL  = "#6A1B9A"
NODE_SE   = "#2E7D32"
EDGE_DEF  = "#78909C"
EDGE_COND = "#FFD54F"
EDGE_BACK = "#FF7043"
WHITE     = "#FFFFFF"
GREY      = "#B0BEC5"


# ── helpers ───────────────────────────────────────────────────────────────────

def _node_box(ax, x, y, label, color, fontsize=9, width=0.28, height=0.10):
    box = mpatches.FancyBboxPatch(
        (x - width / 2, y - height / 2), width, height,
        boxstyle="round,pad=0.015",
        facecolor=color, edgecolor="white", linewidth=1.4,
        zorder=3, transform=ax.transData, clip_on=False,
    )
    ax.add_patch(box)
    ax.text(x, y, label, ha="center", va="center",
            fontsize=fontsize, color=WHITE, fontweight="bold",
            zorder=4, wrap=False,
            path_effects=[pe.withStroke(linewidth=2, foreground=color)])


def _diamond(ax, x, y, label, color, size=0.06):
    d = mpatches.FancyBboxPatch(
        (x - size, y - size / 2), size * 2, size,
        boxstyle="round,pad=0.01",
        facecolor=color, edgecolor="white", linewidth=1.4,
        zorder=3, transform=ax.transData, clip_on=False,
    )
    ax.add_patch(d)
    ax.text(x, y, label, ha="center", va="center",
            fontsize=8, color=WHITE, fontweight="bold", zorder=4)


def _arrow(ax, x0, y0, x1, y1, color, label="", rad=0.0, lw=1.6, ls="-"):
    ax.annotate(
        "", xy=(x1, y1), xytext=(x0, y0),
        arrowprops=dict(
            arrowstyle="-|>", color=color, lw=lw,
            linestyle=ls,
            connectionstyle=f"arc3,rad={rad}",
            mutation_scale=14,
        ),
        zorder=2,
    )
    if label:
        mx = (x0 + x1) / 2
        my = (y0 + y1) / 2
        offset_x = 0.07 if rad >= 0 else -0.07
        ax.text(mx + offset_x, my, label,
                fontsize=7.5, color=color, ha="center", va="center",
                style="italic", zorder=5,
                bbox=dict(facecolor=BG, edgecolor="none", alpha=0.7, pad=1))


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)

    graph = build_graph()
    raw = graph.get_graph()
    (DOCS / "graph.mmd").write_text(raw.draw_mermaid(), encoding="utf-8")
    (DOCS / "graph.txt").write_text(raw.draw_ascii(), encoding="utf-8")

    # ── figure setup ─────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(11, 13))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    fig.suptitle("NotifyBot — Agent Graph", fontsize=15, fontweight="bold",
                 color=WHITE, y=0.97)
    ax.text(0.5, 0.965,
            "ReAct loop: LLM reasons -> tools execute -> LLM observes -> repeat until finalize_output",
            ha="center", fontsize=8.5, color=GREY, transform=ax.transAxes)

    # ── node positions ───────────────────────────────────────────────────────
    #
    #       __start__
    #           |
    #          llm  ←─────────────────────────────╮
    #         /   \                               │  retry (errors, max 1)
    #      tools  validate ── errors? ────────────╯
    #         \       |
    #          ╰─►llm  no errors → END

    POS = {
        "__start__": (0.50, 0.92),
        "llm":       (0.50, 0.74),
        "tools":     (0.20, 0.52),
        "validate":  (0.78, 0.52),
        "__end__":   (0.78, 0.28),
    }

    # ── edges ────────────────────────────────────────────────────────────────

    # __start__ → llm
    _arrow(ax, *POS["__start__"], *POS["llm"], EDGE_DEF)

    # llm → tools  (conditional — tool calls pending)
    _arrow(ax, *POS["llm"], *POS["tools"], EDGE_COND,
           label="tool calls\npending", rad=0.15, ls="--")

    # llm → validate  (conditional — finalize_output called)
    _arrow(ax, *POS["llm"], *POS["validate"], EDGE_COND,
           label="finalize_output\ncalled", rad=-0.15, ls="--")

    # tools → llm  (ReAct back-edge)
    _arrow(ax, *POS["tools"], *POS["llm"], EDGE_BACK,
           label="tool results\nobserved", rad=0.45, lw=2.0)

    # validate → END  (no errors)
    _arrow(ax, *POS["validate"], *POS["__end__"], EDGE_DEF,
           label="no errors", rad=0.0)

    # validate → llm  (retry on errors, curved right side)
    _arrow(ax, *POS["validate"], *POS["llm"], "#EF5350",
           label="errors found\n(max 1 retry)", rad=-0.55, lw=2.0, ls="--")

    # ── draw nodes ───────────────────────────────────────────────────────────

    _diamond(ax, *POS["__start__"], "START", NODE_SE)
    _diamond(ax, *POS["__end__"],   "END",   "#B71C1C")

    _node_box(ax, *POS["llm"],
              "LLM Node\nReason · plan · call tools\n(Anthropic / OpenAI / Gemini)",
              NODE_LLM, width=0.32, height=0.13)

    _node_box(ax, *POS["tools"],
              "Tool Node\n-----------------\n"
              "validate_consent\nget_current_time\ncheck_fair_housing\n"
              "score_personalization\nfinalize_output",
              NODE_TOOL, width=0.30, height=0.22, fontsize=8)

    _node_box(ax, *POS["validate"],
              "Validate Node\n-----------------\n"
              "- opt-out instructions\n- no PII in body\n- fair housing violations\n"
              "- safety_violations_max\n- personalization score\n- latency threshold",
              NODE_VAL, width=0.30, height=0.24, fontsize=8)

    # ── annotations ──────────────────────────────────────────────────────────
    ax.annotate(
        "ReAct loop\n(repeats until\nfinalize_output)",
        xy=(0.16, 0.62), xytext=(0.02, 0.70),
        fontsize=7.5, color=EDGE_BACK,
        arrowprops=dict(arrowstyle="->", color=EDGE_BACK, lw=1),
        bbox=dict(facecolor=BG, edgecolor=EDGE_BACK, boxstyle="round,pad=0.3",
                  linewidth=1, alpha=0.85),
    )

    ax.annotate(
        "Retry loop\nInjects error feedback\ninto LLM context",
        xy=(0.80, 0.63), xytext=(0.88, 0.76),
        fontsize=7.5, color="#EF5350",
        arrowprops=dict(arrowstyle="->", color="#EF5350", lw=1),
        bbox=dict(facecolor=BG, edgecolor="#EF5350", boxstyle="round,pad=0.3",
                  linewidth=1, alpha=0.85),
    )

    # ── legend ───────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(color=NODE_LLM,   label="LLM node — reasoning & planning"),
        mpatches.Patch(color=NODE_TOOL,  label="Tool node — parallel execution"),
        mpatches.Patch(color=NODE_VAL,   label="Validate node — constraint checks"),
        mpatches.Patch(color=EDGE_BACK,  label="ReAct loop (tools -> llm)"),
        mpatches.Patch(color=EDGE_COND,  label="Conditional branch"),
        mpatches.Patch(color="#EF5350",  label="Validation retry (max 1)"),
    ]
    ax.legend(
        handles=legend_items,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.01),
        ncol=2, fontsize=8,
        framealpha=0.25, labelcolor=WHITE,
        facecolor="#2E2E3E", edgecolor="#555",
    )

    # ── save ─────────────────────────────────────────────────────────────────
    png_path = DOCS / "graph.png"
    plt.savefig(png_path, dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"PNG saved to  {png_path}")
    print(f"MMD saved to  {DOCS / 'graph.mmd'}")
    print(f"TXT saved to  {DOCS / 'graph.txt'}")


if __name__ == "__main__":
    main()