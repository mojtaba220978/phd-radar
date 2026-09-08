"""EURAXESS — job offers and funding/hosting offers (HTML listing scraper)."""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from ..util import Opportunity, get, html_to_text, clean, shorten, best_annual_eur

LOG = logging.getLogger("radar.euraxess")

BASE = "https://euraxess.ec.europa.eu"
JOBS_SEARCH = f"{BASE}/jobs/search"
FUNDING_SEARCH = f"{BASE}/funding/search"

_ITEM_SPLIT = re.compile(r'<div id="job-teaser-content">|<article class="ecl-content-item">')
_TITLE_RE = re.compile(r'ecl-content-block__title"><a\s+href="([^"]+)"[^>]*>\s*(?:<span>)?([^<]+)', re.S)
_LABEL_RE = re.compile(r'ecl-label ecl-label--(?:low|highlight)"\s*>([^<]+)<')
_ORG_RE = re.compile(r'primary-meta-item"><a href="/partnering[^"]*"[^>]*>([^<]+)<')
_POSTED_RE = re.compile(r"Posted on:\s*([^<]+)<")
_DESC_RE = re.compile(r'ecl-content-block__description"><p>(.*?)</p>', re.S)
_META_BLOCK_RE = re.compile(r'id-([A-Za-z-]+)\s+ecl-u-d-flex.*?ecl-text-standard[^>]*>(.*?)</div></div>', re.S)


def _parse_listing(html: str) -> list[dict]:
    items: list[dict] = []
    chunks = html.split('<li>\n  \n<div id="job-teaser-content">')
    if len(chunks) < 2:
        chunks = _ITEM_SPLIT.split(html)
    for ch in chunks[1:]:
        m = _TITLE_RE.search(ch)
        if not m:
            continue
        href, title = m.group(1), clean(m.group(2))
        labels = [clean(x) for x in _LABEL_RE.findall(ch[:m.start()] or ch)]
        meta = {}
        for key, val in _META_BLOCK_RE.findall(ch):
            meta[key.replace("-", " ").strip()] = clean(html_to_text(val))
        org = _ORG_RE.search(ch)
        posted = _POSTED_RE.search(ch)
        desc = _DESC_RE.search(ch)
        kind_labels = [l for l in labels if l.upper() in ("JOB", "FUNDING", "HOSTING")]
        country_labels = [l for l in labels if l.upper() not in
                          ("JOB", "FUNDING", "HOSTING", "STATUS:OPEN", "STATUS:CLOSED")]
        items.append({
            "url": href if href.startswith("http") else BASE + href,
            "title": title,
            "kind": (kind_labels[0].lower() if kind_labels else "job"),
            "country": country_labels[0] if country_labels else "",
            "organisation": clean(org.group(1)) if org else "",
            "posted": clean(posted.group(1)) if posted else "",
            "summary": shorten(html_to_text(desc.group(1)) if desc else "", 340),
            "meta": meta,
        })
    return items


def _crawl(url: str, pages: int) -> list[dict]:
    """Polite sequential crawl with adaptive back-off.

    EURAXESS throttles bursts (HTTP 429), so we walk the pages one by one and
    slow down whenever we are told to. A daily run has all the time it needs.
    """
    found: list[dict] = []
    seen: set[str] = set()
    delay = float(os.getenv("EURAXESS_DELAY", "0.8"))
    misses = 0

    for p in range(pages):
        params = {"sort[name]": "created", "sort[direction]": "DESC"}
        if p:
            params["page"] = p
        r = get(url, params=params, timeout=45, retries=3, sleep=5)
        if r is None or r.status_code != 200:
            misses += 1
            delay = min(delay * 1.8, 8.0)
            if misses >= 6:
                LOG.warning("EURAXESS throttling hard — stopping at page %s", p)
                break
            time.sleep(delay)
            continue
        batch = _parse_listing(r.text)
        if not batch:
            break
        fresh = 0
        for it in batch:
            if it["url"] not in seen:
                seen.add(it["url"])
                found.append(it)
                fresh += 1
        if fresh == 0:                       # same page served again → end of list
            break
        misses = 0
        delay = max(delay * 0.85, 0.5)
        time.sleep(delay)
    return found


