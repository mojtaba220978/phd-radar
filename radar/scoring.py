"""Relevance scoring + geography filtering.

Design goals
------------
* A hit in the TITLE (or the research-field label) is what really counts.
  Boiler-plate like "we offer mental health support to employees" must never
  turn a photonics PhD into a psychology match.
* Word-boundary matching, so "postdoctoral" never counts as "doctoral".
"""
from __future__ import annotations

import re

from datetime import date

from .util import Opportunity, parse_date

_WORD = re.compile(r"[^a-z0-9]+")
_CACHE: dict[str, re.Pattern] = {}


def _norm(s: str) -> str:
    return " " + _WORD.sub(" ", (s or "").lower()).strip() + " "


def _pat(kw: str) -> re.Pattern:
    """Word-boundary matcher. A trailing '*' means prefix match:
    'psycholog*' matches psychology / psychological / psychologie / psycholoog."""
    p = _CACHE.get(kw)
    if p is None:
        wild = kw.rstrip().endswith("*")
        core = _WORD.sub(" ", kw.lower().rstrip("* ")).strip().replace(" ", r"\s+")
        tail = r"[a-z]{0,12}(?![a-z0-9])" if wild else r"(?![a-z0-9])"
        p = re.compile(r"(?<![a-z0-9])" + core + tail)
        _CACHE[kw] = p
    return p


def has(kw: str, text: str) -> bool:
    return bool(_pat(kw).search(text))


PHD_WORDS = ("phd", "ph d", "phd student", "phd candidate", "phd researcher", "phd fellow",
             "phd position", "phd vacancy", "doctoral candidate", "doctoral researcher",
             "doctoral student", "doctoral position", "doctoral fellow", "doctorate",
             "doctoral training", "promovendus", "promovenda", "promotieonderzoek",
             "promotieplaats", "aio", "oio", "early stage researcher", "esr",
             "predoctoral", "pre doctoral", "doktorand", "doktorandin", "doctorant",
             "doctorante", "dottorato", "doctoral")
POSTDOC_WORDS = ("postdoc", "postdoctoral", "post doc", "post doctoral", "post-doc")
GRANT_WORDS = ("grant", "fellowship", "scholarship", "call", "programme", "program",
               "award", "funding", "beurs", "stipend")
FACULTY_WORDS = ("assistant professor", "associate professor", "full professor", "professor",
                 "lecturer", "senior researcher", "research fellow", "hoogleraar",
                 "universitair docent", "universitair hoofddocent", "tenure track",
                 "docent", "teacher", "instructor")

# support / administrative / technical staff — never relevant for a PhD hunt
STAFF_WORDS = ("assistent", "assistant", "secretaresse", "secretary", "medewerker",
               "management", "adviseur", "advisor", "consultant", "officer",
               "coordinator", "coördinator", "manager", "technician", "technicus",
               "analyst", "engineer", "developer", "programmer", "administrator",
               "controller", "recruiter", "communicatie", "marketing", "hr ",
               "intern", "internship", "stagiair", "student assistant", "onderzoeksassistent",
               "research assistant", "lab manager", "data steward", "data manager",
               "nurse", "verpleegkundige", "psycholoog gz", "gz-psycholoog")


def _is_phd(title: str) -> bool:
    if any(has(w, title) for w in POSTDOC_WORDS):
        # "PhD and postdoc positions" still counts, plain postdoc does not
        return has("phd", title) or has("doctoral candidate", title) or has("promovendus", title)
    return any(has(w, title) for w in PHD_WORDS)


def make_keyword_test(cfg: dict):
    """Cheap pre-filter, used before we spend HTTP requests on detail pages."""
    f = cfg["filters"]
    topics = list(f.get("topic_keywords", {}))
    excl = list(f.get("exclude_keywords", []))

    def test(op: Opportunity) -> bool:
        title = _norm(f"{op.title} {op.field}")
        if any(has(e, title) for e in excl):
            return False
        body = _norm(f"{op.title} {op.summary} {op.field}")
        return any(has(t, body) for t in topics)

    return test


