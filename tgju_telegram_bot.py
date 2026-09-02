# -*- coding: utf-8 -*-
"""
ربات تلگرامی قیمت طلا، سکه و ارز از سایت tgju.org
====================================================

این اسکریپت هر ۵ دقیقه یک‌بار قیمت‌های زیر را از tgju.org می‌خواند
و به‌صورت یک پیام مرتب در کانال تلگرام شما ارسال می‌کند:

  ارزها : دلار، تتر، یورو، پوند، لیر ترکیه، دلار استرالیا، دلار سنگاپور،
           دلار کانادا، درهم امارات، دینار عراق، ریال قطر، افغانی، یوان چین
  طلا   : طلای ۱۸ عیار، طلای ۲۴ عیار، طلای دست دوم، انس طلا، انس نقره، نقره داخلی
  سکه   : سکه امامی (تمام سکه)، نیم سکه، ربع سکه، حباب سکه، حباب نیم و ربع سکه


پیش‌نیازها (روی سروری که اسکریپت را اجرا می‌کنید نصب کنید):
    pip install requests beautifulsoup4 lxml


مرحله ۱ - ساخت ربات تلگرام:
    1) در تلگرام به @BotFather پیام دهید و دستور /newbot را بزنید.
    2) نام و یوزرنیم دلخواه بدهید تا یک TOKEN شبیه این بگیرید:
       123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    3) آن را در متغیر BOT_TOKEN پایین قرار دهید.

مرحله ۲ - افزودن ربات به کانال:
    1) ربات ساخته‌شده را به کانال خود (به‌عنوان ادمین) اضافه کنید.
    2) اگر کانال عمومی است، آیدی آن چیزی مثل "@mychannel" است.
    3) اگر کانال خصوصی است، باید Chat ID عددی (مثل -1001234567890) را
       پیدا کنید؛ ساده‌ترین راه: یک پیام در کانال بفرستید و آدرس زیر را
       در مرورگر باز کنید (به‌جای TOKEN، توکن خودتان را بگذارید):
           https://api.telegram.org/botTOKEN/getUpdates
       عدد chat.id همان Chat ID شماست.

مرحله ۳ - اجرای مداوم روی سرور:
    ساده‌ترین حالت همین اجرای مستقیم است (این اسکریپت خودش هر ۵ دقیقه
    تکرار می‌شود، نیازی به cron نیست):
        python3 tgju_telegram_bot.py
    برای اینکه با قطع شدن ترمینال متوقف نشود، از screen/tmux یا یک
    systemd service استفاده کنید (نمونه در انتهای همین فایل، در کامنت).
"""

import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# =========================== تنظیمات کاربر ============================

BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"          # توکن ربات از BotFather
CHAT_ID = "@your_channel_username"                # یا مثلا "-1001234567890"

FETCH_INTERVAL_SECONDS = 5 * 60                   # هر ۵ دقیقه

# اگر True باشد، مبالغ ریالی سایت (که tgju به‌صورت ریال نمایش می‌دهد)
# تقسیم بر ۱۰ شده و به‌صورت تومان نمایش داده می‌شوند.
SHOW_IN_TOMAN = True

CHANNEL_USERNAME = "@Gheymat_Moment"          # آیدی کانال، در انتهای هر پیام درج می‌شود
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))  # ساعت رسمی ایران (بدون تغییر فصلی)

TGJU_BASE = "https://www.tgju.org"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("tgju-bot")

# ============================ فهرست آیتم‌ها ============================
# هر آیتم: (برچسب فارسی, شناسه ردیف در tgju روی صفحه اصلی)
# این شناسه‌ها همان id="l-<slug>" هستند که در HTML صفحه tgju.org قرار دارند.

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

# آیتم‌هایی که در صفحه اصلی نیستند و از صفحه پروفایل مخصوص خودشان خوانده می‌شوند
SPECIAL_PROFILE_ITEMS = [
    ("تتر (Tether)", "crypto-tether"),  # قیمت این مورد روی tgju به دلار است
]


