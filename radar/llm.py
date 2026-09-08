"""AI summariser — writes a short, accurate, bilingual brief for each advert.

Works with any OpenAI-compatible endpoint, so you can use a free provider:

    provider        base_url                                            free model
    ------------    -------------------------------------------------   ---------------------------------
    openrouter      https://openrouter.ai/api/v1                        deepseek/deepseek-chat-v3-0324:free
    groq            https://api.groq.com/openai/v1                      llama-3.3-70b-versatile
    gemini          https://generativelanguage.googleapis.com/v1beta/openai/   gemini-2.0-flash
    deepseek        https://api.deepseek.com/v1                         deepseek-chat

Set the key in the ``LLM_API_KEY`` environment variable / GitHub Secret.
If no key is present (or the call fails) the pipeline silently falls back to the
rule-based extractor + machine translation, so the report is never empty.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time

import requests

LOG = logging.getLogger("radar.llm")

CACHE_PATH = os.path.join("data", "summaries.json")
_LOCK = threading.Lock()
_CACHE: dict[str, dict] | None = None

PRESETS = {
    "openrouter": ("https://openrouter.ai/api/v1", "minimax/minimax-m3:free"),
    "groq":       ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash"),
    "deepseek":   ("https://api.deepseek.com/v1", "deepseek-chat"),
    "mistral":    ("https://api.mistral.ai/v1", "mistral-small-latest"),
}

SYSTEM = (
    "You are a research-career assistant for an Iranian clinical-psychology graduate "
    "who is hunting for funded PhD positions in Europe. You read a job/grant advert and "
    "write a factual mini-brief. You never invent facts. If something is not stated in "
    "the advert, you omit it rather than guessing."
)

USER_TMPL = """Advert title: {title}
Organisation: {org} — {country}
Advert text (may be English or Dutch, may contain boiler-plate):
\"\"\"{text}\"\"\"

Write a brief that answers, in this order and only from the advert:
1. WHAT the research is about — the concrete topic/research question.
2. WHO it studies — the population or sample (e.g. patients with PTSD, adolescents,
   older adults, healthy volunteers, rodents, existing cohort data). If the advert
   does not say, write "population not specified".
3. HOW — the main methods (e.g. RCT, EEG/fMRI, longitudinal cohort, interviews,
   computational modelling) and, if stated, the duration.

Rules:
- English: 2–3 sentences, max 55 words, plain and concrete. No marketing language,
  no university self-praise, no salary/benefits information.
- Persian: a faithful translation of your English text into natural, fluent Persian
  (فارسی روان و علمی). Keep technical terms that Iranian academics use in English
  (fMRI, EEG, PTSD, RCT, ...) in Latin script. Do not add anything new.
- Never output Chinese, Japanese or Korean characters. Persian text must use only
  Persian/Arabic script plus Latin technical terms.
