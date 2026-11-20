import os
import asyncio
import random
import re
import time
import unicodedata
from datetime import timedelta
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- RENDER 7/24 UPTIME SUNUCUSU ---
# Not: yerelde yuop 8080 portunu kullandığı için bu sunucu sadece Render'da
# (RENDER ortam değişkeni varken) veya KEEP_ALIVE=1 verilirse başlar.
app = Flask('')


@app.route('/')
def home():
    return "Bot aktif."


def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))


def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()
# -----------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True
intents.voice_states = True


class ClanBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()


bot = ClanBot()

BASVURU_LOG_CHANNEL_ID = 1554563763779272813
WARN_LOG_CHANNEL_ID = 1554563763779272811
VOTE_CHANNEL_ID = 1555619236125220994

# --- AI SAĞLAYICI AYARLARI ---
# Birincil: bu AI (yuop). YUOP_KEY varsa önce o denenir.
YUOP_URL = (os.environ.get("YUOP_URL") or "http://127.0.0.1:8080").rstrip("/")
YUOP_KEY = (os.environ.get("YUOP_KEY") or "").strip()
YUOP_MODEL = (os.environ.get("YUOP_MODEL") or "gemma3:4b").strip()
# Yerel model ilk istekte belleğe yüklenir; bu yüzden süre cömert.
YUOP_TIMEOUT = float(os.environ.get("YUOP_TIMEOUT") or 120)

# Yedek: Groq (bulut). Sadece anahtar varsa kullanılır.
GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
GROQ_MODELS = ["llama-3.1-8b-instant", "openai/gpt-oss-20b"]
GROQ_TIMEOUT = 10

# --- 30 DAKİKALIK SOHBET HAFIZASI (SON 6 MESAJ) ---
user_conversations = {}
MAX_HISTORY = 6


def cleanup_memory():
    now = time.time()
    for user_id in list(user_conversations.keys()):
        recent = [m for m in user_conversations[user_id] if now - m['time'] < 1800]
        if recent:
            user_conversations[user_id] = recent[-MAX_HISTORY:]
        else:
            del user_conversations[user_id]


# --- YETKİ KONTROL FONKSİYONLARI (OWNER + TAM "." ROLÜ) ---
def has_dot_role(member):
    if not member or not hasattr(member, "roles"):
        return False
    return any(role.name.strip() == "." for role in member.roles)


async def get_member_fast(guild, user_id):
    if not guild:
        return None
    member = guild.get_member(user_id)
    if member:
        return member
    try:
        return await guild.fetch_member(user_id)
    except Exception:
        return None


# Rol adlarında emoji, boşluk, nokta, sıfır genişlikli karakter olabilir;
# karşılaştırma için sadece harf/rakam bırakıyoruz ("ㅤMember ✦" -> "member").
def _clean_role_name(name: str) -> str:
    base = unicodedata.normalize("NFKD", (name or "").casefold())
    ascii_name = "".join(ch for ch in base if not unicodedata.combining(ch))
    return "".join(ch for ch in ascii_name if ch.isalnum())


ALLOWED_ROLE_KEYWORDS = (
    "owner", "founder", "coleader", "staff", "moderation", "moderator",
    "admin", "member", "booster", "uye", "yetkili", "yonetici",
)


async def check_user_permission(user, guild=None):
    """Owner, . rolü veya izinli rollerden birine sahip olanlar AI ile konuşabilir."""
    if guild:
        member = await get_member_fast(guild, user.id)
        if not member:
            print(f"Yetki: {user} ({user.id}) sunucuda bulunamadı.", flush=True)
            return False
        if guild.owner_id == member.id or has_dot_role(member):
            return True
        perms = getattr(member, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild):
            return True
        for role in member.roles:
            cleaned = _clean_role_name(role.name)
            if any(k in cleaned for k in ALLOWED_ROLE_KEYWORDS):
                return True
        print(
            f"Yetki reddi: {user} ({user.id}) rolleri = "
            f"{[r.name for r in member.roles]}",
            flush=True,
        )
        return False

    for g in bot.guilds:
        member = await get_member_fast(g, user.id)
        if not member:
            continue
        if g.owner_id == member.id or has_dot_role(member):
            return True
        perms = getattr(member, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild):
            return True
        for role in member.roles:
            cleaned = _clean_role_name(role.name)
            if any(k in cleaned for k in ALLOWED_ROLE_KEYWORDS):
                return True
    return False


