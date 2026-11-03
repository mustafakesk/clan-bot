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

# --- RENDER 7/24 UPTIME SUNUCUSU ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

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

BASVURU_LOG_CHANNEL_ID = 1554563763779272813
WARN_LOG_CHANNEL_ID = 1554563763779272811
VOTE_CHANNEL_ID = 1555619236125220994

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
            await interaction.response.send_message("Only administrators can use this button!", ephemeral=True)
            return

        vote_channel = bot.get_channel(VOTE_CHANNEL_ID)
        if not vote_channel:
            await interaction.response.send_message("Vote channel not found!", ephemeral=True)
            return

        old_content = interaction.message.content
        vote_msg_content = old_content.replace("📥 **New ClanJoin Application Received!**", "📋 **New ClanJoin Application Vote!**")

        try:
            msg = await vote_channel.send(vote_msg_content, embeds=interaction.message.embeds)
            await msg.add_reaction("👍")
            await msg.add_reaction("❌")

            button.disabled = True
            button.label = "Accepted & Poll Opened"
            await interaction.message.edit(view=self, embeds=interaction.message.embeds)
            await interaction.response.send_message("Success.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.event
async def on_ready():
    print(f'{bot.user.name} active!')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        allowed = await check_user_permission(message.author, message.guild)
        if not allowed:
            await message.reply("⛔ You need to get the required roles first.")
            return

        text = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        raw_msg = text
        msg = raw_msg.lower()

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
                    await message.reply(f"Result: **{result}**")
                    await bot.process_commands(message)
                    return
                except Exception:
                    pass

        if any(w in msg for w in ["klanın sahibi", "sunucunun sahibi", "sahibi kim", "kurucusu kim"]):
            if message.guild and message.guild.owner:
                await message.reply(f"The owner is {message.guild.owner.mention}.")
                await bot.process_commands(message)
                return

    await bot.process_commands(message)

@bot.tree.command(name="voicejoin", description="Joins a specified voice channel (Owner only).")
@app_commands.describe(channel_id="Voice Channel ID", duration="Duration (e.g., 10s, 5m, 2h, 1d or 7/24)")
async def voicejoin(interaction: discord.Interaction, channel_id: str, duration: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_only_owner(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You must be the Owner to use this command.", ephemeral=True)
        return

    try:
        v_channel_id = int(channel_id)
    except ValueError:
        await interaction.response.send_message("❌ Invalid Channel ID format.", ephemeral=True)
        return

    channel = bot.get_channel(v_channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(v_channel_id)
        except Exception:
            channel = None

    if not channel or not isinstance(channel, discord.VoiceChannel):
        await interaction.response.send_message("❌ Voice channel not found.", ephemeral=True)
        return

    duration_lower = duration.lower().strip()
    delta_seconds = None

    if duration_lower != "7/24":
        match = re.match(r"^(\d+)([smhd])$", duration_lower)
        if not match:
            await interaction.response.send_message("❌ Invalid duration format! Use e.g., `10s`, `5m`, `2h`, `1d` or `7/24`.", ephemeral=True)
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
            title="🔊 Voice Channel Joined",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Channel / Kanal", value=f"{channel.name} (`{channel.id}`)", inline=False)
        embed.add_field(name="Duration / Süre", value=f"`{duration}`", inline=False)
        embed.add_field(name="Moderator / Yetkili", value=str(interaction.user), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

        if delta_seconds is not None:
            await asyncio.sleep(delta_seconds)
            if interaction.guild.voice_client and interaction.guild.voice_client.channel.id == channel.id:
                await interaction.guild.voice_client.disconnect()

    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to join voice channel: {e}", ephemeral=True)

@bot.tree.command(name="voiceleft", description="Leaves the current voice channel (Owner only).")
async def voiceleft(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_only_owner(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You must be the Owner to use this command.", ephemeral=True)
        return

    if interaction.guild.voice_client:
        channel_name = interaction.guild.voice_client.channel.name
        await interaction.guild.voice_client.disconnect()
        
        embed = discord.Embed(
            title="🔇 Left Voice Channel",
            description=f"Successfully left **{channel_name}**.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Moderator / Yetkili", value=str(interaction.user), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)
    else:
        await interaction.response.send_message("❌ The bot is not currently in any voice channel.", ephemeral=True)

@bot.tree.command(name="mute", description="Mutes a member for a specified time.")
@app_commands.describe(person="Member to mute", time="Duration (e.g., 10s, 5m, 2h, 1d)", reason="Reason for mute")
async def mute(interaction: discord.Interaction, person: discord.Member, time: str, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You must be Staff, Co-Leader, or Owner to use this command.", ephemeral=True)
        return

    match = re.match(r"^(\d+)([smhd])$", time.lower())
    if not match:
        await interaction.response.send_message("❌ Invalid time format! Example usage: `10s`, `5m`, `2h`, `1d`", ephemeral=True)
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
            title="🔇 Mute / Timeout",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        chat_embed.add_field(name="Kullanıcı / User", value=f"{person.mention} ({person} | `{person.id}`)", inline=False)
        chat_embed.add_field(name="Süre / Time", value=f"`{time}`", inline=False)
        chat_embed.add_field(name="Sebep / Reason", value=f"`{reason}`", inline=False)
        chat_embed.add_field(name="Yetkili / Moderator", value=str(interaction.user), inline=False)
        if person.avatar:
            chat_embed.set_thumbnail(url=person.avatar.url)
            
        await interaction.response.send_message(embed=chat_embed, ephemeral=False)

        log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=chat_embed)
            
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to execute: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Warns a member. 2nd warn kicks the user.")
@app_commands.describe(person="Member to warn", reason="Reason for warning")
async def warn(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You must be Staff, Co-Leader, or Owner to use this command.", ephemeral=True)
        return

    role_warn1 = discord.utils.get(interaction.guild.roles, name="⛔️ Warn 1 ⛔️")
    role_warn2 = discord.utils.get(interaction.guild.roles, name="⛔️ Warn 2 ⛔️")

    if not role_warn1 or not role_warn2:
        await interaction.response.send_message("❌ '⛔️ Warn 1 ⛔️' or '⛔️ Warn 2 ⛔️' roles not found in the server!", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        if role_warn1 in person.roles:
            await person.remove_roles(role_warn1, reason=reason)
            await person.add_roles(role_warn2, reason=reason)
            await person.kick(reason=reason)
            
            warn_embed = discord.Embed(
                title="⚠️ Uyarı / Warning (Warn 2 & Kick)",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            warn_embed.add_field(name="Kullanıcı / User", value=f"{person.mention} ({person} | `{person.id}`)", inline=False)
            warn_embed.add_field(name="Sebep / Reason", value=f"`{reason}`", inline=False)
            warn_embed.add_field(name="Aktif Uyarı / Active Warns", value="`2/2`", inline=False)
            warn_embed.add_field(name="Toplam Uyarı / Total Warns", value="`2`", inline=False)
            warn_embed.add_field(name="Yetkili / Moderator", value=str(interaction.user), inline=False)
            if person.avatar:
                warn_embed.set_thumbnail(url=person.avatar.url)
            
            await interaction.response.send_message(embed=warn_embed, ephemeral=False)
            if log_channel:
                await log_channel.send(embed=warn_embed)
        else:
            await person.add_roles(role_warn1, reason=reason)
            
            warn_embed = discord.Embed(
                title="⚠️ Uyarı / Warning",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            warn_embed.add_field(name="Kullanıcı / User", value=f"{person.mention} ({person} | `{person.id}`)", inline=False)
            warn_embed.add_field(name="Sebep / Reason", value=f"`{reason}`", inline=False)
            warn_embed.add_field(name="Aktif Uyarı / Active Warns", value="`1/2`", inline=False)
            warn_embed.add_field(name="Toplam Uyarı / Total Warns", value="`1`", inline=False)
            warn_embed.add_field(name="Yetkili / Moderator", value=str(interaction.user), inline=False)
            if person.avatar:
                warn_embed.set_thumbnail(url=person.avatar.url)
            
            await interaction.response.send_message(embed=warn_embed, ephemeral=False)
            if log_channel:
                await log_channel.send(embed=warn_embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to execute: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Kicks a member from the server.")
@app_commands.describe(person="Member to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You must be Staff, Co-Leader, or Owner to use this command.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await person.kick(reason=reason)
        
        kick_embed = discord.Embed(
            title="👢 Atılma / Kick",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        kick_embed.add_field(name="Kullanıcı / User", value=f"{person.mention} ({person} | `{person.id}`)", inline=False)
        kick_embed.add_field(name="Sebep / Reason", value=f"`{reason}`", inline=False)
        kick_embed.add_field(name="Yetkili / Moderator", value=str(interaction.user), inline=False)
        if person.avatar:
            kick_embed.set_thumbnail(url=person.avatar.url)

        await interaction.response.send_message(embed=kick_embed, ephemeral=False)

        if log_channel:
            await log_channel.send(embed=kick_embed)
            
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to execute: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Bans a member from the server.")
@app_commands.describe(person="Member to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, person: discord.Member, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You must be Staff, Co-Leader, or Owner to use this command.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await person.ban(reason=reason)
        
        ban_embed = discord.Embed(
            title="🔨 Yasaklama / Ban",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        ban_embed.add_field(name="Kullanıcı / User", value=f"{person.mention} ({person} | `{person.id}`)", inline=False)
        ban_embed.add_field(name="Sebep / Reason", value=f"`{reason}`", inline=False)
        ban_embed.add_field(name="Yetkili / Moderator", value=str(interaction.user), inline=False)
        if person.avatar:
            ban_embed.set_thumbnail(url=person.avatar.url)

        await interaction.response.send_message(embed=ban_embed, ephemeral=False)

        if log_channel:
            await log_channel.send(embed=ban_embed)
            
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to execute: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Unbans a user from the server using their Discord ID.")
@app_commands.describe(person_id="Discord User ID to unban", reason="Reason for unban")
async def unban(interaction: discord.Interaction, person_id: str, reason: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_owner_co_leader_or_staff(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You must be Staff, Co-Leader, or Owner to use this command.", ephemeral=True)
        return

    try:
        user_id = int(person_id)
        user = await bot.fetch_user(user_id)
    except ValueError:
        await interaction.response.send_message("❌ Invalid User ID format.", ephemeral=True)
        return
    except discord.NotFound:
        await interaction.response.send_message("❌ User not found with this ID.", ephemeral=True)
        return

    log_channel = bot.get_channel(WARN_LOG_CHANNEL_ID)

    try:
        await interaction.guild.unban(user, reason=reason)
        
        unban_embed = discord.Embed(
            title="🔓 Yasak Kaldırma / Unban",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        unban_embed.add_field(name="Kullanıcı / User", value=f"{user.mention} ({user} | `{user.id}`)", inline=False)
        unban_embed.add_field(name="Sebep / Reason", value=f"`{reason}`", inline=False)
        unban_embed.add_field(name="Yetkili / Moderator", value=str(interaction.user), inline=False)
        if user.avatar:
            unban_embed.set_thumbnail(url=user.avatar.url)

        await interaction.response.send_message(embed=unban_embed, ephemeral=False)

        if log_channel:
            await log_channel.send(embed=unban_embed)
            
    except discord.NotFound:
        await interaction.response.send_message("❌ User is not banned from this server.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to execute: {e}", ephemeral=True)

@bot.tree.command(name="say", description="Sends a message to the specified channel.")
@app_commands.describe(kanal_id="Channel ID", message="Message")
async def say(interaction: discord.Interaction, kanal_id: str, message: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in servers.", ephemeral=True)
        return

    is_allowed = await check_owner_or_co_leader(interaction.user, interaction.guild)
    if not is_allowed:
        await interaction.response.send_message("⛔ You don't have permission.", ephemeral=True)
        return

    try:
        target_channel_id = int(kanal_id)
    except ValueError:
        await interaction.response.send_message("❌ Invalid ID.", ephemeral=True)
        return

    channel = bot.get_channel(target_channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(target_channel_id)
        except Exception:
            channel = None

    if not channel or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
        return

    try:
        await channel.send(message)
        await interaction.response.send_message("✅ Sent successfully.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="apply", description="Apply for the clan.")
@app_commands.choices(kategori=[
    app_commands.Choice(name="ClanJoin", value="ClanJoin")
])
async def apply(interaction: discord.Interaction, kategori: str):
    if kategori != "ClanJoin":
        await interaction.response.send_message("Invalid category.", ephemeral=True)
        return

    await interaction.response.send_message("Application started via DM.", ephemeral=True)
    user = interaction.user
    
    questions = [
        "1. What is your in-game name?",
        "2. How many hours do you have in the game?",
        "3. Do you have wars with anyone from Ascend, Letancs, Velocity clans? (If yes, who?)"
    ]
    answers = []

    try:
        await user.send(f"🎮 Welcome to the **{kategori}** application!")
        for q in questions:
            await user.send(f"❓ {q}")
            def check(m):
                return m.author == user and isinstance(m.channel, discord.DMChannel)
            msg = await bot.wait_for('message', timeout=300.0, check=check)
            answers.append(msg.content)
        await user.send("✅ Application completed!")
    except Exception:
        await user.send("❌ Timeout.")
        return

    log_channel = bot.get_channel(BASVURU_LOG_CHANNEL_ID)
    if log_channel:
        qa_pairs = list(zip(questions, answers))
        qa_text = "\n".join([f"**{q}**\n> {a}" for q, a in qa_pairs])
        
        log_content = (
            f"📥 **New Application!**\n"
            f"👤 **User:** {user.mention} (`{user}`)\n\n"
            f"{qa_text}"
        )
        
        embed = discord.Embed(
            title="🤖 Application Review",
            description="Application successfully received.",
            color=discord.Color.blurple()
        )
        
        view = ReviewView()
        await log_channel.send(log_content, embed=embed, view=view)

# --- ÇALIŞTIRMA VE TOKEN GÜVENLİĞİ ---
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_TOKEN")
    
    if not TOKEN:
        print("❌ HATA: DISCORD_TOKEN ortam değişkeni bulunamadı!")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"Bot çalıştırılırken hata oluştu: {e}")
