"""
Check the SDR qualification notes (MEDDPICC) and the path to SQL.

MEDDPICC fields: metrics, economic_buyer, decision_criteria, decision_process, paper_process,
identified_pain, champion, competition.

The policy:
  - Not every field is needed to book a discovery meeting.
  - The minimum to book is pain plus at least one other field.
  - A lead is a Sales Qualified Lead (SQL) only after the AE's discovery call was held.

Flags
  booked_below_minimum      a meeting was booked without pain plus one more field
  sql_without_discovery     marked SQL but no discovery call was held
  qualified_without_meeting a net-new lead is marked Qualified but no meeting was ever booked

Usage:
  python check_qualification.py [--data-dir ../gtm-synthetic-data/data]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import MIN_MEDDPICC_FIELDS, ROOT

FIELDS = ["metrics", "economic_buyer", "decision_criteria", "decision_process", "paper_process",
          "identified_pain", "champion", "competition"]


def check(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    q = pd.read_csv(data_dir / "lead_qualification.csv", keep_default_na=False, na_values=[""])
    leads = pd.read_csv(data_dir / "leads.csv", keep_default_na=False, na_values=[""])
    asg = pd.read_csv(data_dir / "lead_assignments.csv")
    for f in FIELDS:
        q[f] = q[f].astype(str).str.lower().eq("true")
    q["fields_filled"] = q[FIELDS].sum(axis=1)
    q["meets_minimum"] = q.identified_pain & (q.fields_filled >= MIN_MEDDPICC_FIELDS)
    q["missing_fields"] = q[FIELDS].apply(lambda r: ", ".join(f for f in FIELDS if not r[f]), axis=1)

    flags = []
    for r in q.itertuples():
        if not r.meets_minimum:
            flags.append({"lead_id": r.lead_id, "issue_type": "booked_below_minimum",
                          "detail": f"booked with {r.fields_filled} of 8 fields and pain {'known' if r.identified_pain else 'missing'}"})
        if pd.notna(r.sql_ts) and pd.isna(r.discovery_held_ts):
            flags.append({"lead_id": r.lead_id, "issue_type": "sql_without_discovery",
                          "detail": "marked SQL but no discovery call was held"})
    net_new = set(asg.lead_id)
    booked = set(q.lead_id)
    for r in leads[(leads.status == "Qualified") & leads.lead_id.isin(net_new)].itertuples():
        if r.lead_id not in booked:
            flags.append({"lead_id": r.lead_id, "issue_type": "qualified_without_meeting",
                          "detail": "status is Qualified but no meeting was booked"})
    return q, pd.DataFrame(flags)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT.parent / "gtm-synthetic-data" / "data"))
    ap.add_argument("--out-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    q, flags = check(Path(args.data_dir))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    q.to_csv(out / "qualification_check.csv", index=False)
    flags.sort_values(["issue_type", "lead_id"]).to_csv(out / "qualification_flags.csv", index=False)

    print(f"Meetings booked by SDRs: {len(q):,}")
    print(f"Average MEDDPICC fields filled: {q.fields_filled.mean():.1f} of 8")
    print("\nHow often each field was captured")
    print((100 * q[FIELDS].mean()).round(0).astype(int).astype(str).add("%").to_string())
    held = q.discovery_held_ts.notna().sum()
    print(f"\nDiscovery calls held: {held:,}   SQLs: {q.sql_ts.notna().sum():,}")
    print("\nFlags")
    print(flags.issue_type.value_counts().to_string())


if __name__ == "__main__":
    main()
