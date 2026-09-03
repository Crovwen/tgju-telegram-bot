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
import jdatetime
from flask import Flask, jsonify

# =========================== تنظیمات (از Environment Variables) ===========================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
FETCH_INTERVAL_SECONDS = int(os.environ.get("FETCH_INTERVAL_SECONDS", "300"))
SHOW_IN_TOMAN = os.environ.get("SHOW_IN_TOMAN", "true").strip().lower() != "false"

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Gheymat_Moment")

# منابع داده — هر بخش از معتبرترین منبعی که برایش پیدا شد:
# ۱) ارزها: API شخص‌ثالث پایدار (BlackIQ/tgju-api) که مشکل مسدودسازی ربات‌ها
#    روی tgju.org را حل کرده.
# ۲) طلا/سکه: Navasan (navasan.tech) — سرویس شناخته‌شده‌ی ایرانی، مستقل از tgju.
#    نیاز به یک API KEY رایگان دارد (از ربات تلگرام navasan_contact_bot).
# ۳) تتر: API رسمی و رایگان صرافی نوبیتکس (بدون نیاز به کلید).
CURRENCY_API_URL = "https://tgju.amirhossein.info/api/price/currency"
NAVASAN_API_KEY = os.environ.get("NAVASAN_API_KEY", "")
NAVASAN_API_URL = "http://api.navasan.tech/latest/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("tgju-bot")

# ============================ فهرست آیتم‌ها ============================

# هر آیتم: (برچسب فارسی, شناسه در API ارزها, ایموجی/پرچم)
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

# هر آیتم: (برچسب فارسی, شناسه در Navasan, ایموجی)
# نکته: Navasan مقادیر را مستقیماً به تومان برمی‌گرداند (نه ریال).
GOLD_ITEMS = [
    ("طلای ۱۸ عیار (هر گرم)", "18ayar", "🥇"),
    ("انس جهانی طلا", "xau", "🥇"),
]

COIN_ITEMS = [
    ("سکه امامی (تمام سکه)", "sekkeh", "🪙"),
    ("نیم سکه", "nim", "🪙"),
    ("ربع سکه", "rob", "🪙"),
    ("حباب سکه امامی", "bub_sekkeh", "🫧"),
    ("حباب نیم سکه", "bub_nim", "🫧"),
    ("حباب ربع سکه", "bub_rob", "🫧"),
]

# وضعیت آخرین اجرا، برای نمایش در صفحه‌ی وب (health check)
STATUS = {
    "last_run_utc": None,
    "last_success": None,
    "last_error": None,
    "runs_count": 0,
}

# ============================== توابع کمکی ==============================


def clean_number(text: str) -> str:
    return text.strip().replace("\u200c", "").replace("\xa0", "")


def to_toman(rial_text: str) -> str:
    digits = rial_text.replace(",", "").strip()
    try:
        value = int(float(digits))
        return f"{value // 10:,}"
    except ValueError:
        return rial_text


def format_toman(value) -> str:
    """عدد یا رشته‌ی عددی را با جداکننده‌ی هزارگان به‌صورت رشته برمی‌گرداند."""
    try:
        return f"{int(float(str(value).replace(',', ''))):,}"
    except (ValueError, TypeError):
        return str(value)


