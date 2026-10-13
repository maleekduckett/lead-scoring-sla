"""
Score every lead, put it in a tier, say why, and check that its lead source is believable.

For each lead, as of the moment it was created:
  fit      points for company size, country and job title
  intent   points for what the lead did, fading over time (half-life 14 days)
  tier     Hot if the lead asked for a demo or to talk to sales, or fit + intent >= 100
           Warm if fit + intent >= 55
           Cold otherwise
  reason   one sentence a rep can read: which action drove the tier

Source check: the event that created the lead should fit its lead_source.
A "Webinar" lead whose creating event is a Demo Request gets flagged.

Usage:
  python score_leads.py [--data-dir ../gtm-synthetic-data/data]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import (DEDUPE_SECONDS, EVENT_POINTS, FIT_COUNTRIES, FIT_SIZE, HALF_LIFE_DAYS, HOT_AT, OVERRIDE_HOT,
                    ROOT, SENIOR_WORDS, SOURCE_EVENTS, WARM_AT, parse_ts)


def fit_points(size_band, title, country) -> tuple[int, str]:
    """Points for how well the company and person fit, plus a short note on why."""
    pts, notes = FIT_SIZE.get(size_band, 0), []
    if pts:
        notes.append(f"company size {size_band}")
    if country in FIT_COUNTRIES:
        pts += 5
        notes.append(country)
    t = title if isinstance(title, str) else ""
    if any(w in t for w in SENIOR_WORDS):
        pts += 10
        notes.append("senior title")
    elif "Manager" in t:
        pts += 5
        notes.append("manager title")
    return pts, ", ".join(notes) if notes else "no fit signals"


def drop_duplicate_events(ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove the same action repeated within 2 minutes (a double submit). Returns kept and dropped."""
    ev = ev.sort_values(["lead_id", "event_type", "event_ts"]).copy()
    gap = ev.groupby(["lead_id", "event_type"]).event_ts.diff().dt.total_seconds()
    dup = gap.le(DEDUPE_SECONDS)
    return ev[~dup], ev[dup]


def score_one(lead, events: pd.DataFrame, created) -> dict:
    """Score one lead using only events up to the moment it was created."""
    seen = events[events.event_ts <= created]
    age_days = (created - seen.event_ts).dt.total_seconds() / 86400
    points = seen.event_type.map(EVENT_POINTS) * 0.5 ** (age_days / HALF_LIFE_DAYS)
    intent = min(100.0, float(points.sum()))
    fit, fit_note = fit_points(lead.company_size, lead.title, lead.country)
    recent_override = seen[seen.event_type.isin(OVERRIDE_HOT) & (age_days <= HALF_LIFE_DAYS)]
    total = fit + intent
    if len(recent_override):
        tier = "Hot"
        top = recent_override.sort_values("event_ts").iloc[-1]
        reason = f"Hot: {top.event_type} on {top.event_ts:%Y-%m-%d} (always Hot). Fit {fit}, intent {intent:.0f}."
    else:
        tier = "Hot" if total >= HOT_AT else "Warm" if total >= WARM_AT else "Cold"
        best = (points.groupby(seen.event_type).sum().sort_values(ascending=False).head(2))
        drivers = ", ".join(f"{t} ({p:.0f})" for t, p in best.items()) or "no activity"
        reason = f"{tier}: score {total:.0f} = fit {fit} ({fit_note}) + intent {intent:.0f} from {drivers}."
    return {"fit_score": fit, "intent_score": round(intent, 1), "total_score": round(total, 1),
            "tier": tier, "override": bool(len(recent_override)), "reason": reason}


def score_leads(data_dir: Path) -> pd.DataFrame:
    leads = pd.read_csv(data_dir / "leads.csv", keep_default_na=False, na_values=[""])
    ev = pd.read_csv(data_dir / "lead_events.csv", keep_default_na=False, na_values=[""])
    ev["event_ts"] = parse_ts(ev.event_ts)
    ev, dropped = drop_duplicate_events(ev)
    dup_leads = set(dropped.lead_id)

    creating = ev[ev.created_lead.astype(str).str.lower().eq("true")].set_index("lead_id")
    by_lead = {k: g for k, g in ev.groupby("lead_id")}
    rows = []
    for lead in leads.itertuples():
        c = creating.loc[lead.lead_id]
        out = score_one(lead, by_lead[lead.lead_id], c.event_ts)
        ok = c.event_type in SOURCE_EVENTS.get(lead.lead_source, set())
        out.update({"lead_id": lead.lead_id, "lead_source": lead.lead_source, "creating_event": c.event_type,
                    "created_ts": c.event_ts.strftime("%Y-%m-%d %H:%M:%S"), "source_valid": ok,
                    "source_note": "" if ok else f"lead_source is {lead.lead_source} but the lead was created by {c.event_type}",
                    "duplicate_event": lead.lead_id in dup_leads})
        rows.append(out)
    cols = ["lead_id", "tier", "total_score", "fit_score", "intent_score", "override", "reason", "lead_source",
            "creating_event", "created_ts", "source_valid", "source_note", "duplicate_event"]
    return pd.DataFrame(rows)[cols]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT.parent / "gtm-synthetic-data" / "data"))
    ap.add_argument("--out", default=str(ROOT / "results" / "lead_scores.csv"))
    args = ap.parse_args()

    df = score_leads(Path(args.data_dir))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Scored {len(df):,} leads\n")
    tiers = df.tier.value_counts().rename("leads").to_frame()
    tiers["pct"] = (100 * tiers.leads / len(df)).round(1)
    print(tiers.to_string())
    print(f"\nHot because of a demo or sales request: {int(df.override.sum()):,}")
    print(f"Lead source does not fit the creating event: {int((~df.source_valid).sum()):,}")
    print(f"Leads with a double-submitted event: {int(df.duplicate_event.sum()):,}")
    print(f"\nExample reason: {df.reason.iloc[0]}")


if __name__ == "__main__":
    main()
