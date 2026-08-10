import os
import re
import json
import html
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse, urljoin

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

MEMORY_FILE = Path("news_memory.json")

MAX_MEMORY = 1500

memory = []

prepared = {}

# ============================================================

# LOGGING

# ============================================================

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("gamefa")

# ============================================================

# MEMORY

# ============================================================

def load_memory():

```
global memory

try:

    if not MEMORY_FILE.exists():
        memory = []
        return

    memory = json.loads(
        MEMORY_FILE.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(memory, list):
        memory = []

except Exception as error:

    log.warning(
        "Memory load error: %s",
        error
    )

    memory = []
```

def save_memory():

```
try:

    MEMORY_FILE.write_text(
        json.dumps(
            memory[-MAX_MEMORY:],
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

except Exception as error:

    log.warning(
        "Memory save error: %s",
        error
    )
```

# ============================================================

# TEXT NORMALIZATION

# ============================================================

def norm(text):

```
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
```

def similarity(a, b):

```
a = set(
    norm(a).split()
)

b = set(
    norm(b).split()
)

if not a or not b:
    return 0

return len(
    a & b
) / len(
    a | b
)
```

def duplicate(text):

```
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
```

# ============================================================

# ADMIN

# ============================================================

def is_admin(message):

```
return bool(
    ADMIN_ID
    and message.from_user
    and message.from_user.id == ADMIN_ID
)
```

# ============================================================

# URL

# ============================================================

def extract_url(text):

```
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
```

# ============================================================

# HTML

# ============================================================

def escape_html(text):

```
return html.escape(
    text or "",
    quote=False
)
```

# ============================================================

# PERSIAN DETECTION

# ============================================================

PERSIAN_RE = re.compile(
r"[\u0600-\u06FF]"
)

def starts_with_persian(text):

```
if not text:
    return False

clean = text.strip()

# حذف ایموجی‌های ابتدایی
clean = re.sub(
    r"^[🎮🎬📱🟣🔵🟢🟡🔴⚪⚫\s]+",
    "",
    clean
)

if not clean:
    return False

# پیدا کردن اولین کاراکتر واقعی
for char in clean:

    if char.isalnum():

        return bool(
            PERSIAN_RE.search(char)
        )

return False
```

def make_persian_start(
text,
is_title=False
):

```
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
```

# ============================================================

# FORMAT POST

# ============================================================

def format_post(ai_text):

```
ai_text = ai_text or ""

# --------------------------------------------------------
# حذف Markdown
# --------------------------------------------------------

ai_text = re.sub(
    r"\*\*(.*?)\*\*",
    r"\1",
    ai_text,
    flags=re.S
)

ai_text = re.sub(
    r"__(.*?)__",
    r"\1",
    ai_text,
    flags=re.S
)

ai_text = re.sub(
    r"\*(.*?)\*",
    r"\1",
    ai_text,
    flags=re.S
)

# --------------------------------------------------------
# حذف امضای احتمالی
# --------------------------------------------------------

ai_text = re.sub(
    r"(?im)^\s*(?:🆔\s*)?@Gamefa_official\s*$",
    "",
    ai_text
)

# --------------------------------------------------------
# حذف خطوط خالی
# --------------------------------------------------------

lines = [
    x.strip()
    for x in ai_text.splitlines()
    if x.strip()
]

if not lines:
    return ""

# ========================================================
# TITLE
# ========================================================

title = lines[0]

# حذف ایموجی دسته‌بندی احتمالی
title = re.sub(
    r"^[🎮🎬📱]\s*",
    "",
    title
).strip()

# اطمینان از فارسی بودن ابتدای تیتر
title = make_persian_start(
    title,
    is_title=True
)

# ========================================================
# BODY
# ========================================================

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

    # حذف شماره‌گذاری احتمالی
    line = re.sub(
        r"^\s*[-•]\s*",
        "",
        line
    ).strip()

    # اطمینان از شروع فارسی
    line = make_persian_start(
        line,
        is_title=False
    )

    paragraphs.append(
        "🟣 " + line
    )

# ========================================================
# CATEGORY
# ========================================================

full_text = (
    title
    + " "
    + " ".join(
        body_lines
    )
).lower()

# بازی
game_words = [
    "بازی",
    "گیم",
    "گیمینگ",
    "game",
    "gaming",
    "playstation",
    "xbox",
    "nintendo",
    "steam",
    "doom",
    "gta",
    "resident evil",
    "halo",
    "assassin",
    "far cry",
    "minecraft",
    "fortnite",
    "call of duty",
    "battlefield"
]

# فیلم و سریال
movie_words = [
    "فیلم",
    "سریال",
    "بازیگر",
    "کارگردان",
    "movie",
    "film",
    "series",
    "season",
    "actor",
    "actress",
    "director",
    "netflix",
    "hbo",
    "disney",
    "amazon prime",
    "squid game"
]

if any(
    word in full_text
    for word in game_words
):

    category = "🎮"

elif any(
    word in full_text
    for word in movie_words
):

    category = "🎬"

else:

    category = "📱"

# ========================================================
# FINAL TITLE
# ========================================================

title = (
    category
    + " "
    + title
)

# ========================================================
# FINAL POST
# ========================================================

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
```

