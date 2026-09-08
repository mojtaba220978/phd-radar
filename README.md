# 📡 PhD Radar — رادار روزانه‌ی موقعیت‌های دکترا و گرنت در اروپا

ابزاری که **هر روز صبح** سایت‌های اصلی موقعیت‌های دکترا و گرنت اروپا را می‌گردد،
آگهی‌های مرتبط با **روانشناسی بالینی و علوم اعصاب شناختی** را جدا می‌کند،
برای هرکدام یک **خلاصهٔ فارسی خودکار** می‌نویسد،
آن‌ها را **بر اساس مبلغ گرنت/حقوق سالانه مرتب** می‌کند و در قالب کارت‌های خوانا
به کانال تلگرام و/یا ایمیل تو می‌فرستد.

> اولویت جغرافیایی: **هلند** (برچسب 🇳🇱 و ۲۰ امتیاز اضافه) — ولی کل اروپا هم پوشش داده می‌شود.

---

## ۱) منابعی که چک می‌شوند

| منبع | چه چیزی | چطور خوانده می‌شود | مبلغ دارد؟ |
|---|---|---|---|
| **AcademicTransfer** (academictransfer.com) | تقریباً تمام موقعیت‌های دکترا/پست‌داک دانشگاه‌های هلند | همان API عمومی JSON که خود سایتشان استفاده می‌کند (توکن به‌صورت خودکار از صفحه برداشته می‌شود) | ✅ حقوق ماهانه دقیق |
| **EURAXESS – Jobs** (euraxess.ec.europa.eu) | آگهی‌های پژوهشی کل اروپا | خزیدن روی صفحات جستجو + باز کردن صفحه‌ی جزئیاتِ فقط آگهی‌های منتخب | 🔸 اگر در متن ذکر شده باشد |
| **EURAXESS – Funding** | گرنت‌ها، فلوشیپ‌ها و بورس‌ها | خزیدن روی `funding/search` | 🔸 |
| **NWO** (nwo.nl/en/calls) | فراخوان‌های گرنت شورای پژوهش هلند | خزیدن روی صفحات calls + صفحه‌ی هر فراخوان | 🔸 بودجه‌ی پروژه |
| **RSS دلخواه** | هر فیدی که خودت اضافه کنی (پیش‌فرض: فید رسمی EURAXESS) | RSS/Atom | 🔸 |

چند نکته که موقع ساخت کشف شد و توی کد لحاظ شده:
* `studyinnl.org` پایگاه‌دادهٔ بورس‌هایش دیگر آدرس ثابت/عمومی ندارد؛ برای دکترا در هلند
  عملاً **PhD یک شغل با حقوق است** و از طریق AcademicTransfer منتشر می‌شود — به همین دلیل
  آن سایت جای خود را به منابع بالا داده. (اگر خواستی، هر URL دیگری را در `extra_rss` اضافه کن.)
* `findaphd.com` پشت Cloudflare است و اسکرپ نمی‌شود؛ عمداً حذف شده تا اجرای روزانه نشکند.

---

## ۲) نصب و اجرای دستی (روی لپ‌تاپ)

```bash
cd phd-radar
pip install -r requirements.txt

python main.py --no-send        # فقط گزارش بساز، چیزی نفرست
python main.py                  # بساز و ارسال کن (ایمیل/تلگرام)
```

خروجی‌ها:

```
reports/phd-radar-YYYY-MM-DD.html   ← جدول کامل و رنگی (همینو باز کن)
reports/phd-radar-YYYY-MM-DD.csv    ← برای اکسل
reports/phd-radar-YYYY-MM-DD.md     ← جدول مارک‌داون
reports/latest.html                 ← همیشه آخرین گزارش
docs/index.html                     ← نسخه‌ای که روی GitHub Pages منتشر می‌شود
data/seen.json                      ← حافظه: چه آگهی‌هایی را قبلاً دیده‌ای (برچسب 🆕)
```

آپشن‌های مفید:

```bash
python main.py --email you@gmail.com --email friend@x.com   # گیرنده‌ها را از خط فرمان بده
python main.py --min-score 35        # فیلتر شل‌تر (نتایج بیشتر)
python main.py --only-new            # فقط آگهی‌های جدید از آخرین اجرا
python main.py --dry-run             # حافظه‌ی seen.json را دست نزن
```

---

## ۳) اجرای خودکار روزانه با GitHub Actions (رایگان، بدون نیاز به روشن بودن لپ‌تاپ)

1. یک ریپوی **خصوصی** در گیت‌هاب بساز و کل پوشه‌ی `phd-radar` را داخلش پوش کن:

   ```bash
   cd phd-radar
   git init && git add . && git commit -m "PhD Radar"
   git branch -M main
   git remote add origin https://github.com/<username>/phd-radar.git
   git push -u origin main
   ```

