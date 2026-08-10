```python
import os
import re
import json
import html
import asyncio
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus

import aiohttp
from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from openai import AsyncOpenAI


# ============================================================
# SETTINGS
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    ""
).strip()

CHANNEL_ID = os.getenv(
    "CHANNEL_ID",
    "@Gamefa_official"
).strip()

MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.4-mini"
).strip()

try:
    ADMIN_ID = int(
        os.getenv("ADMIN_ID", "0")
    )
except Exception:
    ADMIN_ID = 0


MEMORY_FILE = Path(
    "news_memory.json"
)

MAX_MEMORY = 1500

memory = []

prepared = {}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("gamefa")


# ============================================================
# MEMORY
# ============================================================

def load_memory():

    global memory

    try:

        memory = json.loads(
            MEMORY_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(memory, list):
            memory = []

    except Exception:

        memory = []


def save_memory():

    MEMORY_FILE.write_text(
        json.dumps(
            memory[-MAX_MEMORY:],
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def norm(text):

    text = text or ""

    text = re.sub(
        r"https?://\S+",
        " ",
        text
    )

    text = text.lower()

    text = re.sub(
        r"[^\w\u0600-\u06FF\s]",
        " ",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def similarity(a, b):

    a = set(
        norm(a).split()
    )

    b = set(
        norm(b).split()
    )

    if not a or not b:
        return 0

    return len(a & b) / len(a | b)


def duplicate(text):

    for item in memory:

        if similarity(
            text,
            item.get(
                "source",
                ""
            )
        ) >= 0.82:

            return True

    return False


def is_admin(message):

    return bool(
        ADMIN_ID
        and message.from_user
        and message.from_user.id == ADMIN_ID
    )


def extract_url(text):

    match = re.search(
        r"https?://[^\s<>()]+",
        text or ""
    )

    if not match:
        return None

    return match.group(
        0
    ).rstrip(
        ".,)]}"
    )


def escape_html(text):

    return html.escape(
        text or "",
        quote=False
    )


# ============================================================
# PERSIAN START DETECTION
# ============================================================

PERSIAN_RE = re.compile(
    r"[\u0600-\u06FF]"
)

LATIN_RE = re.compile(
    r"[A-Za-z]"
)


def starts_with_persian(text):

    if not text:
        return False

    # حذف فاصله و ایموجی‌های ابتدایی
    clean = text.strip()

    clean = re.sub(
        r"^[🎮🎬📱🟣\s]+",
        "",
        clean
    )

    if not clean:
        return False

    # اولین کاراکتر واقعی
    first = clean[0]

    return bool(
        PERSIAN_RE.search(first)
    )


def make_persian_start(
    text,
    is_title=False
):

    """
    اگر AI جمله را با انگلیسی شروع کند،
    یک عبارت فارسی طبیعی قبل آن قرار می‌دهد.

    این مرحله فقط برای اطمینان نهایی است.
    """

    if not text:
        return text

    text = text.strip()

    if starts_with_persian(text):
        return text

    if is_title:

        return (
            "گزارش جدید درباره "
            + text
        )

    return (
        "براساس گزارش‌های منتشرشده، "
        + text
    )


# ============================================================
# FORMAT POST
# ============================================================

def format_post(ai_text):

    ai_text = ai_text or ""

    # حذف Markdown bold
    ai_text = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        ai_text,
        flags=re.S
    )

    # حذف Markdown italic
    ai_text = re.sub(
        r"__(.*?)__",
        r"\1",
        ai_text,
        flags=re.S
    )

    # حذف امضای احتمالی
    ai_text = re.sub(
        r"(?im)^\s*(?:🆔\s*)?@Gamefa_official\s*$",
        "",
        ai_text
    )

    # حذف خطوط خالی
    lines = [
        x.strip()
        for x in ai_text.splitlines()
        if x.strip()
    ]

    if not lines:
        return ""

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = lines[0]

    # حذف ایموجی دسته‌بندی احتمالی
    title_without_emoji = re.sub(
        r"^[🎮🎬📱]\s*",
        "",
        title
    ).strip()

    title = make_persian_start(
        title_without_emoji,
        is_title=True
    )

    # --------------------------------------------------------
    # BODY
    # --------------------------------------------------------

    body_lines = lines[1:]

    paragraphs = []

    for line in body_lines:

        # حذف bullet قبلی
        line = re.sub(
            r"^\s*🟣\s*",
            "",
            line
        ).strip()

        if not line:
            continue

        # اطمینان از شروع فارسی
        line = make_persian_start(
            line,
            is_title=False
        )

        paragraphs.append(
            "🟣 " + line
        )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    full_text = (
        title
        + " "
        + " ".join(
            body_lines
        )
    ).lower()

    if any(
        word in full_text
        for word in [
            "بازی",
            "گیم",
            "game",
            "gaming",
            "playstation",
            "xbox",
            "nintendo",
            "steam",
            "doom",
            "gta",
            "resident evil",
            "halo"
        ]
    ):

        category = "🎮"

    elif any(
        word in full_text
        for word in [
            "فیلم",
            "سریال",
            "بازیگر",
            "movie",
            "film",
            "series",
            "season",
            "actor",
            "actress",
            "netflix",
            "hbo"
        ]
    ):

        category = "🎬"

    else:

        category = "📱"

    # --------------------------------------------------------
    # FINAL TITLE
    # --------------------------------------------------------

    title = (
        category
        + " "
        + title
    )

    # --------------------------------------------------------
    # FINAL POST
    # --------------------------------------------------------

    result = (
        "<b>"
        + escape_html(title)
        + "</b>"
    )

    if paragraphs:

        result += (
            "\n\n"
            + "\n\n".join(
                escape_html(
                    paragraph
                )
                for paragraph in paragraphs
            )
        )

    result += (
        "\n\n"
        "<b>🆔 @Gamefa_official</b>"
    )

    return result


# ============================================================
# GAMEFA ARTICLE FETCH
# ============================================================

async def fetch_gamefa(url):

    parsed = urlparse(url)

    if (
        "gamefa.com"
        not in parsed.netloc.lower()
    ):

        raise ValueError(
            "فقط لینک Gamefa پشتیبانی می‌شود."
        )

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151 Safari/537.36"
    }

    timeout = aiohttp.ClientTimeout(
        total=35
    )

    async with aiohttp.ClientSession(
        headers=headers,
        timeout=timeout
    ) as session:

        async with session.get(
            url,
            allow_redirects=True
        ) as response:

            response.raise_for_status()

            final_url = str(
                response.url
            )

            raw = await response.text(
                errors="ignore"
            )

    soup = BeautifulSoup(
        raw,
        "html.parser"
    )

    # حذف عناصر غیرمتنی
    for element in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "form",
            "aside"
        ]
    ):

        element.decompose()

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    h1 = soup.find("h1")

    if h1:

        title = h1.get_text(
            " ",
            strip=True
        )

    elif soup.title:

        title = soup.title.get_text(
            " ",
            strip=True
        )

    else:

        title = ""

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = ""

    meta_options = [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"}
    ]

    for attrs in meta_options:

        meta = soup.find(
            "meta",
            attrs=attrs
        )

        if (
            meta
            and meta.get("content")
        ):

            description = (
                meta["content"]
                .strip()
            )

            break

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image = ""

    image_options = [
        {"property": "og:image"},
        {"name": "twitter:image"},
        {"property": "og:image:url"}
    ]

    for attrs in image_options:

        meta = soup.find(
            "meta",
            attrs=attrs
        )

        if (
            meta
            and meta.get("content")
        ):

            image = urljoin(
                final_url,
                meta["content"].strip()
            )

            break

    # --------------------------------------------------------
    # BODY
    # --------------------------------------------------------

    article = (
        soup.find("article")
        or soup
    )

    paragraphs = article.find_all(
        [
            "p",
            "h2",
            "h3"
        ]
    )

    body_parts = []

    for paragraph in paragraphs:

        text = paragraph.get_text(
            " ",
            strip=True
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        if len(text) >= 35:

            body_parts.append(
                text
            )

    body = "\n".join(
        body_parts
    )[:24000]

    return {
        "url": final_url,
        "title": title,
        "description": description,
        "body": body,
        "image": image
    }


# ============================================================
# AI
# ============================================================

PROMPT = """
تو ویراستار حرفه‌ای اخبار کانال Gamefa هستی.

از اطلاعات داده‌شده یک پست فارسی آماده انتشار بساز.

قوانین بسیار مهم:

1. خط اول فقط تیتر خبر باشد.

2. تیتر حتماً با یک کلمه یا عبارت فارسی شروع شود.

3. هیچ‌وقت تیتر را با نام انگلیسی شروع نکن.
مثلاً این غلط است:
Netflix نسخه آمریکایی Squid Game را...

فرم درست:
نتفلیکس نسخه آمریکایی Squid Game را...

4. متن خبر کاملاً فارسی و روان باشد.

5. ابتدای هر پاراگراف حتماً فارسی باشد.

6. هیچ پاراگرافی را با نام انگلیسی، نام شرکت، نام بازی، نام فیلم یا نام شخص شروع نکن.

مثلاً این غلط است:
David Fincher قرار است...

فرم درست:
دیوید فینچر قرار است...

یا:
براساس گزارش‌ها، David Fincher قرار است...

7. نام‌های انگلیسی را درون جمله حفظ کن.

8. نام بازی‌ها، فیلم‌ها، شرکت‌ها و افراد را در صورت نیاز با نام اصلی انگلیسی بنویس، اما هیچ‌کدام نباید اولین عبارت جمله باشند.

9. متن باید خبری، طبیعی و قابل انتشار باشد.

10. اطلاعات جدید و ساختگی اضافه نکن.

11. خروجی فقط شامل تیتر و متن خبر باشد.

12. Markdown تولید نکن.

13. HTML تولید نکن.

14. لینک تولید نکن.

15. منبع تولید نکن.

16. @Gamefa_official تولید نکن.

17. ایموجی 🟣 تولید نکن.

18. اگر خبر مربوط به بازی است، تیتر با 🎮 شروع شود.

19. اگر خبر مربوط به فیلم یا سریال است، تیتر با 🎬 شروع شود.

20. اگر خبر مربوط به فناوری، هوش مصنوعی، موبایل یا سخت‌افزار است، تیتر با 📱 شروع شود.

21. بعد از ایموجی دسته‌بندی نیز باید اولین کلمه واقعی تیتر فارسی باشد.

خروجی فقط این ساختار را داشته باشد:

تیتر

متن خبر
"""


async def generate_news(source):

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY
    )

    response = await client.responses.create(
        model=MODEL,
        instructions=PROMPT,
        input=source,
        max_output_tokens=1200
    )

    return (
        response.output_text
        or ""
    ).strip()


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

async def download_image(url):

    if not url:
        return None

    try:

        headers = {
            "User-Agent":
                "Mozilla/5.0"
        }

        timeout = aiohttp.ClientTimeout(
            total=30
        )

        async with aiohttp.ClientSession(
            headers=headers,
            timeout=timeout
        ) as session:

            async with session.get(
                url,
                allow_redirects=True
            ) as response:

                if response.status != 200:
                    return None

                content_type = (
                    response.headers.get(
                        "Content-Type",
                        ""
                    ).lower()
                )

                if "image" not in content_type:
                    return None

                data = await response.read()

        # Telegram limit safety
        if not (
            1000
            < len(data)
            <= 15 * 1024 * 1024
        ):

            return None

        if (
            "jpeg" in content_type
            or "jpg" in content_type
        ):

            extension = ".jpg"

        elif "webp" in content_type:

            extension = ".webp"

        else:

            extension = ".png"

        path = Path(
            "gamefa_news_image"
            + extension
        )

        path.write_bytes(
            data
        )

        return path

    except Exception as error:

        log.warning(
            "Image download error: %s",
            error
        )

        return None


# ============================================================
# WEB IMAGE SEARCH
# ============================================================

async def search_image(query):

    if not query:
        return None

    # حذف ایموجی
    query = re.sub(
        r"[🎮🎬📱🟣]",
        "",
        query
    ).strip()

    # محدودیت طول جست‌وجو
    query = query[:250]

    search_url = (
        "https://www.bing.com/images/search"
        "?q="
        + quote_plus(query)
        + "&form=HDRSC2"
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151 Safari/537.36"
    }

    try:

        timeout = aiohttp.ClientTimeout(
            total=25
        )

        async with aiohttp.ClientSession(
            headers=headers,
            timeout=timeout
        ) as session:

            async with session.get(
                search_url
            ) as response:

                if response.status != 200:
                    return None

                raw = await response.text(
                    errors="ignore"
                )

        soup = BeautifulSoup(
            raw,
            "html.parser"
        )

        candidates = []

        # ----------------------------------------------------
        # Bing metadata
        # ----------------------------------------------------

        for item in soup.select(
            "a.iusc"
        ):

            metadata = item.get(
                "m"
            )

            if not metadata:
                continue

            try:

                info = json.loads(
                    metadata
                )

                image_url = (
                    info.get("murl")
                    or info.get("turl")
                )

                if image_url:

                    candidates.append(
                        image_url
                    )

            except Exception:
                continue

        # ----------------------------------------------------
        # Fallback
        # ----------------------------------------------------

        if not candidates:

            for image in soup.find_all(
                "img"
            ):

                src = (
                    image.get("src")
                    or image.get("data-src")
                )

                if (
                    src
                    and src.startswith(
                        "http"
                    )
                ):

                    candidates.append(
                        src
                    )

        # حذف تکراری
        candidates = list(
            dict.fromkeys(
                candidates
            )
        )

        # فقط 8 نتیجه
        candidates = candidates[:8]

        for image_url in candidates:

            path = await download_image(
                image_url
            )

            if path:

                log.info(
                    "Web image found: %s",
                    image_url
                )

                return path

    except Exception as error:

        log.warning(
            "Image search error: %s",
            error
        )

    return None


# ============================================================
# FIND IMAGE
# ============================================================

async def find_best_image(
    source_image,
    title,
    body
):

    # --------------------------------------------------------
    # 1. IMAGE FROM SOURCE
    # --------------------------------------------------------

    if source_image:

        path = await download_image(
            source_image
        )

        if path:

            log.info(
                "Using source image."
            )

            return path

    # --------------------------------------------------------
    # 2. SEARCH BY TITLE
    # --------------------------------------------------------

    clean_title = re.sub(
        r"^[🎮🎬📱]\s*",
        "",
        title or ""
    ).strip()

    if clean_title:

        log.info(
            "Searching image: %s",
            clean_title
        )

        path = await search_image(
            clean_title
        )

        if path:
            return path

    # --------------------------------------------------------
    # 3. SEARCH BY TITLE + BODY
    # --------------------------------------------------------

    if body:

        query = (
            clean_title
            + " "
            + body[:180]
        )

        path = await search_image(
            query
        )

        if path:
            return path

    # --------------------------------------------------------
    # 4. NO IMAGE
    # --------------------------------------------------------

    log.info(
        "No suitable image found."
    )

    return None


# ============================================================
# PROCESS NEWS
# ============================================================

async def process_news(
    message,
    text
):

    url = extract_url(
        text
    )

    source_image = ""

    article_title = ""

    article_body = ""

    source = text

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    if url:

        await message.answer(
            "⏳ در حال دریافت خبر..."
        )

        article = await fetch_gamefa(
            url
        )

        source_image = article[
            "image"
        ]

        article_title = article[
            "title"
        ]

        article_body = article[
            "body"
        ]

        source = (
            "URL:\n"
            + article["url"]
            + "\n\n"
            "TITLE:\n"
            + article["title"]
            + "\n\n"
            "DESCRIPTION:\n"
            + article["description"]
            + "\n\n"
            "ARTICLE:\n"
            + article["body"]
        )

    # --------------------------------------------------------
    # DUPLICATE CHECK
    # --------------------------------------------------------

    if duplicate(source):

        await message.answer(
            "⚠️ این خبر یا یک خبر بسیار مشابه "
            "قبلاً دریافت شده است."
        )

        return

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    await message.answer(
        "✍️ در حال آماده‌سازی متن خبر..."
    )

    generated = await generate_news(
        source
    )

    post = format_post(
        generated
    )

    if not post:

        raise RuntimeError(
            "متن تولیدشده خالی است."
        )

    # --------------------------------------------------------
    # TITLE FOR IMAGE SEARCH
    # --------------------------------------------------------

    plain_post = re.sub(
        r"<[^>]+>",
        "",
        post
    )

    post_lines = [
        x.strip()
        for x in plain_post.splitlines()
        if x.strip()
    ]

    generated_title = (
        post_lines[0]
        if post_lines
        else article_title
    )

    generated_body = (
        " ".join(
            post_lines[1:]
        )
        if len(post_lines) > 1
        else article_body
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    await message.answer(
        "🖼 در حال بررسی تصویر خبر..."
    )

    image_path = await find_best_image(
        source_image,
        generated_title,
        generated_body
    )

    # --------------------------------------------------------
    # MEMORY
    # --------------------------------------------------------

    memory.append(
        {
            "source": source[:16000],
            "post": post,
            "url": url or ""
        }
    )

    save_memory()

    # --------------------------------------------------------
    # PREPARE
    # --------------------------------------------------------

    prepared[
        message.from_user.id
    ] = {
        "text": post,
        "image": (
            str(image_path)
            if image_path
            else ""
        )
    }

    # --------------------------------------------------------
    # PREVIEW
    # --------------------------------------------------------

    if image_path:

        try:

            await message.answer_photo(
                FSInputFile(
                    image_path
                ),
                caption=post,
                parse_mode=ParseMode.HTML
            )

        except Exception as error:

            log.warning(
                "Photo preview failed: %s",
                error
            )

            await message.answer(
                post,
                parse_mode=ParseMode.HTML
            )

    else:

        await message.answer(
            post,
            parse_mode=ParseMode.HTML
        )

    await message.answer(
        "✅ خبر آماده انتشار است.\n\n"
        "برای ارسال به کانال:\n"
        "/publish"
    )


# ============================================================
# ROUTER
# ============================================================

router = Router()


# ============================================================
# START
# ============================================================

@router.message(
    Command("start")
)
async def start(
    message: Message
):

    if not is_admin(message):

        await message.answer(
            "این ربات خصوصی است."
        )

        return

    await message.answer(
        "ربات Gamefa آماده است.\n\n"
        "لینک Gamefa یا متن خبر را ارسال کن.\n\n"
        "/publish - انتشار خبر\n"
        "/stats - آمار\n"
        "/clear - پاک کردن حافظه"
    )


# ============================================================
# STATS
# ============================================================

@router.message(
    Command("stats")
)
async def stats(
    message: Message
):

    if not is_admin(message):
        return

    await message.answer(
        "📊 تعداد خبرهای ذخیره‌شده: "
        + str(len(memory))
    )


# ============================================================
# CLEAR
# ============================================================

@router.message(
    Command("clear")
)
async def clear(
    message: Message
):

    if not is_admin(message):
        return

    memory.clear()

    save_memory()

    await message.answer(
        "✅ حافظه ربات پاک شد."
    )


# ============================================================
# PUBLISH
# ============================================================

@router.message(
    Command("publish")
)
async def publish(
    message: Message
):

    if not is_admin(message):
        return

    item = prepared.get(
        message.from_user.id
    )

    if not item:

        await message.answer(
            "❌ هنوز خبری برای انتشار آماده نشده است."
        )

        return

    try:

        image = item.get(
            "image",
            ""
        )

        text = item.get(
            "text",
            ""
        )

        # ----------------------------------------------------
        # WITH IMAGE
        # ----------------------------------------------------

        if (
            image
            and Path(image).exists()
        ):

            try:

                await message.bot.send_photo(
                    CHANNEL_ID,
                    FSInputFile(
                        image
                    ),
                    caption=text,
                    parse_mode=ParseMode.HTML
                )

            except Exception as error:

                log.warning(
                    "Channel photo failed: %s",
                    error
                )

                await message.bot.send_message(
                    CHANNEL_ID,
                    text,
                    parse_mode=ParseMode.HTML
                )

        # ----------------------------------------------------
        # WITHOUT IMAGE
        # ----------------------------------------------------

        else:

            await message.bot.send_message(
                CHANNEL_ID,
                text,
                parse_mode=ParseMode.HTML
            )

        await message.answer(
            "✅ خبر با موفقیت در کانال منتشر شد."
        )

    except Exception as error:

        log.exception(
            "Publish error"
        )

        await message.answer(
            "❌ خطا هنگام انتشار:\n"
            + str(error)[:1500]
        )


# ============================================================
# TEXT MESSAGE
# ============================================================

@router.message(
    F.text
)
async def text_handler(
    message: Message
):

    if not is_admin(message):
        return

    try:

        await process_news(
            message,
            message.text.strip()
        )

    except Exception as error:

        log.exception(
            "Processing error"
        )

        await message.answer(
            "❌ خطا:\n"
            + str(error)[:1500]
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN تنظیم نشده است."
        )

    if not OPENAI_API_KEY:

        raise RuntimeError(
            "OPENAI_API_KEY تنظیم نشده است."
        )

    if not ADMIN_ID:

        raise RuntimeError(
            "ADMIN_ID تنظیم نشده است."
        )

    load_memory()

    bot = Bot(
        BOT_TOKEN
    )

    dispatcher = Dispatcher()

    dispatcher.include_router(
        router
    )

    log.info(
        "Gamefa bot started successfully."
    )

    await dispatcher.start_polling(
        bot,
        allowed_updates=dispatcher.resolve_used_update_types()
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
```