# ============================== توابع کمکی ==============================

def fetch_soup(url: str) -> BeautifulSoup | None:
    """گرفتن یک صفحه و تبدیل آن به BeautifulSoup."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:  # noqa: BLE001
        log.warning("خطا در دریافت %s: %s", url, exc)
        return None


def clean_number(text: str) -> str:
    """پاکسازی متن قیمت (حذف فاصله‌های اضافه)."""
    return text.strip().replace("\u200c", "").replace("\xa0", "")


def to_toman(rial_text: str) -> str:
    """تبدیل رشته ریالی به تومان (تقسیم بر ۱۰)، در صورت امکان."""
    digits = rial_text.replace(",", "").strip()
    try:
        value = int(digits)
        return f"{value // 10:,}"
    except ValueError:
        return rial_text  # اگر عدد نبود (مثلا انس/دلاری با اعشار) دست‌نخورده برگردان


def get_price_from_homepage(soup: BeautifulSoup, slug: str, is_rial: bool) -> str:
    """
    استخراج قیمت یک ردیف با شناسه l-<slug> از صفحه اصلی tgju.
    ساختار هر ردیف چیزی شبیه این است:
        <tr id="l-price_dollar_rl">
            <td>...لینک نام...</td>
            <td class="nf">2,118,100</td>
            ...
        </tr>
    """
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


def get_tether_price_usd() -> str | None:
    """خواندن قیمت تتر (به دلار) از صفحه پروفایل مخصوص آن."""
    soup = fetch_soup(f"{TGJU_BASE}/profile/crypto-tether")
    if soup is None:
        return None

    # روی صفحات پروفایل tgju معمولا یک span با id مشخص قیمت لحظه‌ای را نشان می‌دهد
    price_span = soup.find(id="last-price-value") or soup.select_one(
        "span.info-price, .price-box .value, [data-col='info.last_trade.PDrCotVal']"
    )
    if price_span:
        return clean_number(price_span.get_text())

    # راه جایگزین: جست‌وجوی ردیف با همان شناسه در جدول صفحه اصلی
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

    # تتر جداگانه (بر حسب دلار آمریکا + تبدیل تقریبی به تومان)
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
        # انس جهانی طلا/نقره به دلار است، نه ریال
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


# ============================== ارسال به تلگرام ==============================

def send_to_telegram(text: str) -> bool:
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


# ================================= اجرای اصلی =================================

def main() -> None:
    if "PASTE_YOUR_BOT_TOKEN_HERE" in BOT_TOKEN:
        log.error("لطفا ابتدا BOT_TOKEN و CHAT_ID را در بالای فایل تنظیم کنید.")
        return

    log.info("ربات شروع به کار کرد. هر %s ثانیه یک‌بار بروزرسانی می‌شود.", FETCH_INTERVAL_SECONDS)

    while True:
        try:
            message = build_message()
            ok = send_to_telegram(message)
            log.info("ارسال پیام: %s", "موفق" if ok else "ناموفق")
        except Exception as exc:  # noqa: BLE001
            log.exception("خطای پیش‌بینی‌نشده: %s", exc)

        time.sleep(FETCH_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()


# ============================================================================
# نمونه‌ی systemd service برای اجرای دائمی روی سرور لینوکس (اختیاری):
#
# فایل: /etc/systemd/system/tgju-bot.service
# -----------------------------------------------------------------
# [Unit]
# Description=TGJU Telegram Price Bot
# After=network.target
#
# [Service]
# WorkingDirectory=/home/YOUR_USER/tgju-bot
# ExecStart=/usr/bin/python3 /home/YOUR_USER/tgju-bot/tgju_telegram_bot.py
# Restart=always
# RestartSec=10
#
# [Install]
# WantedBy=multi-user.target
# -----------------------------------------------------------------
# سپس:
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now tgju-bot
#   journalctl -u tgju-bot -f      # مشاهده لاگ زنده
# ============================================================================
