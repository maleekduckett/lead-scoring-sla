"""
Audit response times (SLAs) for every lead an SDR was given.

Rules checked:
  1. Each assignment has a response clock: Hot 5 minutes, Warm 1 hour, Cold 8 hours.
     The clock only runs while that SDR is on shift (their own timezone, Monday to Friday).
  2. A Hot lead that misses its SLA must be rerouted to a nearby SDR soon after.
     That repeats until 3 SDRs have missed. Then it goes to the manager.
  3. Every missed SLA is logged.
  4. After a call that is not answered, the SDR sends a follow-up email.
     For a Hot lead, the SDR also calls again later.

Writes results/sla_audit.csv (one row per assignment), results/sla_misses.csv (the log of missed SLAs),
and results/process_flags.csv (broken rules).

Usage:
  python audit_sla.py [--data-dir ../gtm-synthetic-data/data]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import (FOLLOW_UP_GAP_MINUTES, LATE_REROUTE_MINUTES, MAX_SDR_STEPS, ROOT, SLA_MINUTES, Shift, parse_ts)
from score_leads import score_leads

CALL_NOT_ANSWERED = {"No Answer", "Left Voicemail"}


def audit(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tiers = score_leads(data_dir).set_index("lead_id").tier
    asg = pd.read_csv(data_dir / "lead_assignments.csv")
    tch = pd.read_csv(data_dir / "lead_touches.csv")
    shifts = pd.read_csv(data_dir / "sdr_shifts.csv").set_index("user_id")
    asg["assigned_ts"], tch["touch_ts"] = parse_ts(asg.assigned_ts), parse_ts(tch.touch_ts)
    shift_of = {u: Shift(r.timezone, r.shift_start_hour, r.shift_end_hour) for u, r in shifts.iterrows()}
    touches = {k: g.sort_values("touch_ts") for k, g in tch.groupby("lead_id")}

    rows, flags = [], []

    def flag(lead_id, issue, detail):
        flags.append({"lead_id": lead_id, "issue_type": issue, "detail": detail})

    for lead_id, g in asg.sort_values(["lead_id", "assigned_ts"]).groupby("lead_id"):
        g = g.reset_index(drop=True)
        tier = tiers[lead_id]
        lead_touches = touches.get(lead_id, tch.iloc[0:0])
        sdr_steps = g[g.assignment_reason != "Manager escalation"]
        has_manager = (g.assignment_reason == "Manager escalation").any()
        for i, a in g.iterrows():
            if a.assignment_reason == "Manager escalation":
                continue
            window_end = g.assigned_ts.iloc[i + 1] if i + 1 < len(g) else pd.Timestamp.max.tz_localize("UTC")
            mine = lead_touches[(lead_touches.user_id == a.assigned_to) & (lead_touches.touch_ts >= a.assigned_ts)
                                & (lead_touches.touch_ts < window_end)]
            shift = shift_of[a.assigned_to]
            start = shift.next_start(a.assigned_ts.to_pydatetime())
            due = shift.add_business_minutes(start, SLA_MINUTES[tier])
            first = mine.iloc[0] if len(mine) else None
            response = first.touch_ts if first is not None else pd.NaT
            met = first is not None and response <= due
            late_min = None if met else (None if first is None else round((response - due).total_seconds() / 60, 1))
            step = int(a.step)
            nxt = g.iloc[i + 1] if i + 1 < len(g) else None
            outcome = ""
            if not met:
                if tier != "Hot":
                    outcome = "logged only"
                elif step < MAX_SDR_STEPS:
                    if nxt is None:
                        outcome = "no reroute"
                        flag(lead_id, "missing_reroute", f"{a.assigned_to} missed the SLA and nobody was assigned next")
                    else:
                        lag = (nxt.assigned_ts - due).total_seconds() / 60
                        outcome = f"rerouted to {nxt.assigned_to}"
                        if lag > LATE_REROUTE_MINUTES:
                            flag(lead_id, "late_reroute", f"rerouted {lag:.0f} minutes after the missed SLA")
                else:
                    if not has_manager:
                        outcome = "no escalation"
                        flag(lead_id, "missing_escalation", "third SLA missed and the manager was never assigned")
                    else:
                        outcome = "escalated to manager"
            # follow-up rules apply to the first call that was not answered
            calls = mine[mine.touch_type == "Call"]
            if len(calls) and calls.iloc[0].outcome in CALL_NOT_ANSWERED:
                c1 = calls.iloc[0]
                emails = mine[(mine.touch_type == "Email") & (mine.touch_ts >= c1.touch_ts)]
                if emails.empty:
                    flag(lead_id, "missing_followup_email", f"{a.assigned_to} did not email after an unanswered call")
                if tier == "Hot":
                    later = calls[calls.touch_ts >= c1.touch_ts + pd.Timedelta(minutes=FOLLOW_UP_GAP_MINUTES)]
                    if later.empty:
                        flag(lead_id, "missing_second_call", f"{a.assigned_to} did not call again later for a Hot lead")
            rows.append({"lead_id": lead_id, "tier": tier, "step": step, "assignee": a.assigned_to,
                         "assigned_ts": a.assigned_ts.strftime("%Y-%m-%d %H:%M:%S"),
                         "sla_start_ts": start.strftime("%Y-%m-%d %H:%M:%S"), "sla_minutes": SLA_MINUTES[tier],
                         "due_ts": due.strftime("%Y-%m-%d %H:%M:%S"),
                         "response_ts": "" if first is None else response.strftime("%Y-%m-%d %H:%M:%S"),
                         "met": met, "minutes_late": late_min, "what_happened": outcome})
    sla = pd.DataFrame(rows)
    misses = sla[~sla.met].copy()
    return sla, misses, pd.DataFrame(flags)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT.parent / "gtm-synthetic-data" / "data"))
    ap.add_argument("--out-dir", default=str(ROOT / "results"))
    args = ap.parse_args()

    sla, misses, flags = audit(Path(args.data_dir))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sla.to_csv(out / "sla_audit.csv", index=False)
    misses.to_csv(out / "sla_misses.csv", index=False)
    flags.sort_values(["issue_type", "lead_id"]).to_csv(out / "process_flags.csv", index=False)

    print(f"Assignments audited: {len(sla):,} on {sla.lead_id.nunique():,} leads\n")
    by = sla.groupby("tier").met.agg(["size", "mean"]).rename(columns={"size": "assignments", "mean": "met_pct"})
    by["met_pct"] = (100 * by.met_pct).round(1)
    print("SLA met, by tier\n" + by.to_string())
    print(f"\nMissed SLAs logged: {len(misses):,}")
    print(misses.what_happened.value_counts().to_string())
    print("\nProcess problems found")
    print(flags.issue_type.value_counts().to_string())


if __name__ == "__main__":
    main()
