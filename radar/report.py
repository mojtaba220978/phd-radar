"""Build the HTML / CSV / Markdown / JSON deliverables.

The HTML report is fully self-contained — no external fonts, scripts or images —
so it looks identical in an e-mail client, in Telegram's in-app browser, on
GitHub Pages and offline on a laptop.
"""
from __future__ import annotations

import csv
import html
import json
import os
from datetime import date, datetime

from .brief import facts_fa
from .util import Opportunity, fmt_eur, fmt_range_eur, parse_date

FLAGS = {
    "Netherlands": "🇳🇱", "Germany": "🇩🇪", "Belgium": "🇧🇪", "Denmark": "🇩🇰",
    "Sweden": "🇸🇪", "Norway": "🇳🇴", "Finland": "🇫🇮", "Austria": "🇦🇹",
    "Switzerland": "🇨🇭", "Ireland": "🇮🇪", "France": "🇫🇷", "Spain": "🇪🇸",
    "Italy": "🇮🇹", "Portugal": "🇵🇹", "Poland": "🇵🇱", "Czechia": "🇨🇿",
    "Czech Republic": "🇨🇿", "Luxembourg": "🇱🇺", "Iceland": "🇮🇸",
    "Estonia": "🇪🇪", "Slovenia": "🇸🇮", "United Kingdom": "🇬🇧",
}
MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}

COUNTRY_FA = {
    "Netherlands": "هلند", "Germany": "آلمان", "Belgium": "بلژیک", "Denmark": "دانمارک",
    "Sweden": "سوئد", "Norway": "نروژ", "Finland": "فنلاند", "Austria": "اتریش",
    "Switzerland": "سوئیس", "Ireland": "ایرلند", "France": "فرانسه", "Spain": "اسپانیا",
    "Italy": "ایتالیا", "Portugal": "پرتغال", "Poland": "لهستان", "Czechia": "چک",
    "Czech Republic": "چک", "Luxembourg": "لوکزامبورگ", "Iceland": "ایسلند",
    "Estonia": "استونی", "Slovenia": "اسلوونی", "United Kingdom": "بریتانیا",
}

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_num(n) -> str:
    return str(n).translate(FA_DIGITS)


def country_fa(c: str) -> str:
    return COUNTRY_FA.get(c, c or "نامشخص")


def days_left(op: Opportunity):
    d = parse_date(op.deadline)
    return (d - date.today()).days if d else None


