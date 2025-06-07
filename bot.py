import os
import json
import time
import random
import asyncio
import datetime
from uuid import uuid4
from collections import defaultdict

from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from supabase import create_client

# --- Environment Variables ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Supabase Client ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Admin IDs ---
admin_ids = [int(i.strip()) for i in os.getenv("ADMIN_ID", "5110224851").split(",") if i.strip().isdigit()]

# --- Pyrogram App ---
app = Client("reku_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Access Check ---
async def check_user_access(user_id: int) -> bool:
    res = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
    if res.data:
        expiry = datetime.datetime.fromisoformat(res.data[0]["expiry"].replace("Z", "+00:00"))
        return expiry > datetime.datetime.utcnow()
    return False

# --- Command: /start ---
@app.on_message(filters.command("start"))
async def start(client, message):
    is_premium = await check_user_access(message.from_user.id)
    if is_premium:
        caption = (
            "🛡️ <b>PREMIUM TXT SEARCHER</b> 🛡️\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "🎯 <b>Account Status:</b> ACTIVE\n"
            "🔓 <b>Access Level:</b> PREMIUM\n\n"
            "📌 Available commands:\n"
            "• /search - Find accounts\n"
            "• /dice - Get random reward\n"
            "• /help - Show all commands"
        )
        keyboard = None
    else:
        caption = (
            "🔎 <b>PREMIUM TXT GENERATOR</b> 🔍\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "Access premium accounts database with verified credentials\n\n"
            "🚀 <b>Get Started:</b>\n"
            "1. Purchase access key from seller\n"
            "2. Redeem using /redeem <key>\n\n"
            "💎 <b>Premium Features:</b>\n"
            "- Unlimited searches\n"
            "- Premium and fresh results\n"
            "- Exclusive categories"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 GET ACCESS KEY", url="https://t.me/Rikushittt")],
            [InlineKeyboardButton("❓ REDEEM GUIDE", callback_data="redeem_help")]
        ])

    await message.reply_text(caption, reply_markup=keyboard, parse_mode=ParseMode.HTML)

# --- Command: /help ---
@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "🔥 <b>BOT COMMANDS</b> 🔥\n\n"
        "🔹 <b>GENERAL</b>\n"
        "• /start - Check bot status\n"
        "• /help - Show this message\n"
        "• /redeem - Activate premium key\n"
        "• /myinfo - View subscription info\n"
        "• /feedback - Send suggestions\n\n"
        "🔹 <b>SEARCH</b>\n"
        "• /search - Find accounts\n"
        "• /dice - Random account reward\n"
        "• /countlines - Check database count\n\n"
        "🔹 <b>ADMIN</b>\n"
        "• /generate - Create new key\n"
        "• /bulkgenerate - Bulk generate keys\n"
        "• /remove - Delete license key\n"
        "• /users - List subscribers"
    )
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

# --- Duration Parser ---
def parse_duration(duration_str: str) -> datetime.datetime:
    amount = int(duration_str[:-1])
    unit = duration_str[-1]
    delta = {
        "h": datetime.timedelta(hours=amount),
        "d": datetime.timedelta(days=amount),
        "w": datetime.timedelta(weeks=amount),
        "m": datetime.timedelta(days=30 * amount),
        "y": datetime.timedelta(days=365 * amount)
    }.get(unit)
    if delta is None:
        raise ValueError("Invalid duration unit. Use h/d/w/m/y.")
    return datetime.datetime.utcnow() + delta

# --- Command: /generate ---
@app.on_message(filters.command("generate") & filters.user(admin_ids))
async def generate_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /generate <duration> (e.g. 1d, 3w)")
    try:
        expiry = parse_duration(message.command[1])
    except Exception as e:
        return await message.reply(str(e))
    key = uuid4().hex
    supabase.table("reku_keys").insert({
        "key": key,
        "expiry": expiry.isoformat(),
        "created": datetime.datetime.utcnow().isoformat(),
        "duration": message.command[1],
        "owner_id": message.from_user.id
    }).execute()
    await message.reply(f"✅ Key generated:\n<code>{key}</code>\n📅 Expires: {expiry}", parse_mode=ParseMode.HTML)

# --- Command: /bulkgenerate ---
@app.on_message(filters.command("bulkgenerate") & filters.user(admin_ids))
async def bulk_generate_keys(client, message):
    if len(message.command) < 3:
        return await message.reply("Usage: /bulkgenerate <duration> <count>")
    try:
        duration_str = message.command[1]
        count = int(message.command[2])
        expiry = parse_duration(duration_str)
    except Exception as e:
        return await message.reply(str(e))
    now = datetime.datetime.utcnow().isoformat()
    keys = [{
        "key": uuid4().hex,
        "expiry": expiry.isoformat(),
        "created": now,
        "duration": duration_str,
        "owner_id": message.from_user.id
    } for _ in range(count)]
    supabase.table("reku_keys").insert(keys).execute()
    text = "\n".join([f"`{k['key']}`" for k in keys])
    await message.reply(f"✅ {count} keys generated:\n\n{text}", parse_mode=ParseMode.MARKDOWN)

# --- Command: /redeem ---
@app.on_message(filters.command("redeem"))
async def redeem_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /redeem <key>")
    key = message.command[1]
    user_id = message.from_user.id
    res = supabase.table("reku_keys").select("*").eq("key", key).execute()
    if not res.data:
        return await message.reply("❌ Invalid key.")
    record = res.data[0]
    if record["redeemed_by"]:
        return await message.reply("⚠️ This key has already been used.")
    expiry = datetime.datetime.fromisoformat(record["expiry"].replace("Z", "+00:00"))
    if expiry < datetime.datetime.utcnow():
        return await message.reply("⛔ This key has expired.")
    supabase.table("reku_keys").update({"redeemed_by": user_id}).eq("key", key).execute()
    await message.reply("✅ Key redeemed! You now have premium access.")

# --- Run Bot ---
app.run()
