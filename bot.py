import os
import re
import json
import html
import base64
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

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()

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
        os.getenv(
            "ADMIN_ID",
            "0"
        )
    )
except Exception:
    ADMIN_ID = 0


MEMORY_FILE = Path(
    "news_memory.json"
)

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

log = logging.getLogger(
    "gamefa"
)


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

        if not isinstance(
            memory,
            list
        ):
            memory = []

    except Exception:
        memory = []


def save_memory():

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
        return 0.0

    return len(
        a & b
    ) / len(
        a | b
    )


def duplicate(text):

    for item in memory:

        old_source = item.get(
            "source",
            ""
        )

        if similarity(
            text,
            old_source
        ) >= 0.82:

            return True

    return False


# ============================================================
# ADMIN
# ============================================================

def is_admin(message):

    return bool(
        ADMIN_ID
        and message.from_user
        and message.from_user.id == ADMIN_ID
    )


# ============================================================
# URL
# ============================================================

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


# ============================================================
# HTML
# ============================================================

def escape_html(text):

    return html.escape(
        text or "",
        quote=False
    )


# ============================================================
# PERSIAN START
# ============================================================

PERSIAN_RE = re.compile(
    r"[\u0600-\u06FF]"
)


def starts_with_persian(text):

    if not text:
        return False

    clean = text.strip()

    clean = re.sub(
        r"^[🎮🎬📱🟣\s]+",
        "",
        clean
    )

    if not clean:
        return False

    first = clean[0]

    return bool(
        PERSIAN_RE.search(
            first
        )
    )


def make_persian_start(
    text,
    is_title=False
):

    if not text:
        return text

    text = text.strip()

    if starts_with_persian(
        text
    ):
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

    # حذف Markdown
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
        r"`(.*?)`",
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

    title = re.sub(
        r"^[🎮🎬📱]\s*",
        "",
        title
    ).strip()

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

        line = re.sub(
            r"^\s*🟣\s*",
            "",
            line
        ).strip()

        if not line:
            continue

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

    gaming_words = [
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
        "halo",
        "resident evil",
        "assassin",
        "call of duty",
        "spider-man",
        "spiderman"
    ]

    movie_words = [
        "فیلم",
        "سریال",
        "بازیگر",
        "سینما",
        "movie",
        "film",
        "series",
        "season",
        "actor",
        "actress",
        "netflix",
        "hbo",
        "amazon prime",
        "disney",
        "squid game"
    ]

    if any(
        word in full_text
        for word in gaming_words
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
    # FINAL
    # ========================================================

    title = (
        category
        + " "
        + title
    )

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
# GAMEFA ARTICLE
# ============================================================

async def fetch_gamefa(url):

    parsed = urlparse(
        url
    )

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

    # حذف عناصر اضافی
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

    h1 = soup.find(
        "h1"
    )

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

    # ========================================================
    # SOURCE IMAGE
    # ========================================================

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

    # ========================================================
    # BODY
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


# ============================================================
# AI NEWS
# ============================================================

PROMPT = """
تو ویراستار حرفه‌ای اخبار کانال Gamefa هستی.

از اطلاعات داده‌شده یک پست فارسی آماده انتشار بساز.

قوانین:

1. خط اول فقط تیتر باشد.

2. تیتر حتماً با فارسی شروع شود.

3. تیتر نباید با نام انگلیسی شروع شود.

غلط:
Netflix نسخه آمریکایی Squid Game را...

درست:
نتفلیکس نسخه آمریکایی Squid Game را...

4. متن خبر کاملاً فارسی و روان باشد.

5. ابتدای هر بند حتماً فارسی باشد.

6. هیچ بند را با نام انگلیسی شروع نکن.

غلط:
David Fincher قرار است...

درست:
دیوید فینچر قرار است...

یا:
براساس گزارش‌ها، David Fincher قرار است...

7. نام‌های انگلیسی را داخل جمله حفظ کن.

8. اطلاعات ساختگی اضافه نکن.

9. خروجی فقط تیتر و متن خبر باشد.

10. Markdown تولید نکن.

11. HTML تولید نکن.

12. لینک تولید نکن.

13. @Gamefa_official تولید نکن.

14. ایموجی 🟣 تولید نکن.

15. برای بازی‌ها تیتر با 🎮 شروع شود.

16. برای فیلم و سریال تیتر با 🎬 شروع شود.

17. برای فناوری، هوش مصنوعی، موبایل و سخت‌افزار تیتر با 📱 شروع شود.

18. بعد از ایموجی نیز اولین کلمه واقعی تیتر باید فارسی باشد.

خروجی:

تیتر

متن خبر
"""


async def generate_news(
    source
):

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY
    )

    response = await client.responses.create(
        model=MODEL,
        instructions=PROMPT,
        input=source,
        max_output_tokens=1400
    )

    return (
        response.output_text
        or ""
    ).strip()


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

