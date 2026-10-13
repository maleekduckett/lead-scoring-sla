"""Shared settings and helpers. The scoring rules live here so every script uses the same ones."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT.parent / "gtm-synthetic-data" / "data"
DEFAULT_KEY = ROOT.parent / "gtm-synthetic-data" / "answer_key"
UTC = timezone.utc

# ---- Scoring rules --------------------------------------------------------
# Points for the kind of action a lead took. Demo and Contact Sales requests are
# also an override: those leads are Hot no matter what else is true.
EVENT_POINTS = {
    "Demo Request": 100, "Contact Sales Request": 90, "Trial Signup": 45, "Partner Referral": 40,
    "Outbound Reply": 40, "Pricing Page Visit": 30, "Webinar Attended": 30, "Event Badge Scan": 25,
    "General Inquiry": 20, "Webinar Registered": 15, "Content Download": 15, "Email Click": 5,
}
OVERRIDE_HOT = {"Demo Request", "Contact Sales Request"}
HALF_LIFE_DAYS = 14        # an action loses half its points every 14 days
DEDUPE_SECONDS = 120       # the same action twice within 2 minutes counts once
HOT_AT, WARM_AT = 100, 55  # fit + intent
FIT_SIZE = {"1-50": 0, "51-200": 8, "201-1000": 12, "1001-5000": 15, "5000+": 15}
FIT_COUNTRIES = {"United States", "Canada", "United Kingdom", "Germany"}
SENIOR_WORDS = ("Chief", "VP", "Head", "Director")

# What a creating event normally looks like for each lead source.
SOURCE_EVENTS = {
    "Website Form": {"Demo Request", "Contact Sales Request", "General Inquiry"},
    "Webinar": {"Webinar Attended", "Webinar Registered"},
    "Event": {"Event Badge Scan"},
    "Content Download": {"Content Download"},
    "Partner Referral": {"Partner Referral"},
    "Outbound List": {"Outbound Reply", "Email Click"},
    "Trial Signup": {"Trial Signup"},
}

# ---- SLA rules ------------------------------------------------------------
SLA_MINUTES = {"Hot": 5, "Warm": 60, "Cold": 480}   # business minutes in the SDR's own shift
MAX_SDR_STEPS = 3                                   # original SDR plus 2 reroutes, then the manager
LATE_REROUTE_MINUTES = 5                            # reroute should follow a miss within this long
FOLLOW_UP_GAP_MINUTES = 30                          # a second Hot call must be at least this long after the first
MIN_MEDDPICC_FIELDS = 2                             # to book: pain plus at least one other field


def parse_ts(series):
    """Timestamps in the data are UTC text. Return timezone-aware values."""
    import pandas as pd
    return pd.to_datetime(series, utc=True)


# ---- Business hours -------------------------------------------------------
class Shift:
    """One SDR's working hours, in their own timezone, Monday to Friday."""

    def __init__(self, tz: str, start_hour: float, end_hour: float):
        self.tz, self.start, self.end = ZoneInfo(tz), start_hour, end_hour

    def on_shift(self, ts: datetime) -> bool:
        local = ts.astimezone(self.tz)
        hour = local.hour + local.minute / 60 + local.second / 3600
        return local.weekday() < 5 and self.start <= hour < self.end

    def next_start(self, ts: datetime) -> datetime:
        """ts itself if the SDR is working, otherwise the start of their next shift."""
        if self.on_shift(ts):
            return ts
        local = ts.astimezone(self.tz)
        for i in range(10):
            day = local.date() + timedelta(days=i)
            start = datetime(day.year, day.month, day.day, int(self.start), 0, tzinfo=self.tz)
            if start.weekday() < 5 and start.astimezone(UTC) > ts:
                return start.astimezone(UTC)
        raise RuntimeError("no shift found")

    def shift_end(self, ts: datetime) -> datetime:
        local = ts.astimezone(self.tz)
        return datetime(local.year, local.month, local.day, int(self.end), 0, tzinfo=self.tz).astimezone(UTC)

    def add_business_minutes(self, ts: datetime, minutes: float) -> datetime:
        """Move forward by minutes that fall inside shifts. Nights and weekends do not count."""
        t, remaining = self.next_start(ts), minutes
        while True:
            available = (self.shift_end(t) - t).total_seconds() / 60
            if remaining <= available:
                return t + timedelta(minutes=remaining)
            remaining -= available
            t = self.next_start(self.shift_end(t) + timedelta(seconds=1))
