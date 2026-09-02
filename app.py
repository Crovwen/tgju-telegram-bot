# -*- coding: utf-8 -*-
"""
ربات تلگرامی قیمت طلا، سکه و ارز از tgju.org — نسخه‌ی مخصوص Render (Web Service رایگان)
==========================================================================================

چرا Flask؟
    پلن رایگان Render فقط از نوع سرویس "Web Service" پشتیبانی می‌کند، یعنی برنامه
    باید روی یک پورت HTTP گوش بدهد و به درخواست پاسخ دهد. به همین دلیل این نسخه
    یک سرور کوچک Flask دارد که فقط یک صفحه‌ی وضعیت نشان می‌دهد؛ کار اصلی
    (خواندن قیمت‌ها و ارسال به تلگرام) در یک Thread پس‌زمینه هر ۵ دقیقه اجرا می‌شود.

متغیرهای محیطی لازم (در پنل Render تنظیم می‌شوند، نه داخل کد):
    BOT_TOKEN   -> توکن ربات از @BotFather
    CHAT_ID     -> یوزرنیم کانال مثل @mychannel یا آیدی عددی مثل -1001234567890
    (اختیاری) FETCH_INTERVAL_SECONDS -> پیش‌فرض ۳۰۰ (۵ دقیقه)
    (اختیاری) SHOW_IN_TOMAN -> "true" یا "false" (پیش‌فرض true)

نکته‌ی خیلی مهم درباره‌ی پلن رایگان Render:
    سرویس‌های رایگان اگر مدتی (حدود ۱۵ دقیقه) هیچ درخواست HTTP دریافت نکنند
    به خواب می‌روند و کل پردازش (از جمله Thread پس‌زمینه) متوقف می‌شود.
    برای اینکه ربات ۲۴ ساعته بیدار بماند، باید یک سرویس رایگان مثل
    https://cron-job.org یا https://uptimerobot.com را روی آدرس
    اصلی سرویس (همان صفحه‌ی /) تنظیم کنید تا هر ۵ تا ۱۰ دقیقه یک‌بار
    درخواست بزند. جزئیات کامل در README.md آمده است.
"""

import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify

# =========================== تنظیمات (از Environment Variables) ===========================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
FETCH_INTERVAL_SECONDS = int(os.environ.get("FETCH_INTERVAL_SECONDS", "300"))
SHOW_IN_TOMAN = os.environ.get("SHOW_IN_TOMAN", "true").strip().lower() != "false"

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Gheymat_Moment")

TGJU_BASE = "https://www.tgju.org"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("tgju-bot")

# ============================ فهرست آیتم‌ها ============================

# هر آیتم: (برچسب فارسی, شناسه در tgju, ایموجی/پرچم)
CURRENCY_ITEMS = [
    ("دلار آمریکا", "price_dollar_rl", "🇺🇸"),
    ("یورو", "price_eur", "🇪🇺"),
    ("پوند انگلیس", "price_gbp", "🇬🇧"),
    ("لیر ترکیه", "price_try", "🇹🇷"),
    ("دلار استرالیا", "price_aud", "🇦🇺"),
    ("دلار سنگاپور", "price_sgd", "🇸🇬"),
    ("دلار کانادا", "price_cad", "🇨🇦"),
    ("درهم امارات", "price_aed", "🇦🇪"),
    ("دینار عراق", "price_iqd", "🇮🇶"),
    ("ریال قطر", "price_qar", "🇶🇦"),
    ("افغانی", "price_afn", "🇦🇫"),
    ("یوان چین", "price_cny", "🇨🇳"),
]

GOLD_ITEMS = [
    ("طلای ۱۸ عیار (هر گرم)", "geram18", "🥇"),
    ("طلای ۲۴ عیار (هر گرم)", "geram24", "🥇"),
    ("طلای دست دوم", "gold_mini_size", "🥇"),
    ("انس جهانی طلا", "ons", "🥇"),
    ("انس جهانی نقره", "silver", "🥈"),
    ("نقره داخلی (۹۹۹ - هر گرم)", "silver_999", "🥈"),
]

COIN_ITEMS = [
    ("سکه امامی (تمام سکه)", "sekee", "🪙"),
    ("نیم سکه", "nim", "🪙"),
    ("ربع سکه", "rob", "🪙"),
    ("حباب سکه امامی", "coin_blubber", "🫧"),
    ("حباب نیم سکه", "nim_blubber", "🫧"),
    ("حباب ربع سکه", "rob_blubber", "🫧"),
]

# وضعیت آخرین اجرا، برای نمایش در صفحه‌ی وب (health check)
STATUS = {
    "last_run_utc": None,
    "last_success": None,
    "last_error": None,
    "runs_count": 0,
}

# ============================== توابع کمکی ==============================


