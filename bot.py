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


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
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
except:
    ADMIN_ID = 0


MEMORY_FILE = Path(
    "news_memory.json"
)

MAX_MEMORY = 1500

memory = []
prepared = {}

log = logging.getLogger("gamefa")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =========================
# MEMORY
# =========================

def load_memory():
    global memory

    try:
        memory = json.loads(
            MEMORY_FILE.read_text(
                encoding="utf-8"
            )
        )
    except:
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


# =========================
# TEXT / DUPLICATE
# =========================

def norm(s):
    s = re.sub(
        r"https?://\S+",
        " ",
        s or ""
    ).lower()

    s = re.sub(
        r"[^\w\u0600-\u06FF\s]",
        " ",
        s
    )

    return re.sub(
        r"\s+",
        " ",
        s
    ).strip()


def sim(a, b):
    a = set(norm(a).split())
    b = set(norm(b).split())

    if not a or not b:
        return 0

    return len(a & b) / len(a | b)


def duplicate(s):
    return any(
        sim(
            s,
            x.get("source", "")
        ) >= 0.82
        for x in memory
    )


def admin(m):
    return bool(
        ADMIN_ID
        and m.from_user
        and m.from_user.id == ADMIN_ID
    )


def url_of(s):
    m = re.search(
        r"https?://[^\s<>()]+",
        s or ""
    )

    return (
        m.group(0).rstrip(".,)]}")
        if m
        else None
    )


def esc(s):
    return html.escape(
        s,
        quote=False
    )


# =========================
# FORMAT POST
# =========================

def format_post(s):

    s = s or ""

    # Remove Markdown bold
    s = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        s,
        flags=re.S
    )

    # Remove __bold__
    s = re.sub(
        r"__(.*?)__",
        r"\1",
        s,
        flags=re.S
    )

    # Remove generated Gamefa ID
    s = re.sub(
        r"(?im)^\s*(?:🆔\s*)?@Gamefa_official\s*$",
        "",
        s
    )

    lines = [
        x.strip()
        for x in s.splitlines()
        if x.strip()
    ]

    if not lines:
        return ""

    title = lines[0]

    # Keep paragraph structure
    body_lines = lines[1:]

    # Detect category
    if not re.match(
        r"^[🎮🎬📱]",
        title
    ):

        low = (
            title
            + " "
            + " ".join(body_lines)
        ).lower()

        if any(
            x in low
            for x in [
                "game",
                "gaming",
                "playstation",
                "xbox",
                "nintendo",
                "steam",
                "quake",
                "doom",
                "gta",
                "resident evil",
                "بازی",
                "گیم"
            ]
        ):
            emoji = "🎮"

        elif any(
            x in low
            for x in [
                "movie",
                "film",
                "series",
                "season",
                "actor",
                "actress",
                "netflix",
                "فیلم",
                "سریال",
                "بازیگر"
            ]
        ):
            emoji = "🎬"

        else:
            emoji = "📱"

        title = emoji + " " + title

    paragraphs = []

    for line in body_lines:

        line = re.sub(
            r"^\s*🟣\s*",
            "",
            line
        ).strip()

        if line:
            paragraphs.append(
                "🟣 " + line
            )

    result = (
        f"<b>{esc(title)}</b>"
    )

    if paragraphs:
        result += (
            "\n\n"
            + "\n\n".join(
                esc(x)
                for x in paragraphs
            )
        )

    result += (
        "\n\n"
        "<b>🆔 @Gamefa_official</b>"
    )

    return result


# =========================
# GAMEFA FETCH
# =========================

