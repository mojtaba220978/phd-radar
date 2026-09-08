#!/usr/bin/env python3
"""
PhD Radar — daily hunter for funded PhD positions & research grants in Europe.

Usage:
    python main.py                     # full run (fetch → filter → rank → report → send)
    python main.py --no-send           # build the report only
    python main.py --config my.yaml
    python main.py --email a@b.com --email c@d.com     # override recipients
    python main.py --min-score 40 --dry-run
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import yaml

from radar import report as R
from radar import llm as LLM
from radar import translate as T
from radar.brief import english_brief
from radar.notify import send_email, send_telegram
from radar.scoring import make_keyword_test, rank
from radar.sources import academictransfer, euraxess, nwo, rss
from radar.store import Store
from radar.util import Opportunity, fmt_eur

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                    datefmt="%H:%M:%S")
LOG = logging.getLogger("radar.main")
HERE = os.path.dirname(os.path.abspath(__file__))


def load_cfg(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def collect(cfg: dict) -> list[Opportunity]:
    money = cfg["money"]
    kw_test = make_keyword_test(cfg)
    ops: list[Opportunity] = []
    steps = [
        ("AcademicTransfer", lambda: academictransfer.fetch(cfg, money)),
        ("EURAXESS jobs", lambda: euraxess.fetch_jobs(cfg, money, kw_test)),
        ("EURAXESS funding", lambda: euraxess.fetch_funding(cfg, money)),
        ("NWO calls", lambda: nwo.fetch(cfg, money)),
        ("Extra RSS", lambda: rss.fetch(cfg, money)),
    ]
    for name, fn in steps:
        try:
            got = fn()
            LOG.info("✔ %-18s → %s items", name, len(got))
            ops.extend(got)
        except Exception as exc:                   # noqa: BLE001
            LOG.error("✘ %-18s failed: %s", name, exc)
    return dedupe(ops)


SOURCE_RANK = {"AcademicTransfer": 0, "NWO": 1, "EURAXESS": 2}


def dedupe(ops: list[Opportunity]) -> list[Opportunity]:
    """Same vacancy is often listed on several boards → keep the richest copy."""
    import re as _re

    def key(op: Opportunity) -> str:
        t = _re.sub(r"[^a-z0-9]+", " ", op.title.lower()).strip()
        t = _re.sub(r"\b(phd|position|positions|candidate|vacancy|m f d|f m d|x)\b", " ", t)
        return _re.sub(r"\s+", " ", t)[:70]

    best: dict[str, Opportunity] = {}
    for op in ops:
        k = key(op)
        cur = best.get(k)
        if cur is None:
            best[k] = op
            continue
        better = (op.amount_eur_year or 0, -SOURCE_RANK.get(op.source, 9), len(op.summary))
        worse = (cur.amount_eur_year or 0, -SOURCE_RANK.get(cur.source, 9), len(cur.summary))
        if better > worse:
            op.raw_text += " " + cur.raw_text
            best[k] = op
        else:
            cur.raw_text += " " + op.raw_text
    seen_uid, out = set(), []
    for op in best.values():
        if op.uid in seen_uid:
            continue
        seen_uid.add(op.uid)
        out.append(op)
    return out


def add_persian(ops: list[Opportunity], cfg: dict) -> None:
    """Give every item an English brief + a Persian brief.

    Preferred path: an AI model (see `llm` in config.yaml) which is told to state
    the research topic, the study population and the methods.
    Fallback path: rule-based sentence picking + machine translation.
    """
    tcfg = cfg.get("translate", {})
    if not tcfg.get("enabled", True):
        return

    lang = tcfg.get("language", "fa")
    model = LLM.LLM(cfg)
    if model.enabled and model.needs_work(ops) == 0:
        LOG.info("AI summariser: همه خلاصه‌ها از کش خوانده شدند (بدون مصرف سهمیه)")
    elif model.enabled:
        ok, info = model.check()
        LOG.info("AI summariser: %s (%s)", "فعال" if ok else "غیرفعال", info)
        model.enabled = ok
    else:
        LOG.info("AI summariser off — using rule-based briefs + machine translation")

    def one(op: Opportunity):
        try:
            if model.enabled:
                en, fa = model.summarize(op)
                if en or fa:
                    op.summary_en = en
                    op.summary_fa = fa or T.translate(en, lang)
                    return
            brief = english_brief(op, int(tcfg.get("max_chars", 420)))
            op.summary_en = brief
            op.summary_fa = T.translate(brief, lang)
        except Exception as exc:                # noqa: BLE001
            LOG.debug("brief failed for %s: %s", op.uid, exc)

    workers = int(cfg.get("llm", {}).get("workers", 3)) if model.enabled \
        else int(tcfg.get("workers", 4))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, ops))

    T.save_cache()
    LLM.save_cache()
    LOG.info("briefs ready: %s/%s Persian · %s/%s English",
             sum(1 for o in ops if o.summary_fa), len(ops),
             sum(1 for o in ops if o.summary_en), len(ops))


def prune_reports(folder: str, keep_days: int) -> None:
    cutoff = (datetime.now() - timedelta(days=keep_days)).timestamp()
    for f in glob.glob(os.path.join(folder, "*")):
        try:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
        except OSError:
            pass


STAMP = os.path.join("data", "last_sent.txt")


def _sent_today() -> bool:
    """آیا گزارش امروز قبلاً ارسال شده است؟"""
    try:
        with open(STAMP, encoding="utf-8") as fh:
            return fh.read().strip() == date.today().isoformat()
    except OSError:
        return False


def _stamp_today() -> None:
    os.makedirs("data", exist_ok=True)
    with open(STAMP, "w", encoding="utf-8") as fh:
        fh.write(date.today().isoformat())


def main() -> int:
    ap = argparse.ArgumentParser(description="PhD Radar")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--no-send", action="store_true", help="build files, do not e-mail/telegram")
    ap.add_argument("--dry-run", action="store_true", help="do not write the seen-database")
    ap.add_argument("--force", action="store_true",
                    help="حتی اگر امروز یک‌بار فرستاده شده، دوباره بفرست")
    ap.add_argument("--email", action="append", default=[], help="override recipients (repeatable)")
    ap.add_argument("--min-score", type=float)
    ap.add_argument("--only-new", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    env_rcpt = [e.strip() for e in os.getenv("RECIPIENTS", "").replace(";", ",").split(",") if e.strip()]
    if env_rcpt:
        cfg["delivery"]["email"]["recipients"] = env_rcpt
        cfg["delivery"]["email"]["enabled"] = True
    if args.email:
        cfg["delivery"]["email"]["recipients"] = args.email
        cfg["delivery"]["email"]["enabled"] = True
    if args.min_score is not None:
        cfg["filters"]["min_score"] = args.min_score
    if args.only_new:
        cfg["output"]["only_new_in_email"] = True

    os.chdir(HERE)
    today = date.today().isoformat()

    # نوبت‌های پشتیبان: اگر گزارش امروز قبلاً رفته، دوباره نفرست.
    # (گیت‌هاب گاهی اجرای زمان‌بندی‌شده را می‌اندازد، پس چند نوبت تعریف
    #  کرده‌ایم؛ اولین نوبتی که موفق شود کار را تمام می‌کند.)
    if _sent_today() and not (args.force or args.no_send):
        LOG.info("گزارش امروز (%s) قبلاً ارسال شده — این نوبت رد شد.", today)
        return 0

    LOG.info("── collecting ───────────────────────────────")
    ops = collect(cfg)
    LOG.info("collected %s unique opportunities", len(ops))

    LOG.info("── filtering & ranking ──────────────────────")
    ranked = rank(ops, cfg)
    LOG.info("%s opportunities match your profile", len(ranked))

    store = Store()
    new = store.mark(ranked)
    new_uids = {o.uid for o in new}
    LOG.info("%s of them are new since the last run", len(new))

    shown = [o for o in ranked if o.uid in new_uids] if cfg["output"].get("only_new_in_email") else ranked
    shown = shown[: int(cfg["output"].get("max_rows_in_email", 60))]

    LOG.info("── Persian summaries ────────────────────────")
    add_persian(shown, cfg)

    html_doc = R.build_html(shown, new_uids, cfg)
    md = R.build_markdown(shown, new_uids)

    os.makedirs("reports", exist_ok=True)
    html_path = os.path.join("reports", f"phd-radar-{today}.html")
    csv_path = os.path.join("reports", f"phd-radar-{today}.csv")
    md_path = os.path.join("reports", f"phd-radar-{today}.md")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(f"# PhD Radar — {today}\n\n{md}\n")
    R.write_csv(shown, csv_path)
    R.write_json(shown, os.path.join("reports", "latest.json"))
    shutil.copyfile(html_path, os.path.join("reports", "latest.html"))
    shutil.copyfile(csv_path, os.path.join("reports", "latest.csv"))

    if cfg["delivery"].get("pages", {}).get("enabled"):
        out = cfg["delivery"]["pages"].get("output_dir", "docs")
        os.makedirs(out, exist_ok=True)
        shutil.copyfile(html_path, os.path.join(out, "index.html"))
        shutil.copyfile(csv_path, os.path.join(out, "latest.csv"))

    prune_reports("reports", int(cfg["output"].get("keep_days", 60)))

    print("\n" + "=" * 78)
    print(f"TOP MATCHES — {today}   ({len(ranked)} total, {len(new)} new)")
    print("=" * 78)
    for i, op in enumerate(shown[:20], 1):
        print(f"{i:>2}. {fmt_eur(op.amount_eur_year):>10}/yr  [{op.country or '—':<12}] "
              f"{op.title[:64]}\n     {op.url}")
    print("=" * 78 + f"\nHTML : {html_path}\nCSV  : {csv_path}\n")

    if not args.no_send and not (
            cfg["delivery"]["telegram"].get("skip_if_empty") and not shown):
        subject = (f"{cfg['delivery']['email'].get('subject_prefix','[PhD Radar]')} "
                   f"{len(shown)} opportunities · {len(new)} new · {today}")
        send_email(cfg, subject, html_doc, attachments=[csv_path, html_path])
        send_telegram(cfg, shown, new_uids, html_path,
                      header=f"<b>📡 PhD Radar — {today}</b>\n"
                             f"{len(ranked)} مورد مناسب · {len(new)} تازه · مرتب بر اساس مبلغ سالانه")

    if not args.no_send:
        _stamp_today()

    if not args.dry_run:
        store.prune()
        store.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