def fetch_soup(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:  # noqa: BLE001
        log.warning("خطا در دریافت %s: %s", url, exc)
        return None


def clean_number(text: str) -> str:
    return text.strip().replace("\u200c", "").replace("\xa0", "")


def to_toman(rial_text: str) -> str:
    digits = rial_text.replace(",", "").strip()
    try:
        value = int(digits)
        return f"{value // 10:,}"
    except ValueError:
        return rial_text


def get_price_from_homepage(soup, slug: str, is_rial: bool) -> str:
    if soup is None:
        return "خطا در دریافت"

    row = soup.find("tr", id=f"l-{slug}")
    if row is None:
        return "یافت نشد"

    cells = row.find_all("td")
    if len(cells) < 2:
        return "یافت نشد"

    price_text = clean_number(cells[1].get_text())
    if not price_text:
        return "یافت نشد"

    if is_rial and SHOW_IN_TOMAN:
        return to_toman(price_text)
    return price_text


def get_tether_price_usd():
    soup = fetch_soup(f"{TGJU_BASE}/profile/crypto-tether")
    if soup is None:
        return None

    price_span = soup.find(id="last-price-value") or soup.select_one(
        "span.info-price, .price-box .value, [data-col='info.last_trade.PDrCotVal']"
    )
    if price_span:
        return clean_number(price_span.get_text())

    home_soup = fetch_soup(TGJU_BASE)
    row = home_soup.find("tr", id="l-crypto-tether") if home_soup else None
    if row:
        cells = row.find_all("td")
        if len(cells) >= 2:
            return clean_number(cells[1].get_text())

    return None


# ============================== ساخت پیام ==============================


def quote(content: str) -> str:
    """هر خط را به‌صورت یک نقل‌قول (blockquote) جداگانه و بولد برمی‌گرداند."""
    return f"<blockquote><b>{content}</b></blockquote>"


def build_message() -> str:
    now = datetime.now(IRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    soup = fetch_soup(TGJU_BASE)

    lines = []
    lines.append("<b>📊 قیمت لحظه‌ای طلا، سکه و ارز</b>")
    lines.append(f"<b>🕒 بروزرسانی: {now}</b>")
    lines.append("")

    unit = "تومان" if SHOW_IN_TOMAN else "ریال"

    lines.append(quote("💵 ارزها"))
    for label, slug, emoji in CURRENCY_ITEMS:
        price = get_price_from_homepage(soup, slug, is_rial=True)
        lines.append(quote(f"{emoji} {label}: {price} {unit}"))

    tether_usd = get_tether_price_usd()
    dollar_toman = get_price_from_homepage(soup, "price_dollar_rl", is_rial=True)
    if tether_usd:
        try:
            dollar_value = int(dollar_toman.replace(",", ""))
            tether_value = float(tether_usd.replace(",", ""))
            tether_toman = f"{int(dollar_value * tether_value):,}"
            lines.append(
                quote(f"💲 تتر (Tether): {tether_usd} دلار (≈ {tether_toman} تومان)")
            )
        except ValueError:
            lines.append(quote(f"💲 تتر (Tether): {tether_usd} دلار"))
    else:
        lines.append(quote("💲 تتر (Tether): یافت نشد"))

    lines.append("")
    lines.append(quote("🥇 طلا و نقره"))
    for label, slug, emoji in GOLD_ITEMS:
        is_rial = slug not in ("ons", "silver")
        price = get_price_from_homepage(soup, slug, is_rial=is_rial)
        unit_label = "دلار" if slug in ("ons", "silver") else unit
        lines.append(quote(f"{emoji} {label}: {price} {unit_label}"))

    lines.append("")
    lines.append(quote("🪙 سکه"))
    for label, slug, emoji in COIN_ITEMS:
        price = get_price_from_homepage(soup, slug, is_rial=True)
        lines.append(quote(f"{emoji} {label}: {price} {unit}"))

    lines.append("")
    lines.append(f"<b>{CHANNEL_USERNAME}</b>")

    return "\n".join(lines)


def send_to_telegram(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        log.error("BOT_TOKEN یا CHAT_ID تنظیم نشده است (در Environment Variables).")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, data=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            log.error("تلگرام خطا داد: %s", result)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("خطا در ارسال به تلگرام: %s", exc)
        return False


# ============================== حلقه‌ی پس‌زمینه ==============================


def background_loop():
    log.info("حلقه‌ی پس‌زمینه شروع شد. هر %s ثانیه یک‌بار اجرا می‌شود.", FETCH_INTERVAL_SECONDS)
    while True:
        STATUS["last_run_utc"] = datetime.now(timezone.utc).isoformat()
        STATUS["runs_count"] += 1
        try:
            message = build_message()
            ok = send_to_telegram(message)
            STATUS["last_success"] = ok
            STATUS["last_error"] = None if ok else "ارسال به تلگرام ناموفق بود"
            log.info("ارسال پیام: %s", "موفق" if ok else "ناموفق")
        except Exception as exc:  # noqa: BLE001
            STATUS["last_success"] = False
            STATUS["last_error"] = str(exc)
            log.exception("خطای پیش‌بینی‌نشده: %s", exc)

        time.sleep(FETCH_INTERVAL_SECONDS)


_background_thread_started = False
_lock = threading.Lock()


def ensure_background_thread_started():
    global _background_thread_started
    with _lock:
        if not _background_thread_started:
            thread = threading.Thread(target=background_loop, daemon=True)
            thread.start()
            _background_thread_started = True


# ============================== وب‌سرور Flask ==============================

app = Flask(__name__)
ensure_background_thread_started()


@app.route("/")
def index():
    """
    این صفحه دو کاربرد دارد:
    ۱) نمایش وضعیت آخرین اجرای ربات (برای دیباگ شما)
    ۲) هدف درخواست‌های سرویس‌های keep-alive مثل UptimeRobot/cron-job.org
       تا Render سرویس رایگان را نخواباند.
    """
    return jsonify(
        {
            "status": "running",
            "bot_configured": bool(BOT_TOKEN and CHAT_ID),
            "fetch_interval_seconds": FETCH_INTERVAL_SECONDS,
            **STATUS,
        }
    )


@app.route("/send-now")
def send_now():
    """ارسال دستی و فوری یک پیام (برای تست)."""
    message = build_message()
    ok = send_to_telegram(message)
    return jsonify({"sent": ok})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