def get_currencies_from_api() -> dict:
    """
    قیمت ارزها را از یک API شخص‌ثالث پایدار می‌گیرد (نه از اسکرپ مستقیم
    tgju.org که به‌خاطر سیستم ضدربات سایت، معمولاً جدول اصلی را برنمی‌گرداند).
    خروجی: دیکشنری slug -> متن قیمت (به ریال، همان‌طور که tgju نمایش می‌دهد).
    """
    try:
        resp = requests.get(CURRENCY_API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = {item["key"]: item["price"] for item in data if item.get("key")}
        log.info("دریافت قیمت ارزها موفق بود (%s مورد)", len(result))
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("خطا در دریافت قیمت ارزها: %s", exc)
        return {}


def get_gold_coin_from_navasan() -> dict:
    """
    قیمت طلا و سکه را از Navasan (سرویس مستقل و شناخته‌شده‌ی ایرانی، نه tgju)
    می‌گیرد. Navasan مقادیر را مستقیماً به تومان برمی‌گرداند.
    نیازمند NAVASAN_API_KEY (رایگان، از ربات تلگرام navasan_contact_bot).
    خروجی: دیکشنری code -> متن قیمت (تومان). اگر کلید تنظیم نشده یا درخواست
    ناموفق باشد، دیکشنری خالی برمی‌گرداند.
    """
    if not NAVASAN_API_KEY:
        log.warning("NAVASAN_API_KEY تنظیم نشده؛ قیمت طلا/سکه در دسترس نیست.")
        return {}
    try:
        resp = requests.get(
            NAVASAN_API_URL, params={"api_key": NAVASAN_API_KEY}, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        result = {code: info.get("value") for code, info in data.items() if isinstance(info, dict)}
        log.info("دریافت قیمت طلا/سکه از Navasan موفق بود (%s مورد)", len(result))
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("خطا در دریافت قیمت طلا/سکه از Navasan: %s", exc)
        return {}


def get_tether_from_navasan(navasan_data: dict) -> str | None:
    """
    قیمت تتر را از همان داده‌ی Navasan که برای طلا/سکه گرفته‌ایم استخراج می‌کند.
    (نوبیتکس را کنار گذاشتیم چون از سرورهای خارج ایران—مثل Render—اصلاً در
    دسترس نیست و همیشه با خطای DNS مواجه می‌شود.)
    چند نام‌ کد احتمالی را امتحان می‌کنیم چون مستندات Navasan نام دقیق کد
    تتر را اعلام نکرده.
    """
    for candidate in ("usdt", "tether", "usdt_sell", "usdt_buy", "crypto_usdt"):
        raw = navasan_data.get(candidate)
        if raw:
            return format_toman(raw)
    return None


def get_iran_datetime_str() -> str:
    """تاریخ شمسی و ساعت به وقت ایران، مثل 1405/06/11 - 14:35:00"""
    now_iran = datetime.now(IRAN_TZ)
    jalali = jdatetime.date.fromgregorian(date=now_iran.date())
    return f"{jalali.strftime('%Y/%m/%d')} - {now_iran.strftime('%H:%M:%S')}"


# ============================== ساخت پیام ==============================


def quote(content: str) -> str:
    """هر خط را به‌صورت یک نقل‌قول (blockquote) جداگانه و بولد برمی‌گرداند."""
    return f"<blockquote><b>{content}</b></blockquote>"


def build_message() -> str:
    now = get_iran_datetime_str()

    currency_api_data = get_currencies_from_api()
    navasan_data = get_gold_coin_from_navasan()

    lines = []
    lines.append("<b>📊 قیمت لحظه‌ای طلا، سکه و ارز</b>")
    lines.append(f"<b>🕒 بروزرسانی: {now}</b>")
    lines.append("")

    unit = "تومان" if SHOW_IN_TOMAN else "ریال"

    lines.append(quote("💵 ارزها"))
    for label, slug, emoji in CURRENCY_ITEMS:
        raw_price = currency_api_data.get(slug)
        price = to_toman(raw_price) if (raw_price and SHOW_IN_TOMAN) else (raw_price or "یافت نشد")
        lines.append(quote(f"{emoji} {label}: {price} {unit}"))

    tether_toman = get_tether_from_navasan(navasan_data)
    if tether_toman:
        lines.append(quote(f"💲 تتر (Tether): {tether_toman} {unit}"))
    else:
        lines.append(quote("💲 تتر (Tether): یافت نشد"))

    lines.append("")
    lines.append(quote("🥇 طلا"))
    for label, code, emoji in GOLD_ITEMS:
        raw_price = navasan_data.get(code)
        price = format_toman(raw_price) if raw_price else "یافت نشد"
        lines.append(quote(f"{emoji} {label}: {price} تومان"))

    lines.append("")
    lines.append(quote("🪙 سکه"))
    for label, code, emoji in COIN_ITEMS:
        raw_price = navasan_data.get(code)
        price = format_toman(raw_price) if raw_price else "یافت نشد"
        lines.append(quote(f"{emoji} {label}: {price} تومان"))

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


@app.route("/debug")
def debug():
    """برای عیب‌یابی سریع: وضعیت هر سه منبع داده را برمی‌گرداند."""
    result = {}

    try:
        api_data = get_currencies_from_api()
        result["currency_api"] = {"ok": bool(api_data), "item_count": len(api_data)}
    except Exception as exc:  # noqa: BLE001
        result["currency_api"] = {"error": str(exc)}

    try:
        navasan_data = get_gold_coin_from_navasan()
        result["navasan"] = {
            "api_key_set": bool(NAVASAN_API_KEY),
            "ok": bool(navasan_data),
            "item_count": len(navasan_data),
        }
        # کدهای موجود که شامل usd/tether/usdt هستند، برای پیدا کردن نام دقیق کد تتر
        result["navasan_usdt_like_keys"] = [
            k for k in navasan_data.keys() if "usd" in k.lower() or "tether" in k.lower()
        ]
        tether = get_tether_from_navasan(navasan_data)
        result["tether"] = {"ok": bool(tether), "value": tether}
    except Exception as exc:  # noqa: BLE001
        result["navasan"] = {"error": str(exc)}

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
