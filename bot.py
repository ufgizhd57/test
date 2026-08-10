import os,re,json,html,asyncio,logging
from pathlib import Path
from urllib.parse import urljoin,urlparse
import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot,Dispatcher,F,Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message,FSInputFile
from openai import AsyncOpenAI

BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","").strip()
CHANNEL_ID=os.getenv("CHANNEL_ID","@Gamefa_official").strip()
MODEL=os.getenv("OPENAI_MODEL","gpt-5.4-mini").strip()
try: ADMIN_ID=int(os.getenv("ADMIN_ID","0"))
except: ADMIN_ID=0

MEMORY_FILE=Path("news_memory.json")
MAX_MEMORY=1500
memory=[]
prepared={}
log=logging.getLogger("gamefa")
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s")

def load_memory():
    global memory
    try: memory=json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except: memory=[]
def save_memory():
    MEMORY_FILE.write_text(json.dumps(memory[-MAX_MEMORY:],ensure_ascii=False,indent=2),encoding="utf-8")
def norm(s):
    s=re.sub(r"https?://\S+"," ",s or "").lower()
    s=re.sub(r"[^\w\u0600-\u06FF\s]"," ",s)
    return re.sub(r"\s+"," ",s).strip()
def sim(a,b):
    a,b=set(norm(a).split()),set(norm(b).split())
    return len(a&b)/len(a|b) if a and b else 0
def duplicate(s): return any(sim(s,x.get("source",""))>=.82 for x in memory)
def admin(m): return bool(ADMIN_ID and m.from_user and m.from_user.id==ADMIN_ID)
def url_of(s):
    m=re.search(r"https?://[^\s<>()]+",s or "")
    return m.group(0).rstrip(".,)]}") if m else None
def esc(s): return html.escape(s,quote=False)

def format_post(s):
    s=re.sub(r"\*\*(.*?)\*\*",r"\1",s or "",flags=re.S)
    s=re.sub(r"__(.*?)__",r"\1",s,flags=re.S)
    s=re.sub(r"(?im)^\s*(?:🆔\s*)?@Gamefa_official\s*$","",s)
    lines=[x.strip() for x in s.splitlines() if x.strip()]
    if not lines:return ""
    title=lines[0]
    body=" ".join(lines[1:]).strip()
    if not re.match(r"^[🎮🎬📱]",title):
        low=(title+" "+body).lower()
        emoji="🎮" if any(x in low for x in ["game","gaming","playstation","xbox","nintendo","steam","quake","doom","gta","resident evil","بازی","گیم"]) else ("🎬" if any(x in low for x in ["movie","film","series","season","actor","actress","netflix","فیلم","سریال","بازیگر"]) else "📱")
        title=emoji+" "+title
    return f"<b>{esc(title)}</b>"+(f"\n\n{esc(body)}" if body else "")+"\n\n<b>🆔 @Gamefa_official</b>"

async def fetch(url):
    if "gamefa.com" not in urlparse(url).netloc.lower(): raise ValueError("فقط لینک Gamefa پشتیبانی می‌شود.")
    headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"}
    async with aiohttp.ClientSession(headers=headers,timeout=aiohttp.ClientTimeout(total=35)) as s:
        async with s.get(url,allow_redirects=True) as r:
            r.raise_for_status(); final=str(r.url); raw=await r.text(errors="ignore")
    soup=BeautifulSoup(raw,"html.parser")
    for x in soup(["script","style","noscript","svg","nav","footer","form","aside"]): x.decompose()
    h=soup.find("h1"); title=h.get_text(" ",strip=True) if h else (soup.title.get_text(" ",strip=True) if soup.title else "")
    desc=""
    for a in [{"name":"description"},{"property":"og:description"},{"name":"twitter:description"}]:
        m=soup.find("meta",attrs=a)
        if m and m.get("content"): desc=m["content"].strip(); break
    image=""
    for a in [{"property":"og:image"},{"name":"twitter:image"},{"property":"og:image:url"}]:
        m=soup.find("meta",attrs=a)
        if m and m.get("content"): image=urljoin(final,m["content"].strip()); break
    article=soup.find("article") or soup
    ps=article.find_all(["p","h2","h3"])
    body="\n".join(re.sub(r"\s+"," ",p.get_text(" ",strip=True)) for p in ps if len(p.get_text(" ",strip=True))>=35)[:24000]
    return {"url":final,"title":title,"desc":desc,"body":body,"image":image}

