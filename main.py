import os
import asyncio
import re
import time
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread
from groq import Groq

# --- RENDER 7/24 UPTIME SUNUCUSU ---
app = Flask('')

@app.route('/')
def home():
    return "Bot aktif."

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
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

# Groq İstemcisi
groq_client = None
try:
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if groq_api_key:
        groq_client = Groq(api_key=groq_api_key)
except Exception as e:
    print(f"Groq istemcisi başlatılamadı: {e}")

BASVURU_LOG_CHANNEL_ID = 1554563763779272813
WARN_LOG_CHANNEL_ID = 1554563763779272811
VOTE_CHANNEL_ID = 1555619236125220994

# --- 30 DAKİKALIK SOHBET HAFIZASI ---
user_conversations = {}

def cleanup_memory():
    now = time.time()
    for user_id in list(user_conversations.keys()):
        user_conversations[user_id] = [
            m for m in user_conversations[user_id] 
            if now - m['time'] < 1800  # 30 dakika
        ]
        if not user_conversations[user_id]:
            del user_conversations[user_id]

async def check_user_permission(user, guild=None):
    if guild:
        member = guild.get_member(user.id)
        if not member:
            try:
                member = await guild.fetch_member(user.id)
            except:
                return False
        if guild.owner == member:
            return True
        for role in member.roles:
            r_name = role.name.lower()
            if "owner" in r_name or "co-leader" in r_name or "staff" in r_name or "moderation" in r_name or "member" in r_name:
                return True
        return False
    else:
        for g in bot.guilds:
            try:
                member = g.get_member(user.id) or await g.fetch_member(user.id)
                if g.owner == member:
                    return True
                for role in member.roles:
                    r_name = role.name.lower()
                    if "owner" in r_name or "co-leader" in r_name or "staff" in r_name or "moderation" in r_name or "member" in r_name:
                        return True
            except:
                continue
        return False

async def check_owner_co_leader_or_staff(user, guild):
    if guild.owner == user:
        return True
    member = guild.get_member(user.id) or await guild.fetch_member(user.id)
    if member:
        for role in member.roles:
            r_name = role.name.lower()
            if "owner" in r_name or "co-leader" in r_name or "staff" in r_name:
                return True
    return False

async def check_only_owner(user, guild):
    if guild.owner == user:
        return True
    member = guild.get_member(user.id) or await guild.fetch_member(user.id)
    if member:
        for role in member.roles:
            r_name = role.name.lower()
            if "owner" in r_name:
                return True
    return False

async def check_owner_or_co_leader(user, guild):
    if guild.owner == user:
        return True
    member = guild.get_member(user.id) or await guild.fetch_member(user.id)
    if member:
        for role in member.roles:
            r_name = role.name.lower()
            if "owner" in r_name or "co-leader" in r_name:
                return True
    return False

class ReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept and Open Poll", style=discord.ButtonStyle.green, custom_id="accept_app")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
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
    print(f'{bot.user.name} aktif.')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        # Yetkisi olmayanlar için tamamen sessizlik (uyarı yok)
        allowed = await check_user_permission(message.author, message.guild)
        if not allowed:
            return

        text = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        raw_msg = text
        msg = raw_msg.lower()

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
                    await bot.process_commands(message)
                    return
                except Exception:
                    pass

        # 2. Klan Sahibi Sorgulama
        owner_keywords = ["klanın sahibi", "sunucunun sahibi", "sahibi kim", "kurucusu kim", "clan owner", "who is the owner", "владелец клана", "хто власник"]
        if any(w in msg for w in owner_keywords):
            if message.guild and message.guild.owner:
                await message.reply(f"{message.guild.owner.mention}")
                await bot.process_commands(message)
                return

        # 3. Groq AI Sohbet & Hafıza Modülü (Doğal, net, insani ve eşit)
        if groq_client and text:
            cleanup_memory()
            user_id = message.author.id
            if user_id not in user_conversations:
                user_conversations[user_id] = []

            user_conversations[user_id].append({'role': 'user', 'content': text, 'time': time.time()})

            messages_payload = [
                {
                    "role": "system", 
                    "content": "You are a real Discord clan member hanging out in chat. Talk like a normal human gamer—dry, straightforward, slightly sarcastic, and natural. NEVER use robotic customer service phrases, cheesy AI enthusiasm, fake exclamation marks, or overly enthusiastic emojis. Treat everyone completely equally. If someone insults you or swears, don't play the sensitive robot; fire back dryly or brush it off like a real person. Keep replies concise, sharp, and natural in whatever language the user speaks."
                }
            ]
            for m in user_conversations[user_id]:
                messages_payload.append({'role': m['role'], 'content': m['content']})

            async with message.channel.typing():
                try:
                    chat_completion = groq_client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=messages_payload,
                        max_tokens=1200
                    )
                    ai_reply = chat_completion.choices[0].message.content
                    
                    user_conversations[user_id].append({'role': 'assistant', 'content': ai_reply, 'time': time.time()})
                    
                    await message.reply(ai_reply)
                    await bot.process_commands(message)
                    return
                except Exception as e:
                    print(f"Groq API Hatası: {e}")

    await bot.process_commands(message)