2. در ریپو برو به **Settings ▸ Secrets and variables ▸ Actions ▸ New repository secret**
   و این‌ها را اضافه کن (هرکدام را که می‌خواهی):

   | Secret | مقدار | برای چه |
   |---|---|---|
   | `RECIPIENTS` | `you@gmail.com,friend@uni.nl` | گیرنده‌های ایمیل |
   | `SMTP_HOST` | `smtp.gmail.com` | سرور ایمیل |
   | `SMTP_PORT` | `587` | |
   | `SMTP_USER` | `you@gmail.com` | |
   | `SMTP_PASS` | App Password ۱۶ رقمی گوگل | **نه** رمز اصلی اکانت |
   | `SMTP_FROM` | `you@gmail.com` | |
   | `TELEGRAM_BOT_TOKEN` | توکن BotFather | ارسال تلگرامی |
   | `TELEGRAM_CHAT_ID` | مثلاً `-1001234567890` | آی‌دی کانال/چت |
   | `LLM_API_KEY` | کلید OpenRouter/Gemini/Groq | خلاصه‌نویسی هوش مصنوعی |

3. **Settings ▸ Pages ▸ Source = GitHub Actions** (اگر لینک همیشگی گزارش را می‌خواهی).

4. تب **Actions ▸ PhD Radar (daily) ▸ Run workflow** را بزن تا همین حالا یک بار اجرا شود.
   از این به بعد هر روز **۹ صبح به وقت تهران** خودکار اجرا می‌شود
   (زمان را در `.github/workflows/daily.yml` خط `cron` عوض کن).

---

## ۴) گزینه‌های ارسال — کدام را انتخاب کنم؟

من نمی‌توانم به‌جای تو حساب ایمیل بسازم یا مالکش شوم (نیاز به تأیید هویت/شماره دارد و امن هم نیست).
سه راه امن پیش رویت است:

**الف) تلگرام (ساده‌ترین، بدون ایمیل و بدون رمز حساس)**
1. در تلگرام به `@BotFather` پیام بده → `/newbot` → توکن را بگیر.
2. یک کانال بساز (private هم می‌شود) و ربات را **Admin** کن.
3. اجرا کن:
   ```bash
   TELEGRAM_BOT_TOKEN=<توکن> python tools/telegram_chat_id.py
   ```
   `chat_id` را بردار و در Secrets بگذار. تمام — جدول هر روز در کانالت می‌آید (+ فایل HTML کامل).

**ب) ایمیل با Gmail**
`myaccount.google.com/apppasswords` → یک App Password بساز → در `SMTP_PASS` بگذار.
(اکانت باید 2-Step Verification روشن داشته باشد.)

**ج) بدون هیچ رمزی**
`delivery.email.enabled: false` و `delivery.telegram.enabled: false` بگذار؛
گزارش هر روز روی **GitHub Pages** منتشر می‌شود:
`https://<username>.github.io/phd-radar/` و در Actions هم به‌صورت Artifact قابل دانلود است.

---

## ۴.۴) خلاصه‌نویسی با هوش مصنوعی

برای هر آگهی، یک مدل زبانی خلاصه‌ای می‌نویسد که **اجباراً** به این سه سؤال پاسخ می‌دهد:

1. **موضوع پژوهش** چیست (سؤال پژوهشی مشخص)
2. **روی چه کسانی** — جامعه/نمونه (بیماران PTSD، نوجوانان، سالمندان، داده‌های کوهورت…)؛
   اگر آگهی نگفته باشد، صریح می‌نویسد «مشخص نشده»
3. **با چه روشی** — RCT، fMRI/EEG، مطالعه طولی، مدل‌سازی محاسباتی و مدت پروژه

خروجی **دوزبانه** است: انگلیسی (اصل) + فارسی (ترجمه وفادار)، و هر دو در گزارش نمایش داده می‌شوند.

```yaml
llm:
  enabled: true
  provider: openrouter          # openrouter | groq | gemini | deepseek | mistral
  model: "minimax/minimax-m3:free"
  fallback_models:              # اگر مدل اصلی از دسترس خارج شد
    - "minimax/minimax-m2.7:free"
    - "nvidia/nemotron-3-super-120b-a12b:free"
  api_key_env: LLM_API_KEY
  workers: 3
```

* کلید را در Secret به نام `LLM_API_KEY` بگذار.
* خلاصه‌ها در `data/summaries.json` کش می‌شوند → هر آگهی فقط یک‌بار به مدل فرستاده می‌شود
  (اجرای روزانه معمولاً کمتر از ۲۰ درخواست).
* اگر کلید نباشد یا سرویس در دسترس نباشد، خودکار به روش قاعده‌محور + ترجمه ماشینی برمی‌گردد:

```yaml
translate:
  enabled: true
  language: fa
  max_chars: 420
  workers: 4
```

## ۴.۶) شکل پیام تلگرام

هر آگهی یک «کارت» جداست و بین کارت‌ها خط جداکننده گذاشته می‌شود:

```
🥇 💶 €81,903 در سال  🆕
PhD candidate 'Neuroplasticity of Brain Stimulation in Depression'
🏛 🇳🇱 هلند · Amsterdam · Amsterdam UMC
⏳ مهلت: 2026-09-23 — فقط ۱۷ روز مانده!
📝 ما به دنبال یک کاندیدای دکترای مشتاق هستیم تا …
🔗 مشاهده آگهی و درخواست
```