# --------------------------------------------------------------------------- #
#  styling
# --------------------------------------------------------------------------- #
CSS = """
:root{
  --bg:#eef2f7; --bg2:#e4ebf3; --card:#fff; --ink:#14212e; --muted:#68788a;
  --brand:#0a4a67; --brand2:#0e86ad; --mint:#0d8a5f; --gold:#c98a12;
  --line:#e4ebf1; --rose:#c8103a;
  --sh:0 1px 3px rgba(14,40,64,.06),0 6px 20px rgba(14,40,64,.06);
  --sh2:0 8px 30px rgba(14,40,64,.14);
}
@media (prefers-color-scheme:dark){
  :root{--bg:#0f1720;--bg2:#131c26;--card:#182430;--ink:#e6edf4;--muted:#93a4b5;
        --line:#243444;--sh:0 1px 3px rgba(0,0,0,.4);--sh2:0 10px 34px rgba(0,0,0,.55);}
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:linear-gradient(180deg,var(--bg) 0%,var(--bg2) 100%);
  background-attachment:fixed;color:var(--ink);line-height:1.8;
  font-family:'Segoe UI',Tahoma,'Iranian Sans','Vazirmatn',system-ui,Arial,sans-serif;
  font-feature-settings:"ss01","kern";}
.wrap{max-width:1100px;margin:0 auto;padding:18px 16px 80px}
.rtl{direction:rtl;text-align:right}.ltr{direction:ltr;text-align:left}

/* ---------------- hero ---------------- */
.hero{position:relative;overflow:hidden;border-radius:24px;padding:34px 34px 30px;color:#fff;
  background:linear-gradient(125deg,#06364c 0%,#0a4a67 42%,#0e86ad 100%);box-shadow:var(--sh2)}
.hero::before{content:"";position:absolute;top:-140px;inset-inline-start:-90px;width:340px;height:340px;
  border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.16),transparent 68%)}
.hero::after{content:"";position:absolute;bottom:-170px;inset-inline-end:-70px;width:400px;height:400px;
  border-radius:50%;background:radial-gradient(circle,rgba(90,220,255,.16),transparent 68%)}
.hero>*{position:relative;z-index:1}
.eyebrow{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.16);
  border:1px solid rgba(255,255,255,.24);border-radius:30px;padding:5px 15px;font-size:12.5px;
  letter-spacing:.3px;backdrop-filter:blur(4px)}
.hero h1{margin:12px 0 8px;font-size:29px;font-weight:800;letter-spacing:-.4px;line-height:1.4}
.hero p{margin:3px 0;font-size:14.5px;opacity:.93}

/* ---------------- stats ---------------- */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px;margin:16px 0 6px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:15px 17px;
  box-shadow:var(--sh);transition:transform .18s ease,box-shadow .18s ease}
.stat:hover{transform:translateY(-3px);box-shadow:var(--sh2)}
.stat b{display:block;font-size:24px;font-weight:800;line-height:1.35;
  background:linear-gradient(90deg,var(--brand2),var(--brand));-webkit-background-clip:text;
  background-clip:text;color:transparent}
.stat.gold b{background:linear-gradient(90deg,#e0a415,#b8760a);-webkit-background-clip:text;background-clip:text}
.stat.rose b{background:linear-gradient(90deg,#e0446a,#b30b31);-webkit-background-clip:text;background-clip:text}
.stat span{font-size:12px;color:var(--muted)}

/* ---------------- toolbar ---------------- */
.toolbar{position:sticky;top:0;z-index:30;margin:14px 0 6px;padding:12px;border-radius:16px;
  background:color-mix(in srgb,var(--card) 88%,transparent);backdrop-filter:blur(14px) saturate(1.4);
  border:1px solid var(--line);box-shadow:var(--sh);
  display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.search{position:relative;flex:1 1 240px;min-width:190px}
.search input{width:100%;padding:11px 42px 11px 14px;border-radius:12px;border:1px solid var(--line);
  font-size:14px;font-family:inherit;background:var(--bg);color:var(--ink);transition:.16s}
.search input:focus{outline:none;border-color:var(--brand2);box-shadow:0 0 0 3px rgba(14,134,173,.16)}
.search .ico{position:absolute;inset-inline-end:14px;top:50%;transform:translateY(-50%);
  color:var(--muted);font-size:15px;pointer-events:none}
.chip{border:1px solid var(--line);background:var(--card);color:var(--brand);border-radius:24px;
  padding:8px 15px;font-size:13px;cursor:pointer;font-family:inherit;transition:.16s;white-space:nowrap}
.chip:hover{border-color:var(--brand2);transform:translateY(-1px)}
.chip.on{background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;border-color:transparent;
  box-shadow:0 3px 10px rgba(10,74,103,.3)}
@media (prefers-color-scheme:dark){.chip{color:#7fd4f0}}
.count{font-size:12.5px;color:var(--muted);margin-inline-start:auto;padding-inline-end:4px}

/* ---------------- cards ---------------- */
.list{display:flex;flex-direction:column;gap:15px;margin-top:12px}
.item{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;
  box-shadow:var(--sh);transition:transform .18s ease,box-shadow .18s ease,border-color .18s;
  animation:rise .45s cubic-bezier(.2,.7,.3,1) backwards}
.item:hover{transform:translateY(-3px);box-shadow:var(--sh2);border-color:#cfe0ea}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.item.top1{border-color:#e8c569;box-shadow:0 0 0 1px #e8c569,0 8px 26px rgba(200,150,20,.2)}
.item.top2{border-color:#c9d2d9}.item.top3{border-color:#dcb491}
.bar{display:flex;align-items:center;gap:12px;padding:12px 18px;flex-wrap:wrap;
  background:linear-gradient(90deg,rgba(14,134,173,.07),transparent);border-bottom:1px solid var(--line)}
.rank{font-weight:800;color:var(--muted);font-size:16px;min-width:28px;text-align:center}
.amount{font-weight:800;color:var(--mint);font-size:17px;white-space:nowrap;line-height:1.25}
.amount small{display:block;font-weight:500;font-size:10.5px;color:var(--muted);line-height:1.35}
.amount.alt{color:var(--brand2);font-size:14.5px}
.amount.unk{color:var(--muted);font-weight:600;font-size:14px}
.bar .amount+.amount{padding-inline-start:13px;border-inline-start:1px solid var(--line)}
.spacer{flex:1}
.body{padding:15px 19px 17px}
.title{display:block;color:var(--brand);font-weight:700;font-size:17px;text-decoration:none;line-height:1.55}
@media (prefers-color-scheme:dark){.title{color:#7fd4f0}.item:hover{border-color:#31485c}}
.title:hover{color:var(--brand2);text-decoration:underline;text-underline-offset:3px}
.meta{color:var(--muted);font-size:13px;margin-top:6px}

/* funding strength bar */
.gauge{height:5px;border-radius:99px;background:var(--line);overflow:hidden;margin:11px 0 3px}
.gauge i{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--mint),#4ec99a);animation:grow .8s cubic-bezier(.2,.8,.3,1) backwards}
@keyframes grow{from{width:0 !important}}

.fa{direction:rtl;text-align:right;background:linear-gradient(180deg,rgba(14,134,173,.07),rgba(14,134,173,.03));
  border-inline-start:3px solid var(--brand2);border-radius:12px;padding:11px 15px;margin-top:12px;
  font-size:14.2px;line-height:2.05}
.fa .lbl,.en .lbl{display:block;font-size:10.5px;font-weight:800;letter-spacing:.5px;margin-bottom:3px;
  text-transform:uppercase}
.fa .lbl{color:var(--brand2)}
.en{direction:ltr;text-align:left;background:rgba(130,150,170,.07);border-inline-start:3px solid #b6c4d0;
  border-radius:12px;padding:10px 15px;margin-top:9px;font-size:13px;color:var(--muted);line-height:1.72}
.en .lbl{color:#93a6b5}
details.en-wrap{margin-top:9px}
details.en-wrap>summary{cursor:pointer;font-size:12px;color:var(--muted);list-style:none;
  padding:5px 0;user-select:none;transition:.15s}
details.en-wrap>summary:hover{color:var(--brand2)}
details.en-wrap>summary::-webkit-details-marker{display:none}
details.en-wrap[open]>summary{color:var(--brand2)}

.kw{margin-top:11px;display:flex;flex-wrap:wrap;gap:6px}
.tag{background:rgba(14,134,173,.09);color:var(--brand);border-radius:24px;padding:3px 11px;font-size:11px}
@media (prefers-color-scheme:dark){.tag{color:#8ccfe6}}
.badges{margin-top:11px;display:flex;flex-wrap:wrap;gap:6px}
.badge{display:inline-flex;align-items:center;gap:4px;border-radius:24px;padding:4px 11px;
  font-size:11.5px;font-weight:700}
.b-src{background:rgba(90,70,200,.13);color:#5442b8}
.b-nl{background:rgba(200,16,58,.12);color:var(--rose)}
.b-eu{background:rgba(28,79,143,.12);color:#1c4f8f}
.b-new{background:rgba(230,160,20,.16);color:#9a6200}
.b-grant{background:rgba(13,138,95,.13);color:var(--mint)}
@media (prefers-color-scheme:dark){
  .b-src{color:#b3a6ff}.b-nl{color:#ff8fa6}.b-eu{color:#8cbdf0}.b-new{color:#f0c060}.b-grant{color:#5fd6a6}
}
.dl{font-size:12.5px;color:var(--brand);background:rgba(14,134,173,.09);border-radius:10px;
  padding:4px 12px;white-space:nowrap;font-weight:600}
.dl.soon{background:rgba(200,16,58,.11);color:var(--rose)}
.dl.warn{background:rgba(230,160,20,.15);color:#9a6200}
@media (prefers-color-scheme:dark){.dl{color:#8ccfe6}.dl.soon{color:#ff8fa6}.dl.warn{color:#f0c060}}
.actions{margin-top:14px;display:flex;gap:9px;flex-wrap:wrap;align-items:center}
.btn{display:inline-flex;align-items:center;gap:6px;background:linear-gradient(135deg,var(--brand),var(--brand2));
  color:#fff;text-decoration:none;border-radius:12px;padding:9px 19px;font-size:13.5px;font-weight:700;
  box-shadow:0 3px 10px rgba(10,74,103,.26);transition:.16s;border:none;cursor:pointer;font-family:inherit}
.btn:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(10,74,103,.34)}
.btn.ghost{background:var(--card);color:var(--brand);border:1px solid var(--line);box-shadow:none}
.btn.ghost:hover{border-color:var(--brand2)}
@media (prefers-color-scheme:dark){.btn.ghost{color:#7fd4f0}}

.empty{background:var(--card);border:1px dashed var(--line);border-radius:18px;padding:44px 24px;
  text-align:center;color:var(--muted)}
.empty .big{font-size:38px;display:block;margin-bottom:8px}
footer{margin-top:32px;padding:20px;background:var(--card);border:1px solid var(--line);
  border-radius:18px;color:var(--muted);font-size:12.3px;text-align:center;line-height:2.1}
footer b{color:var(--brand)}
@media (prefers-color-scheme:dark){footer b{color:#7fd4f0}}
.top-btn{position:fixed;inset-inline-end:18px;bottom:18px;width:46px;height:46px;border-radius:50%;
  background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;border:none;cursor:pointer;
  font-size:19px;box-shadow:var(--sh2);opacity:0;pointer-events:none;transition:.25s;z-index:40}
.top-btn.show{opacity:1;pointer-events:auto}
@media (max-width:620px){
  .hero{padding:24px 20px}.hero h1{font-size:22px}.wrap{padding:12px 10px 60px}
  .title{font-size:15.5px}.bar{gap:8px;padding:11px 14px}.body{padding:13px 15px 15px}
  .amount{font-size:15.5px}.amount.alt{font-size:13px}
}
@media print{
  body{background:#fff}.toolbar,.actions,.top-btn{display:none}
  .item{break-inside:avoid;box-shadow:none;border:1px solid #ccc;animation:none}
  .hero{background:#0a4a67 !important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}}
"""