PROMPT="""تو ویراستار خبر کانال Gamefa هستی.
از منبع داده‌شده یک پست فارسی آماده انتشار بساز.
- خط اول فقط تیتر کوتاه و خبری باشد و با فارسی شروع شود.
- بعد از تیتر فقط یک پاراگراف خبری.
- متن روان و خلاصه اما کامل باشد.
- اطلاعاتی که در منبع نیست اختراع نکن.
- نام بازی‌ها، فیلم‌ها، شرکت‌ها و افراد با نام انگلیسی اصلی حفظ شود.
- Markdown/HTML، لینک، منبع و امضا تولید نکن.
- خبر بازی با 🎮، فیلم/سریال با 🎬 و فناوری/AI/سخت‌افزار با 📱 شروع شود.
خروجی فقط تیتر و یک پاراگراف باشد."""

async def ai(source):
    c=AsyncOpenAI(api_key=OPENAI_API_KEY)
    r=await c.responses.create(model=MODEL,instructions=PROMPT,input=source,max_output_tokens=1000)
    return (r.output_text or "").strip()

async def image_file(url):
    if not url:return None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),headers={"User-Agent":"Mozilla/5.0"}) as s:
            async with s.get(url) as r:
                if r.status!=200 or "image" not in r.headers.get("Content-Type",""):return None
                data=await r.read()
        if not 1000<len(data)<=15*1024*1024:return None
        ext=".jpg" if "jpeg" in r.headers.get("Content-Type","") or "jpg" in r.headers.get("Content-Type","") else ".png"
        p=Path("news_image"+ext);p.write_bytes(data);return p
    except Exception: return None

async def process(m,text):
    u=url_of(text); image=""; source=text
    if u:
        await m.answer("⏳ در حال خواندن خبر و ساخت متن...")
        a=await fetch(u); image=a["image"]
        source=f"URL: {a['url']}\nTITLE: {a['title']}\nDESCRIPTION: {a['desc']}\nARTICLE:\n{a['body']}"
    if duplicate(source):
        await m.answer("⚠️ این خبر یا یک خبر بسیار مشابه قبلاً دریافت شده است.");return
    post=format_post(await ai(source))
    if not post: raise RuntimeError("متن تولیدشده خالی است.")
    p=await image_file(image) if image else None
    prepared[m.from_user.id]={"text":post,"image":str(p) if p else ""}
    memory.append({"source":source[:16000],"post":post,"url":u or ""});save_memory()
    if p:
        try: await m.answer_photo(FSInputFile(p),caption=post,parse_mode=ParseMode.HTML)
        except: await m.answer(post,parse_mode=ParseMode.HTML)
    else: await m.answer(post,parse_mode=ParseMode.HTML)
    await m.answer("✅ آماده انتشار است. برای ارسال به کانال /publish را بفرست.")

router=Router()
@router.message(Command("start"))
async def start(m:Message):
    if not admin(m):return await m.answer("این ربات خصوصی است.")
    await m.answer("ربات Gamefa آماده است.\n\nلینک Gamefa یا متن خبر را بفرست.\n/publish انتشار آخرین خبر\n/stats آمار\n/clear پاک‌کردن حافظه")
@router.message(Command("stats"))
async def stats(m:Message):
    if admin(m): await m.answer(f"خبرهای ذخیره‌شده: {len(memory)}")
@router.message(Command("clear"))
async def clear(m:Message):
    if not admin(m):return
    memory.clear();save_memory();await m.answer("✅ حافظه پاک شد.")
@router.message(Command("publish"))
async def publish(m:Message):
    if not admin(m):return
    x=prepared.get(m.from_user.id)
    if not x:return await m.answer("❌ خبری برای انتشار آماده نیست.")
    try:
        if x["image"] and Path(x["image"]).exists():
            try: await m.bot.send_photo(CHANNEL_ID,FSInputFile(x["image"]),caption=x["text"],parse_mode=ParseMode.HTML)
            except: await m.bot.send_message(CHANNEL_ID,x["text"],parse_mode=ParseMode.HTML)
        else: await m.bot.send_message(CHANNEL_ID,x["text"],parse_mode=ParseMode.HTML)
        await m.answer("✅ خبر در کانال منتشر شد.")
    except Exception as e: await m.answer("❌ خطای انتشار:\n"+str(e)[:1200])
@router.message(F.text)
async def text(m:Message):
    if not admin(m):return
    try: await process(m,m.text.strip())
    except Exception as e:
        log.exception("process error");await m.answer("❌ خطا:\n"+str(e)[:1500])

async def main():
    if not BOT_TOKEN:raise RuntimeError("BOT_TOKEN تنظیم نشده است.")
    if not OPENAI_API_KEY:raise RuntimeError("OPENAI_API_KEY تنظیم نشده است.")
    if not ADMIN_ID:raise RuntimeError("ADMIN_ID تنظیم نشده است.")
    load_memory();bot=Bot(BOT_TOKEN);dp=Dispatcher();dp.include_router(router)
    log.info("Gamefa bot started")
    await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())

if __name__=="__main__":asyncio.run(main())
