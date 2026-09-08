"""Shared helpers: HTTP, HTML→text, money parsing, dates."""
from __future__ import annotations

import html as _html
import logging
import re
import time
import dataclasses
from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Any

import requests

LOG = logging.getLogger("radar")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en,nl;q=0.8"})


def get(url: str, *, params=None, headers=None, timeout=40, retries=3, sleep=1.5):
    """GET with polite retries. Returns requests.Response or None."""
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            LOG.warning("HTTP %s for %s", r.status_code, r.url)
            if r.status_code in (401, 403, 404):
                return r
            if r.status_code == 429:
                time.sleep(4 * (attempt + 1))
        except Exception as exc:                     # noqa: BLE001
            LOG.warning("request failed (%s/%s) %s: %s", attempt + 1, retries, url, exc)
        time.sleep(sleep * (attempt + 1))
    return None


# --------------------------------------------------------------------------- #
#  HTML helpers
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    t = _SCRIPT_RE.sub(" ", raw)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</(p|li|div|h\d)>", "\n", t, flags=re.I)
    t = _TAG_RE.sub(" ", t)
    t = _html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", _html.unescape(s or "")).strip()


def shorten(s: str, n: int = 320) -> str:
    s = clean(s)
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------- #
#  Money parsing  →  everything is normalised to EUR / year
# --------------------------------------------------------------------------- #
_CUR_SYMBOLS = {"€": "EUR", "£": "GBP", "$": "USD", "chf": "CHF", "eur": "EUR",
                "gbp": "GBP", "sek": "SEK", "dkk": "DKK", "nok": "NOK",
                "pln": "PLN", "czk": "CZK", "usd": "USD"}

_NUM = r"\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d{4,7}"

_MONEY_RE = re.compile(
    rf"(?P<pre>€|£|\$|EUR|CHF|GBP|SEK|DKK|NOK|PLN|CZK|USD)?\s?"
    rf"(?P<num>{_NUM})"
    rf"\s?(?P<post>€|£|EUR|CHF|GBP|SEK|DKK|NOK|PLN|CZK|USD|k|K)?",
    re.I,
)

_PER_MONTH = re.compile(r"per\s+month|/\s?month|monthly|pro\s?monat|per\s+maand|p/m|a month", re.I)
_PER_YEAR = re.compile(r"per\s+year|/\s?year|annual|per\s+annum|p\.a\.|yearly|per\s+jaar", re.I)
_TOTAL_HINT = re.compile(r"total|budget|maximum of|up to|grant of|worth|funding of|awarded", re.I)


def _to_float(num: str) -> float | None:
    s = num.strip().replace(" ", "")
    # 1.234,56 (EU)  |  1,234.56 (UK/US)  |  1.234  |  1,234
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") \
            else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "." if len(s.split(",")[-1]) == 2 else "")
    elif s.count(".") == 1 and len(s.split(".")[-1]) == 3:
        s = s.replace(".", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def extract_amounts(text: str, fx: dict[str, float], *, max_hits: int = 40):
    """Find plausible money amounts. Returns list of (eur_value, period, raw)."""
    if not text:
        return []
    out = []
    for m in list(_MONEY_RE.finditer(text))[:400]:
        pre, post = (m.group("pre") or "").lower(), (m.group("post") or "").lower()
        cur = _CUR_SYMBOLS.get(pre) or _CUR_SYMBOLS.get(post)
        val = _to_float(m.group("num"))
        if val is None:
            continue
        if post in ("k",) and val < 1000:
            val *= 1000
            cur = cur or "EUR"
        if not cur:
            continue
        if val < 500 or val > 50_000_000:
            continue
        window = text[max(0, m.start() - 90): m.end() + 90]
        if _PER_MONTH.search(window):
            period = "month"
        elif _PER_YEAR.search(window):
            period = "year"
        elif val >= 100_000 and _TOTAL_HINT.search(window):
            period = "total"
        elif 1500 <= val <= 9000:
            period = "month"          # typical European PhD/postdoc gross salary
        else:
            period = "unknown"
        out.append((val * fx.get(cur, 1.0), period, clean(m.group(0))))
        if len(out) >= max_hits:
            break
    return out


def best_annual_eur(text: str, fx: dict[str, float]) -> tuple[float, str]:
    """Best guess of yearly EUR value + human readable note."""
    hits = extract_amounts(text, fx)
    if not hits:
        return 0.0, ""
    scored = []
    for eur, period, raw in hits:
        if period == "month":
            scored.append((eur * 12, f"{raw} /month"))
        elif period == "year":
            scored.append((eur, f"{raw} /year"))
        elif period == "total":
            scored.append((eur / 4.0, f"{raw} (total)"))   # assume ~4y project
        else:
            scored.append((eur if eur > 15000 else eur * 12, raw))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0]