def score(op: Opportunity, cfg: dict) -> tuple[float, list[str]]:
    f = cfg["filters"]
    geo = cfg["geography"]
    include_postdoc = bool(f.get("include_postdoc", False))

    title = _norm(f"{op.title} {op.field}")
    body = _norm(f"{op.summary} {op.raw_text}")[:30000]

    # ---- hard exclusions (title only) ------------------------------------
    for e in f.get("exclude_keywords", []):
        if has(e, title):
            return -1, []

    # ---- topical relevance ------------------------------------------------
    title_pts, body_pts = 0.0, 0.0
    matched: list[str] = []
    body_hits = 0
    for kw, w in f.get("topic_keywords", {}).items():
        w = float(w)
        if has(kw, title):
            title_pts += w * 2.4
            matched.append(kw)
        elif has(kw, body):
            body_pts += w
            body_hits += 1
            matched.append(kw)

    strong_body = (body_hits >= 3 and body_pts >= 22) or body_pts >= 34
    if title_pts <= 0 and not strong_body:
        return -1, []                       # boiler-plate mention only → drop

    pts = title_pts + min(body_pts, 30) * 0.6

    # ---- what kind of opportunity is it? ---------------------------------
    is_phd = _is_phd(title)
    is_postdoc = any(has(w, title) for w in POSTDOC_WORDS) and not is_phd
    is_grantish = op.kind in ("funding", "call") or any(has(w, title) for w in GRANT_WORDS)

    if is_postdoc and not include_postdoc:
        return -1, []

    # --- hard gate: a *job* must really be a doctoral position -------------
    if op.kind == "job" and not is_grantish:
        allowed = is_phd
        if include_postdoc and is_postdoc:
            allowed = True
        if f.get("include_faculty", False) and any(has(w, title) for w in FACULTY_WORDS):
            allowed = True
        if not allowed:
            return -1, []
    if any(has(w, title) for w in STAFF_WORDS) and not is_phd and not is_grantish:
        return -1, []

    if is_phd:
        pts += 30
    elif is_grantish:
        # a grant is only useful to you if it is aimed at doctoral / early-career people
        elig = f"{title} {body[:6000]}"
        if any(has(w, elig) for w in ("phd", "doctoral", "doctorate", "promovendus",
                                      "predoctoral", "pre doctoral", "early career",
                                      "early stage researcher", "master", "graduate",
                                      "scholarship", "students")):
            pts += 16
        else:
            return -1, []                   # senior/institutional call → not for you
    elif is_postdoc and include_postdoc:
        pts += 8
    elif op.kind == "job":
        pts -= 15                           # professor / staff vacancy

    # ---- geography --------------------------------------------------------
    # --- deadline ----------------------------------------------------------
    d = parse_date(op.deadline)
    if d:
        left = (d - date.today()).days
        if left < 0 and f.get("hide_expired", True):
            return -1, []
        grace = int(f.get("min_days_to_deadline", 0))
        if 0 <= left < grace:
            return -1, []                   # too late to realistically apply
        if left <= 21:
            pts += 4                        # urgent → surface it

    country = (op.country or "").strip()
    priority = geo.get("priority_countries", [])
    if geo.get("mode") == "only" and country and country not in priority:
        return -1, []
    allowed = geo.get("allowed_countries") or []
    if allowed and country and country not in allowed and geo.get("mode") != "all":
        return -1, []
    if country in priority:
        pts += float(geo.get("priority_bonus", 20))

    if op.amount_eur_year:
        pts += 5

    seen, uniq = set(), []
    for m in matched:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return round(min(pts, 100.0), 1), uniq[:8]


def rank(ops: list[Opportunity], cfg: dict) -> list[Opportunity]:
    """Keep what matches, then sort by grant/salary amount (descending)."""
    keep = []
    for op in ops:
        s, m = score(op, cfg)
        if s >= float(cfg["filters"].get("min_score", 45)):
            op.score, op.matched = s, m
            keep.append(op)
    unknown_last = cfg["money"].get("unknown_amount_position", "bottom") == "bottom"
    keep.sort(key=lambda o: (
        0 if (o.amount_eur_year or not unknown_last) else 1,
        -(o.amount_eur_year or 0),
        -o.score,
    ))
    return keep
