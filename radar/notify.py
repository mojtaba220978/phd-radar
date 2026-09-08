"""Delivery: e-mail (SMTP) and Telegram."""
from __future__ import annotations

import logging
import mimetypes
import os
import time
import smtplib
from email.message import EmailMessage

import requests

from .util import Opportunity, fmt_eur, fmt_range_eur

LOG = logging.getLogger("radar.notify")


# --------------------------------------------------------------------------- #
#  E-mail
# --------------------------------------------------------------------------- #
def send_email(cfg: dict, subject: str, html_body: str, attachments: list[str] | None = None) -> bool:
    ecfg = cfg["delivery"]["email"]
    if not ecfg.get("enabled", False):
        return False
    recipients = [r for r in ecfg.get("recipients", []) if r and "example.com" not in r]
    host = os.getenv(ecfg.get("smtp_host_env", "SMTP_HOST"), "")
    port = int(os.getenv(ecfg.get("smtp_port_env", "SMTP_PORT"), "587") or 587)
    user = os.getenv(ecfg.get("smtp_user_env", "SMTP_USER"), "")
    password = os.getenv(ecfg.get("smtp_pass_env", "SMTP_PASS"), "")
    sender = os.getenv(ecfg.get("from_env", "SMTP_FROM"), "") or user

    if not (recipients and host and user and password):
        LOG.warning("e-mail skipped (missing recipients or SMTP_* env vars)")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content("This report is best viewed as HTML.\n")
    msg.add_alternative(html_body, subtype="html")

    for path in attachments or []:
        if not os.path.exists(path):
            continue
        ctype, _ = mimetypes.guess_type(path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype,
                               filename=os.path.basename(path))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=60) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as s:
                s.ehlo()
                s.starttls()
                s.login(user, password)
                s.send_message(msg)
        LOG.info("e-mail sent to %s", recipients)
        return True
    except Exception as exc:                       # noqa: BLE001
        LOG.error("e-mail failed: %s", exc)
        return False


# --------------------------------------------------------------------------- #
#  Telegram
# --------------------------------------------------------------------------- #
def _tg(token: str, method: str, **kwargs):
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kwargs)
        if r.status_code != 200:
            LOG.error("telegram %s → %s %s", method, r.status_code, r.text[:200])
        return r.status_code == 200
    except Exception as exc:                       # noqa: BLE001
        LOG.error("telegram %s failed: %s", method, exc)
        return False


def _fa_num(n) -> str:
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


COUNTRY_TAG = {
    "Netherlands": "#هلند", "Germany": "#آلمان", "Belgium": "#بلژیک", "Denmark": "#دانمارک",
    "Sweden": "#سوئد", "Norway": "#نروژ", "Finland": "#فنلاند", "Austria": "#اتریش",
    "Switzerland": "#سوئیس", "Ireland": "#ایرلند", "France": "#فرانسه", "Spain": "#اسپانیا",
    "Italy": "#ایتالیا", "Portugal": "#پرتغال", "Poland": "#لهستان",
    "United Kingdom": "#بریتانیا", "Czechia": "#چک", "Luxembourg": "#لوکزامبورگ",
}
TOPIC_TAG = [
    (("clinical psychology", "psychotherapy", "psychopathology", "cbt"), "#روانشناسی_بالینی"),
    (("neuroscience", "neuroimaging", "fmri", "eeg", "meg", "cognition"), "#علوم_اعصاب"),
    (("psychiatry", "depression", "anxiety", "ptsd", "trauma", "mental health"), "#سلامت_روان"),
    (("addiction", "substance use"), "#اعتیاد"),
]


def _tags(op: Opportunity) -> str:
    tags = ["#دکترا" if op.kind == "job" else "#گرنت"]
    if op.country in COUNTRY_TAG:
        tags.append(COUNTRY_TAG[op.country])
    hay = " ".join([op.title, " ".join(op.matched)]).lower()
    for words, tag in TOPIC_TAG:
        if any(w in hay for w in words) and tag not in tags:
            tags.append(tag)
    return " ".join(tags[:4])


