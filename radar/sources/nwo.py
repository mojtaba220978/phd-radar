"""NWO (Dutch Research Council) — open calls for proposals / grants."""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

from ..util import Opportunity, get, html_to_text, clean, shorten, best_annual_eur

LOG = logging.getLogger("radar.nwo")

BASE = "https://www.nwo.nl"
CALLS = f"{BASE}/en/calls"

_CARD_RE = re.compile(
    r'<h3 class="card__title"><a href="(/en/calls/[^"]+)"[^>]*>(.*?)</a></h3>\s*<p>(.*?)</p>', re.S)
_DEADLINE_RE = re.compile(r"(Deadline|Closing date)[^0-9]{0,40}(\d{1,2}\s+\w+\s+\d{4})", re.I)


def fetch(cfg: dict, money_cfg: dict) -> list[Opportunity]:
    scfg = cfg["sources"].get("nwo_calls", {})
    if not scfg.get("enabled", True):
        return []
    fx = money_cfg.get("fx_to_eur", {"EUR": 1.0})
    pages = int(scfg.get("pages", 3))
    cards: list[tuple[str, str, str]] = []

    def one(p: int):
        r = get(CALLS, params={"page": p} if p else None, timeout=45, retries=2)
        return _CARD_RE.findall(r.text) if r is not None and r.status_code == 200 else []

    with ThreadPoolExecutor(max_workers=4) as ex:
        for batch in ex.map(one, range(pages)):
            cards.extend(batch)

    seen, ops = set(), []
    for href, title, desc in cards:
        if href in seen:
            continue
        seen.add(href)
        title, desc = clean(html_to_text(title)), clean(html_to_text(desc))
        text = f"{title} {desc}"
        amount, note = best_annual_eur(text, fx)
        ops.append(Opportunity(
            uid="nwo:" + href.rsplit("/", 1)[-1],
            source="NWO",
            kind="funding",
            title=title,
            url=BASE + href,
            organisation="NWO — Dutch Research Council",
            country="Netherlands",
            summary=shorten(desc, 340),
            amount_eur_year=amount,
            amount_note=note,
            raw_text=text,
        ))
    LOG.info("NWO: %s calls", len(ops))

    # enrich the shortlisted ones with the call page (deadline + budget)
    def enrich(op: Opportunity):
        time.sleep(0.4)
        r = get(op.url, timeout=40, retries=2, sleep=3)
        if r is None or r.status_code != 200:
            return
        txt = html_to_text(r.text)[:20000]
        op.raw_text += " " + txt
        m = _DEADLINE_RE.search(txt)
        if m:
            op.deadline = clean(m.group(2))
        amt, note = best_annual_eur(txt, fx)
        if amt > op.amount_eur_year:
            op.amount_eur_year, op.amount_note = amt, note

    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(enrich, ops[:60]))
    return ops
