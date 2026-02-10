import os
import random
from typing import Any, List, Optional
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands
from discord.errors import HTTPException
from dotenv import load_dotenv
import sqlite3
import aiohttp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------
# Profanity list
# -----------------------
profanity: List[str] = ["nigga", "fuck", "bitch", "asshole", "dick", "pussy", "cunt", "faggot"]

# -----------------------
# Database tables
# -----------------------
def create_user_table() -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS "user_per_guild" (
            "user_id" INTEGER,
            "warning_count" INTEGER,
            "guild_id" INTEGER,
            PRIMARY KEY ("user_id","guild_id")
        )
    """)
    connection.commit()
    connection.close()

def create_roles_table() -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS "user_roles" (
            "user_id" INTEGER,
            "guild_id" INTEGER,
            "role_ids" TEXT,
            PRIMARY KEY ("user_id","guild_id")
        )
    """)
    connection.commit()
    connection.close()

def create_verification_table() -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS "verified_users" (
            "user_id" INTEGER,
            "guild_id" INTEGER,
            "roblox_username" TEXT,
            "roblox_id" INTEGER,
            "verified_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY ("user_id","guild_id")
        )
    """)
    connection.commit()
    connection.close()

def create_pending_verifications_table() -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS "pending_verifications" (
            "user_id" INTEGER,
            "guild_id" INTEGER,
            "roblox_id" INTEGER,
            "code" TEXT,
            PRIMARY KEY ("user_id","guild_id")
        )
    """)
    connection.commit()
    connection.close()

# Initialize all tables
create_user_table()
create_roles_table()
create_verification_table()
create_pending_verifications_table()

# -----------------------
# Warning system
# -----------------------
def increase_and_get_warnings(user_id: int, guild_id: int) -> int:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""SELECT warning_count FROM user_per_guild WHERE user_id=? AND guild_id=?""",
                   (user_id, guild_id))
    result = cursor.fetchone()
    if result is None:
        cursor.execute("""INSERT INTO user_per_guild (user_id, warning_count, guild_id) VALUES (?, 1, ?)""",
                       (user_id, guild_id))
        connection.commit()
        connection.close()
        return 1
    new_count = result[0] + 1
    cursor.execute("""UPDATE user_per_guild SET warning_count=? WHERE user_id=? AND guild_id=?""",
                   (new_count, user_id, guild_id))
    connection.commit()
    connection.close()
    return new_count

def get_warnings(user_id: int, guild_id: int) -> int:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""SELECT warning_count FROM user_per_guild WHERE user_id=? AND guild_id=?""",
                   (user_id, guild_id))
    result = cursor.fetchone()
    connection.close()
    return result[0] if result else 0

def clear_warnings(user_id: int, guild_id: int) -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""DELETE FROM user_per_guild WHERE user_id=? AND guild_id=?""", (user_id, guild_id))
    connection.commit()
    connection.close()

# -----------------------
# Role save/restore
# -----------------------
def save_user_roles(user_id: int, guild_id: int, role_ids: List[int]) -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""INSERT OR REPLACE INTO user_roles (user_id, guild_id, role_ids) VALUES (?, ?, ?)""",
                   (user_id, guild_id, ",".join(str(r) for r in role_ids)))
    connection.commit()
    connection.close()

def get_user_roles(user_id: int, guild_id: int) -> List[int]:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""SELECT role_ids FROM user_roles WHERE user_id=? AND guild_id=?""", (user_id, guild_id))
    result = cursor.fetchone()
    connection.close()
    return [int(r) for r in result[0].split(",")] if result else []

def delete_user_roles(user_id: int, guild_id: int) -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""DELETE FROM user_roles WHERE user_id=? AND guild_id=?""", (user_id, guild_id))
    connection.commit()
    connection.close()

# -----------------------
# Bot setup
# -----------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready() -> None:
    print(f"{bot.user} is online!")
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.watching, name="Bean Bot")
    )
    try:
        synced: List[app_commands.AppCommand] = await bot.tree.sync()
        print(f"Synced {len(synced)} app command(s)")
    except HTTPException as e:
        if e.code != 50240:
            print(f"Error syncing commands: {e}")

# -----------------------
# Member events
# -----------------------
@bot.event
async def on_member_join(member: discord.Member) -> None:
    try:
        saved_role_ids = get_user_roles(member.id, member.guild.id)
        if saved_role_ids:
            roles_to_add = [member.guild.get_role(r) for r in saved_role_ids if member.guild.get_role(r)]
            if roles_to_add:
                await member.add_roles(*roles_to_add) # type: ignore
                delete_user_roles(member.id, member.guild.id)
    except Exception as e:
        print(f"Error restoring roles for {member}: {e}")