async def check_owner_co_leader_staff_or_dot(user, guild):
    if guild.owner_id == user.id:
        return True
    member = await get_member_fast(guild, user.id)
    if member:
        if has_dot_role(member):
            return True
        for role in member.roles:
            r_name = role.name.lower()
            if "owner" in r_name or "co-leader" in r_name or "staff" in r_name:
                return True
    return False


async def check_owner_or_dot(user, guild):
    if guild.owner_id == user.id:
        return True
    member = await get_member_fast(guild, user.id)
    if member:
        if has_dot_role(member):
            return True
        for role in member.roles:
            r_name = role.name.lower()
            if "owner" in r_name:
                return True
    return False


async def check_owner_co_leader_or_dot(user, guild):
    if guild.owner_id == user.id:
        return True
    member = await get_member_fast(guild, user.id)
    if member:
        if has_dot_role(member):
            return True
        for role in member.roles:
            r_name = role.name.lower()
            if "owner" in r_name or "co-leader" in r_name:
                return True
    return False


# --- HAFİF YEDEK ŞAMATA TEPKİLERİ ---
def _fallback_banter(text: str) -> str:
    t = (text or "").lower().strip()
    if re.search(r"[а-яА-ЯёЁ]", text or ""):
        return random.choice([
            "Апишка моргнула, но я всё ещё в строю — давай дальше.",
            "Сервер сейчас на перекуре, но рофлы продолжаются."
        ])
    if t in {"sa", "s.a", "selam", "slm", "merhaba", "naber", "nbr"} or re.search(r"[çğıöşüÇĞİÖŞÜ]", text or "") or any(
        w in t for w in ["sa", "selam", "naber", "lan", "kanka", "klan", "oyun", "ne haber"]
    ):
        return random.choice([
            "Aleykümselam kral, API şu an kahve molasında ama ben buradayım.",
            "Selam kanka, API tarafı tekledi ama klan şamatası kesilmez.",
            "Geldin mi? API bir saniyeliğine fişi çekti, devam et sen."
        ])
    return random.choice([
        "API şu an ufak bir tekledi, klan geyiğine devam.",
        "Sunucu bir anlığına takıldı ama ben buradayım, sıradaki lafı at."
    ])


# --- ASENKRON AI SOHBET MOTORU ---
CLAN_BANTER_PROMPT = (
    "You are a sharp, funny, dry-witted Discord clan buddy hanging out in chat. "
    "You know and understand EVERY language and script on Earth: Turkish, English, Russian, Ukrainian, Azerbaijani, Arabic, Persian, Spanish, Portuguese, German, French, Italian, Dutch, Polish, Hindi, Urdu, Bengali, Indonesian, Japanese, Korean, Chinese, Greek, Hebrew, Swahili, and any other language, dialect, slang, transliteration, or mixed-language message. "
    "You never say you only speak one language and never ask the user to switch languages. "
    "Always reply in the EXACT language of the user's message—even if the message contains profanity, slang, or swear words, still respond in that user's language without switching languages or lecturing. "
    "If the message mixes languages, use the language of the user's main sentence and mirror their slang and tone. "
    "Never act like an encyclopedia, teacher, or customer support bot. Do not give long explanations or facts unless jokingly roasted. "
    "Keep replies short, snappy, playful, and comedic—like real clan banter, jokes, and quick comebacks. "
    "Never scold, lecture, or get offended by swearing or trash talk; answer with dry humor or witty comeback banter."
)


LANG_NAMES = {
    "tr": "Turkish",
    "en": "English",
    "ru": "Russian",
    "uk": "Ukrainian",
    "az": "Azerbaijani",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "ar": "Arabic",
    "fa": "Persian",
    "hi": "Hindi",
    "el": "Greek",
    "he": "Hebrew",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}


