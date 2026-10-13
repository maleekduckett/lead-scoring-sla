"""Small checks on the rules. Run: python tests/test_rules.py"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import Shift  # noqa: E402
from score_leads import drop_duplicate_events, fit_points, score_one  # noqa: E402

UTC = timezone.utc
et = Shift("America/New_York", 8, 17)


def test_clock_runs_in_shift():
    # Tuesday 2026-10-13 10:00 ET = 14:00 UTC (EDT). 5 minutes later is 10:05 ET.
    start = datetime(2026, 10, 13, 14, 0, tzinfo=UTC)
    assert et.add_business_minutes(start, 5) == datetime(2026, 10, 13, 14, 5, tzinfo=UTC)


def test_clock_skips_night_and_weekend():
    # Friday 2026-10-16 16:55 ET = 20:55 UTC. 10 minutes: 5 on Friday, 5 on Monday after 8:00 ET (12:00 UTC).
    start = datetime(2026, 10, 16, 20, 55, tzinfo=UTC)
    assert et.add_business_minutes(start, 10) == datetime(2026, 10, 19, 12, 5, tzinfo=UTC)


def test_clock_starts_when_shift_starts():
    # Saturday 2026-10-17 12:00 UTC. The clock starts Monday 8:00 ET (12:00 UTC).
    sat = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    assert et.next_start(sat) == datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def test_clock_handles_daylight_saving():
    # After clocks fall back on 2026-11-01, 8:00 ET is 13:00 UTC instead of 12:00 UTC.
    mon = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)
    assert et.next_start(mon) == datetime(2026, 11, 2, 13, 0, tzinfo=UTC)


def test_fit_points():
    assert fit_points("5000+", "VP of Sales", "United States")[0] == 15 + 5 + 10
    assert fit_points("1-50", "Analyst", "Brazil")[0] == 0


def lead(size="1-50", title="Analyst", country="Brazil"):
    return type("L", (), {"company_size": size, "title": title, "country": country})()


def events(rows):
    return pd.DataFrame({"event_type": [r[0] for r in rows], "event_ts": pd.to_datetime([r[1] for r in rows], utc=True)})


def test_demo_request_is_always_hot():
    created = pd.Timestamp("2026-10-01 12:00", tz="UTC")
    out = score_one(lead(), events([("Demo Request", "2026-10-01 12:00")]), created)
    assert out["tier"] == "Hot" and out["override"]


def test_email_click_is_cold_and_old_activity_fades():
    created = pd.Timestamp("2026-10-01 12:00", tz="UTC")
    assert score_one(lead(), events([("Email Click", "2026-10-01 12:00")]), created)["tier"] == "Cold"
    fresh = score_one(lead(), events([("Pricing Page Visit", "2026-10-01 11:00")]), created)["intent_score"]
    old = score_one(lead(), events([("Pricing Page Visit", "2026-08-01 12:00")]), created)["intent_score"]
    assert old < fresh / 8


def test_double_submit_counts_once():
    ev = pd.DataFrame({"lead_id": ["L1", "L1"], "event_type": ["Demo Request"] * 2,
                       "event_ts": pd.to_datetime(["2026-10-01 12:00:00", "2026-10-01 12:00:30"], utc=True)})
    kept, dropped = drop_duplicate_events(ev)
    assert len(kept) == 1 and len(dropped) == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"All {len(tests)} tests passed.")
