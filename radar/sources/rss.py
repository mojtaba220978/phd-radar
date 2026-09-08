"""Generic RSS/Atom source — add any feed you like in config.yaml."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from ..util import Opportunity, get, html_to_text, clean, shorten, best_annual_eur

LOG = logging.getLogger("radar.rss")


def fetch(cfg: dict, money_cfg: dict) -> list[Opportunity]:
    scfg = cfg["sources"].get("extra_rss", {})
    if not scfg.get("enabled", False):
        return []
    fx = money_cfg.get("fx_to_eur", {"EUR": 1.0})
    ops: list[Opportunity] = []
    for feed in scfg.get("feeds", []):
        r = get(feed["url"], timeout=40, retries=2)
        if r is None or r.status_code != 200:
            LOG.warning("feed failed: %s", feed.get("url"))
            continue
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as exc:
            LOG.warning("bad XML %s: %s", feed.get("url"), exc)
            continue
        entries = root.iter("item") if root.find(".//item") is not None else \
            root.iter("{http://www.w3.org/2005/Atom}entry")
        for e in entries:
            def tx(tag: str) -> str:
                node = e.find(tag) if not tag.startswith("{") else e.find(tag)
                if node is None:
                    node = e.find("{http://www.w3.org/2005/Atom}" + tag)
                return clean(node.text if node is not None and node.text else "")

            title = tx("title")
            link = tx("link")
            if not link:
                node = e.find("{http://www.w3.org/2005/Atom}link")
                link = node.attrib.get("href", "") if node is not None else ""
            desc = html_to_text(tx("description") or tx("summary"))
            creator = e.find("{http://purl.org/dc/elements/1.1/}creator")
            org = clean(creator.text) if creator is not None and creator.text else ""
            if not title or not link:
                continue
            amount, note = best_annual_eur(f"{title} {desc}", fx)
            ops.append(Opportunity(
                uid="rss:" + re.sub(r"\W+", "-", link)[-70:],
                source=feed.get("name", "RSS"),
                kind="job",
                title=title,
                url=link,
                organisation=org,
                posted=tx("pubDate")[:16],
                summary=shorten(desc, 340),
                amount_eur_year=amount,
                amount_note=note,
                raw_text=f"{title} {desc}",
            ))
    LOG.info("RSS: %s items", len(ops))
    return ops