def detect_lang(text: str):
    """Metnin yazı sistemine bakarak dil tahmini yapar; emin değilse None."""
    t = (text or "").lower()
    if not t.strip():
        return None
    if re.search(r"[\u0400-\u04ff]", t):
        return "uk" if re.search(r"[іїєґ]", t) else "ru"
    if re.search(r"[\u0600-\u06ff]", t):
        return "fa" if re.search(r"[پچژگ]", t) else "ar"
    if re.search(r"[\u4e00-\u9fff]", t):
        return "zh"
    if re.search(r"[\u3040-\u30ff]", t):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", t):
        return "ko"
    if re.search(r"[\u0900-\u097f]", t):
        return "hi"
    if re.search(r"[\u0370-\u03ff]", t):
        return "el"
    if re.search(r"[\u0590-\u05ff]", t):
        return "he"
    if re.search(r"[çğıöşü]", t):
        return "tr"
    if re.search(
        r"(^|\s)(sa|selam|slm|merhaba|naber|nbr|kanka|lan|kardeşim|nasılsın|oyun|bugün|yarın|geldin|gidiyoruz)(\s|$)",
        t,
    ):
        return "tr"
    if re.search(
        r"(^|\s)(the|and|you|your|what|how|is|are|was|we|they|tonight|bro|dude|hello|hi|hey|thanks|please|playing|game|going|lol)(\s|$)",
        t,
    ):
        return "en"
    return None


async def _post_yuop(session: aiohttp.ClientSession, model: str, messages: list) -> str:
    """Bu AI (yuop) üzerinden yanıt alır."""
    headers = {
        "Authorization": f"Bearer {YUOP_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.85, "num_predict": 220},
    }
    async with session.post(f"{YUOP_URL}/api/chat", headers=headers, json=payload) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {data.get('error') or data}")
        content = ((data.get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("Boş yanıt (yuop)")
        return content


async def _post_groq(session: aiohttp.ClientSession, model: str, messages: list) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 220,
    }
    async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload) as resp:
        data = await resp.json()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} ({model}): {data}")
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Choices boş ({model})")
        raw_content = (choices[0].get("message") or {}).get("content")
        content = (raw_content or "").strip()
        if not content:
            raise RuntimeError(f"Boş yanıt ({model})")
        return content


async def ask_clan_ai(history: list, user_text: str) -> str:
    if not YUOP_KEY and not GROQ_API_KEY:
        raise RuntimeError("YUOP_KEY veya GROQ_API_KEY tanımlı değil.")

    system_prompt = CLAN_BANTER_PROMPT
    detected = detect_lang(user_text)
    if detected and detected in LANG_NAMES:
        ad = LANG_NAMES[detected]
        system_prompt += (
            f"\n\nIMPORTANT: The user's latest message is in {ad}. "
            f"Write your entire reply in {ad} only. Do not translate it into another language."
        )

    messages = [{"role": "system", "content": system_prompt}]
    for m in history[-MAX_HISTORY:]:
        m_content = (m.get("content") or "").strip()
        if m_content:
            messages.append({
                "role": m["role"],
                "content": m_content
            })
    messages.append({"role": "user", "content": user_text})

    last_error = None
    timeout = aiohttp.ClientTimeout(total=YUOP_TIMEOUT)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1) Bu AI (yuop) — yerel model
        if YUOP_KEY:
            try:
                reply = await _post_yuop(session, YUOP_MODEL, messages)
                if reply:
                    return reply
            except Exception as e:
                last_error = e
                print(f"yuop yanıt vermedi, yedeğe geçiliyor: {e}", flush=True)

        # 2) Yedek: Groq
        if GROQ_API_KEY:
            groq_timeout = aiohttp.ClientTimeout(total=GROQ_TIMEOUT)
            async with aiohttp.ClientSession(timeout=groq_timeout) as groq_session:
                for model in GROQ_MODELS:
                    try:
                        reply = await _post_groq(groq_session, model, messages)
                        if reply and reply.strip():
                            return reply.strip()
                    except Exception as e:
                        last_error = e
                        continue

    raise RuntimeError(f"AI yanıt vermedi: {last_error}")


class ReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept and Open Poll", style=discord.ButtonStyle.green, custom_id="accept_app")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        if not interaction.user.guild_permissions.administrator and not (member and has_dot_role(member)):
            await interaction.response.send_message("Yetkin yok.", ephemeral=True)
            return

        vote_channel = bot.get_channel(VOTE_CHANNEL_ID)
        if not vote_channel:
            await interaction.response.send_message("Oylama kanalı bulunamadı.", ephemeral=True)
            return

        old_content = interaction.message.content
        vote_msg_content = old_content.replace("📥 **New ClanJoin Application Received!**", "📋 **New ClanJoin Application Vote!**")

        try:
            msg = await vote_channel.send(vote_msg_content, embeds=interaction.message.embeds)
            await msg.add_reaction("👍")
            await msg.add_reaction("❌")

            button.disabled = True
            button.label = "Kabul Edildi"
            await interaction.message.edit(view=self, embeds=interaction.message.embeds)
            await interaction.response.send_message("Tamamdır.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.event
async def on_ready():
    print(f'{bot.user.name} aktif.', flush=True)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        allowed = await check_user_permission(message.author, message.guild)
        if not allowed:
            return

        text = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        msg = text.lower()

        # 1. Matematik Hesaplama Modülü
        word_to_num = {
            'sıfır': '0', 'bir': '1', 'iki': '2', 'üç': '3', 'dört': '4',
            'beş': '5', 'altı': '6', 'yedi': '7', 'sekiz': '8', 'dokuz': '9', 'on': '10',
            'yirmi': '20', 'otuz': '30', 'elli': '50', 'yüz': '100', 'bin': '1000'
        }
        parsed_msg = msg
        for w, n in word_to_num.items():
            parsed_msg = parsed_msg.replace(w, n)

        math_trans = parsed_msg.replace(',', '.').replace('x', '*').replace('X', '*')
        math_trans = math_trans.replace('bölünce', '/').replace('bölü', '/').replace('böl', '/').replace('bölersem', '/')
        math_trans = math_trans.replace('çarpı', '*').replace('çarp', '*').replace('kere', '*')
        math_trans = math_trans.replace('artı', '+').replace('topla', '+')
        math_trans = math_trans.replace('eksi', '-').replace('çıkar', '-')

        clean_math = re.sub(r'[^0-9\+\-\*/\.]', '', math_trans)

        if clean_math and any(char.isdigit() for char in clean_math):
            if any(op in clean_math for op in ["+", "-", "*", "/"]) and not (clean_math.startswith('-') and clean_math.count('-') == 1 and not any(op in clean_math for op in ["+", "*", "/"])):
                try:
                    result = eval(clean_math)
                    if isinstance(result, float) and result.is_integer():
                        result = int(result)
                    await message.reply(f"{result}")
                    return
                except Exception:
                    pass

        # 2. Klan Sahibi Sorgulama
        owner_keywords = ["klanın sahibi", "sunucunun sahibi", "sahibi kim", "kurucusu kim", "clan owner", "who is the owner", "владелец клана", "хто власник"]
        if any(w in msg for w in owner_keywords):
            if message.guild and message.guild.owner:
                await message.reply(f"{message.guild.owner.mention}")
                return

        # 3. Sohbet & Hafıza Modülü
        if text:
            cleanup_memory()
            user_id = message.author.id
            user_conversations.setdefault(user_id, [])
            user_conversations[user_id].append({'role': 'user', 'content': text, 'time': time.time()})
            user_conversations[user_id] = user_conversations[user_id][-MAX_HISTORY:]

            try:
                ai_reply = await ask_clan_ai(user_conversations[user_id][:-1], text)
            except Exception as e:
                print(f"AI Hatası: {e}", flush=True)
                ai_reply = _fallback_banter(text)

            if not ai_reply or not ai_reply.strip():
                ai_reply = _fallback_banter(text)

            user_conversations[user_id].append({'role': 'assistant', 'content': ai_reply, 'time': time.time()})
            user_conversations[user_id] = user_conversations[user_id][-MAX_HISTORY:]

            # Discord 2000 karakter sınırı
            for parca in [ai_reply[i:i + 1900] for i in range(0, len(ai_reply), 1900)]:
                await message.reply(parca)
            return


# --- KOMUTLAR ---
@bot.tree.command(name="voicejoin", description="Ses kanalına katılır (Owner ve . rolü).")
@app_commands.describe(channel_id="Ses Kanalı ID", duration="Süre (örn: 10s, 5m, 2h, 1d veya 7/24)")
async def voicejoin(interaction: discord.Interaction, channel_id: str, duration: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Bunu sadece Klan Sahibi veya . rolü kullanabilir.", ephemeral=True)
        return

    try:
        v_channel_id = int(channel_id)
    except ValueError:
        await interaction.response.send_message("Geçersiz ID.", ephemeral=True)
        return

    channel = bot.get_channel(v_channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(v_channel_id)
        except Exception:
            channel = None

    if not channel or not isinstance(channel, discord.VoiceChannel):
        await interaction.response.send_message("Kanal bulunamadı.", ephemeral=True)
        return

    duration_lower = duration.lower().strip()
    delta_seconds = None

    if duration_lower != "7/24":
        match = re.match(r"^(\d+)([smhd])$", duration_lower)
        if not match:
            await interaction.response.send_message("Geçersiz süre formatı (`10s`, `5m`, `2h`, `1d` veya `7/24`).", ephemeral=True)
            return
        val, unit = int(match.group(1)), match.group(2)
        delta_seconds = {'s': val, 'm': val * 60, 'h': val * 3600, 'd': val * 86400}[unit]

    try:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()

        embed = discord.Embed(
            title="🔊 Ses Kanalına Girildi",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Kanal", value=f"{channel.name} (`{channel.id}`)", inline=False)
        embed.add_field(name="Süre", value=f"`{duration}`", inline=False)
        embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)

        if delta_seconds is not None:
            await asyncio.sleep(delta_seconds)
            if interaction.guild.voice_client and interaction.guild.voice_client.channel.id == channel.id:
                await interaction.guild.voice_client.disconnect()
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="voiceleft", description="Ses kanalından çıkar (Owner ve . rolü).")
async def voiceleft(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Sadece Klan Sahibi veya . rolü kullanabilir.", ephemeral=True)
        return

    if interaction.guild.voice_client:
        channel_name = interaction.guild.voice_client.channel.name
        await interaction.guild.voice_client.disconnect()
        embed = discord.Embed(
            title="🔇 Ses Kanalından Çıkıldı",
            description=f"**{channel_name}** odasından ayrıldım.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)
    else:
        await interaction.response.send_message("Zaten bir ses kanalında değilim.", ephemeral=True)


@bot.tree.command(name="mute", description="Üyeyi susturur.")
@app_commands.describe(person="Üye", time="Süre (örn: 10s, 5m, 2h, 1d)", reason="Sebep")
async def mute(interaction: discord.Interaction, person: discord.Member, time: str, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_co_leader_staff_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    match = re.match(r"^(\d+)([smhd])$", time.lower())
    if not match:
        await interaction.response.send_message("Geçersiz süre formatı.", ephemeral=True)
        return

    val, unit = int(match.group(1)), match.group(2)
    delta_seconds = {'s': val, 'm': val * 60, 'h': val * 3600, 'd': val * 86400}[unit]

    try:
        duration = discord.utils.utcnow() + timedelta(seconds=delta_seconds)
        await person.timeout(duration, reason=reason)
        chat_embed = discord.Embed(title="🔇 Mute", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        chat_embed.add_field(name="Kullanıcı", value=f"{person.mention} (`{person.id}`)", inline=False)
        chat_embed.add_field(name="Süre", value=f"`{time}`", inline=False)
        chat_embed.add_field(name="Sebep", value=f"`{reason}`", inline=False)
        chat_embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        if person.avatar:
            chat_embed.set_thumbnail(url=person.avatar.url)
        await interaction.response.send_message(embed=chat_embed, ephemeral=False)

        log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=chat_embed)
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="unmute", description="Üyenin susturmasını (timeout) kaldırır.")
@app_commands.describe(person="Üye", reason="Sebep")
async def unmute(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_co_leader_staff_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    try:
        await person.timeout(None, reason=reason)
        chat_embed = discord.Embed(title="🔊 Unmute", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        chat_embed.add_field(name="Kullanıcı", value=f"{person.mention} (`{person.id}`)", inline=False)
        chat_embed.add_field(name="Sebep", value=f"`{reason}`", inline=False)
        chat_embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        if person.avatar:
            chat_embed.set_thumbnail(url=person.avatar.url)
        await interaction.response.send_message(embed=chat_embed, ephemeral=False)

        log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=chat_embed)
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="warn", description="Üyeyi uyarır (2. uyarı kickler).")
@app_commands.describe(person="Üye", reason="Sebep")
async def warn(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_co_leader_staff_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    role_warn1 = discord.utils.get(interaction.guild.roles, name="⛔️ Warn 1 ⛔️")
    role_warn2 = discord.utils.get(interaction.guild.roles, name="⛔️ Warn 2 ⛔️")
    if not role_warn1 or not role_warn2:
        await interaction.response.send_message("Warn rolleri bulunamadı.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        if role_warn1 in person.roles:
            await person.remove_roles(role_warn1, reason=reason)
            await person.add_roles(role_warn2, reason=reason)
            await person.kick(reason=reason)
            warn_embed = discord.Embed(title="⚠️ Uyarı & Kick (2/2)", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        else:
            await person.add_roles(role_warn1, reason=reason)
            warn_embed = discord.Embed(title="⚠️ Uyarı (1/2)", color=discord.Color.gold(), timestamp=discord.utils.utcnow())

        warn_embed.add_field(name="Kullanıcı", value=f"{person.mention} (`{person.id}`)", inline=False)
        warn_embed.add_field(name="Sebep", value=f"`{reason}`", inline=False)
        warn_embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        if person.avatar:
            warn_embed.set_thumbnail(url=person.avatar.url)

        await interaction.response.send_message(embed=warn_embed, ephemeral=False)
        if log_channel:
            await log_channel.send(embed=warn_embed)
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="kick", description="Üyeyi atar.")
@app_commands.describe(person="Üye", reason="Sebep")
async def kick(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_co_leader_staff_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await person.kick(reason=reason)
        kick_embed = discord.Embed(title="👢 Kick", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        kick_embed.add_field(name="Kullanıcı", value=f"{person.mention} (`{person.id}`)", inline=False)
        kick_embed.add_field(name="Sebep", value=f"`{reason}`", inline=False)
        kick_embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        if person.avatar:
            kick_embed.set_thumbnail(url=person.avatar.url)
        await interaction.response.send_message(embed=kick_embed, ephemeral=False)

        if log_channel:
            await log_channel.send(embed=kick_embed)
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="ban", description="Üyeyi yasaklar.")
@app_commands.describe(person="Üye", reason="Sebep")
async def ban(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_co_leader_staff_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await person.ban(reason=reason)
        ban_embed = discord.Embed(title="🔨 Ban", color=discord.Color.dark_red(), timestamp=discord.utils.utcnow())
        ban_embed.add_field(name="Kullanıcı", value=f"{person.mention} (`{person.id}`)", inline=False)
        ban_embed.add_field(name="Sebep", value=f"`{reason}`", inline=False)
        ban_embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        if person.avatar:
            ban_embed.set_thumbnail(url=person.avatar.url)
        await interaction.response.send_message(embed=ban_embed, ephemeral=False)

        if log_channel:
            await log_channel.send(embed=ban_embed)
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="unban", description="ID ile ban kaldırır.")
@app_commands.describe(person_id="Kullanıcı ID", reason="Sebep")
async def unban(interaction: discord.Interaction, person_id: str, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_co_leader_staff_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    try:
        user_id = int(person_id)
        user = await bot.fetch_user(user_id)
    except ValueError:
        await interaction.response.send_message("Geçersiz ID.", ephemeral=True)
        return
    except discord.NotFound:
        await interaction.response.send_message("Kullanıcı bulunamadı.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await interaction.guild.unban(user, reason=reason)
        unban_embed = discord.Embed(title="🔓 Unban", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        unban_embed.add_field(name="Kullanıcı", value=f"{user.mention} (`{user.id}`)", inline=False)
        unban_embed.add_field(name="Sebep", value=f"`{reason}`", inline=False)
        unban_embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
        if user.avatar:
            unban_embed.set_thumbnail(url=user.avatar.url)
        await interaction.response.send_message(embed=unban_embed, ephemeral=False)

        if log_channel:
            await log_channel.send(embed=unban_embed)
    except discord.NotFound:
        await interaction.response.send_message("Bu kullanıcının banı yok.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="say", description="Mesaj gönderir.")
@app_commands.describe(kanal_id="Kanal ID", message="Mesaj")
async def say(interaction: discord.Interaction, kanal_id: str, message: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    if not await check_owner_co_leader_or_dot(interaction.user, interaction.guild):
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    try:
        target_channel_id = int(kanal_id)
    except ValueError:
        await interaction.response.send_message("Geçersiz ID.", ephemeral=True)
        return

    channel = bot.get_channel(target_channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(target_channel_id)
        except Exception:
            channel = None

    if not channel or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Yazı kanalı bulunamadı.", ephemeral=True)
        return

    try:
        await channel.send(message)
        await interaction.response.send_message("Gönderildi.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Hata: {e}", ephemeral=True)


@bot.tree.command(name="apply", description="Klan başvurusu yapar.")
@app_commands.choices(kategori=[
    app_commands.Choice(name="ClanJoin", value="ClanJoin")
])
async def apply(interaction: discord.Interaction, kategori: str):
    if kategori != "ClanJoin":
        await interaction.response.send_message("Geçersiz kategori.", ephemeral=True)
        return

    await interaction.response.send_message("Başvuru DM üzerinden başlatıldı.", ephemeral=True)
    user = interaction.user

    questions = [
        "1. Oyun içi adın (IGN) nedir?",
        "2. Oyunda toplam kaç saat tecrüben var?",
        "3. Ascend, Letancs veya Velocity klanlarından herhangi biriyle husumetin var mı? (Kimler?)"
    ]
    answers = []

    try:
        await user.send(f"🎮 **{kategori}** başvuru soruları:")
        for q in questions:
            await user.send(f"❓ {q}")

            def check(m):
                return m.author == user and isinstance(m.channel, discord.DMChannel)
            msg = await bot.wait_for('message', timeout=300.0, check=check)
            answers.append(msg.content)
        await user.send("✅ Başvuru tamamlandı.")
    except Exception:
        await user.send("⏰ Zaman aşımı.")
        return

    log_channel = bot.get_channel(BASVURU_LOG_CHANNEL_ID)
    if log_channel:
        qa_pairs = list(zip(questions, answers))
        qa_text = "\n".join([f"**{q}**\n> {a}" for q, a in qa_pairs])
        log_content = (
            f"📥 **Yeni Başvuru**\n"
            f"👤 **Kullanıcı:** {user.mention} (`{user}`)\n\n"
            f"{qa_text}"
        )
        embed = discord.Embed(title="🤖 Başvuru Masası", color=discord.Color.blurple())
        view = ReviewView()
        await log_channel.send(log_content, embed=embed, view=view)


if __name__ == "__main__":
    # Render'da (veya KEEP_ALIVE=1 iken) uptime sunucusunu başlat.
    if os.environ.get("RENDER") or os.environ.get("KEEP_ALIVE") == "1":
        keep_alive()

    TOKEN = (os.environ.get("DISCORD_TOKEN") or "").strip()
    if not TOKEN:
        print("❌ HATA: DISCORD_TOKEN bulunamadı!", flush=True)
    else:
        if YUOP_KEY:
            print(f"🤖 AI: yuop ({YUOP_URL}, model={YUOP_MODEL})", flush=True)
        elif GROQ_API_KEY:
            print("🤖 AI: Groq (bulut)", flush=True)
        else:
            print("⚠️ YUOP_KEY veya GROQ_API_KEY yok — AI yanıt veremez.", flush=True)
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"Hata: {e}", flush=True)