def _clip(text: str, limit: int) -> str:
    """Cut at a sentence boundary if possible, otherwise at a word boundary."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[: limit + 1]
    for stop in (". ", "؟ ", "! ", "، ", " "):
        cut = window.rfind(stop)
        if cut > limit * 0.55:
            return window[: cut + (1 if stop.strip() in ".؟!" else 0)].rstrip(" ،") + " …"
    return window[:limit].rstrip() + " …"


def _card(i: int, op: Opportunity, is_new: bool) -> str:
    """One clean, well-spaced block per opportunity."""
    from .report import FLAGS, MEDAL, country_fa, days_left
    from .brief import facts_fa

    head = MEDAL.get(i, f"<b>{_fa_num(i)}.</b>")
    if op.salary_min_month or op.salary_max_month:
        monthly = fmt_range_eur(op.salary_min_month, op.salary_max_month, isolate=True)
        yearly = fmt_range_eur(op.amount_eur_year, op.amount_max_eur_year, isolate=True)
        money = f"💶 <b>{monthly}</b> ناخالص در ماه  (≈ {yearly} در سال)"
    elif op.amount_eur_year:
        money = f"💶 <b>{fmt_eur(op.amount_eur_year, isolate=True)}</b> در سال (تخمین از متن آگهی)"
    else:
        money = "💶 <i>مبلغ در آگهی ذکر نشده</i>"
    new = "  🆕" if is_new else ""

    lines = [f"{head} {money}{new}",
             f"<b>{_esc(_clip(op.title, 110))}</b>"]

    place = " · ".join(filter(None, [
        f"{FLAGS.get(op.country, '🌍')} {country_fa(op.country)}" if op.country else "",
        _esc(op.city) if op.city else "",
        _esc(op.organisation[:45]) if op.organisation else "",
    ]))
    if place:
        lines.append(f"🏛 {place}")

    if op.deadline:
        d = days_left(op)
        dl = op.deadline.split(" - ")[0]
        if d is not None and 0 <= d <= 14:
            lines.append(f"⏳ <b>مهلت: {dl} — فقط {_fa_num(d)} روز مانده!</b>")
        elif d is not None and d >= 0:
            lines.append(f"🗓 مهلت: {dl} ({_fa_num(d)} روز مانده)")
        else:
            lines.append(f"🗓 مهلت: {dl}")

    if op.summary_fa:
        lines.append(f"📝 {_esc(_clip(op.summary_fa, 430))}")
    if op.summary_en:
        lines.append(f"🇬🇧 <i>{_esc(_clip(op.summary_en, 350))}</i>")

    lines.append(f'🔗 <a href="{op.url}">مشاهده آگهی و درخواست</a>')
    lines.append(f"<i>{_tags(op)}</i>")
    return "\n".join(lines)


def send_telegram(cfg: dict, ops: list[Opportunity], new_uids: set[str],
                  html_path: str | None = None, header: str = "") -> bool:
    tcfg = cfg["delivery"]["telegram"]
    if not tcfg.get("enabled", False):
        return False
    token = os.getenv(tcfg.get("token_env", "TELEGRAM_BOT_TOKEN"), "")
    chat = os.getenv(tcfg.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
    if not (token and chat):
        LOG.warning("telegram skipped (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set)")
        return False

    top = ops[: int(tcfg.get("top_n", 15))]
    per_msg = max(1, int(tcfg.get("items_per_message", 3)))
    sep = "\n\n" + "─" * 18 + "\n\n"
    ok = True

    def post(text: str) -> bool:
        return _tg(token, "sendMessage",
                   data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                         "disable_web_page_preview": "true"})

    if header:
        ok &= post(header)
        time.sleep(0.4)

    cards = [_card(i, op, op.uid in new_uids) for i, op in enumerate(top, 1)]
    for start in range(0, len(cards), per_msg):
        block = sep.join(cards[start:start + per_msg])
        if len(block) > 4000:                       # Telegram hard limit
            for single in cards[start:start + per_msg]:
                ok &= post(single[:4000])
                time.sleep(0.4)
        else:
            ok &= post(block)
        time.sleep(0.5)

    tail = []
    if len(ops) > len(top):
        tail.append(f"➕ <b>{_fa_num(len(ops) - len(top))} مورد دیگر</b> در فایل کامل زیر 👇")
    tail.append("📎 فایل HTML پیوست: همهٔ موارد + جستجو + فیلتر کشور و مهلت.")
    sig = tcfg.get("signature", "")
    if sig:
        tail.append("")
        tail.append(sig)
    ok &= post("\n".join(tail))

    if html_path and tcfg.get("send_html_file", True) and os.path.exists(html_path):
        time.sleep(0.4)
        with open(html_path, "rb") as fh:
            ok &= _tg(token, "sendDocument", data={"chat_id": chat},
                      files={"document": (os.path.basename(html_path), fh, "text/html")})
    return ok


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def telegram_alert(text: str) -> bool:
    """Fire-and-forget message (used by CI when a run fails)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not (token and chat):
        return False
    return _tg(token, "sendMessage",
               data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                     "disable_web_page_preview": "true"})
