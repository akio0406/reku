import re
import random
import string
import logging
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from supabase import create_client

# === Configuration (hardcoded) ===
API_ID = 22193151  # Your API ID here
API_HASH = "7b38173cfec819a182c81a89abdef224"
BOT_TOKEN = "7976486179:AAFe7462sUPNmxBQaN-MDCICIN9YqEKbMnw"
ADMIN_ID = 5110224851  # Single admin ID only

SUPABASE_URL = "https://psxjagzdlcrxtonmezpm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzeGphZ3pkbGNyeHRvbm1lenBtIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NDIwNDM2OCwiZXhwIjoyMDU5NzgwMzY4fQ.9-UTy_y0qDEfK6N0n_YspX3BcY3CVMb2bk9tPaiddWU"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# === Initialize Supabase Client ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Initialize Pyrogram Bot ===
app = Client("log_search_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def check_user_access(user_id: int) -> bool:
    try:
        res = supabase.table("keys_reku").select("*").eq("redeemed_by", user_id).execute()
        if res.error or not res.data:
            return False
        now_utc = datetime.now(timezone.utc)
        for key in res.data:
            expiry = datetime.fromisoformat(key["expiry"].replace("Z", "+00:00"))
            if expiry > now_utc:
                return True
        return False
    except Exception as e:
        print(f"Error checking user access: {e}")
        return False

def generate_custom_key():
    chars = string.ascii_uppercase + string.digits
    return "REKU-" + ''.join(random.choices(chars, k=10))

def parse_duration(duration_str: str) -> int:
    match = re.fullmatch(r"(\d+)([dhm])", duration_str)
    if not match:
        return None

    amount, unit = int(match.group(1)), match.group(2)

    if unit == "d":
        return amount * 86400  # 24 * 60 * 60
    elif unit == "h":
        return amount * 3600  # 60 * 60
    elif unit == "m":
        return amount * 60
    else:
        return None

@app.on_message(filters.command("generate"))
async def generate_key(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ You are not authorized to use this command.")

    if len(message.command) < 2:
        return await message.reply("Usage: /generate <duration> (e.g. 1d, 3h, 5m)")

    duration_str = message.command[1].lower()
    duration_seconds = parse_duration(duration_str)

    if duration_seconds is None:
        return await message.reply("❌ Invalid format. Use: 1d (days), 3h, or 5m")

    key = generate_custom_key()
    attempts = 0

    # Loop to avoid duplicates
    while True:
        existing = supabase.table("keys_reku").select("key").eq("key", key).execute()
        if not existing.data:
            break
        key = generate_custom_key()
        attempts += 1
        if attempts > 5:
            return await message.reply("❌ Failed to generate a unique key. Try again.")

    # Insert new key
    insert_res = supabase.table("keys_reku").insert({
        "key": key,
        "duration_seconds": duration_seconds
    }).execute()

    if not insert_res.data:
        print(f"Insertion failed: {insert_res.model_dump()}")
        return await message.reply("❌ Failed to insert the key into the database.")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)

    await message.reply(
        f"✅ Key generated:\n`{key}`\n"
        f"Valid for {duration_str} (until {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')})",
        quote=True
    )

@app.on_message(filters.command("redeem"))
async def redeem_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /redeem <key>")

    input_key = message.command[1]
    user_id = message.from_user.id

    try:
        result = supabase.table("keys_reku").select("*").eq("key", input_key).single().execute()
    except Exception as e:
        print(f"[!] Error during key lookup: {e}")
        return await message.reply("❌ An error occurred while checking the key.")

    data = result.data

    if not data:
        return await message.reply("❌ Invalid key.")

    if data.get("redeemed"):
        return await message.reply("❌ This key has already been redeemed.")

    expiry = datetime.now(timezone.utc) + timedelta(seconds=data["duration_seconds"])

    try:
        update_res = supabase.table("keys_reku").update({
            "redeemed": True,
            "redeemed_by": user_id,
            "redeemed_at": datetime.now(timezone.utc).isoformat(),
            "expiry": expiry.isoformat()
        }).eq("key", input_key).execute()

        if not update_res.data:
            print(f"[!] Failed to update key: {update_res.model_dump()}")
            return await message.reply("❌ Failed to redeem the key. Please try again.")
    except Exception as e:
        print(f"[!] Update error: {e}")
        return await message.reply("❌ An error occurred while redeeming the key.")

    readable_duration = str(timedelta(seconds=data["duration_seconds"]))

    await message.reply(
        f"🎉 Key redeemed!\nPremium access granted for {readable_duration}."
    )

@app.on_message(filters.command("start"))
async def start(client, message):
    try:
        user_id = message.from_user.id
        res = supabase.table("keys_reku").select("*").eq("redeemed_by", user_id).execute()

        is_premium = False
        if res.data:
            try:
                key_info = res.data[0]
                expiry = datetime.fromisoformat(key_info["expiry"].replace("Z", "+00:00"))
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
        if message.photo:
            await client.send_photo(ADMIN_ID, message.photo.file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
        elif message.video:
            await client.send_video(ADMIN_ID, message.video.file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
        else:
            await client.send_message(ADMIN_ID, caption, parse_mode=ParseMode.MARKDOWN)
        await message.reply("✅ Your message has been sent to the admin. Thank you!")
    except Exception as e:
        await message.reply(f"❌ Failed to send: {str(e)}")
    finally:
        user_state.pop(user_id, None)

app.run()