# ============================================================

# GAMEFA ARTICLE FETCH

# ============================================================

async def fetch_gamefa(url):

```
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

# ========================================================
# REMOVE UNWANTED ELEMENTS
# ========================================================

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

# ========================================================
# TITLE
# ========================================================

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

# ========================================================
# DESCRIPTION
# ========================================================

description = ""

meta_options = [
    {
        "name": "description"
    },
    {
        "property": "og:description"
    },
    {
        "name": "twitter:description"
    }
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

# ========================================================
# ORIGINAL ARTICLE IMAGE
# ========================================================

image = ""

image_options = [
    {
        "property": "og:image"
    },
    {
        "name": "twitter:image"
    },
    {
        "property": "og:image:url"
    }
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

        candidate = (
            meta["content"]
            .strip()
        )

        if candidate:

            image = urljoin(
                final_url,
                candidate
            )

            break

# ========================================================
# ARTICLE BODY
# ========================================================

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
```

# ============================================================

# AI PROMPT

# ============================================================

PROMPT = """
تو ویراستار حرفه‌ای اخبار کانال Gamefa هستی.

از اطلاعات داده‌شده یک پست فارسی آماده انتشار بساز.

قوانین بسیار مهم:

1. خط اول فقط تیتر خبر باشد.

2. تیتر حتماً با یک کلمه یا عبارت فارسی شروع شود.

3. هیچ‌وقت تیتر را با نام انگلیسی شروع نکن.

مثال غلط:
Netflix نسخه آمریکایی Squid Game را...

مثال درست:
نتفلیکس نسخه آمریکایی Squid Game را...

4. متن خبر کاملاً فارسی، طبیعی و روان باشد.

5. ابتدای هر بند حتماً فارسی باشد.

6. هیچ بند را با نام انگلیسی، نام شرکت، نام بازی، نام فیلم یا نام شخص شروع نکن.

مثال غلط:
David Fincher قرار است...

مثال درست:
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

22. اگر اطلاعات ورودی لینک منبع یا متن انگلیسی داشت، آن را به فارسی روان تبدیل کن.

23. خبر را بیش از حد خلاصه نکن و اطلاعات مهم داده‌شده را حفظ کن.

24. اگر تیتر اصلی با انگلیسی شروع شده بود، آن را به شکل طبیعی فارسی‌سازی کن.

خروجی فقط این ساختار را داشته باشد:

تیتر

متن خبر
"""

# ============================================================

# AI GENERATION

# ============================================================

async def generate_news(source):

```
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
```

# ============================================================

# IMAGE DOWNLOAD

# ============================================================

async def download_image(url):

```
if not url:
    return None

try:

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151 Safari/537.36"
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

                log.warning(
                    "Image HTTP status: %s",
                    response.status
                )

                return None

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                ).lower()
            )

            if "image" not in content_type:

                log.warning(
                    "URL is not an image: %s",
                    content_type
                )

                return None

            data = await response.read()

    # ====================================================
    # SIZE CHECK
    # ====================================================

    if not (
        1000
        < len(data)
        <= 15 * 1024 * 1024
    ):

        log.warning(
            "Invalid image size: %s bytes",
            len(data)
        )

        return None

    # ====================================================
    # EXTENSION
    # ====================================================

    if (
        "jpeg" in content_type
        or "jpg" in content_type
    ):

        extension = ".jpg"

    elif "webp" in content_type:

        extension = ".webp"

    elif "gif" in content_type:

        extension = ".gif"

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
```

# ============================================================

# PROCESS NEWS

# ============================================================

async def process_news(
message,
text
):