JS = """
(function(){
 var items=[].slice.call(document.querySelectorAll('.item'));
 var q=document.getElementById('q'),cnt=document.getElementById('cnt'),
     empty=document.getElementById('empty'),list=document.getElementById('list'),
     top=document.getElementById('topbtn');
 var f={country:'',kind:'',fresh:false},sortBy='amount';
 function norm(s){return (s||'').toLowerCase().replace(/[\\u064A]/g,'\\u06CC').replace(/[\\u0643]/g,'\\u06A9');}
 function apply(){
   var t=norm(q.value.trim()),n=0;
   items.forEach(function(el){
     var ok=(!t||norm(el.dataset.search).indexOf(t)>-1)
       &&(!f.country||el.dataset.country===f.country)
       &&(!f.kind||el.dataset.kind===f.kind)
       &&(!f.fresh||el.dataset.new==='1');
     el.style.display=ok?'':'none';if(ok)n++;
   });
   cnt.textContent=n===items.length?(n+' مورد'):(n+' از '+items.length+' مورد');
   empty.style.display=n?'none':'';
 }
 function sortItems(){
   var vis=items.slice();
   vis.sort(function(a,b){
     if(sortBy==='amount')return (+b.dataset.amount)-(+a.dataset.amount);
     if(sortBy==='deadline'){
       var da=+a.dataset.days,db=+b.dataset.days;
       if(da<0)da=99999;if(db<0)db=99999;return da-db;}
     return (+b.dataset.score)-(+a.dataset.score);
   });
   vis.forEach(function(el,i){list.appendChild(el);
     var r=el.querySelector('.rank');
     if(r&&!r.dataset.fixed)r.textContent=(i<3&&sortBy==='amount')?['🥇','🥈','🥉'][i]:('#'+(i+1));});
 }
 q.addEventListener('input',apply);
 [].forEach.call(document.querySelectorAll('.chip'),function(c){
   c.addEventListener('click',function(){
     var k=c.dataset.k,v=c.dataset.v,was=c.classList.contains('on');
     [].forEach.call(document.querySelectorAll('.chip[data-k="'+k+'"]'),function(x){x.classList.remove('on');});
     if(k==='sort'){sortBy=v;c.classList.add('on');sortItems();apply();return;}
     if(k==='fresh'){f.fresh=!was;if(!was)c.classList.add('on');}
     else{f[k]=was?'':v;if(!was)c.classList.add('on');}
     apply();
   });
 });
 window.addEventListener('scroll',function(){top.classList.toggle('show',window.scrollY>500);});
 top.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'});});
 apply();
})();
"""

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='7' fill='%230a4a67'/%3E%3Ctext x='16' y='23' "
           "font-size='19' text-anchor='middle'%3E%F0%9F%93%A1%3C/text%3E%3C/svg%3E")


