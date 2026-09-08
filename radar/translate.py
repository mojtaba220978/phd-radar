"""Automatic English → Persian translation with an on-disk cache.

Two free back-ends are tried in order; results are cached in
``data/translations.json`` so the same advert is never translated twice
(daily runs stay fast and the wording stays stable).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request

LOG = logging.getLogger("radar.translate")

CACHE_PATH = os.path.join("data", "translations.json")
_LOCK = threading.Lock()
_CACHE: dict[str, str] | None = None
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


# --------------------------------------------------------------------------- #
#  cache
# --------------------------------------------------------------------------- #
def _load() -> dict[str, str]:
    global _CACHE
    if _CACHE is None:
        try:
            with open(CACHE_PATH, encoding="utf-8") as fh:
                _CACHE = json.load(fh)
        except Exception:                       # noqa: BLE001
            _CACHE = {}
    return _CACHE


def save_cache() -> None:
    if _CACHE is None:
        return
    os.makedirs(os.path.dirname(CACHE_PATH) or ".", exist_ok=True)
    with _LOCK:
        tmp = dict(_CACHE)
    # keep the file from growing forever
    if len(tmp) > 4000:
        tmp = dict(list(tmp.items())[-3000:])
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(tmp, fh, ensure_ascii=False, indent=0)


def _key(text: str, lang: str) -> str:
    return lang + ":" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


# --------------------------------------------------------------------------- #
#  back-ends
# --------------------------------------------------------------------------- #
def _fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _google(text: str, lang: str) -> str:
    url = ("https://translate.googleapis.com/translate_a/single"
           f"?client=dict-chrome-ex&sl=auto&tl={lang}&dt=t&q={urllib.parse.quote(text)}")
    data = json.loads(_fetch(url))
    if isinstance(data, list) and data and isinstance(data[0], list):
        parts = []
        for seg in data[0]:
            if isinstance(seg, list) and seg and isinstance(seg[0], str):
                parts.append(seg[0])
            elif isinstance(seg, str):
                parts.append(seg)
        return "".join(parts).strip()
    return ""


def _mymemory(text: str, lang: str) -> str:
    out = []
    for chunk in _split(text, 480):
        url = ("https://api.mymemory.translated.net/get"
               f"?q={urllib.parse.quote(chunk)}&langpair=en|{lang}")
        data = json.loads(_fetch(url))
        out.append((data.get("responseData") or {}).get("translatedText", ""))
        time.sleep(0.4)
    return " ".join(p for p in out if p).strip()


BACKENDS = (("google", _google), ("mymemory", _mymemory))


def _split(text: str, size: int) -> list[str]:
    """Split on sentence boundaries so translations stay coherent."""
    if len(text) <= size:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?؛;])\s+", text):
        if len(cur) + len(sent) + 1 > size and cur:
            parts.append(cur.strip())
            cur = ""
        cur += sent + " "
    if cur.strip():
        parts.append(cur.strip())
    return parts


# --------------------------------------------------------------------------- #
#  public API
# --------------------------------------------------------------------------- #
def translate(text: str, lang: str = "fa", *, enabled: bool = True) -> str:
    text = (text or "").strip()
    if not text or not enabled:
        return ""
    if _looks_persian(text):
        return text
    cache = _load()
    k = _key(text, lang)
    if k in cache:
        return cache[k]

    result = ""
    for name, fn in BACKENDS:
        try:
            pieces = [fn(chunk, lang) for chunk in _split(text, 1600)]
            result = " ".join(p for p in pieces if p).strip()
            if result:
                break
        except Exception as exc:                # noqa: BLE001
            LOG.debug("translate backend %s failed: %s", name, exc)
            time.sleep(0.8)
    if not result:
        LOG.warning("translation failed for a %s-char text", len(text))
        return ""
    result = _tidy(result)
    with _LOCK:
        cache[k] = result
    return result


def _looks_persian(text: str) -> bool:
    fa = len(re.findall(r"[\u0600-\u06FF]", text))
    return fa > len(text) * 0.3


def _tidy(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ,", "،").replace(" ?", "؟")
    s = re.sub(r"\s+([،.؛:؟!])", r"\1", s)
    return s
