# ربات تلگرامی قیمت طلا، سکه و ارز (tgju.org)

این پروژه هر ۵ دقیقه یک‌بار قیمت دلار، تتر، یورو، پوند، لیر ترکیه، دلار
استرالیا/سنگاپور/کانادا، درهم امارات، دینار عراق، ریال قطر، افغانی، یوان
چین، طلای ۱۸ و ۲۴ عیار، طلای دست دوم، انس طلا و نقره، نقره داخلی، سکه
امامی، نیم و ربع سکه و حباب سکه را از tgju.org می‌گیرد و در قالب یک پیام
مرتب در کانال تلگرام شما پست می‌کند.

طراحی شده برای اجرای رایگان روی **Render** (پلن Free مربوط به Web Service).

---

## ۱) ساخت ربات تلگرام

1. در تلگرام به [@BotFather](https://t.me/BotFather) پیام دهید و `/newbot` را بزنید.
2. یک نام و یوزرنیم انتخاب کنید تا یک **توکن** شبیه این بگیرید:
   ```
   123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
3. ربات را به کانال خود اضافه کرده و آن را **ادمین** کنید (حداقل با دسترسی ارسال پیام).
4. **Chat ID** کانال را پیدا کنید:
   - اگر کانال عمومی است: همان `@yourchannel` کافی است.
   - اگر خصوصی است: یک پیام در کانال بفرستید، سپس در مرورگر آدرس زیر را باز کنید
     (به‌جای `TOKEN` توکن خودتان را بگذارید):
     ```
     https://api.telegram.org/botTOKEN/getUpdates
     ```
     عدد داخل `"chat":{"id": -1001234567890 ...}` همان Chat ID شماست.

---

## ۲) آپلود پروژه در گیت‌هاب

```bash
git init
git add .
git commit -m "tgju telegram bot"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git push -u origin main
```

> نکته: توکن ربات را هرگز داخل کد یا مخزن گیت‌هاب قرار ندهید. در این پروژه
> توکن و Chat ID از Environment Variables خوانده می‌شوند، نه از کد.

---

## ۳) دیپلوی روی Render (رایگان)

### روش الف) با فایل render.yaml (ساده‌تر)
1. وارد [render.com](https://render.com) شوید و حساب بسازید (می‌توانید با گیت‌هاب وارد شوید).
2. New → **Blueprint** → مخزن گیت‌هاب همین پروژه را انتخاب کنید.
3. Render فایل `render.yaml` را می‌خواند و سرویس را می‌سازد؛ فقط باید مقادیر
   `BOT_TOKEN` و `CHAT_ID` را در بخش Environment وارد کنید.
4. روی **Apply** بزنید.

### روش ب) دستی
1. New → **Web Service** → مخزن گیت‌هاب را انتخاب کنید.
2. تنظیمات:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --workers 1 --threads 4 --timeout 120`
   - **Plan**: `Free`
3. در بخش **Environment Variables** این‌ها را اضافه کنید:
   | Key | Value |
   |---|---|
   | `BOT_TOKEN` | توکن ربات تلگرام |
   | `CHAT_ID` | یوزرنیم یا آیدی عددی کانال |
   | `FETCH_INTERVAL_SECONDS` | `300` (اختیاری) |
   | `SHOW_IN_TOMAN` | `true` یا `false` (اختیاری) |
4. **Create Web Service** را بزنید. بعد از چند دقیقه، یک آدرس مثل
   `https://tgju-telegram-bot.onrender.com` می‌گیرید.

برای تست فوری، آدرس `https://YOUR-APP.onrender.com/send-now` را در مرورگر باز
کنید؛ باید بلافاصله یک پیام در کانال ببینید.

---

## ۴) ⚠️ خیلی مهم: بیدار نگه‌داشتن سرویس رایگان

سرویس‌های رایگان Render اگر حدود ۱۵ دقیقه هیچ درخواست HTTP دریافت نکنند
**به خواب می‌روند** و در نتیجه ارسال خودکار پیام‌ها هم متوقف می‌شود.

برای جلوگیری از این اتفاق، یکی از این سرویس‌های رایگان را تنظیم کنید تا هر
۵ تا ۱۰ دقیقه یک‌بار به آدرس اصلی سرویس‌تان (`https://YOUR-APP.onrender.com/`)
درخواست GET بزند:

- [cron-job.org](https://cron-job.org) (رایگان و ساده)
- [UptimeRobot](https://uptimerobot.com) (رایگان، هر ۵ دقیقه هم می‌شود تنظیم کرد)

با این کار هم سرویس بیدار می‌ماند و هم می‌توانید از داشبورد آن، آپ‌تایم
ربات را رصد کنید.

---

## ۵) بررسی وضعیت ربات

آدرس اصلی سرویس (`/`) یک JSON با وضعیت آخرین اجرا برمی‌گرداند، مثل:

```json
{
  "status": "running",
  "bot_configured": true,
  "fetch_interval_seconds": 300,
  "last_run_utc": "2026-09-02T10:15:00+00:00",
  "last_success": true,
  "last_error": null,
  "runs_count": 42
}
```

اگر `bot_configured` مقدار `false` بود یعنی `BOT_TOKEN` یا `CHAT_ID` را در
Render تنظیم نکرده‌اید.

---

## فایل‌های پروژه

- `app.py` — کد اصلی (Flask + حلقه‌ی پس‌زمینه‌ی خواندن قیمت و ارسال به تلگرام)
- `requirements.txt` — وابستگی‌های پایتون
- `render.yaml` — پیکربندی دیپلوی خودکار Render
- `.gitignore`

## نکته درباره‌ی ساختار سایت tgju.org

قیمت‌ها با خواندن شناسه‌ی هر ردیف (`id="l-<slug>"`) از صفحه‌ی اصلی tgju.org
استخراج می‌شوند. اگر روزی tgju ساختار HTML را تغییر دهد و مقداری «یافت نشد»
نشان داد، کافی‌ست در مرورگر روی آن ردیف Inspect بزنید، شناسه‌ی جدید را پیدا
کنید و در لیست‌های `CURRENCY_ITEMS` / `GOLD_ITEMS` / `COIN_ITEMS` در ابتدای
`app.py` اصلاح کنید.