@bot.event
async def on_member_remove(member: discord.Member) -> None:
    try:
        roles = [role.id for role in member.roles if role.name != "@everyone"]
        if roles:
            save_user_roles(member.id, member.guild.id, roles)
    except Exception as e:
        print(f"Error saving roles for {member}: {e}")

# -----------------------
# Profanity filter
# -----------------------
@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author == bot.user:
        return
    for word in profanity:
        if word in message.content.lower():
            await message.delete()
            warnings = increase_and_get_warnings(message.author.id, message.guild.id) # type: ignore
            await message.channel.send(f"{message.author.mention}, please refrain from using profanity. You have {warnings} warning(s).")
            break
    await bot.process_commands(message)

# -----------------------
# Basic moderation commands
# -----------------------
@bot.command()
async def test(ctx):
    await ctx.send("Test command works!")

@bot.command()
@commands.has_permissions(administrator=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    warnings = increase_and_get_warnings(member.id, ctx.guild.id)
    await ctx.send(f"{member.mention} warned ({warnings}/5). Reason: {reason}")
    if warnings >= 5:
        await member.ban(reason="Reached 5 warnings")

@bot.command()
async def warnings(ctx, member: discord.Member):
    count = get_warnings(member.id, ctx.guild.id)
    await ctx.send(f"{member.mention} has {count} warning(s).")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def clearwarnings(ctx, member: discord.Member):
    clear_warnings(member.id, ctx.guild.id)
    await ctx.send(f"Cleared warnings for {member.mention}")

import aiohttp
import string

# -----------------------
# Roblox helpers
# -----------------------
def generate_verification_code(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

async def get_roblox_user_info(username: str) -> Optional[dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        payload = {"usernames": [username], "excludeBannedUsers": False}
        async with session.post("https://users.roblox.com/v1/usernames/users", json=payload) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if not data.get("data"):
                return None
            user = data["data"][0]
            return {"user_id": user["id"], "username": user["name"], "display_name": user.get("displayName", user["name"])}

async def get_roblox_description(user_id: int) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://users.roblox.com/v1/users/{user_id}") as resp:
            if resp.status != 200:
                return ""
            data = await resp.json()
            return data.get("description", "")

def save_verification(user_id: int, guild_id: int, roblox_username: str, roblox_id: int) -> None:
    connection = sqlite3.connect(f"{BASE_DIR}\\user_warnings.db")
    cursor = connection.cursor()
    cursor.execute("""INSERT OR REPLACE INTO verified_users (user_id, guild_id, roblox_username, roblox_id) VALUES (?, ?, ?, ?)""",
                   (user_id, guild_id, roblox_username, roblox_id))
    connection.commit()
    connection.close()

# -----------------------
# Verification Button
# -----------------------
class VerifyView(discord.ui.View):
    def __init__(self, discord_user: discord.Member, roblox_user: dict[str, Any], code: str):
        super().__init__(timeout=300)
        self.discord_user = discord_user
        self.roblox_user = roblox_user
        self.code = code

    @discord.ui.button(label="I've Verified", style=discord.ButtonStyle.green)
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.discord_user.id:
            await interaction.response.send_message("Only you can confirm this verification!", ephemeral=True)
            return

        description = await get_roblox_description(self.roblox_user["user_id"])
        if self.code not in description:
            await interaction.response.send_message(
                "Code not found in your Roblox profile description. Make sure you saved it correctly.",
                ephemeral=True
            )
            return

        save_verification(
            self.discord_user.id,
            interaction.guild.id, # type: ignore
            self.roblox_user["username"],
            self.roblox_user["user_id"]
        )

        verified_role = discord.utils.get(interaction.guild.roles, name="Verified") # type: ignore
        if verified_role:
            await self.discord_user.add_roles(verified_role)

        await interaction.response.edit_message(
            content=f"✅ Verification complete! You are now verified as {self.roblox_user['username']}.",
            embed=None,
            view=None
        )

# -----------------------
# Slash command for verification
# -----------------------
@bot.tree.command(name="verify", description="Verify your Roblox account")
@app_commands.describe(roblox_username="Your Roblox username")
async def verify_slash(interaction: discord.Interaction, roblox_username: str):
    await interaction.response.defer(ephemeral=True)

    user_info = await get_roblox_user_info(roblox_username)
    if not user_info:
        await interaction.followup.send("Roblox user not found.", ephemeral=True)
        return

    code = generate_verification_code()

    embed = discord.Embed(title="Roblox Verification", color=discord.Color.blue())
    embed.add_field(name="Step 1", value="Copy the code below into your Roblox profile description.")
    embed.add_field(name="Verification Code", value=f"`{code}`", inline=False)
    embed.add_field(name="Step 2", value="After saving, click 'I've Verified' below.")
    embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_info['user_id']}&width=420&height=420&format=png")

    view = VerifyView(interaction.user, user_info, code) # type: ignore
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))  # type: ignore