async def download_image(
    url
):

    if not url:
        return None

    try:

        headers = {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151 Safari/537.36",

            "Accept":
                "image/avif,image/webp,image/apng,"
                "image/svg+xml,image/*,*/*;q=0.8"
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

        # رد تصاویر بسیار کوچک
        if len(data) < 15 * 1024:
            return None

        # محدودیت حجم
        if len(data) > 15 * 1024 * 1024:
            return None

        if (
            "jpeg" in content_type
            or "jpg" in content_type
        ):

            extension = ".jpg"

        elif "webp" in content_type:

            extension = ".webp"

        elif "png" in content_type:

            extension = ".png"

        else:

            return None

        path = Path(
            "gamefa_image"
            + extension
        )

        # جلوگیری از استفاده از فایل قبلی
        if path.exists():

            try:
                path.unlink()
            except Exception:
                pass

        path.write_bytes(
            data
        )

        return path

    except Exception as error:

        log.warning(
            "Image download failed: %s",
            error
        )

        return None


# ============================================================
# BING IMAGE SEARCH
# ============================================================

async def image_search_candidates(
    query
):

    if not query:
        return []

    query = re.sub(
        r"[🎮🎬📱🟣]",
        "",
        query
    ).strip()

    query = re.sub(
        r"\s+",
        " ",
        query
    )

    query = query[:220]

    search_url = (
        "https://www.bing.com/images/search"
        "?q="
        + quote_plus(query)
        + "&form=HDRSC2"
        + "&first=1"
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151 Safari/537.36",

        "Accept-Language":
            "en-US,en;q=0.9"
    }

    candidates = []

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
                    return []

                raw = await response.text(
                    errors="ignore"
                )

        soup = BeautifulSoup(
            raw,
            "html.parser"
        )

        # ====================================================
        # Bing JSON
        # ====================================================

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

                page_url = info.get(
                    "purl",
                    ""
                )

                title = info.get(
                    "t",
                    ""
                )

                if image_url:

                    candidates.append(
                        {
                            "image": image_url,
                            "page": page_url,
                            "title": title
                        }
                    )

            except Exception:
                continue

    except Exception as error:

        log.warning(
            "Bing search failed: %s",
            error
        )

    # ========================================================
    # Remove duplicates
    # ========================================================

    unique = []

    seen = set()

    for item in candidates:

        image_url = item[
            "image"
        ]

        if image_url in seen:
            continue

        seen.add(
            image_url
        )

        unique.append(
            item
        )

    return unique[:15]


# ============================================================
# IMAGE SEARCH QUERIES
# ============================================================

def build_image_queries(
    title,
    body
):

    title = re.sub(
        r"^[🎮🎬📱]\s*",
        "",
        title or ""
    ).strip()

    body = body or ""

    queries = []

    # --------------------------------------------------------
    # Exact title
    # --------------------------------------------------------

    if title:

        queries.append(
            title + " official"
        )

    # --------------------------------------------------------
    # English entities
    # --------------------------------------------------------

    english_terms = re.findall(
        r"[A-Za-z][A-Za-z0-9'’\- ]{2,}",
        title
    )

    if english_terms:

        english_query = " ".join(
            english_terms
        ).strip()

        if english_query:

            queries.append(
                english_query
                + " official"
            )

            queries.append(
                english_query
                + " news"
            )

    # --------------------------------------------------------
    # Title + news
    # --------------------------------------------------------

    if title:

        queries.append(
            title
            + " news"
        )

    # --------------------------------------------------------
    # Title + body
    # --------------------------------------------------------

    if body and title:

        clean_body = re.sub(
            r"\s+",
            " ",
            body
        ).strip()

        queries.append(
            title
            + " "
            + clean_body[:100]
        )

    # --------------------------------------------------------
    # Unique
    # --------------------------------------------------------

    result = []

    seen = set()

    for query in queries:

        query = query.strip()

        if not query:
            continue

        key = query.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            query
        )

    return result[:5]