def _deadline_chip(op: Opportunity) -> str:
    if not op.deadline:
        return '<span class="dl" style="opacity:.6">🗓 مهلت اعلام نشده</span>'
    d = days_left(op)
    txt = html.escape(op.deadline.split(" - ")[0].strip())
    if d is None:
        return f'<span class="dl">🗓 {txt}</span>'
    if d < 0:
        return f'<span class="dl" style="opacity:.55">🗓 {txt}</span>'
    if d <= 7:
        return f'<span class="dl soon">🔥 {txt} · {fa_num(d)} روز مانده</span>'
    if d <= 21:
        return f'<span class="dl warn">⏳ {txt} · {fa_num(d)} روز مانده</span>'
    return f'<span class="dl">🗓 {txt} · {fa_num(d)} روز</span>'


def _money_html(op: Opportunity) -> str:
    """Salary/grant block: monthly range + honest yearly range."""
    if op.salary_min_month or op.salary_max_month:
        monthly = fmt_range_eur(op.salary_min_month, op.salary_max_month, isolate=True)
        yearly = fmt_range_eur(op.amount_eur_year, op.amount_max_eur_year, isolate=True)
        fte = f" · {fa_num(f'{op.fte*38:.0f}')} ساعت/هفته" if op.fte and op.fte < 0.999 else ""
        return (f'<span class="amount">{monthly}<small>ناخالص در ماه</small></span>'
                f'<span class="amount alt">{yearly}<small>ناخالص در سال{fte}</small></span>')
    if op.amount_eur_year:
        note = html.escape(op.amount_note[:44]) or "تخمین از متن آگهی"
        return (f'<span class="amount">{fmt_eur(op.amount_eur_year, isolate=True)}'
                f'<small>{note} · در سال</small></span>')
    return '<span class="amount unk">💬 مبلغ در آگهی ذکر نشده</span>'