async def fetch(url):

    if (
        "gamefa.com"
        not in urlparse(url).netloc.lower()
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

    async with aiohttp.ClientSession(
        headers=headers,
        timeout=aiohttp.ClientTimeout(
            total=35
        )
    ) as session:

        async with session.get(
            url,
            allow_redirects=True
        ) as r:

            r.raise_for_status()

            final = str(r.url)

            raw = await r.text(
                errors="ignore"
            )

    soup = BeautifulSoup(
        raw,
        "html.parser"
    )

    for x in soup(
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
        x.decompose()

    h = soup.find("h1")

    title = (
        h.get_text(
            " ",
            strip=True
        )
        if h
        else (
            soup.title.get_text(
                " ",
                strip=True
            )
            if soup.title
            else ""
        )
    )

    desc = ""

    for attrs in [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"}
    ]:

        meta = soup.find(
            "meta",
            attrs=attrs
        )

        if (
            meta
            and meta.get("content")
        ):
            desc = meta[
                "content"
            ].strip()

            break

    image = ""

    for attrs in [
        {"property": "og:image"},
        {"name": "twitter:image"},
        {"property": "og:image:url"}
    ]:

        meta = soup.find(
            "meta",
            attrs=attrs
        )

        if (
            meta
            and meta.get("content")
        ):
            image = urljoin(
                final,
                meta["content"].strip()
            )

            break

    article = (
        soup.find("article")
        or soup
    )

    ps = article.find_all(
        ["p", "h2", "h3"]
    )

    body = "\n".join(
        re.sub(
            r"\s+",
            " ",
            p.get_text(
                " ",
                strip=True
            )
        )
        for p in ps
        if len(
            p.get_text(
                " ",
                strip=True
            )
        ) >= 35
    )[:24000]

    return {
        "url": final,
        "title": title,
        "desc": desc,
        "body": body,
        "image": image
    }


# =========================
# AI
# =========================

PROMPT = """تو ویراستار خبر کانال Gamefa هستی.

از منبع داده‌شده یک پست فارسی آماده انتشار بساز.

قوانین:

- خط اول فقط تیتر کوتاه و خبری باشد.
- تیتر حتماً با متن فارسی شروع شود.
- بعد از تیتر فقط یک پاراگراف خبری بنویس.
- متن روان، طبیعی، خبری و خلاصه اما کامل باشد.
- اطلاعاتی که در منبع نیست اختراع نکن.
- نام بازی‌ها، فیلم‌ها، شرکت‌ها و افراد با نام انگلیسی اصلی حفظ شود.
- Markdown و HTML تولید نکن.
- لینک تولید نکن.
- منبع و امضا تولید نکن.
- @Gamefa_official تولید نکن.
- ایموجی 🟣 تولید نکن.
- خبر بازی با 🎮 شروع شود.
- خبر فیلم و سریال با 🎬 شروع شود.
- خبر فناوری، هوش مصنوعی و سخت‌افزار با 📱 شروع شود.
- خروجی فقط تیتر و یک پاراگراف باشد.
"""


async def ai(source):

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY
    )

    response = await client.responses.create(
        model=MODEL,
        instructions=PROMPT,
        input=source,
        max_output_tokens=1000
    )

    return (
        response.output_text
        or ""
    ).strip()


# =========================
# IMAGE DOWNLOAD
# =========================

async def image_file(url):

    if not url:
        return None

    try:

        headers = {
            "User-Agent":
                "Mozilla/5.0"
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=30
            ),
            headers=headers
        ) as session:

            async with session.get(
                url,
                allow_redirects=True
            ) as r:

                if r.status != 200:
                    return None

                content_type = (
                    r.headers.get(
                        "Content-Type",
                        ""
                    ).lower()
                )

                if "image" not in content_type:
                    return None

                data = await r.read()

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
            ext = ".jpg"

        elif "webp" in content_type:
            ext = ".webp"

        else:
            ext = ".png"

        p = Path(
            "news_image" + ext
        )

        p.write_bytes(data)

        return p

    except Exception as e:

        log.warning(
            "Image download failed: %s",
            e
        )

        return None


# =========================
# WEB IMAGE SEARCH
# =========================

