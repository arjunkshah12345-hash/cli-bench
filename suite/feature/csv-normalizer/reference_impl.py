"""Independent reference normalizer used ONLY by the verifier.

Deliberately implemented differently from what the spec suggests an agent
would write (manual parsing, no pandas), so agreement between the agent's
output and this reference is meaningful.
"""

import re
from datetime import datetime

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
PLANS = {"basic", "pro", "enterprise"}


def norm_name(raw: str) -> str:
    s = raw.strip()
    if not s:
        return "unknown"
    return " ".join(w[:1].upper() + w[1:].lower() for w in s.split() if w) or "unknown"


def norm_email(raw: str) -> str:
    s = raw.strip().lower()
    if not s or " " in s or s.count("@") != 1:
        return ""
    local, domain = s.split("@")
    if "." not in domain or not local:
        return ""
    return s


def norm_date(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime(y, mo, d)
            return f"{y:04d}-{mo:02d}-{d:02d}"
        except ValueError:
            return ""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime(y, mo, d)
            return f"{y:04d}-{mo:02d}-{d:02d}"
        except ValueError:
            return ""
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$", s)
    if m:
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            d, y = int(m.group(2)), int(m.group(3))
            try:
                datetime(y, mon, d)
                return f"{y:04d}-{mon:02d}-{d:02d}"
            except ValueError:
                return ""
    return ""


def norm_plan(raw: str) -> str:
    s = raw.strip().lower()
    return s if s in PLANS else "unknown"


def norm_mrr(raw: str) -> str:
    s = raw.strip().lower()
    if s in ("", "free"):
        return "0.00"
    s = s.replace("$", "").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return "0.00"
    if v < 0:
        v = 0.0
    return f"{v:.2f}"


def normalize(rows: list[list[str]]) -> list[list[str]]:
    out = []
    for r in rows:
        if len(r) != 6:
            continue
        rid = r[0]
        out.append(
            [
                rid,
                norm_name(r[1]),
                norm_email(r[2]),
                norm_date(r[3]),
                norm_plan(r[4]),
                norm_mrr(r[5]),
            ]
        )
    out.sort(key=lambda row: (row[4], -float(row[5]), row[2], int(row[0]) if row[0].isdigit() else 0))
    return out