def _item_html(i: int, op: Opportunity, is_new: bool, max_amount: float) -> str:
    flag = FLAGS.get(op.country, "🌍")
    badges = [f'<span class="badge b-src">{html.escape(op.source)}</span>']
    if op.country:
        cls = "b-nl" if op.country == "Netherlands" else "b-eu"
        badges.append(f'<span class="badge {cls}">{flag} {html.escape(country_fa(op.country))}</span>')
    if op.kind in ("funding", "call"):
        badges.append('<span class="badge b-grant">💰 گرنت</span>')
    if is_new:
        badges.append('<span class="badge b-new">🆕 جدید</span>')

    fa = (html.escape(op.summary_fa) if op.summary_fa
          else '<i style="opacity:.7">خلاصه در دسترس نبود — متن اصلی: </i>' + html.escape(op.summary[:240]))
    en_block = (f'<details class="en-wrap"><summary>🇬🇧 نمایش متن اصلی انگلیسی</summary>'
                f'<div class="en"><span class="lbl">Original summary</span>'
                f'{html.escape(op.summary_en)}</div></details>') if op.summary_en else ""
    kw = "".join(f'<span class="tag">{html.escape(k)}</span>' for k in op.matched[:6])
    search_blob = html.escape(" ".join([op.title, op.organisation, op.country, op.city,
                                        country_fa(op.country), op.summary_fa, op.summary_en,
                                        op.summary, " ".join(op.matched)]).lower())
    pct = int(min(100, (op.amount_eur_year / max_amount * 100))) if (max_amount and op.amount_eur_year) else 0
    gauge = (f'<div class="gauge" title="نسبت به بالاترین مبلغ این گزارش">'
             f'<i style="width:{pct}%"></i></div>') if pct else ""
    d = days_left(op)
    top_cls = f" top{i}" if i <= 3 else ""

    return f"""
  <article class="item{top_cls}" data-country="{html.escape(op.country)}"
           data-kind="{html.escape(op.kind)}" data-new="{'1' if is_new else '0'}"
           data-amount="{op.amount_eur_year:.0f}" data-score="{op.score:.0f}"
           data-days="{d if d is not None else -1}" data-search="{search_blob}"
           style="animation-delay:{min(i * 45, 500)}ms">
    <div class="bar">
      <span class="rank">{MEDAL.get(i, f'#{i}')}</span>
      {_money_html(op)}
      <span class="spacer"></span>
      {_deadline_chip(op)}
    </div>
    <div class="body">
      <a class="title ltr" href="{html.escape(op.url)}" target="_blank" rel="noopener">{html.escape(op.title)}</a>
      <div class="meta rtl">{html.escape(facts_fa(op))}</div>
      {f'<div class="meta ltr" style="font-size:12.3px">💶 {html.escape(op.salary_text)}</div>' if op.salary_text else ''}
      {gauge}
      <div class="fa"><span class="lbl">📝 خلاصه فارسی</span>{fa}</div>
      {en_block}
      <div class="kw">{kw}</div>
      <div class="badges">{''.join(badges)}</div>
      <div class="actions">
        <a class="btn" href="{html.escape(op.url)}" target="_blank" rel="noopener">مشاهده و درخواست ↗</a>
      </div>
    </div>
  </article>"""