```
url = extract_url(
    text
)

source_image = ""

article_title = ""

article_body = ""

source = text

# ========================================================
# LINK / GAMEFA
# ========================================================

if url:

    parsed = urlparse(
        url
    )

    # ----------------------------------------------------
    # فقط Gamefa
    # ----------------------------------------------------

    if (
        "gamefa.com"
        not in parsed.netloc.lower()
    ):

        await message.answer(
            "❌ فعلاً فقط لینک‌های Gamefa پشتیبانی می‌شوند."
        )

        return

    await message.answer(
        "⏳ در حال دریافت خبر از Gamefa..."
    )

    article = await fetch_gamefa(
        url
    )

    source_image = article.get(
        "image",
        ""
    )

    article_title = article.get(
        "title",
        ""
    )

    article_body = article.get(
        "body",
        ""
    )

    source = (
        "URL:\n"
        + article.get(
            "url",
            ""
        )
        + "\n\n"
        + "TITLE:\n"
        + article_title
        + "\n\n"
        + "DESCRIPTION:\n"
        + article.get(
            "description",
            ""
        )
        + "\n\n"
        + "ARTICLE:\n"
        + article_body
    )

# ========================================================
# DUPLICATE
# ========================================================

if duplicate(source):

    await message.answer(
        "⚠️ این خبر یا یک خبر بسیار مشابه "
        "قبلاً دریافت شده است."
    )

    return

# ========================================================
# AI
# ========================================================

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

# ========================================================
# IMAGE
#
# بسیار مهم:
#
# اینجا دیگر هیچ image search وجود ندارد.
#
# اگر مقاله عکس داشته باشد:
#     همان عکس مقاله دانلود می‌شود.
#
# اگر مقاله عکس نداشته باشد:
#     image_path = None
#
# هیچ عکس تصادفی از Bing یا سایت‌های دیگر گرفته نمی‌شود.
# ========================================================

image_path = None

if source_image:

    await message.answer(
        "🖼 تصویر اصلی خبر پیدا شد؛ در حال دریافت..."
    )

    image_path = await download_image(
        source_image
    )

    if image_path:

        log.info(
            "Original article image downloaded."
        )

    else:

        log.info(
            "Original image could not be downloaded. "
            "Text-only mode."
        )

else:

    log.info(
        "Article has no image. "
        "Text-only mode."
    )

# ========================================================
# MEMORY
# ========================================================

memory.append(
    {
        "source": source[:16000],
        "post": post,
        "url": url or ""
    }
)

save_memory()

# ========================================================
# PREPARE
# ========================================================

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

# ========================================================
# PREVIEW
# ========================================================

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

# ========================================================
# READY
# ========================================================

await message.answer(
    "✅ خبر آماده انتشار است.\n\n"
    "برای ارسال به کانال:\n"
    "/publish"
)
```

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

```
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
```

# ============================================================

# STATS

# ============================================================

@router.message(
Command("stats")
)
async def stats(
message: Message
):

```
if not is_admin(message):
    return

await message.answer(
    "📊 تعداد خبرهای ذخیره‌شده: "
    + str(len(memory))
)
```

# ============================================================

# CLEAR

# ============================================================

@router.message(
Command("clear")
)
async def clear(
message: Message
):

```
if not is_admin(message):
    return

memory.clear()

save_memory()

await message.answer(
    "✅ حافظه ربات پاک شد."
)
```

# ============================================================

# PUBLISH

# ============================================================

@router.message(
Command("publish")
)
async def publish(
message: Message
):

```
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

    # ====================================================
    # WITH IMAGE
    # ====================================================

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

            # اگر ارسال عکس شکست خورد،
            # متن به تنهایی ارسال می‌شود.

            await message.bot.send_message(
                CHANNEL_ID,
                text,
                parse_mode=ParseMode.HTML
            )

    # ====================================================
    # TEXT ONLY
    # ====================================================

    else:

        await message.bot.send_message(
            CHANNEL_ID,
            text,
            parse_mode=ParseMode.HTML
        )

    # ====================================================
    # CLEAN PREPARED
    # ====================================================

    prepared.pop(
        message.from_user.id,
        None
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
```

# ============================================================

# TEXT MESSAGE

# ============================================================

@router.message(
F.text
)
async def text_handler(
message: Message
):

```
if not is_admin(message):
    return

try:

    text = (
        message.text
        or ""
    ).strip()

    if not text:

        await message.answer(
            "❌ متن خبر خالی است."
        )

        return

    await process_news(
        message,
        text
    )

except Exception as error:

    log.exception(
        "Processing error"
    )

    await message.answer(
        "❌ خطا:\n"
        + str(error)[:1500]
    )
```

# ============================================================

# MAIN

# ============================================================

async def main():

```
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
    token=BOT_TOKEN
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
```

# ============================================================

# RUN

# ============================================================

if **name** == "**main**":

```
asyncio.run(
    main()
)