- Do not show your reasoning. Output the final answer only.
- Answer with STRICT JSON only, no markdown fences:
{{"en": "...", "fa": "..."}}"""


# --------------------------------------------------------------------------- #
#  cache
# --------------------------------------------------------------------------- #
def _load() -> dict[str, dict]:
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
        data = dict(_CACHE)
    if len(data) > 3000:
        data = dict(list(data.items())[-2000:])
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=0)


def _key(op) -> str:
    blob = (op.title + "|" + op.raw_text[:1200]).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:20]


# --------------------------------------------------------------------------- #
#  provider
# --------------------------------------------------------------------------- #
class LLM:
    def __init__(self, cfg: dict):
        lc = cfg.get("llm", {}) or {}
        provider = (lc.get("provider") or "openrouter").lower()
        base, model = PRESETS.get(provider, PRESETS["openrouter"])
        self.base_url = (lc.get("base_url") or base).rstrip("/")
        self.model = lc.get("model") or model
        self.key = os.getenv(lc.get("api_key_env", "LLM_API_KEY"), "").strip()
        self.timeout = int(lc.get("timeout", 90))
        self.retries = int(lc.get("retries", 3))
        self.max_input = int(lc.get("max_input_chars", 6000))
        self.temperature = float(lc.get("temperature", 0.2))
        self.fallback_models = list(lc.get("fallback_models") or [])
        self.pace = float(lc.get("pace_seconds", 0.6))
        self.enabled = bool(lc.get("enabled", True)) and bool(self.key)
        self.provider = provider
        self._fails = 0

    # -- low level ---------------------------------------------------------
    def _chat(self, messages: list[dict], model: str | None = None) -> str:
        """Try the configured model, then any fallbacks (free models come and go)."""
        for candidate in [model or self.model, *self.fallback_models]:
            out = self._chat_one(messages, candidate)
            if out:
                if candidate != self.model:
                    LOG.warning("switched to fallback model %s", candidate)
                    self.model = candidate
                return out
        return ""

    def _chat_one(self, messages: list[dict], model: str) -> str:
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/phd-radar"
            headers["X-Title"] = "PhD Radar"
        payload = {"model": model, "messages": messages,
                   "temperature": self.temperature,
                   "max_tokens": 40 if len(messages) == 1 else 700}
        for attempt in range(self.retries):
            try:
                r = requests.post(f"{self.base_url}/chat/completions", headers=headers,
                                  json=payload, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                if r.status_code == 404:
                    LOG.error("model %s unavailable: %s", model, r.text[:160])
                    return ""
                if r.status_code in (429, 500, 502, 503, 529):
                    wait = 6 * (attempt + 1)
                    LOG.warning("LLM %s → waiting %ss", r.status_code, wait)
                    time.sleep(wait)
                    continue
                LOG.error("LLM error %s: %s", r.status_code, r.text[:220])
                return ""
            except Exception as exc:            # noqa: BLE001
                LOG.warning("LLM request failed (%s/%s): %s", attempt + 1, self.retries, exc)
                time.sleep(4 * (attempt + 1))
        return ""

    # -- public ------------------------------------------------------------
    def check(self) -> tuple[bool, str]:
        """Cheap health-check (a few tokens) so problems surface in the log early."""
        if not self.key:
            return False, "کلید API تنظیم نشده (LLM_API_KEY)"
        saved, self.temperature = self.temperature, 0.0
        try:
            out = self._chat([{"role": "user", "content": "Reply with exactly: OK"}])
        finally:
            self.temperature = saved
        return (True, f"{self.provider} · {self.model}") if out else (False, "پاسخی از سرویس دریافت نشد")

    def needs_work(self, ops) -> int:
        """How many items are not in the cache yet (0 → no API call needed at all)."""
        cache = _load()
        return sum(1 for o in ops if _key(o) not in cache)

    def summarize(self, op) -> tuple[str, str]:
        if not self.enabled or self._fails >= 5:
            return "", ""
        cache = _load()
        k = _key(op)
        hit = cache.get(k)
        if hit and hit.get("en") and hit.get("fa"):
            return hit["en"], hit["fa"]

        if self.pace:
            time.sleep(self.pace)
        text = re.sub(r"\s+", " ", op.raw_text or op.summary)[: self.max_input]
        prompt = USER_TMPL.format(title=op.title, org=op.organisation or "—",
                                  country=op.country or "—", text=text)
        out = self._chat([{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": prompt}])
        if not out:
            self._fails += 1
            return "", ""
        self._fails = 0
        en, fa = _parse(out)
        if _CJK.search(fa) or _CJK.search(en):          # rare model glitch → one retry
            out2 = self._chat([{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": prompt},
                               {"role": "assistant", "content": out},
                               {"role": "user", "content":
                                "Your answer contained non-Persian (CJK) characters. "
                                "Rewrite the same JSON using only Persian script and Latin "
                                "technical terms."}])
            if out2:
                en2, fa2 = _parse(out2)
                if en2 or fa2:
                    en, fa = en2 or en, fa2 or fa
        en, fa = _clean(en), _clean(fa)
        if en or fa:
            with _LOCK:
                cache[k] = {"en": en, "fa": fa}
        return en, fa


_CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]")


def _clean(s: str) -> str:
    s = _CJK.sub("", s or "")
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"\s+([.،؛:!؟])", r"\1", s)
    return s


def _parse(raw: str) -> tuple[str, str]:
    txt = raw.strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            return str(d.get("en", "")).strip(), str(d.get("fa", "")).strip()
        except Exception:                       # noqa: BLE001
            pass
    # very defensive fallback: split on the first Persian character
    i = next((j for j, ch in enumerate(txt) if "\u0600" <= ch <= "\u06FF"), -1)
    if i > 0:
        return txt[:i].strip(" \"'{}en:,\n"), txt[i:].strip(" \"'{}\n")
    return txt[:400], ""
