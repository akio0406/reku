import os
import re
import json
import time
import random
import asyncio
import datetime
import base64
from collections import Counter, defaultdict
from uuid import uuid4
from datetime import timezone

import pytz
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.filters import Filter

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
admin_ids = [5110224851]  # Default fallback
env_admins = os.getenv("ADMIN_ID", "")
if env_admins:
    admin_ids = [int(id.strip()) for id in env_admins.split(",") if id.strip()]

# --- Pyrogram App ---
app = Client("mybot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def check_user_access(user_id: int) -> bool:
    response = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
    if response.data:
        key_data = response.data[0]
        expiry = datetime.datetime.fromisoformat(key_data["expiry"].replace("Z", "+00:00"))
        return expiry > datetime.datetime.utcnow()
    return False

@app.on_message(filters.command("start"))
async def start(client, message):
    if await check_user_access(message.from_user.id):
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

    await message.reply_text(
        caption,
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "🔥 <b>𝗕𝗢𝗧 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b> 🔥\n"
        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
        "🔹 <b>𝗚𝗘𝗡𝗘𝗥𝗔𝗟 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n"
        "• /start - Check bot status\n"
        "• /help - Show this message\n"
        "• /redeem - Activate premium key\n"
        "• /payment - Submit payment proof\n"
        "• /myinfo - View subscription info\n"
        "• /feedback - Send suggestions\n\n"
        "🔹 <b>𝗦𝗘𝗔𝗥𝗖𝗛 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n"
        "• /search - Find accounts\n"
        "• /dice - Random account reward\n"
        "• /countlines - Check database count\n\n"
        "🔹 <b>𝗙𝗜𝗟𝗘 𝗧𝗢𝗢𝗟𝗦</b>\n"
        "• /removeurl - Clean combo files\n"
        "• /merge - Combine multiple files\n\n"
        "🔹 <b>𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n"
        "• /generate - Create new keys\n"
        "• /masskey - Bulk generate keys\n"
        "• /remove - Delete license key\n"
        "• /users - List subscribers\n"
        "• /payments - View pending payments\n"
        "• /broadcast - Send announcements\n"
        "• /useractivity - View user activities\n"
        "• /activeusers - List active users\n"
        "• /deleteallkeys - Delete all keys (DANGER)"
    )

    await message.reply_text(
        help_text,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )

user_state = {}

@app.on_message(filters.command("send"))
async def send_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Feedback", callback_data="send_feedback"),
         InlineKeyboardButton("💳 Payment", callback_data="send_payment")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
    ])

    await message.reply("📨 What would you like to send?", reply_markup=keyboard)

@app.on_callback_query()
async def handle_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "send_feedback":
        user_state[user_id] = {"action": "awaiting_feedback"}
        await callback_query.message.edit_text(
            "📣 Please send your feedback (text, photo, or video).\n\n"
            "You can include:\n"
            "- Bug reports\n"
            "- Feature requests\n"
            "- General feedback\n\n"
            "Type /cancel to abort."
        )
    elif data == "send_payment":
        user_state[user_id] = {"action": "awaiting_payment_proof"}
        await callback_query.message.edit_text(
            "💳 <b>Payment Process</b> 💳\n\n"
            "1. Send your payment proof (screenshot/photo)\n"
            "2. Include amount paid in the caption\n"
            "3. Your payment will be verified within 24 hours\n\n"
            "📝 Example caption:\n"
            "<code>Payment for Premium Access - ₱200</code>\n\n"
            "Type /cancel to abort.",
            parse_mode=enums.ParseMode.HTML
        )
    elif data == "cancel_action":
        user_state.pop(user_id, None)
        await callback_query.message.edit_text("❌ Action cancelled.")

@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
    user_state.pop(message.from_user.id, None)
    await message.reply("❌ Action cancelled.")

