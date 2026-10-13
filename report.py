"""
Print the three summary tables in sql/report.sql. The SQL runs in an in-memory SQLite database
loaded from the CSVs the other scripts wrote.

Usage:
  python report.py
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from common import ROOT

RES = ROOT / "results"


def main() -> None:
    con = sqlite3.connect(":memory:")
    pd.read_csv(RES / "lead_scores.csv").to_sql("scores", con, index=False)
    sla = pd.read_csv(RES / "sla_audit.csv")
    sla["met"] = sla.met.astype(int)
    sla.to_sql("sla", con, index=False)
    pd.read_csv(RES / "qualification_check.csv").to_sql("qual", con, index=False)

    text = (ROOT / "sql" / "report.sql").read_text()
    parts = re.split(r"^-- name: ", text, flags=re.M)[1:]
    for part in parts:
        title, sql = part.split("\n", 1)
        print(f"\n{title}")
        print(pd.read_sql_query(sql, con).to_string(index=False))


if __name__ == "__main__":
    main()