def build_html(ops: list[Opportunity], new_uids: set[str], cfg: dict, *, title_note: str = "") -> str:
    today = date.today().isoformat()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    nl = sum(1 for o in ops if o.country == "Netherlands")
    funded = [o.amount_eur_year for o in ops if o.amount_eur_year]
    top_amount = max(funded) if funded else 0.0
    soon = sum(1 for o in ops if (d := days_left(o)) is not None and 0 <= d <= 21)
    countries = sorted({o.country for o in ops if o.country},
                       key=lambda c: (c != "Netherlands", c))

    chips = ['<button class="chip on" data-k="sort" data-v="amount">💶 بیشترین مبلغ</button>',
             '<button class="chip" data-k="sort" data-v="deadline">⏳ نزدیک‌ترین مهلت</button>',
             '<button class="chip" data-k="sort" data-v="score">🎯 بیشترین تطابق</button>',
             '<button class="chip" data-k="fresh" data-v="1">🆕 فقط جدیدها</button>']
    if any(o.kind in ("funding", "call") for o in ops):
        chips.append('<button class="chip" data-k="kind" data-v="funding">💰 فقط گرنت‌ها</button>')
    for c in countries[:7]:
        chips.append(f'<button class="chip" data-k="country" data-v="{html.escape(c)}">'
                     f'{FLAGS.get(c,"🌍")} {html.escape(country_fa(c))}</button>')

    cards = "".join(_item_html(i, op, op.uid in new_uids, top_amount)
                    for i, op in enumerate(ops, 1))

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="موقعیت‌های دکترا و گرنت روانشناسی بالینی و علوم اعصاب شناختی در هلند و اروپا">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="{FAVICON}">
<title>📡 رادار دکترا — {today}</title><style>{CSS}</style></head>
<body><div class="wrap">

  <header class="hero rtl">
    <span class="eyebrow">📡 گزارش خودکار روزانه · {fa_num(today)}</span>
    <h1>موقعیت‌های دکترا و گرنت در اروپا</h1>
    <p>روانشناسی بالینی · علوم اعصاب شناختی — 🇳🇱 هلند در اولویت، پوشش سراسر اروپا</p>
    <p>مرتب‌شده بر اساس مبلغ حقوق/گرنت · هر مورد با خلاصهٔ فارسی و انگلیسی</p>
    {f'<p>{html.escape(title_note)}</p>' if title_note else ''}
  </header>

  <div class="stats rtl">
    <div class="stat"><b>{fa_num(len(ops))}</b><span>موقعیت مناسب</span></div>
    <div class="stat gold"><b>{fa_num(len(new_uids))}</b><span>جدید نسبت به دیروز</span></div>
    <div class="stat"><b>{fa_num(nl)}</b><span>در هلند 🇳🇱</span></div>
    <div class="stat rose"><b>{fa_num(soon)}</b><span>مهلت کمتر از ۳ هفته</span></div>
    <div class="stat"><b>{fmt_eur(top_amount)}</b><span>بالاترین مبلغ سالانه</span></div>
  </div>

  <nav class="toolbar rtl">
    <label class="search"><span class="ico">🔎</span>
      <input type="search" id="q" placeholder="جستجو در عنوان، دانشگاه، شهر یا خلاصه…"
             aria-label="جستجو"></label>
    {''.join(chips)}
    <span class="count" id="cnt"></span>
  </nav>

  <main class="list" id="list">{cards}</main>
  <div class="empty rtl" id="empty" style="display:none">
    <span class="big">🔍</span>موردی با این فیلترها پیدا نشد — عبارت جستجو را کوتاه‌تر کن یا فیلترها را بردار.
  </div>

  <footer class="rtl">
    <b>📡 PhD Radar</b> — ساخته‌شده در {fa_num(stamp)}<br>
    منابع: AcademicTransfer · EURAXESS · NWO · فیدهای دلخواه<br>
    مبالغ به‌صورت خودکار از متن آگهی استخراج و به یورو در سال تبدیل شده‌اند؛
    برای موقعیت‌های هلندی، رتبه‌بندی بر اساس <b>کف بازهٔ حقوق</b> است.<br>
    خلاصه‌ها با هوش مصنوعی تولید شده‌اند — پیش از اقدام، حتماً صفحهٔ اصلی آگهی را بخوانید.
  </footer>
