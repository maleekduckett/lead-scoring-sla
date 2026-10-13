"""
Grade the scorer and the auditors against the answer key.

Only this file reads answer_key/. It checks:
  1. tier and source check for every lead (lead_lifecycle_truth.csv)
  2. every planted process problem: how many were found, and how many flags were wrong
     (lifecycle_issues.csv)

Run score_leads.py, audit_sla.py and check_qualification.py first.

Note on what this proves: the answer key was written by the data generator, which follows the same written
rules (see common.py). A perfect score shows the code applies the rules correctly. It does not show the
rules are the right rules for a real business.

Usage:
  python grade.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import ROOT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default=str(ROOT / "results"))
    ap.add_argument("--key-dir", default=str(ROOT.parent / "gtm-synthetic-data" / "answer_key"))
    args = ap.parse_args()
    res, key = Path(args.results_dir), Path(args.key_dir)

    scores = pd.read_csv(res / "lead_scores.csv")
    truth = pd.read_csv(key / "lead_lifecycle_truth.csv")
    m = scores.merge(truth, on="lead_id", suffixes=("", "_true"))
    tier_ok = (m.tier == m.expected_tier)
    print("Tiers")
    print(f"  Right tier for {int(tier_ok.sum()):,} of {len(m):,} leads ({100 * tier_ok.mean():.1f}%)")
    print(pd.crosstab(m.expected_tier, m.tier, rownames=["should be"], colnames=["scored as"]).to_string())
    print(f"  Source check agrees with the key for {int((m.source_valid == m.source_valid_true).sum()):,} of {len(m):,} leads")

    issues = pd.read_csv(key / "lifecycle_issues.csv")
    found = pd.concat([pd.read_csv(res / "process_flags.csv"), pd.read_csv(res / "qualification_flags.csv"),
                       scores[~scores.source_valid].assign(issue_type="source_mismatch")[["lead_id", "issue_type"]],
                       scores[scores.duplicate_event].assign(issue_type="duplicate_event")[["lead_id", "issue_type"]]])
    print("\nPlanted problems")
    rows = []
    for t in sorted(set(issues.issue_type) | set(found.issue_type)):
        planted = set(issues[issues.issue_type == t].lead_id)
        flagged = set(found[found.issue_type == t].lead_id)
        rows.append({"issue": t, "planted": len(planted), "found": len(planted & flagged),
                     "false_flags": len(flagged - planted), "missed": len(planted - flagged)})
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    tot_p, tot_f, tot_x = out.planted.sum(), out.found.sum(), out.false_flags.sum()
    print(f"\n  Found {tot_f} of {tot_p} planted problems. {tot_x} flags had no planted problem behind them.")
    extra = []
    for t in out[out.false_flags > 0].issue:
        planted = set(issues[issues.issue_type == t].lead_id)
        extra += [f"{t}: {l}" for l in sorted(set(found[found.issue_type == t].lead_id) - planted)]
    if extra:
        print("  Unplanted flags: " + "; ".join(extra))


if __name__ == "__main__":
    main()
