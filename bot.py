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
# --- Command: /start ---
@app.on_message(filters.command("start"))
async def start(client, message):
    try:
        user_id = message.from_user.id
        res = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
        is_premium = False
        if res.data:
            try:
                expiry_str = res.data[0]["expiry"].replace("Z", "+00:00")
                expiry = datetime.datetime.fromisoformat(expiry_str)
                is_premium = expiry > datetime.datetime.utcnow()
            except Exception as e:
                print(f"Expiry parsing error: {e}")

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

    except Exception as e:
        await message.reply_text("❌ An error occurred in /start.")
        print(f"Error in /start: {e}")

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

# --- User Send ---

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
            f"🆔 *User ID:* {user_id}\n"
            f"📅 *Date:* {now}\n\n"
            f"💬 *Feedback:*\n{content}"
        )
    elif action == "awaiting_payment_proof":
        caption = (
            f"💰 *New Payment Proof*\n\n"
            f"👤 *From:* {user_info}\n"
            f"🆔 *User ID:* {user_id}\n"
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
        
# --- Timezone helper ---
PHT = zoneinfo.ZoneInfo("Asia/Manila")

def utc_to_pht(dt_utc: datetime.datetime) -> datetime.datetime:
    """Convert naive or UTC datetime to Philippine Time zone aware datetime."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)
    return dt_utc.astimezone(PHT)

# --- Duration Parser ---
def parse_duration(duration_str: str) -> datetime.datetime:
    """
    Parses duration string and returns expiration datetime in UTC.
    Supported units:
    m = minutes
    h = hours
    d = days
    y = years (365 days)
    """
    if len(duration_str) < 2:
        raise ValueError("Invalid duration format.")
    try:
        amount = int(duration_str[:-1])
    except ValueError:
        raise ValueError("Duration must start with a number, e.g. 10d, 3h")

    unit = duration_str[-1].lower()
    if unit == "m":
        delta = datetime.timedelta(minutes=amount)
    elif unit == "h":
        delta = datetime.timedelta(hours=amount)
    elif unit == "d":
        delta = datetime.timedelta(days=amount)
    elif unit == "y":
        delta = datetime.timedelta(days=365 * amount)
    else:
        raise ValueError("Invalid duration unit. Use m/h/d/y.")
    return datetime.datetime.utcnow() + delta

# --- Command: /generate ---
@app.on_message(filters.command("generate") & filters.user(admin_ids))
async def generate_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /generate <duration> (e.g. 1d, 3h)")
    try:
        expiry = parse_duration(message.command[1])
    except Exception as e:
        return await message.reply(f"Error: {e}")
    key = uuid4().hex
    supabase.table("reku_keys").insert({
        "key": key,
        "expiry": expiry.isoformat() + "Z",  # UTC ISO format with Z
        "created": datetime.datetime.utcnow().isoformat() + "Z",
        "duration": message.command[1],
        "owner_id": message.from_user.id,
        "redeemed_by": None
    }).execute()
    expiry_pht = utc_to_pht(expiry)
    await message.reply(
        f"✅ Key generated:\n<code>{key}</code>\n📅 Expires: {expiry_pht.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        parse_mode=ParseMode.HTML
    )

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
        return await message.reply(f"Error: {e}")
    now = datetime.datetime.utcnow().isoformat() + "Z"
    keys = [{
        "key": uuid4().hex,
        "expiry": expiry.isoformat() + "Z",
        "created": now,
        "duration": duration_str,
        "owner_id": message.from_user.id,
        "redeemed_by": None
    } for _ in range(count)]
    supabase.table("reku_keys").insert(keys).execute()
    text = "\n".join([f"`{k['key']}`" for k in keys])
    expiry_pht = utc_to_pht(expiry)
    await message.reply(
        f"✅ {count} keys generated:\n\n{text}\n\n📅 Expires: {expiry_pht.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        parse_mode=ParseMode.MARKDOWN
    )

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
    if record["redeemed_by"] is not None:
        return await message.reply("⚠️ This key has already been used.")
    expiry = datetime.datetime.fromisoformat(record["expiry"].replace("Z", "+00:00"))
    if expiry < datetime.datetime.utcnow():
        return await message.reply("⛔ This key has expired.")
    supabase.table("reku_keys").update({"redeemed_by": user_id}).eq("key", key).execute()
    expiry_pht = utc_to_pht(expiry)
    await message.reply(
        f"✅ Key redeemed! You now have premium access.\n⏳ Expires: {expiry_pht.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )

# --- Run Bot ---
app.run()