# --- KOMUTLAR ---
@bot.tree.command(name="voicejoin", description="Ses kanalına katılır (Sadece Owner).")
@app_commands.describe(channel_id="Ses Kanalı ID", duration="Süre (örn: 10s, 5m, 2h, 1d veya 7/24)")
async def voicejoin(interaction: discord.Interaction, channel_id: str, duration: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    is_allowed = await check_only_owner(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("Bunu sadece Klan Sahibi kullanabilir.", ephemeral=True)
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
        delta_seconds = {
            's': val,
            'm': val * 60,
            'h': val * 3600,
            'd': val * 86400
        }[unit]

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

@bot.tree.command(name="voiceleft", description="Ses kanalından çıkar (Sadece Owner).")
async def voiceleft(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    is_allowed = await check_only_owner(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("Sadece Klan Sahibi kullanabilir.", ephemeral=True)
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

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    match = re.match(r"^(\d+)([smhd])$", time.lower())
    if not match:
        await interaction.response.send_message("Geçersiz süre formatı.", ephemeral=True)
        return

    val, unit = int(match.group(1)), match.group(2)
    delta_seconds = {
        's': val,
        'm': val * 60,
        'h': val * 3600,
        'd': val * 86400
    }[unit]

    try:
        duration = discord.utils.utcnow() + timedelta(seconds=delta_seconds)
        await person.timeout(duration, reason=reason)
        
        chat_embed = discord.Embed(
            title="🔇 Mute",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
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

@bot.tree.command(name="warn", description="Üyeyi uyarır (2. uyarı kickler).")
@app_commands.describe(person="Üye", reason="Sebep")
async def warn(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("Sadece sunucularda geçerli.", ephemeral=True)
        return

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
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
            
            warn_embed = discord.Embed(
                title="⚠️ Uyarı & Kick (2/2)",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            warn_embed.add_field(name="Kullanıcı", value=f"{person.mention} (`{person.id}`)", inline=False)
            warn_embed.add_field(name="Sebep", value=f"`{reason}`", inline=False)
            warn_embed.add_field(name="Yetkili", value=str(interaction.user), inline=False)
            if person.avatar:
                warn_embed.set_thumbnail(url=person.avatar.url)
            
            await interaction.response.send_message(embed=warn_embed, ephemeral=False)
            if log_channel:
                await log_channel.send(embed=warn_embed)
        else:
            await person.add_roles(role_warn1, reason=reason)
            
            warn_embed = discord.Embed(
                title="⚠️ Uyarı (1/2)",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
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

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await person.kick(reason=reason)
        
        kick_embed = discord.Embed(
            title="👢 Kick",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
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

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await person.ban(reason=reason)
        
        ban_embed = discord.Embed(
            title="🔨 Ban",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
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

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
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
        
        unban_embed = discord.Embed(
            title="🔓 Unban",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
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

    is_allowed = await check_owner_or_co_leader(interaction.user, interaction.guild)
    if not is_allowed:
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
        
        embed = discord.Embed(
            title="🤖 Başvuru Masası",
            color=discord.Color.blurple()
        )
        
        view = ReviewView()
        await log_channel.send(log_content, embed=embed, view=view)

# --- BOTU BAŞLATMA ---
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_TOKEN")
    
    if not TOKEN:
        print("❌ HATA: DISCORD_TOKEN bulunamadı!")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"Hata: {e}")