LRI, PDI = "\u2066", "\u2069"          # isolate numbers so RTL text stays tidy


def fmt_eur(v: float | None, *, isolate: bool = False) -> str:
    """€51,750 — optionally wrapped in bidi isolates for Persian sentences."""
    if not v:
        return "—"
    s = f"€{v:,.0f}"
    return f"{LRI}{s}{PDI}" if isolate else s


def fmt_range_eur(lo: float | None, hi: float | None, *, isolate: bool = False) -> str:
    if lo and hi and round(hi) > round(lo):
        s = f"€{lo:,.0f}–€{hi:,.0f}"
    elif lo or hi:
        s = f"€{(lo or hi):,.0f}"
    else:
        return "—"
    return f"{LRI}{s}{PDI}" if isolate else s


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_MONTHS.update({m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)})


def parse_date(s: str | None):
    """Robustly read the many date shapes our sources use.

    Handles: 2026-09-23, 2026-09-23T12:00:00+02:00, '5 Oct 2026 - 21:59 (UTC)',
    '23 September 2026', 23/09/2026, 23-09-2026, 'Sat, 22 Aug 26 14:10:53 +0200'.
    """
    if not s:
        return None
    s = clean(s)

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)             # ISO first
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,})\.?\s+(\d{4})\b", s)   # 5 Oct 2026
    if m:
        mon = _MONTHS.get(m.group(2).lower()) or _MONTHS.get(m.group(2)[:3].lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                return None

    m = re.search(r"\b([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})\b", s)  # Oct 5, 2026
    if m:
        mon = _MONTHS.get(m.group(1).lower()) or _MONTHS.get(m.group(1)[:3].lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                return None

    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", s)         # 23/09/2026
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2})\b", s)        # 22 Aug 26 (RSS)
    if m:
        mon = _MONTHS.get(m.group(2).lower())
        if mon:
            try:
                return date(2000 + int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                return None
    return None


# --------------------------------------------------------------------------- #
#  Data model
# --------------------------------------------------------------------------- #
@dataclass
class Opportunity:
    uid: str
    source: str
    kind: str                 # job | funding | call
    title: str
    url: str
    organisation: str = ""
    country: str = ""
    city: str = ""
    deadline: str = ""
    posted: str = ""
    field: str = ""
    summary: str = ""
    summary_fa: str = ""
    summary_en: str = ""
    title_fa: str = ""
    salary_text: str = ""
    salary_min_month: float = 0.0     # gross €/month, start of scale
    salary_max_month: float = 0.0     # gross €/month, top of scale
    fte: float = 0.0                  # 1.0 = full time
    amount_eur_year: float = 0.0      # yearly gross at the START of the scale (used for sorting)
    amount_max_eur_year: float = 0.0  # yearly gross at the TOP of the scale
    amount_note: str = ""
    score: float = 0.0
    matched: list[str] = dataclasses.field(default_factory=list)
    raw_text: str = ""
    first_seen: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw_text", None)
        d["matched"] = ", ".join(self.matched)
        return d
