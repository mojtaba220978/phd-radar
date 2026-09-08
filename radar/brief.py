"""Turn a long, boiler-plate-heavy advert into 2–3 informative sentences,
then hand it to the translator so the report can show a short Persian brief.

Works on English *and* Dutch adverts (AcademicTransfer publishes many in Dutch).
"""
from __future__ import annotations

import re

from .util import Opportunity, clean

# ---- sentences that carry real information (EN + NL cues) ------------------
_GOOD = re.compile(
    r"\b(you will|your (task|job|role|project)|we are (looking|seeking|offering)|we offer|"
    r"the (project|position|candidate|research|phd|study|aim|goal)|this (project|position|phd|study)|"
    r"in this (project|role|position)|research (focus|question|topic|aims?|project)|"
    r"aims? (to|at)|focus(es|ing)? on|investigat|examin|explor|develop|analys|analyz|"
    r"the successful candidate|supervis|embedded in|is part of|funded by|collaborat|"
    r"data collection|patients|participants|clinical|trial|intervention|imaging|therapy|"
    r"zoeken wij|wij zoeken|je gaat|jij gaat|je zult|binnen dit|dit promotieonderzoek|"
    r"het (project|onderzoek)|de promovendus|onderzoek naar|richt zich op|je onderzoekt|"
    r"in dit project|doel van)\b", re.I)

# ---- pure boiler-plate we never want -------------------------------------
_BAD = re.compile(
    r"(welcome to|equal opportunit|diversity|inclusi|we value|our university|is a (leading|top)|"
    r"ranked|apply (now|via|through|before)|application (procedure|process|deadline)|"
    r"for more information|contact (us|person)|questions\?|cookie|privacy|acquisition|agencies|"
    r"acquisitie|terms of employment|collective labour agreement|\bcao\b|pension|"
    r"holiday allowance|end-of-year|salary (is|ranges|scale|will)|gross monthly|"
    r"working conditions|the netherlands is|campus|located in|founded in|"
    r"students and staff|employees work|solliciteer|sollicitatie|arbeidsvoorwaarden|"
    r"salaris|vakantiegeld|eindejaarsuitkering|wij bieden je een|meer informatie|"
    r"functie ?omschrijving|job description|about us|over ons|what we offer|wat wij bieden|"
    r"^\s*(functie|profiel|aanbod|organisatie|afdeling|requirements|qualifications)\s*:?\s*$)",
    re.I)

_NOISE = re.compile(r"(https?://\S+|\S+@\S+\.\w+|\+\d[\d\s().-]{7,}|\b\d{4}\s?[A-Z]{2}\b)")

# structured metadata that EURAXESS puts before the real advert text
_META = re.compile(
    r"(job information|organisation/company|research field|researcher profile|"
    r"application deadline|type of contract|job status|hours per week|"
    r"number of offers|work location|reference number|is the job funded|"
    r"country\s+[A-Z]|department:|first stage researcher|recognised researcher|"
    r"funding programme|posted on|status:open|où postuler|where to apply)", re.I)

# the advert usually really starts after one of these markers
_START_MARKERS = ("offer description", "job description", "the offer", "about the project",
                  "project description", "functieomschrijving", "offer descriptions")
_SPLIT = re.compile(r"(?<=[.!?])\s+")
_HEADERS = re.compile(
    r"^(functie|functieomschrijving|profiel|wat vragen wij|wat bieden wij|aanbod|organisatie|"
    r"afdeling|job description|about (us|the (job|position|role))|your (profile|job)|"
    r"we ask|we offer|requirements|qualifications|the position|description)\s*[:\-–]?\s*",
    re.I)


def english_brief(op: Opportunity, max_chars: int = 420) -> str:
    """Pick 2–3 complete, informative sentences from the advert."""
    text = op.raw_text if len(op.raw_text) > len(op.summary) else op.summary
    text = clean(text)

    # 1) jump to where the real advert starts (skip EURAXESS metadata blocks)
    low = text.lower()
    for marker in _START_MARKERS:
        i = low.find(marker)
        if 0 <= i < 4000:
            text = text[i + len(marker):].lstrip(" :-–—")
            break

    # 2) drop repetitions of the title (shown separately anyway)
    full = clean(op.title)
    for variant in (full, full.split("(")[0].strip(), full.split("–")[0].strip()):
        if len(variant) > 15:
            text = re.sub(re.escape(variant), " ", text, flags=re.I)

    # 3) if we now start mid-word / mid-sentence, skip to the next sentence
    text = text.lstrip(" ,;:.-–—)")
    m = re.match(r"^[a-z\u00e0-\u00ff)\]]{1,25}[\s.,)]", text)
    if m:
        text = text[m.end():]

    text = _NOISE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)[:9000]

    picked: list[str] = []
    for raw in _SPLIT.split(text):
        s = _HEADERS.sub("", clean(raw)).strip()
        if not (45 <= len(s) <= 300):
            continue
        if "…" in s or s.endswith(("-", ",")):
            continue
        if not s.endswith((".", "!", "?")):
            continue
        if _BAD.search(s) or _META.search(s) or not _GOOD.search(s):
            continue
        if sum(ch.isdigit() for ch in s) > len(s) * 0.15:
            continue
        if any(_similar(s, p) for p in picked):
            continue
        picked.append(s)
        if sum(len(p) for p in picked) >= max_chars or len(picked) >= 3:
            break

    if not picked:                       # relaxed fallback
        for raw in _SPLIT.split(text):
            s = _HEADERS.sub("", clean(raw)).strip()
            if (45 <= len(s) <= 300 and s.endswith((".", "!", "?"))
                    and not _BAD.search(s) and not _META.search(s)
                    and s[:1].isupper()):
                picked.append(s)
                if len(picked) >= 2:
                    break
    if not picked:
        s = clean(op.summary).replace("…", "")
        picked = [s[:max_chars].rsplit(" ", 1)[0] + "."] if s else []

    out = " ".join(picked).strip()
    if len(out) > max_chars + 120:       # never cut mid-sentence
        keep, total = [], 0
        for s in picked:
            if total + len(s) > max_chars + 120 and keep:
                break
            keep.append(s)
            total += len(s)
        out = " ".join(keep)
    return out


def _similar(a: str, b: str) -> bool:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return False
    return len(sa & sb) / min(len(sa), len(sb)) > 0.7


# --------------------------------------------------------------------------- #
#  A one-line Persian "facts" strip that needs no translation at all
# --------------------------------------------------------------------------- #
def facts_fa(op: Opportunity) -> str:
    bits = []
    title = op.title.lower()
    if any(w in title for w in ("phd", "doctoral", "promovendus", "promovenda", "doctorate")):
        bits.append("🎓 دکترا")
    elif op.kind in ("funding", "call"):
        bits.append("💰 گرنت/بورس")
    if op.organisation:
        bits.append(f"🏛 {op.organisation}")
    if op.city:
        bits.append(f"📍 {op.city}")
    return " · ".join(bits)