</div>
<button class="top-btn" id="topbtn" aria-label="بازگشت به بالا">↑</button>
<script>{JS}</script>
</body></html>"""


# --------------------------------------------------------------------------- #
#  Markdown + CSV + JSON
# --------------------------------------------------------------------------- #
def build_markdown(ops: list[Opportunity], new_uids: set[str], limit: int = 40) -> str:
    lines = ["| # | عنوان | مبلغ سالانه | کشور | مهلت | خلاصه فارسی | لینک |",
             "|---|---|---|---|---|---|---|"]
    for i, op in enumerate(ops[:limit], 1):
        tag = " 🆕" if op.uid in new_uids else ""
        fa = (op.summary_fa or op.summary)[:120].replace("|", "/").replace("\n", " ")
        amount = (fmt_range_eur(op.amount_eur_year, op.amount_max_eur_year)
                  if op.amount_max_eur_year else fmt_eur(op.amount_eur_year))
        lines.append(
            f"| {i} | {op.title.replace('|','/')[:65]}{tag} | {amount} "
            f"| {country_fa(op.country)} | {op.deadline or '—'} | {fa} | [باز کردن]({op.url}) |")
    return "\n".join(lines)


def write_csv(ops: list[Opportunity], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cols = ["rank", "title", "summary_fa", "summary_en", "url", "amount_eur_year",
            "amount_max_eur_year", "salary_min_month", "salary_max_month", "fte",
            "amount_note", "source", "kind", "organisation", "country", "city",
            "deadline", "posted", "field", "salary_text", "score", "matched",
            "summary", "first_seen"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for i, op in enumerate(ops, 1):
            d = op.as_dict()
            d["rank"] = i
            w.writerow(d)


def write_json(ops: list[Opportunity], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([op.as_dict() for op in ops], fh, ensure_ascii=False, indent=1)
