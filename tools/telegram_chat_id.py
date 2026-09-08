#!/usr/bin/env python3
"""
کمک‌ابزار تلگرام — chat_id را پیدا می‌کند.

۱) در تلگرام به @BotFather پیام بده → /newbot → یک اسم و یوزرنیم بده → توکن را کپی کن
۲) به ربات خودت در تلگرام /start بزن (یا ربات را ادمین کانالت کن و یک پیام در کانال بگذار)
۳) این را اجرا کن:

    TELEGRAM_BOT_TOKEN=123456:ABC...  python tools/telegram_chat_id.py

خروجی، chat_id هایی است که باید در Secrets گیت‌هاب بگذاری.
"""
import json
import os
import sys
import urllib.request

token = os.getenv("TELEGRAM_BOT_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not token:
    sys.exit("TELEGRAM_BOT_TOKEN را ست کن یا به عنوان آرگومان بده.")

with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30) as r:
    data = json.load(r)

if not data.get("ok"):
    sys.exit(f"خطا: {data}")

seen = {}
for upd in data.get("result", []):
    for key in ("message", "channel_post", "my_chat_member", "edited_message"):
        chat = (upd.get(key) or {}).get("chat")
        if chat:
            seen[chat["id"]] = f'{chat.get("type")} · {chat.get("title") or chat.get("username") or chat.get("first_name")}'

if not seen:
    print("چیزی پیدا نشد. یک پیام به ربات بده (یا ربات را ادمین کانال کن و در کانال پیام بگذار) و دوباره اجرا کن.")
for cid, desc in seen.items():
    print(f"TELEGRAM_CHAT_ID = {cid}    ({desc})")
