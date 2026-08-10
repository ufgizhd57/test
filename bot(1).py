import os
import re
import json
import logging
import asyncio
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# Railway Variables:
# BOT_TOKEN=توکن ربات
# OPENAI_API_KEY=کلید OpenAI
# ADMIN_ID=آیدی عددی ادمین
# CHANNEL_ID=@Gamefa_official
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Gamefa_official").strip()

DATA_FILE = Path("news_memory.json")
MAX_MEMORY = 1000

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("gamefa-bot")


# ---------------------- Storage ----------------------

def load_memory():
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_memory(items):
    items = items[-MAX_MEMORY:]
    DATA_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


memory = load_memory()


def normalize(text):
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\u0600-\u06FF\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a, b):
    # بدون وابستگی به دیتابیس؛ برای جلوگیری از ارسال خبرهای بسیار مشابه
    sa = set(normalize(a).split())
    sb = set(normalize(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def is_duplicate(text):
    n = normalize(text)
    for item in memory:
        if similarity(n, item.get("text", "")) >= 0.82:
            return True
    return False


# ---------------------- URL extraction ----------------------

URL_RE = re.compile(r"https?://[^\s<>()]+")


def extract_url(text):
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(".,)]") if m else None


async def fetch_article(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/138 Safari/537.36"
        )
    }

    timeout = aiohttp.ClientTimeout(total=25)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as response:
            response.raise_for_status()
            html = await response.text(errors="ignore")

    soup = BeautifulSoup(html, "html.parser")

    # حذف عناصر غیرمحتوایی
    for tag in soup([
        "script", "style", "noscript", "svg", "nav",
        "footer", "header", "form", "aside"
    ]):
        tag.decompose()

    title = ""
    if soup.title:
        title = soup.title.get_text(" ", strip=True)

    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        description = meta.get("content", "")

    article = soup.find("article")
    if article:
        body = article.get_text("\n", strip=True)
    else:
        candidates = soup.find_all(["p", "h1", "h2", "h3"])
        body = "\n".join(
            x.get_text(" ", strip=True)
            for x in candidates
            if len(x.get_text(" ", strip=True)) > 30
        )

    body = re.sub(r"\n{3,}", "\n\n", body)
    body = body[:18000]

    return {
        "url": url,
        "title": title[:1000],
        "description": description[:3000],
        "body": body,
    }


# ---------------------- OpenAI ----------------------

async def ai_generate(article_text):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY تنظیم نشده است.")

    system = """
تو دستیار تولید خبر برای کانال تلگرامی Gamefa هستی.

وظیفه:
از متن خبر یا صفحه Gamefa یک پست آماده انتشار فارسی بساز.

قوانین بسیار مهم:
1) تیتر حتماً با متن فارسی شروع شود.
2) متن خبر فقط یک بند باشد.
3) متن بند با فارسی شروع شود و سپس نام‌های انگلیسی بیایند.
4) متن را روان، خبری، دقیق و خلاصه بنویس.
5) اطلاعاتی که در منبع نیست اختراع نکن.
6) نام بازی‌ها، فیلم‌ها، شرکت‌ها، افراد و اصطلاحات مهم را با نام انگلیسی اصلی حفظ کن.
7) از بولد، ایتالیک، Markdown و لینک داخل متن استفاده نکن.
8) متن باید مستقیماً قابل کپی در Telegram باشد.
9) در پایان دقیقاً این خط را اضافه کن:
🆔 @Gamefa_official
10) از اضافه کردن توضیح خارج از پست خودداری کن.
11) از دو بند کردن خبر خودداری کن.
12) اگر منبع خبری به زبان انگلیسی است، مفهوم را به فارسی طبیعی منتقل کن.
13) اگر خبر درباره بازی است، تیتر با 🎮 شروع شود.
14) اگر خبر درباره فیلم/سریال/بازیگر است، تیتر با 🎬 شروع شود.
15) اگر خبر درباره فناوری، AI، سخت‌افزار و موارد مشابه است، تیتر با 📱 شروع شود.
"""

    payload = {
        "model": "gpt-5.4-mini",
        "input": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": "متن منبع:\n\n" + article_text,
            },
        ],
        "max_output_tokens": 1200,
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:
        async with session.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=payload,
        ) as response:
            data = await response.json()

            if response.status >= 400:
                raise RuntimeError(
                    data.get("error", {}).get("message", str(data))
                )

    # Responses API خروجی متنی را در output_text برمی‌گرداند.
    result = data.get("output_text", "").strip()

    if not result:
        # fallback برای ساختارهای احتمالی
        chunks = []
        for item in data.get("output", []):
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    chunks.append(c.get("text", ""))
        result = "\n".join(chunks).strip()

    if not result:
        raise RuntimeError("پاسخ متنی از OpenAI دریافت نشد.")

    return result


# ---------------------- Bot ----------------------

def admin_only(update):
    return ADMIN_ID and update.effective_user and update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update):
        await update.message.reply_text("این ربات خصوصی است.")
        return

    await update.message.reply_text(
        "ربات آماده است.\n\n"
        "یک لینک Gamefa بفرست یا متن خبر را ارسال کن.\n"
        "ربات خبر را با فرمت کانال Gamefa آماده می‌کند.\n\n"
        "/stats - آمار حافظه\n"
        "/clear - پاک کردن حافظه خبرها"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update):
        return

    await update.message.reply_text(
        f"تعداد خبرهای ذخیره‌شده برای تشخیص تکراری: {len(memory)}"
    )


async def clear_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update):
        return

    memory.clear()
    save_memory(memory)
    await update.message.reply_text("حافظه خبرها پاک شد.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update):
        return

    text = (update.message.text or update.message.caption or "").strip()
    if not text:
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        url = extract_url(text)

        if url:
            parsed = urlparse(url)

            if "gamefa.com" not in parsed.netloc.lower():
                await update.message.reply_text(
                    "فعلاً برای لینک‌های Gamefa طراحی شده است."
                )
                return

            article = await fetch_article(url)

            source = (
                f"عنوان صفحه: {article['title']}\n\n"
                f"توضیحات: {article['description']}\n\n"
                f"متن خبر:\n{article['body']}\n\n"
                f"URL: {url}"
            )
        else:
            source = text

        if is_duplicate(source):
            await update.message.reply_text(
                "⚠️ این خبر یا یک خبر بسیار مشابه قبلاً دریافت شده است."
            )
            return

        result = await ai_generate(source)

        # ذخیره برای تشخیص تکراری
        memory.append({
            "text": source[:12000],
            "result": result,
        })
        save_memory(memory)

        await update.message.reply_text(result)

        # ارسال اختیاری به کانال با دستور /publish
        context.user_data["last_result"] = result

    except Exception as e:
        log.exception("processing error")
        await update.message.reply_text(
            "❌ خطا هنگام پردازش خبر:\n" + str(e)[:1500]
        )


async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update):
        return

    result = context.user_data.get("last_result")
    if not result:
        await update.message.reply_text(
            "ابتدا یک خبر ارسال کن تا متن آماده شود."
        )
        return

    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=result,
        )
        await update.message.reply_text("✅ خبر در کانال منتشر شد.")
    except Exception as e:
        await update.message.reply_text(
            "❌ انتشار در کانال ناموفق بود:\n" + str(e)[:1200]
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled error", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")
    if not ADMIN_ID:
        raise RuntimeError("ADMIN_ID تنظیم نشده است.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("clear", clear_memory))
    app.add_handler(CommandHandler("publish", publish))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    app.add_error_handler(error_handler)

    log.info("Gamefa AI News Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