# ============================================================
# AI IMAGE SELECTION
# ============================================================

async def choose_best_image(
    title,
    body,
    candidates
):

    if not candidates:
        return None

    if not OPENAI_API_KEY:

        log.warning(
            "OPENAI_API_KEY unavailable for image selection."
        )

        return None

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY
    )

    content = [
        {
            "type": "input_text",
            "text": f"""
تو انتخاب‌کننده تصویر برای کانال خبری Gamefa هستی.

عنوان خبر:
{title}

متن خبر:
{body[:3000]}

تصاویر کاندید را بررسی کن.

معیارها:

- تصویر باید مستقیماً به موضوع خبر مرتبط باشد.
- اگر خبر درباره یک بازی است، تصویر باید همان بازی یا شخصیت/رویداد مربوط به آن باشد.
- اگر خبر درباره فیلم یا سریال است، تصویر باید همان فیلم/سریال یا افراد مرتبط با خبر باشد.
- اگر خبر درباره یک شرکت است، تصویر باید به همان شرکت یا محصول مرتبط باشد.
- تصویر باید برای انتشار خبری مناسب باشد.
- تصاویر کاملاً نامرتبط را رد کن.
- لوگوی صرف را ترجیح نده.
- آواتار و عکس پروفایل را رد کن.
- تصاویر تبلیغاتی نامرتبط را رد کن.
- فن‌آرت نامرتبط را رد کن.
- اگر چند تصویر مرتبط هستند، باکیفیت‌ترین و خبری‌ترین تصویر را انتخاب کن.
- اگر هیچ تصویر مناسبی وجود ندارد، NO_IMAGE بده.

فقط JSON معتبر برگردان:

{{
    "best": 1,
    "score": 8,
    "reason": "..."
}}

best شماره تصویر است و از 1 شروع می‌شود.

اگر هیچ تصویر مناسب نیست:

{{
    "best": "NO_IMAGE",
    "score": 0,
    "reason": "..."
}}
"""
        }
    ]

    valid_count = 0

    for index, item in enumerate(
        candidates,
        start=1
    ):

        try:

            path = Path(
                item["path"]
            )

            data = path.read_bytes()

            encoded = base64.b64encode(
                data
            ).decode(
                "utf-8"
            )

            suffix = (
                path.suffix
                .lower()
            )

            if suffix == ".jpg":

                mime = "image/jpeg"

            elif suffix == ".webp":

                mime = "image/webp"

            else:

                mime = "image/png"

            content.append(
                {
                    "type": "input_text",
                    "text":
                        f"IMAGE {index}\n"
                        f"Search result title: "
                        f"{item.get('search_title', '')}\n"
                        f"Source page: "
                        f"{item.get('page', '')}"
                }
            )

            content.append(
                {
                    "type": "input_image",
                    "image_url":
                        f"data:{mime};base64,{encoded}"
                }
            )

            valid_count += 1

        except Exception as error:

            log.warning(
                "Could not prepare image for AI: %s",
                error
            )

    if valid_count == 0:
        return None

    try:

        response = await client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": content
                }
            ],
            max_output_tokens=300
        )

        result_text = (
            response.output_text
            or ""
        ).strip()

        log.info(
            "Image AI response: %s",
            result_text[:1000]
        )

        match = re.search(
            r"\{.*\}",
            result_text,
            flags=re.S
        )

        if not match:
            return None

        result = json.loads(
            match.group(0)
        )

        best = result.get(
            "best"
        )

        if str(best).upper() == "NO_IMAGE":

            log.info(
                "AI rejected all candidate images."
            )

            return None

        try:

            best = int(best)

        except Exception:

            return None

        try:

            score = float(
                result.get(
                    "score",
                    0
                )
            )

        except Exception:

            score = 0

        # کمتر از 6 یعنی ارتباط کافی نیست
        if score < 6:

            log.info(
                "Image score too low: %.1f",
                score
            )

            return None

        if not (
            1
            <= best
            <= len(candidates)
        ):

            return None

        selected = candidates[
            best - 1
        ]

        log.info(
            "Selected image %s | score %.1f | %s",
            best,
            score,
            result.get(
                "reason",
                ""
            )
        )

        return selected["path"]

    except Exception as error:

        log.warning(
            "AI image selection failed: %s",
            error
        )

        return None


