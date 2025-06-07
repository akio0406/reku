import os
import re
import random
import logging
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from supabase import create_client

# === Load Configuration from Environment Variables ===
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# === Initialize Supabase Client ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Initialize Pyrogram Bot ===
app = Client("log_search_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def check_user_access(user_id: int) -> bool:
    res = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
    if res.data:
        expiry = datetime.fromisoformat(res.data[0]["expiry"].replace("Z", "+00:00"))
        return expiry > datetime.now(timezone.utc)
    return False

@app.on_message(filters.command("start"))
async def start(client, message):
    try:
        user_id = message.from_user.id
        res = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
        is_premium = False

        if res.data:
            try:
                expiry = datetime.fromisoformat(res.data[0]["expiry"].replace("Z", "+00:00"))
                is_premium = expiry > datetime.now(timezone.utc)
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
            parse_mode=ParseMode.HTML
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
                await client.send_photo(admin_id, message.photo.file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            elif message.video:
                await client.send_video(admin_id, message.video.file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
            else:
                await client.send_message(admin_id, caption, parse_mode=ParseMode.MARKDOWN)
        await message.reply("✅ Your message has been sent to the admin. Thank you!")
    except Exception as e:
        await message.reply(f"❌ Failed to send: {str(e)}")
    finally:
        user_state.pop(user_id, None)

from datetime import datetime, timedelta, timezone
import random
import re

@app.on_message(filters.command("generate") & filters.user(ADMIN_ID))
async def generate_key(client, message):
    print(f"/generate command received from user {message.from_user.id} with text: {message.text}")  # Debug print
    try:
        args = message.text.split()
        if len(args) < 2:
            return await message.reply(
                "❌ Usage: `/generate <duration>`\n"
                "Examples:\n`/generate 30d` - 30 days\n"
                "`/generate 1w` - 1 week\n`/generate 12h` - 12 hours",
                parse_mode=ParseMode.MARKDOWN
            )

        duration_str = args[1].lower()
        match = re.fullmatch(r"(\d+)([hdwy])", duration_str)
        if not match:
            return await message.reply(
                "❌ Invalid format. Use:\n- `h` = hours\n- `d` = days\n- `w` = weeks\n- `y` = years\n"
                "Example: `/generate 7d`",
                parse_mode=ParseMode.MARKDOWN
            )

        value, unit = int(match.group(1)), match.group(2)
        now = datetime.now(timezone.utc)
        expiry = {
            "h": now + timedelta(hours=value),
            "d": now + timedelta(days=value),
            "w": now + timedelta(weeks=value),
            "y": now + timedelta(days=365 * value)
        }.get(unit)

        if not expiry:
            return await message.reply("❌ Invalid time unit.")

        # Generate random key
        key = "ISAGI-" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))

        # Insert key into Supabase
        response = supabase.table("reku_keys").insert({
            "key": key,
            "expiry": expiry.isoformat(),
            "redeemed_by": None,
            "owner_id": message.from_user.id
        }).execute()

        if response.error:
            return await message.reply("❌ Failed to generate key. Please try again later.")

        unit_map = {"h": "hour(s)", "d": "day(s)", "w": "week(s)", "y": "year(s)"}
        human_duration = f"{value} {unit_map[unit]}"
        expiry_display = expiry.strftime('%Y-%m-%d %H:%M:%S UTC')

        await message.reply(
            f"✅ Key generated successfully!\n"
            f"🔑 Key: `{key}`\n"
            f"⏳ Duration: {human_duration}\n"
            f"📅 Expires on: `{expiry_display}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Error in /generate: {e}")
        await message.reply(f"❌ An unexpected error occurred:\n`{e}`", parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("redeem"))
async def redeem_key(client, message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("❌ Usage: /redeem <key>\nExample: /redeem ISAGI-ABC123XYZ")

    key_input = args[1].strip().upper()

    # Check key in Supabase
    response = supabase.table("reku_keys").select("*").eq("key", key_input).execute()
    if response.error or not response.data:
        return await message.reply("❌ Invalid key! Please check and try again.")

    key_info = response.data[0]

    # Check if already redeemed
    if key_info.get("redeemed_by"):
        return await message.reply("❌ This key has already been redeemed!")

    # Check if expired
    try:
        expiry = datetime.fromisoformat(key_info["expiry"])
        if expiry < datetime.now(timezone.utc):
            return await message.reply("⌛ This key has expired!")
    except Exception:
        return await message.reply("⚠️ Key has an invalid expiry format.")

    # Ensure user has no other redeemed key
    user_keys = supabase.table("reku_keys").select("*").eq("redeemed_by", message.from_user.id).execute()
    if user_keys.data:
        existing = user_keys.data[0]
        return await message.reply(
            "⚠️ You already have an active subscription!\n\n"
            f"🔑 Current Key: `{existing['key']}`\n"
            f"📅 Expires on: `{existing['expiry']}`\n\n"
            "You can only redeem one key at a time."
        )

    # Redeem the key
    update_resp = supabase.table("reku_keys").update({
        "redeemed_by": message.from_user.id
    }).eq("key", key_input).execute()

    if update_resp.error:
        return await message.reply("❌ Failed to redeem key. Please try again later.")

    expiry_display = expiry.strftime('%Y-%m-%d %H:%M:%S UTC')

    await message.reply(
        f"🎉 Key redeemed successfully!\n\n"
        f"🔑 Key: `{key_input}`\n"
        f"📅 Expires on: `{expiry_display}`\n\n"
        f"Enjoy your premium access! Use /search to start finding accounts.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notify admin
    try:
        user = await client.get_users(message.from_user.id)
        username = f"{user.first_name} {user.last_name or ''}".strip()
        if user.username:
            username += f" (@{user.username})"

        await client.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🔑 Key Redeemed Notification\n"
                f"├─ Key: `{key_input}`\n"
                f"├─ User: {username}\n"
                f"├─ ID: `{message.from_user.id}`\n"
                f"└─ Expiry: `{expiry_display}`"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Failed to notify admin: {e}")

@app.on_message(filters.command("myinfo"))
async def myinfo(client, message):
    user_id = message.from_user.id
    response = supabase.table("reku_keys").select("*").eq("redeemed_by", user_id).execute()
    if not response.data:
        return await message.reply("❌ You do not have an active premium subscription.")

    key_info = response.data[0]
    expiry = datetime.fromisoformat(key_info["expiry"]).strftime('%Y-%m-%d %H:%M:%S UTC')
    await message.reply(
        f"🔑 Your Premium Info:\n"
        f"• Key: `{key_info['key']}`\n"
        f"• Expires on: `{expiry}`",
        parse_mode=ParseMode.MARKDOWN
    )

if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
