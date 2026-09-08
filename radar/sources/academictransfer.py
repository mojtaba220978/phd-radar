"""AcademicTransfer (Netherlands) — public JSON API used by their own website.

The site is a Nuxt app that talks to https://api.academictransfer.com with a
public bearer token embedded in the page. We scrape that token at runtime so the
scraper keeps working when they rotate it.
"""
from __future__ import annotations

import logging
import re

from ..util import Opportunity, get, html_to_text, clean, shorten

LOG = logging.getLogger("radar.academictransfer")

API = "https://api.academictransfer.com/vacancies/"
SITE = "https://www.academictransfer.com/en/jobs/"
FALLBACK_TOKEN = "jFf7DQQzOhbO28NrmqLPY8T72QRj5wmJ7PBu1PWAaC"

CONTRACT_TYPES = {1: "Permanent", 2: "Temporary", 3: "Tenure track"}
_TOKEN_CACHE: dict[str, str] = {}


def _probe(token: str) -> bool:
    """Does this token actually open the API?"""
    r = get(API, params={"is_active": "true", "limit": 1},
            headers={"Authorization": f"Bearer {token}"}, timeout=25, retries=1)
    return r is not None and r.status_code == 200


def _token() -> str:
    """Find a working bearer token.

    The site ships a public token inside its Nuxt payload and rotates it, so we
    scrape *candidates* and verify each one against the API instead of trusting a
    fragile regex. The last-known-good token is kept as a final fallback.
    """
    if "t" in _TOKEN_CACHE:
        return _TOKEN_CACHE["t"]

    candidates: list[str] = []
    r = get(SITE, timeout=30, retries=2)
    if r is not None and r.status_code == 200:
        for c in re.findall(r'"([A-Za-z0-9_\-]{30,60})"', r.text):
            if "-" in c or "_" in c:
                continue
            if not (re.search(r"[A-Z]", c) and re.search(r"[a-z]", c) and re.search(r"\d", c)):
                continue
            if any(b in c.lower() for b in ("nuxt", "http", "organisation", "vacanc", "compon")):
                continue
            if c not in candidates:
                candidates.append(c)

    for cand in candidates[:6]:
        if _probe(cand):
            LOG.info("AcademicTransfer token found on page (%s…)", cand[:8])
            _TOKEN_CACHE["t"] = cand
            return cand

    if _probe(FALLBACK_TOKEN):
        LOG.info("AcademicTransfer: using the built-in fallback token")
        _TOKEN_CACHE["t"] = FALLBACK_TOKEN
        return FALLBACK_TOKEN

    LOG.error("AcademicTransfer: no working API token found — source will be skipped")
    _TOKEN_CACHE["t"] = ""
    return ""


def _fetch(params: dict, token: str):
    return get(API, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=40)


def fetch(cfg: dict, money_cfg: dict) -> list[Opportunity]:
    scfg = cfg["sources"]["academictransfer"]
    if not scfg.get("enabled", True):
        return []
    token = _token()
    if not token:
        return []
    factor = float(money_cfg.get("nl_annual_factor", 13.96))
    out: dict[str, Opportunity] = {}

    for query in scfg.get("queries", []):
        offset, limit = 0, 50
        cap = int(scfg.get("max_per_query", 100))
        while offset < cap:
            params = {"is_active": "true", "limit": limit, "offset": offset,
                      "search": query, "boost_spotlights": "false"}
            r = _fetch(params, token)
            if r is None or r.status_code != 200:
                if r is not None and r.status_code == 401:
                    _TOKEN_CACHE.pop("t", None)
                    token = _token()
                    r = _fetch(params, token)
                if r is None or r.status_code != 200:
                    LOG.warning("AcademicTransfer query %r failed", query)
                    break
            try:
                data = r.json()
            except Exception:                      # noqa: BLE001
                break
            results = data.get("results", [])
            for v in results:
                op = _to_opportunity(v, factor)
                if op:
                    out[op.uid] = op
            if not data.get("next") or not results:
                break
            offset += limit
    LOG.info("AcademicTransfer: %s vacancies", len(out))
    return list(out.values())


def _to_opportunity(v: dict, factor: float) -> Opportunity | None:
    trs = v.get("translations") or []
    tr = next((t for t in trs if t.get("language_code") == "en"), trs[0] if trs else None)
    if not tr:
        return None
    desc = html_to_text(tr.get("description", ""))
    extra = " ".join(html_to_text(tr.get(k, "")) for k in
                     ("requirements", "contract_terms", "contract_duration", "additional_info", "extra_info"))
    mn = float(v.get("min_salary") or 0)
    mx = float(v.get("max_salary") or 0)
    hrs = float(v.get("max_weekly_hours") or v.get("min_weekly_hours") or 0)
    fte = min(hrs / 38.0, 1.0) if hrs else 1.0

    # AcademicTransfer publishes the employer's whole pay-scale band, which for a
    # PhD advert often reaches far above what a PhD actually earns. We therefore
    # rank on the START of the scale (what you would really be paid at the
    # beginning) and show the full range for transparency.
    annual_min = mn * factor * fte
    annual_max = mx * factor * fte
    if mn and mx:
        salary_text = f"€{mn:,.0f}–€{mx:,.0f} gross/month"
    elif mn or mx:
        salary_text = f"€{(mn or mx):,.0f} gross/month"
    else:
        salary_text = ""

    return Opportunity(
        uid=f"at:{v.get('external_id') or v.get('id')}",
        source="AcademicTransfer",
        kind="job",
        title=clean(tr.get("title")),
        url=v.get("absolute_url") or v.get("short_url") or "",
        organisation=clean(tr.get("organisation_name")),
        country="Netherlands" if (v.get("country_code") == "NL") else (v.get("country_code") or ""),
        city=clean(v.get("city")),
        deadline=(v.get("end_date") or "")[:10],
        posted=(v.get("created_datetime") or "")[:10],
        field=clean(tr.get("department_name")),
        summary=shorten(tr.get("excerpt") or desc, 340),
        salary_text=" · ".join(filter(None, [
            salary_text,
            CONTRACT_TYPES.get(v.get("contract_type"), ""),
            f"{hrs:g} h/week" if hrs else "",
        ])),
        salary_min_month=mn,
        salary_max_month=mx,
        fte=fte,
        amount_eur_year=float(annual_min or annual_max),
        amount_max_eur_year=float(annual_max),
        amount_note=("شامل ۸٪ حق تعطیلات و ۸٫۳٪ پاداش پایان سال"
                     + (f" · {hrs:g} ساعت در هفته" if hrs and fte < 1 else "")) if annual_min else "",
        raw_text=" ".join([clean(tr.get("title")), desc, extra]),
    )