# ============================================================
# SMART IMAGE FINDER
# ============================================================

async def find_best_image(
    source_image,
    title,
    body
):

    # ========================================================
    # 1. ORIGINAL ARTICLE IMAGE
    # ========================================================

    if source_image:

        log.info(
            "Trying original article image."
        )

        original = await download_image(
            source_image
        )

        if original:

            log.info(
                "Using original Gamefa image."
            )

            return original

    # ========================================================
    # 2. BUILD SEARCH QUERIES
    # ========================================================

    queries = build_image_queries(
        title,
        body
    )

    log.info(
        "Image queries: %s",
        queries
    )

    # ========================================================
    # 3. SEARCH
    # ========================================================

    all_candidates = []

    seen = set()

    for query in queries:

        results = await image_search_candidates(
            query
        )

        for item in results:

            image_url = item[
                "image"
            ]

            if image_url in seen:
                continue

            seen.add(
                image_url
            )

            path = await download_image(
                image_url
            )

            if not path:
                continue

            item["path"] = str(
                path
            )

            item["search_title"] = (
                item.get(
                    "title",
                    ""
                )
                or query
            )

            all_candidates.append(
                item
            )

            if len(
                all_candidates
            ) >= 10:

                break

        if len(
            all_candidates
        ) >= 10:

            break

    # ========================================================
    # 4. NOTHING FOUND
    # ========================================================

    if not all_candidates:

        log.info(
            "No image candidates found."
        )

        return None

    log.info(
        "Found %d image candidates.",
        len(all_candidates)
    )

    # ========================================================
    # 5. AI CHOICE
    # ========================================================

    selected = await choose_best_image(
        title,
        body,
        all_candidates
    )

    selected_path = (
        str(selected)
        if selected
        else ""
    )

    # ========================================================
    # 6. DELETE UNUSED
    # ========================================================

    for item in all_candidates:

        path = Path(
            item["path"]
        )

        if (
            path.exists()
            and str(path)
            != selected_path
        ):

            try:

                path.unlink()

            except Exception:
                pass

    # ========================================================
    # 7. RESULT
    # ========================================================

    if selected:

        return Path(
            selected
        )

    log.info(
        "No image passed relevance check."
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

    # ========================================================
    # URL
    # ========================================================

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
            + "TITLE:\n"
            + article["title"]
            + "\n\n"
            + "DESCRIPTION:\n"
            + article["description"]
            + "\n\n"
            + "ARTICLE:\n"
            + article["body"]
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
    # AI NEWS
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
    # TEXT FOR IMAGE SEARCH
    # ========================================================

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

    generated_title = re.sub(
        r"^[🎮🎬📱]\s*",
        "",
        generated_title
    ).strip()

    generated_title = re.sub(
        r"^🟣\s*",
        "",
        generated_title
    ).strip()

    # ========================================================
    # IMAGE
    # ========================================================

    await message.answer(
        "🖼 در حال انتخاب بهترین تصویر..."
    )

    image_path = await find_best_image(
        source_image,
        generated_title,
        generated_body
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
        + str(
            len(memory)
        )
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

                await message.bot.send_message(
                    CHANNEL_ID,
                    text,
                    parse_mode=ParseMode.HTML
                )

        # ====================================================
        # WITHOUT IMAGE
        # ====================================================

        else:

            await message.bot.send_message(
                CHANNEL_ID,
                text,
                parse_mode=ParseMode.HTML
            )

        # حذف خبر آماده‌شده
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