def _detail(url: str) -> str:
    r = get(url, timeout=40, retries=2)
    if r is None or r.status_code != 200:
        return ""
    body = r.text
    i = body.find("Job Information")
    j = body.find("Where to apply")
    chunk = body[i:j] if 0 <= i < j else body
    return html_to_text(chunk)


def _uid(url: str) -> str:
    m = re.search(r"/(\d+)$", url)
    return f"eux:{m.group(1)}" if m else "eux:" + re.sub(r"\W+", "-", url.split("/")[-1])[:60]


# Marie Skłodowska-Curie doctoral networks pay a standardised EU rate; the advert
# itself usually stays silent about it, which used to show up as "amount unknown".
MSCA_MONTHLY_GROSS = 3_400.0
_MSCA = re.compile(r"\b(msca|marie\s+sk[l\u0142]odowska|marie\s+curie|doctoral network|"
                   r"innovative training network|\bitn\b|horizon europe)\b", re.I)


def _mk(it: dict, fx: dict) -> Opportunity:
    meta = it.get("meta", {})
    text = " ".join([it["title"], it.get("summary", ""), " ".join(meta.values())])
    amount, note = best_annual_eur(text, fx)
    if not amount and _MSCA.search(text):
        amount = MSCA_MONTHLY_GROSS * 12
        note = "نرخ استاندارد MSCA (تخمینی) — رقم دقیق به ضریب کشور بستگی دارد"
    return Opportunity(
        uid=_uid(it["url"]),
        source="EURAXESS",
        kind=it.get("kind", "job"),
        title=it["title"],
        url=it["url"],
        organisation=it.get("organisation", ""),
        country=it.get("country", "") or _country_from_meta(meta),
        city="",
        deadline=meta.get("Deadline", "") or meta.get("Application Deadline", ""),
        posted=it.get("posted", ""),
        field=meta.get("Research Field", ""),
        summary=it.get("summary", ""),
        salary_text=meta.get("Funding Programme", ""),
        amount_eur_year=amount,
        amount_note=note,
        raw_text=text,
    )


def _country_from_meta(meta: dict) -> str:
    loc = meta.get("Work Locations", "")
    m = re.search(r"Number of offers:\s*\d+,\s*([^,]+)", loc)
    return clean(m.group(1)) if m else ""


def fetch_jobs(cfg: dict, money_cfg: dict, keyword_test) -> list[Opportunity]:
    scfg = cfg["sources"]["euraxess_jobs"]
    if not scfg.get("enabled", True):
        return []
    fx = money_cfg.get("fx_to_eur", {"EUR": 1.0})
    items = _crawl(JOBS_SEARCH, int(scfg.get("pages", 20)))
    LOG.info("EURAXESS jobs: %s listings crawled", len(items))
    ops = [_mk(it, fx) for it in items]

    if scfg.get("fetch_details", True):
        shortlist = [o for o in ops if keyword_test(o)]
        LOG.info("EURAXESS jobs: fetching details for %s shortlisted", len(shortlist))
        with ThreadPoolExecutor(max_workers=6) as ex:
            for op, det in zip(shortlist, ex.map(lambda o: _detail(o.url), shortlist)):
                if not det:
                    continue
                op.raw_text += " " + det
                op.summary = op.summary or shorten(det, 340)
                amount, note = best_annual_eur(det, fx)
                if amount > op.amount_eur_year:
                    op.amount_eur_year, op.amount_note = amount, note
                d = re.search(r"Application Deadline\s+([0-9]{1,2} \w+ \d{4})", det)
                if d:
                    op.deadline = clean(d.group(1))
                c = re.search(r"Country\s+([A-Za-z .]+?)\s+(Type of Contract|Job Status|Reference)", det)
                if c:
                    op.country = clean(c.group(1))
    return ops


def fetch_funding(cfg: dict, money_cfg: dict) -> list[Opportunity]:
    scfg = cfg["sources"]["euraxess_funding"]
    if not scfg.get("enabled", True):
        return []
    fx = money_cfg.get("fx_to_eur", {"EUR": 1.0})
    items = _crawl(FUNDING_SEARCH, int(scfg.get("pages", 8)))
    LOG.info("EURAXESS funding: %s listings", len(items))
    ops = []
    for it in items:
        it["kind"] = "funding"
        ops.append(_mk(it, fx))
    return ops
