# -*- coding: utf-8 -*-
"""
بات قیمت‌گیر چند ارزی (لیر / یورو / درهم -> تومن) - برای مشتری‌ها
====================================================================
کارکرد:
  - مشتری فقط لینک محصول رو می‌فرسته (زارا در ترکیه، زارا در اسپانیا، و ...)
  - بات خودش سعی می‌کنه قیمت و ارز (TL / EUR / AED) رو از صفحه بخونه
  - قیمت × 1.23 (مارجین ثابت ۲۳٪ برای همه‌ی ارزها توی همین بات) × نرخ همون
    ارز به تومن که ادمین قبلاً ثبت کرده
  - اگه نتونست از لینک بخونه، از مشتری می‌خواد قیمت رو دستی با ارزش بفرسته

نصب کتابخونه‌ها (یک بار):
    pip install python-telegram-bot==21.4 requests

قبل از اجرا پر کن:
    BOT_TOKEN   -> توکن این بات (از BotFather، جدا از بات موجودی بگیر)
    ADMIN_IDS   -> آیدی عددی ادمین‌ها (فقط اونا اجازه دارن نرخ رو عوض کنن)

نرخ هر ارز رو ادمین با این دستورها ثبت می‌کنه (فقط یک بار، تا وقتی عوضش نکنه می‌مونه):
    /setrate try 950     -> نرخ هر ۱ لیر ترکیه به تومن
    /setrate eur 62000   -> نرخ هر ۱ یورو به تومن
    /setrate aed 17000   -> نرخ هر ۱ درهم امارات به تومن
"""

import json
import logging
import re
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ================== تنظیمات (این‌ها رو پر کن) ==================
BOT_TOKEN = "8824972641:AAGvxnayAuTNpIYK6lFmkGVfJ060DXSnXmc"

ADMIN_IDS = {
    5063260641,  # m
}

MARGIN = 1.23  # ۲۳٪ مارجین ثابت برای همه‌ی ارزها، فقط توی همین بات
RATE_FILE = "rates.json"  # نرخ هر ارز اینجا ذخیره می‌شه

# هر ارز: الگوی متنی که توی صفحه‌ی سایت دنبالش می‌گردیم + اسم فارسی برای نمایش
CURRENCIES = {
    "TRY": {"pattern": r"([\d]+[.,]\d{2})\s*TL\b", "label": "لیر"},
    "EUR": {"pattern": r"€\s*([\d]+[.,]\d{2})|([\d]+[.,]\d{2})\s*€", "label": "یورو"},
    "AED": {"pattern": r"([\d]+[.,]\d{2})\s*AED\b", "label": "درهم"},
}
# =================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_rates() -> dict:
    try:
        with open(RATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_rate(currency: str, rate: float):
    rates = load_rates()
    rates[currency] = rate
    with open(RATE_FILE, "w") as f:
        json.dump(rates, f)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def fetch_price_from_link(url: str):
    """سعی می‌کنه قیمت و ارز رو مستقیم از صفحه‌ی محصول بخونه.
    خروجی: (قیمت, کد_ارز) یا (None, None) اگه پیدا نشد."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"خطا در گرفتن صفحه: {e}")
        return None, None

    for code, info in CURRENCIES.items():
        match = re.search(info["pattern"], resp.text)
        if match:
            price_str = next(g for g in match.groups() if g).replace(",", ".")
            try:
                return float(price_str), code
            except ValueError:
                continue

    return None, None


def parse_manual_price(text: str):
    """برای وقتی مشتری خودش قیمت رو دستی می‌نویسه، مثلاً '650 try' یا '60 eur'."""
    text_lower = text.lower()
    for code in CURRENCIES:
        if code.lower() in text_lower or (code == "TRY" and "لیر" in text) \
                or (code == "EUR" and ("یورو" in text or "€" in text)) \
                or (code == "AED" and "درهم" in text):
            numbers = re.findall(r"[\d,.]+", text)
            for n in numbers:
                try:
                    return float(n.replace(",", "")), code
                except ValueError:
                    continue
    return None, None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام 👋\n"
        "لینک محصول رو بفرست (زارا ترکیه، زارا اسپانیا، یا هر سایتی که پشتیبانی بشه).\n"
        "اگه نتونستم قیمت رو خودم بخونم، بهت می‌گم قیمت رو با کدوم ارز (لیر/یورو/درهم) بفرستی."
    )


async def setrate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ فقط ادمین می‌تونه نرخ رو تنظیم کنه.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "فرمت درست:\n/setrate try 950\n/setrate eur 62000\n/setrate aed 17000"
        )
        return

    currency = context.args[0].upper()
    if currency not in CURRENCIES:
        await update.message.reply_text("❌ ارز نامعتبره. از try، eur یا aed استفاده کن.")
        return

    try:
        rate = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ فقط عدد بفرست. مثال: /setrate try 950")
        return

    save_rate(currency, rate)
    label = CURRENCIES[currency]["label"]
    await update.message.reply_text(f"✅ نرخ {label} به تومن روی {rate:,.0f} تنظیم شد.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    rates = load_rates()

    price = None
    currency = None

    url_match = re.search(r"https?://\S+", text)
    if url_match:
        price, currency = fetch_price_from_link(url_match.group(0))

    if price is None:
        text_without_url = re.sub(r"https?://\S+", "", text)
        price, currency = parse_manual_price(text_without_url)

    if price is None or currency is None:
        if url_match:
            await update.message.reply_text(
                "⚠️ نتونستم قیمت رو خودم از صفحه بخونم.\n"
                "لطفاً قیمت رو با ارزش بفرست، مثلاً: 650 try یا 60 eur یا 500 aed"
            )
        else:
            await update.message.reply_text(
                "❌ لینک یا قیمت رو پیدا نکردم. لینک محصول رو بفرست."
            )
        return

    rate = rates.get(currency)
    if rate is None:
        label = CURRENCIES[currency]["label"]
        await update.message.reply_text(
            f"⚠️ نرخ {label} هنوز تنظیم نشده. ادمین باید اول با دستور "
            f"/setrate {currency.lower()} عدد_نرخ این کارو انجام بده."
        )
        return

    final_toman = price * MARGIN * rate
    label = CURRENCIES[currency]["label"]

    await update.message.reply_text(
        f"💰 قیمت پایه: {price:,.2f} {label}\n"
        f"📈 با احتساب مارجین: {price * MARGIN:,.2f} {label}\n"
        f"💵 قیمت نهایی: {final_toman:,.0f} تومن\n"
        f"(بدون هزینه باربری)"
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setrate", setrate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("بات قیمت‌گیر روشن شد...")
    app.run_polling()


if __name__ == "__main__":
    main()