تنظیمات مربوطه:

```yaml
telegram:
  top_n: 12              # چند آگهی برتر در پیام بیاید
  items_per_message: 3   # چند کارت در هر پیام (کمتر = خواناتر)
  send_html_file: true   # فایل HTML کامل هم فرستاده شود
```

## ۵) شخصی‌سازی فیلترها (`config.yaml`)

```yaml
filters:
  min_score: 45            # پایین‌تر = نتایج بیشتر ولی نویز بیشتر
  include_postdoc: false   # true کن اگر پست‌داک هم می‌خواهی
  include_faculty: false   # true کن اگر Assistant Professor هم می‌خواهی
  topic_keywords:
    psycholog*: 8          # ستاره = هر پسوندی (psychology / psychologie / psychological)
    computational psychiatry: 9
  exclude_keywords: [...]  # هرچه در عنوان باشد، حذف می‌شود
geography:
  mode: priority           # priority | only | all
  priority_countries: [Netherlands]
```

منطق امتیازدهی (خلاصه):

```
امتیاز = (کلیدواژه در عنوان × ۲.۴) + (کلیدواژه در متن × ۰.۶، سقف‌دار)
        + ۳۰ اگر PhD باشد | ۱۶ اگر گرنت مناسب مقطع دکترا باشد
        + ۲۰ اگر هلند باشد + ۵ اگر مبلغ مشخص باشد
        ⇒ پست‌داک/هیئت‌علمی و آگهی‌هایی که فقط در متن پاورقی‌شان
          «mental health» دارند خودکار حذف می‌شوند.
```

## ۶) مرتب‌سازی بر اساس مبلغ چطور کار می‌کند؟

* **AcademicTransfer**: حقوق ماهانهٔ ناخالص × **۱۳٫۹۶** (۱۲ ماه + ۸٪ holiday allowance + ۸٫۳٪ پاداش پایان سال) × **کسر اشتغال** (مثلاً ۳۲ از ۳۸ ساعت) → یورو در سال.
  <br>⚠️ نکته مهم: AcademicTransfer معمولاً **کل بازهٔ اسکیل حقوقی کارفرما** را منتشر می‌کند (مثلاً €۳٬۲۱۷ تا €۵٬۸۶۷)
  که سقف آن ربطی به حقوق دکترا ندارد. برای همین **رتبه‌بندی بر اساس حقوق شروع (کف بازه)** انجام می‌شود
  و در گزارش، کل بازه به‌صورت شفاف نمایش داده می‌شود.
* **بقیهٔ منابع**: مبالغ از متن آگهی استخراج می‌شوند (`€ 2.901 per month`, `50,000 per annum`, `budget of €800,000`) و به یورو در سال نرمال می‌شوند؛ بودجهٔ کل پروژه تقسیم بر ۴ سال می‌شود. نرخ ارزها در `config.yaml ▸ money.fx_to_eur`.
* آگهی‌هایی که مبلغشان در متن نیامده، با `—` و در **انتهای** جدول می‌آیند (قابل تغییر با `unknown_amount_position`).

⚠️ مبالغ **تخمینی و خودکار** هستند؛ قبل از اقدام، همیشه صفحهٔ اصلی آگهی را چک کن.

---

## ۷) ساختار پروژه

```
phd-radar/
├── main.py                     # اجرا: جمع‌آوری → فیلتر → رتبه‌بندی → گزارش → ارسال
├── config.yaml                 # تمام تنظیمات (تنها فایلی که لازم است دست بزنی)
├── requirements.txt
├── radar/
│   ├── util.py                 # HTTP، پارس HTML، استخراج مبلغ، مدل داده
│   ├── llm.py                  # خلاصه‌نویسی دوزبانه با هوش مصنوعی + کش
│   ├── brief.py                # روش پشتیبان: انتخاب جملات مفید از متن آگهی
│   ├── translate.py            # روش پشتیبان: ترجمه ماشینی + کش
│   ├── scoring.py              # امتیازدهی و فیلتر جغرافیایی/موضوعی
│   ├── store.py                # حافظهٔ آگهی‌های دیده‌شده (برچسب 🆕)
│   ├── report.py               # ساخت HTML/CSV/Markdown
│   ├── notify.py               # ارسال ایمیل (SMTP) و تلگرام
│   └── sources/
│       ├── academictransfer.py
│       ├── euraxess.py
│       ├── nwo.py
│       └── rss.py              # هر فید دلخواهی
├── tools/telegram_chat_id.py
└── .github/workflows/daily.yml # اجرای روزانهٔ ۰۹:۰۰ تهران
```

## ۸) اضافه کردن منبع جدید

ساده‌ترین راه: در `config.yaml` زیر `sources.extra_rss.feeds` یک فید اضافه کن.
برای سایت بدون RSS: یک فایل در `radar/sources/` بساز که تابع
`fetch(cfg, money_cfg) -> list[Opportunity]` داشته باشد و آن را در لیست `steps` داخل
`main.py ▸ collect()` اضافه کن. بقیهٔ زنجیره (فیلتر، رتبه‌بندی، ایمیل) خودکار کار می‌کند.
