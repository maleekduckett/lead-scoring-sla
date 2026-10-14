"""
Draw the charts used in the README. Reads the files in results/, writes PNGs to docs/.

Colors follow the tier, so Hot is always orange, Warm blue and Cold green. Every bar is labeled
with its value, so color is never the only way to tell them apart.

Usage:
  python charts.py          (needs matplotlib: pip install matplotlib)
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from common import ROOT  # noqa: E402

RES, DOCS = ROOT / "results", ROOT / "docs"
SURFACE, INK, MUTED = "#fcfcfb", "#1a1a1a", "#6b6b6b"
TIER_COLOR = {"Hot": "#d9650a", "Warm": "#2f6fd6", "Cold": "#1f9d7a"}
TIERS = ["Hot", "Warm", "Cold"]


def frame(title: str, subtitle: str, size=(8, 3.8)):
    fig, ax = plt.subplots(figsize=size, dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#cfcfcf")
    ax.tick_params(colors=MUTED, length=0, labelsize=10)
    ax.yaxis.label.set_color(MUTED)
    fig.text(0.04, 0.95, title, fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.875, subtitle, fontsize=10, color=MUTED, va="top")
    return fig, ax


def label_bars(ax, bars, texts, pad=0.01):
    xmax = ax.get_xlim()[1]
    for b, t in zip(bars, texts):
        ax.text(b.get_width() + xmax * pad, b.get_y() + b.get_height() / 2, t, va="center", fontsize=10, color=INK)


def tier_mix(scores: pd.DataFrame):
    counts = scores.tier.value_counts().reindex(TIERS)
    fig, ax = frame("How the 4,100 leads split into tiers", "Hot is mostly demo and sales requests")
    bars = ax.barh(TIERS[::-1], counts[TIERS[::-1]], color=[TIER_COLOR[t] for t in TIERS[::-1]], height=0.5)
    ax.set_xlim(0, counts.max() * 1.25)
    ax.set_xticks([])
    label_bars(ax, bars, [f"{counts[t]:,}  ({100 * counts[t] / len(scores):.0f}%)" for t in TIERS[::-1]])
    fig.subplots_adjust(left=0.1, right=0.97, top=0.78, bottom=0.08)
    fig.savefig(DOCS / "tier_mix.png", facecolor=SURFACE)
    plt.close(fig)


def booked_by_tier(scores: pd.DataFrame, sla: pd.DataFrame, qual: pd.DataFrame):
    worked = sla[["lead_id"]].drop_duplicates().merge(scores[["lead_id", "tier"]], on="lead_id")
    worked["booked"] = worked.lead_id.isin(qual.lead_id)
    g = worked.groupby("tier").booked.agg(["size", "sum"]).reindex(TIERS)
    pct = 100 * g["sum"] / g["size"]
    fig, ax = frame("Share of SDR leads that booked a meeting", "Tiers separate Cold well. Hot and Warm look alike here.")
    bars = ax.barh(TIERS[::-1], pct[TIERS[::-1]], color=[TIER_COLOR[t] for t in TIERS[::-1]], height=0.5)
    ax.set_xlim(0, pct.max() * 1.35)
    ax.set_xticks([])
    label_bars(ax, bars, [f"{pct[t]:.1f}%  ({int(g['sum'][t])} of {int(g['size'][t])})" for t in TIERS[::-1]])
    fig.subplots_adjust(left=0.1, right=0.97, top=0.78, bottom=0.08)
    fig.savefig(DOCS / "booked_by_tier.png", facecolor=SURFACE)
    plt.close(fig)


def sla_met(sla: pd.DataFrame):
    sla = sla.copy()
    sla["met"] = sla.met.astype(bool)
    rows = [("Hot, 1st SDR", "Hot", sla[(sla.tier == "Hot") & (sla.step == 1)]),
            ("Hot, 2nd SDR", "Hot", sla[(sla.tier == "Hot") & (sla.step == 2)]),
            ("Hot, 3rd SDR", "Hot", sla[(sla.tier == "Hot") & (sla.step == 3)]),
            ("Warm", "Warm", sla[sla.tier == "Warm"]),
            ("Cold", "Cold", sla[sla.tier == "Cold"])]
    labels = [r[0] for r in rows][::-1]
    pct = [100 * r[2].met.mean() for r in rows][::-1]
    n = [len(r[2]) for r in rows][::-1]
    fig, ax = frame("Share of response clocks met", "Hot is the hardest to hit, and reroutes do worse than the first SDR")
    bars = ax.barh(labels, pct, color=[TIER_COLOR[r[1]] for r in rows][::-1], height=0.55)
    ax.set_xlim(0, 118)
    ax.set_xticks([])
    label_bars(ax, bars, [f"{p:.0f}%  (n={k})" for p, k in zip(pct, n)], pad=0.008)
    fig.subplots_adjust(left=0.17, right=0.97, top=0.78, bottom=0.08)
    fig.savefig(DOCS / "sla_met.png", facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    scores = pd.read_csv(RES / "lead_scores.csv")
    sla = pd.read_csv(RES / "sla_audit.csv")
    qual = pd.read_csv(RES / "qualification_check.csv")
    tier_mix(scores)
    booked_by_tier(scores, sla, qual)
    sla_met(sla)
    print("Wrote tier_mix.png, booked_by_tier.png, sla_met.png to docs/")


if __name__ == "__main__":
    main()