@app.on_message((filters.text | filters.photo | filters.video))
async def process_user_content(client, message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    if not state:
        return

    action = state.get("action")
    content = message.text or message.caption or "[No message text]"

    try:
        user = await client.get_users(user_id)
        user_info = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        user_info += f" (@{user.username})" if user.username else ""
    except:
        user_info = f"User ID: {user_id}"

    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if action == "awaiting_feedback":
        caption = (
            f"📬 *New Feedback*\n\n"
            f"👤 *From:* {user_info}\n"
            f"🆔 *User ID:* `{user_id}`\n"
            f"📅 *Date:* {now}\n\n"
            f"💬 *Feedback:*\n{content}"
        )
    elif action == "awaiting_payment_proof":
        caption = (
            f"💰 *New Payment Proof*\n\n"
            f"👤 *From:* {user_info}\n"
            f"🆔 *User ID:* `{user_id}`\n"
            f"📅 *Date:* {now}\n\n"
            f"💬 *Caption:*\n{content}"
        )
    else:
        return

    try:
        for admin_id in admin_ids:
            if message.photo:
                await client.send_photo(
                    chat_id=admin_id,
                    photo=message.photo.file_id,
                    caption=caption,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            elif message.video:
                await client.send_video(
                    chat_id=admin_id,
                    video=message.video.file_id,
                    caption=caption,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            else:
                await client.send_message(
                    chat_id=admin_id,
                    text=caption,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
        await message.reply("✅ Your message has been sent to the admin. Thank you!")
    except Exception as e:
        await message.reply(f"❌ Failed to send: {str(e)}")
    finally:
        user_state.pop(user_id, None)

# KEY SYSTEM
def parse_duration(duration_str: str) -> datetime.datetime:
    amount = int(duration_str[:-1])
    unit = duration_str[-1]

    delta = {
        "h": datetime.timedelta(hours=amount),
        "d": datetime.timedelta(days=amount),
        "w": datetime.timedelta(weeks=amount),
        "m": datetime.timedelta(days=30 * amount),
        "y": datetime.timedelta(days=365 * amount),
    }.get(unit)

    if delta is None:
        raise ValueError("Invalid duration unit. Use h/d/w/m/y.")

    return datetime.datetime.utcnow() + delta

@app.on_message(filters.command("generate") & filters.user(admin_ids))
async def generate_key(client, message):
    if len(message.command) < 2:
        await message.reply("Usage: /generate <duration> (e.g. 1d, 3w)")
        return

    duration_str = message.command[1]
    try:
        expiry = parse_duration(duration_str)
    except ValueError as e:
        return await message.reply(str(e))

    key = uuid4().hex
    supabase.table("reku_keys").insert({
        "key": key,
        "expiry": expiry.isoformat(),
        "created": datetime.datetime.utcnow().isoformat(),
        "duration": duration_str,
        "owner_id": message.from_user.id
    }).execute()

    await message.reply(f"✅ Key generated:\n<code>{key}</code>\n📅 Expires: {expiry}", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("bulkgenerate") & filters.user(admin_ids))
async def bulk_generate_keys(client, message):
    if len(message.command) < 3:
        return await message.reply("Usage: /bulkgenerate <duration> <count>")

    duration_str = message.command[1]
    try:
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

@app.on_message(filters.command("redeem"))
async def redeem_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /redeem <key>")

    user_id = message.from_user.id
    key = message.command[1]

    res = supabase.table("reku_keys").select("*").eq("key", key).execute()
    if not res.data:
        return await message.reply("❌ Invalid key.")

    record = res.data[0]
    if record["redeemed_by"]:
        return await message.reply("⚠️ This key has already been used.")
    if datetime.datetime.fromisoformat(record["expiry"].replace("Z", "+00:00")) < datetime.datetime.utcnow():
        return await message.reply("⛔ This key has expired.")

    supabase.table("reku_keys").update({
        "redeemed_by": user_id
    }).eq("key", key).execute()

    await message.reply("✅ Key redeemed! You now have premium access.")

app.run()