async def search_web_image(query):

    if not query:
        return None

    query = re.sub(
        r"[🎮🎬📱]",
        "",
        query
    ).strip()

    # محدود کردن طول query
    query = query[:250]

    search_url = (
        "https://www.bing.com/images/search?q="
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

        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(
                total=25
            )
        ) as session:

            async with session.get(
                search_url
            ) as r:

                if r.status != 200:
                    return None

                raw = await r.text(
                    errors="ignore"
                )

        soup = BeautifulSoup(
            raw,
            "html.parser"
        )

        candidates = []

        # Bing image results
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

            except:
                continue

        # Fallback: direct image links
        if not candidates:

            for img in soup.find_all(
                "img"
            ):

                src = (
                    img.get("src")
                    or img.get("data-src")
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

        # حذف تکراری‌ها
        candidates = list(
            dict.fromkeys(
                candidates
            )
        )

        # فقط چند نتیجه اول
        candidates = candidates[:8]

        for image_url in candidates:

            p = await image_file(
                image_url
            )

            if p:
                log.info(
                    "Found web image: %s",
                    image_url
                )

                return p

    except Exception as e:

        log.warning(
            "Web image search failed: %s",
            e
        )

    return None


# =========================
# FIND BEST IMAGE
# =========================

async def find_image(
    original_url,
    article_title,
    generated_title,
    body
):

    # -------------------------
    # 1. Source image
    # -------------------------

    if original_url:

        p = await image_file(
            original_url
        )

        if p:
            return p

    # -------------------------
    # 2. Search image
    # -------------------------

    clean_title = re.sub(
        r"^[🎮🎬📱]\s*",
        "",
        generated_title or article_title
    ).strip()

    # استفاده از عنوان + بخش کوچکی
    # از متن برای بهتر شدن جست‌وجو
    search_query = clean_title

    if body:
        search_query += (
            " "
            + body[:180]
        )

    log.info(
        "Searching image for: %s",
        search_query
    )

    p = await search_web_image(
        search_query
    )

    if p:
        return p

    # -------------------------
    # 3. Search only title
    # -------------------------

    if body:

        p = await search_web_image(
            clean_title
        )

        if p:
            return p

    # -------------------------
    # 4. No image
    # -------------------------

    return None


# =========================
# PROCESS NEWS
# =========================

async def process(
    m,
    text
):

    u = url_of(text)

    image = ""

    source = text

    article_title = ""

    article_body = ""

    # -------------------------
    # URL NEWS
    # -------------------------

    if u:

        await m.answer(
            "⏳ در حال خواندن خبر و ساخت متن..."
        )

        article = await fetch(
            u
        )

        image = article[
            "image"
        ]

        article_title = article[
            "title"
        ]

        article_body = article[
            "body"
        ]

        source = (
            f"URL: {article['url']}\n"
            f"TITLE: {article['title']}\n"
            f"DESCRIPTION: {article['desc']}\n"
            f"ARTICLE:\n{article['body']}"
        )

    # -------------------------
    # DUPLICATE
    # -------------------------

    if duplicate(source):

        await m.answer(
            "⚠️ این خبر یا یک خبر بسیار "
            "مشابه قبلاً دریافت شده است."
        )

        return

    # -------------------------
    # AI
    # -------------------------

    ai_result = await ai(
        source
    )

    post = format_post(
        ai_result
    )

    if not post:

        raise RuntimeError(
            "متن تولیدشده خالی است."
        )

    # -------------------------
    # Extract generated title
    # -------------------------

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

    # -------------------------
    # Extract body
    # -------------------------

    generated_body = (
        " ".join(
            post_lines[1:]
        )
        if len(post_lines) > 1
        else article_body
    )

    # -------------------------
    # FIND IMAGE
    # -------------------------

    p = await find_image(
        image,
        article_title,
        generated_title,
        generated_body
    )

    # -------------------------
    # SAVE PREPARED
    # -------------------------

    prepared[
        m.from_user.id
    ] = {
        "text": post,
        "image": (
            str(p)
            if p
            else ""
        )
    }

    memory.append(
        {
            "source": source[:16000],
            "post": post,
            "url": u or ""
        }
    )

    save_memory()

    # -------------------------
    # SEND PREVIEW
    # -------------------------

    if p:

        try:

            await m.answer_photo(
                FSInputFile(p),
                caption=post,
                parse_mode=ParseMode.HTML
            )

        except Exception:

            await m.answer(
                post,
                parse_mode=ParseMode.HTML
            )

    else:

        await m.answer(
            post,
            parse_mode=ParseMode.HTML
        )

    await m.answer(
        "✅ خبر آماده انتشار است.\n"
        "برای ارسال به کانال /publish را بفرست."
    )


# =========================
# ROUTER
# =========================

router = Router()


# =========================
# START
# =========================

@router.message(
    Command("start")
)
async def start(
    m: Message
):

    if not admin(m):

        return await m.answer(
            "این ربات خصوصی است."
        )

    await m.answer(
        "ربات Gamefa آماده است.\n\n"
        "لینک Gamefa یا متن خبر را بفرست.\n\n"
        "/publish انتشار آخرین خبر\n"
        "/stats آمار\n"
        "/clear پاک‌کردن حافظه"
    )


# =========================
# STATS
# =========================

@router.message(
    Command("stats")
)
async def stats(
    m: Message
):

    if admin(m):

        await m.answer(
            f"خبرهای ذخیره‌شده: "
            f"{len(memory)}"
        )


# =========================
# CLEAR
# =========================

@router.message(
    Command("clear")
)
async def clear(
    m: Message
):

    if not admin(m):
        return

    memory.clear()

    save_memory()

    await m.answer(
        "✅ حافظه پاک شد."
    )


# =========================
# PUBLISH
# =========================

@router.message(
    Command("publish")
)
async def publish(
    m: Message
):

    if not admin(m):
        return

    x = prepared.get(
        m.from_user.id
    )

    if not x:

        return await m.answer(
            "❌ خبری برای انتشار آماده نیست."
        )

    try:

        if (
            x["image"]
            and Path(
                x["image"]
            ).exists()
        ):

            try:

                await m.bot.send_photo(
                    CHANNEL_ID,
                    FSInputFile(
                        x["image"]
                    ),
                    caption=x["text"],
                    parse_mode=ParseMode.HTML
                )

            except Exception:

                await m.bot.send_message(
                    CHANNEL_ID,
                    x["text"],
                    parse_mode=ParseMode.HTML
                )

        else:

            await m.bot.send_message(
                CHANNEL_ID,
                x["text"],
                parse_mode=ParseMode.HTML
            )

        await m.answer(
            "✅ خبر در کانال منتشر شد."
        )

    except Exception as e:

        await m.answer(
            "❌ خطای انتشار:\n"
            + str(e)[:1200]
        )


# =========================
# TEXT MESSAGE
# =========================

@router.message(
    F.text
)
async def text(
    m: Message
):

    if not admin(m):
        return

    try:

        await process(
            m,
            m.text.strip()
        )

    except Exception as e:

        log.exception(
            "process error"
        )

        await m.answer(
            "❌ خطا:\n"
            + str(e)[:1500]
        )


# =========================
# MAIN
# =========================

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

    dp = Dispatcher()

    dp.include_router(
        router
    )

    log.info(
        "Gamefa bot started"
    )

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types()
    )


if __name__ == "__main__":
    asyncio.run(main())
