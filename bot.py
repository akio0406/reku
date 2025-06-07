import os
import json
import time
import random
import asyncio
import requests
import pytz
from uuid import uuid4
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import logging
logging.basicConfig(level=logging.INFO)

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

# Debug environment
print("ENV loaded -> API_ID:", API_ID, "| BOT_TOKEN starts with:", BOT_TOKEN[:8])

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# --- Supabase Client ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Admin IDs ---
admin_ids = [int(i.strip()) for i in os.getenv("ADMIN_ID", "5110224851").split(",") if i.strip().isdigit()]
print("Admin IDs loaded:", admin_ids)

# --- Pyrogram App ---
app = Client("reku_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Access Check ---
async def check_user_access(user_id: int) -> bool:
    res = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
    if res.data:
        expiry = datetime.fromisoformat(res.data[0]["expiry"].replace("Z", "+00:00"))
        return expiry > datetime.now(timezone.utc)  # <-- fixed here
    return False

# --- Command: /start ---
@app.on_message(filters.command("start"))
async def start(client, message):
    try:
        user_id = message.from_user.id
        res = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
        is_premium = False
        if res.data:
    try:
        expiry = datetime.fromisoformat(res.data[0]["expiry"].replace("Z", "+00:00"))
        now_utc = datetime.now(timezone.utc)  # <-- fixed here
        is_premium = expiry > now_utc
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

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
def store_key(key, duration, owner_id):
    try:
        expiry_time = (datetime.now(timezone.utc) + duration).isoformat()
        data = {
            "key": key,
            "expiry": expiry_time,
            "owner_id": owner_id
        }

        response = requests.post(f"{SUPABASE_URL}/rest/v1/reku_keys", headers=SUPABASE_HEADERS, json=data)
        print("🔍 Supabase Response:", response.status_code, response.text)
        return response.status_code == 201
    except Exception as e:
        print("❌ Error in store_key:", str(e))
        return False

@app.on_message(filters.command("generate"))
async def generate_key(client, message):
    print("✅ /generate received")
    print("🧾 Raw message:", message.text)
    print("👤 From user ID:", message.from_user.id)
    await message.reply("✅ You triggered /generate — this is a test response.")

    try:
        args = message.text.split()
        if len(args) != 2:
            return await message.reply("❌ Usage: `/generate <duration>` (e.g., `/generate 1d`)")

        duration_str = args[1]
        unit = duration_str[-1]
        amount = int(duration_str[:-1])

        duration = {
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount)
        }.get(unit)

        if not duration:
            return await message.reply("❌ Invalid format! Use `m`, `h`, or `d`.")

        key = "REKU-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))

        success = store_key(key, duration, message.from_user.id)
        if success:
            expiry_time = (datetime.now(timezone.utc) + duration).astimezone(pytz.timezone("Asia/Manila")).strftime('%Y-%m-%d %H:%M:%S')
            await message.reply(f"✅ **Generated Key:** `{key}`\n⏳ **Expires at (PHT):** `{expiry_time}`")
        else:
            await message.reply("❌ Failed to generate key. Try again later.")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("redeem"))
async def redeem_key(client, message):
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply("❌ Usage: /redeem <key>")
            return

        key = args[1]
        user_id = message.from_user.id

        # Check if the user is already in the 'users' table
        response = requests.get(f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}", headers=SUPABASE_HEADERS)
        if response.status_code != 200:
            await message.reply(f"❌ Error checking user existence: {response.status_code} - {response.text}")
            return

        if not response.json():
            # If the user does not exist, insert them into the 'users' table
            user_data = {
                "id": user_id,
                "username": message.from_user.username or ""  # Optional: Store username if needed
            }
            insert_response = requests.post(f"{SUPABASE_URL}/rest/v1/users", headers=SUPABASE_HEADERS, json=user_data)
            if insert_response.status_code != 201:
                await message.reply(f"❌ Error adding user: {insert_response.status_code} - {insert_response.text}")
                return

        # Check if the user has already redeemed a key
        response = requests.get(f"{SUPABASE_URL}/rest/v1/reku_keys?redeemed_by=eq.{user_id}", headers=SUPABASE_HEADERS)
        if response.status_code != 200:
            await message.reply(f"❌ Error checking redemption: {response.status_code} - {response.text}")
            return
        if response.json():
            await message.reply("❌ You have already redeemed a key.")
            return

        # Check if key exists and is not redeemed
        response = requests.get(f"{SUPABASE_URL}/rest/v1/reku_keys?key=eq.{key}", headers=SUPABASE_HEADERS)
        if response.status_code != 200:
            await message.reply(f"❌ Error fetching key: {response.status_code} - {response.text}")
            return

        keys = response.json()
        if not keys:
            await message.reply("❌ Invalid or expired key!")
            return

        key_data = keys[0]
        if key_data["redeemed_by"]:
            await message.reply("❌ This key has already been redeemed!")
            return

        expiry_time_utc = datetime.fromisoformat(key_data["expiry"]).replace(tzinfo=timezone.utc)
        expiry_time_pht = expiry_time_utc.astimezone(pytz.timezone("Asia/Manila"))

        if expiry_time_utc < datetime.now(timezone.utc):
            await message.reply("❌ This key has expired!")
            return

        # Redeem key by updating "redeemed_by"
        update_data = {"redeemed_by": user_id}
        response = requests.patch(f"{SUPABASE_URL}/rest/v1/reku_keys?key=eq.{key}", headers=SUPABASE_HEADERS, json=update_data)

        if response.status_code in [200, 204]:
            expiry_str = expiry_time_pht.strftime('%Y-%m-%d %H:%M:%S')
            await message.reply(f"✅ Key successfully redeemed! Kindly use /list to see all the available commands.\n⏳ **Expires at (PHT):** {expiry_str}")
        else:
            # Log the error message from Supabase response for debugging
            await message.reply(f"❌ Error redeeming key. Status code: {response.status_code} - {response.text}")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

# --- Run Bot ---
if __name__ == "__main__":
    print("Bot starting...")
    app.run()
