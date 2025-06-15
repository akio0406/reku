import re
import random
import string
import logging
import os
import functools
import asyncio

from collections import Counter
from datetime import datetime, timedelta, timezone

from pytz import timezone as pytz_timezone  # Renamed to avoid conflict

from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

from supabase import create_client


cooldown_tracker = {}
COOLDOWN_PERIOD = timedelta(seconds=30)  # 30-second cooldown per user
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

def requires_premium(func):
    @functools.wraps(func)
    async def wrapper(client, update):
        # figure out the user & how to reply
        if isinstance(update, Message):
            uid = update.from_user.id
            deny = lambda: update.reply("⛔ Redeem a key first with `/redeem <key>`.") 
        elif isinstance(update, CallbackQuery):
            uid = update.from_user.id
            deny = lambda: update.answer("⛔ Redeem a key first with `/redeem <key>`.", show_alert=True)
        else:
            # shouldn’t happen
            return

        # do the access check
        if not check_user_access(uid):
            return await deny()

        # user is premium, run the real handler
        return await func(client, update)

    return wrapper
    
# ── ADMIN-ONLY COMMANDS ──

@app.on_message(filters.command("generate") & filters.user(ADMIN_ID))
async def generate_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /generate <duration> (e.g. 1d, 3h, 5m)")

    duration_str = message.command[1].lower()
    duration_seconds = parse_duration(duration_str)
    if duration_seconds is None:
        return await message.reply("❌ Invalid format. Use: 1d, 3h or 5m")

    # Try up to 5 times to get a unique key
    key = None
    for _ in range(5):
        candidate = generate_custom_key()
        exists = supabase.table("keys_reku").select("key").eq("key", candidate).execute()
        if not exists.data:
            key = candidate
            break

    if not key:
        return await message.reply("❌ Could not generate a unique key. Try again later.")

    ins = supabase.table("keys_reku").insert({
        "key": key,
        "duration_seconds": duration_seconds
    }).execute()
    if not ins.data:
        return await message.reply("❌ Database error on insert.")

    # Compute Manila expiry
    expires_ph = (datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)) \
        .astimezone(pytz_timezone("Asia/Manila"))

    await message.reply(
        f"✅ Key generated!\n"
        f"🔑 `{key}`\n"
        f"⏳ {duration_str}\n"
        f"📅 Expires: `{expires_ph:%Y-%m-%d %H:%M:%S}`",
        quote=True
    )

@app.on_message(filters.command("remove") & filters.user(ADMIN_ID))
async def remove_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /remove <key>")
    key_to_remove = message.command[1]
    res = supabase.table("keys_reku").delete().eq("key", key_to_remove).execute()
    deleted = len(getattr(res, "data", []) or [])
    if deleted:
        await message.reply(f"🗑️ Removed `{key_to_remove}` ({deleted} row).")
    else:
        await message.reply("❌ Key not found or already removed.")

@app.on_message(filters.command("removeallkeys") & filters.user(ADMIN_ID))
async def remove_all_keys(client, message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1].lower() != "confirm":
        return await message.reply(
            "⚠️ This will delete *all* keys!\n"
            "Type `/removeallkeys confirm` to proceed.",
            parse_mode=ParseMode.MARKDOWN
        )

    # DELETE requires a WHERE clause—use key != "" to match every row
    res = supabase.table("keys_reku") \
                  .delete() \
                  .neq("key", "") \
                  .execute()

    rows = getattr(res, "data", []) or []
    count = len(rows)

    await message.reply(f"🗑️ All keys removed: {count} rows deleted.")
    
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_message(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /broadcast <announcement text>")

    text = message.text.split(maxsplit=1)[1]
    resp = supabase.table("keys_reku").select("redeemed_by").execute()
    rows = getattr(resp, "data", []) or []
    users = {row["redeemed_by"] for row in rows if row.get("redeemed_by")}

    if not users:
        return await message.reply("ℹ️ No active subscribers to broadcast to.")

    await message.reply(f"📢 Broadcasting to {len(users)} users…")

    success = failed = 0
    for uid in users:
        try:
            await client.send_message(
                chat_id=int(uid),
                text=f"📢 <b>Admin Announcement</b>\n\n{text}",
                parse_mode=enums.ParseMode.HTML
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.3)

    await message.reply(f"📊 Broadcast done:\n✅ {success} delivered\n❌ {failed} failed")

def escape_md(text):
    # Escape only *, _, and ` for Markdown (basic)
    return re.sub(r'([*_`])', r'\\\1', str(text))

@app.on_message(filters.command("redeem"))
async def redeem_key(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /redeem <key>")

    input_key = message.command[1]
    user_id = message.from_user.id

    # Check if user has already redeemed a key
    try:
        user_keys = supabase.table("keys_reku").select("*").eq("redeemed_by", user_id).execute()
        if user_keys.data:
            return await message.reply("❌ You’ve already redeemed a key. Only one redemption is allowed per user.")
    except Exception as e:
        print(f"[!] Error checking user keys: {e}")
        return await message.reply("❌ Failed to check your key status. Please try again.")

    # Lookup the input key
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

    # Calculate expiry and convert to Philippine time
    expiry_utc = datetime.now(timezone.utc) + timedelta(seconds=data["duration_seconds"])
    ph_tz = pytz_timezone("Asia/Manila")
    expiry_ph = expiry_utc.astimezone(ph_tz)
    expiry_str = expiry_ph.strftime("%Y-%m-%d %H:%M:%S %Z%z")

    # Update database to mark key as redeemed
    try:
        update_res = supabase.table("keys_reku").update({
            "redeemed": True,
            "redeemed_by": user_id,
            "redeemed_at": datetime.now(timezone.utc).isoformat(),
            "expiry": expiry_utc.isoformat()
        }).eq("key", input_key).execute()

        if not update_res.data:
            print(f"[!] Failed to update key: {update_res.model_dump()}")
            return await message.reply("❌ Failed to redeem the key. Please try again.")
    except Exception as e:
        print(f"[!] Update error: {e}")
        return await message.reply("❌ An error occurred while redeeming the key.")

    # Format readable duration
    readable_duration = str(timedelta(seconds=data["duration_seconds"]))

    # Send plain text reply without parse_mode
    try:
        await message.reply(
            f"🎉 Key redeemed successfully!\n\n"
            f"🔑 Key: {input_key}\n"
            f"⏳ Duration: {readable_duration}\n"
            f"📅 Expires on: {expiry_str}\n\n"
            f"Enjoy your premium access! Use /search to start finding accounts."
        )
    except Exception as e:
        print(f"[!] Error sending reply: {e}")

@app.on_message(filters.command("myinfo"))
@requires_premium
async def myinfo(client, message):
    user_id = message.from_user.id

    try:
        result = supabase.table("keys_reku").select("*").eq("redeemed_by", user_id).single().execute()
        key_info = result.data

        if not key_info:
            return await message.reply("❌ No redeemed key found for your account.")

        expiry = datetime.fromisoformat(key_info["expiry"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        status = "✅ ACTIVE" if expiry > now else "❌ EXPIRED"
        readable_expiry = expiry.astimezone(pytz_timezone("Asia/Manila")).strftime("%Y-%m-%d %H:%M:%S")

        await message.reply(
            f"🔐 <b>Subscription Info</b>\n"
            f"• Key: <code>{key_info['key']}</code>\n"
            f"• Status: {status}\n"
            f"• Expires on: {readable_expiry}",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        print(f"Error in /myinfo: {e}")
        await message.reply("❌ Could not retrieve your info. Try again later.")
    
@app.on_message(filters.command("search"))
@requires_premium
async def search_command(client, message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        await message.reply("Usage: /search <keyword>")
        print("[WARN] /search called without keyword.")
        return

    keyword = message.command[1].strip()
    print(f"[INFO] /search keyword received: '{keyword}' from user {user_id}")

    # Format selection buttons
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ User:Pass Only", callback_data=f"fsearch_{keyword}_userpass")],
        [InlineKeyboardButton("🌍 Include URLs", callback_data=f"fsearch_{keyword}_full")]
    ])
    await message.reply(
        f"🔎 Searching keyword: `{keyword}`\n\nChoose result format:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^fsearch_"))
async def perform_search_callback(client, cbq):
    try:
        _, keyword, mode = cbq.data.split("_", 2)
        include_urls = (mode == "full")
        await cbq.message.delete()
        await cbq.answer("🔍 Searching...", show_alert=False)

        msg = await cbq.message.reply_text(f"Searching `{keyword}`...\n[░░░░░░░░░░] 0%")

        try:
            res = supabase.table("reku").select("line").ilike("line", f"%{keyword}%").execute()
            lines = [row["line"] for row in res.data] if res.data else []
            print(f"[INFO] Found {len(lines)} lines for keyword '{keyword}'")
        except Exception as e:
            print(f"[ERROR] Supabase query failed: {e}")
            return await msg.edit_text("❌ Error querying the database.")

        if not lines:
            return await msg.edit_text("❌ No results found.")

        # Format and filter
        formatted = set()
        for line in lines:
            if not include_urls:
                parts = line.split(":")
                if len(parts) >= 2:
                    line = ":".join(parts[-2:])
            formatted.add(line.strip())

        if not formatted:
            return await msg.edit_text("❌ No valid formatted results.")

        # Remove overused duplicates
        result_file = "result.txt"
        existing = []
        if os.path.exists(result_file):
            with open(result_file, "r", encoding="utf-8") as f:
                existing = [x.strip() for x in f]
        counts = Counter(existing)

        filtered = [x for x in formatted if counts[x] < 2]
        for x in filtered:
            counts[x] += 1

        if not filtered:
            return await msg.edit_text("❌ All results already used too many times.")

        selected = random.sample(filtered, min(len(filtered), random.randint(100, 120)))
        with open(result_file, "w", encoding="utf-8") as f:
            for line in selected:
                f.write(f"{line}\n")

        preview = "\n".join(selected[:5]) + ("\n..." if len(selected) > 5 else "")
        fmt_label = "🌍 Full (with URLs)" if include_urls else "✅ User:Pass only"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download Results", callback_data=f"dl_{keyword}")],
            [InlineKeyboardButton("📋 Copy Code", callback_data=f"cc_{keyword}")]
        ])
        await msg.edit_text(
            f"🔎 **Results for:** `{keyword}`\n"
            f"📄 **Format:** {fmt_label}\n"
            f"📌 **Generated:** `{len(selected)}`\n\n"
            f"🔹 **Preview:**\n```\n{preview}\n```",
            reply_markup=keyboard
        )

    except Exception as e:
        print(f"[ERROR] perform_search_callback failed: {e}")
        await cbq.message.reply("❌ An error occurred during the search.")

@app.on_callback_query(filters.regex("^dl_"))
async def send_result_file(client, cbq):
    if os.path.exists("result.txt"):
        await cbq.message.reply_document("result.txt", caption=f"📄 Results for `{cbq.data.split('_', 1)[1]}`")
    else:
        await cbq.answer("❌ Results file not found!", show_alert=True)

@app.on_callback_query(filters.regex("^cc_"))
async def copy_result_text(client, cbq):
    if not os.path.exists("result.txt"):
        return await cbq.answer("❌ Results file not found!", show_alert=True)
    with open("result.txt", "r", encoding="utf-8") as f:
        text = f.read()
    if len(text) > 4096:
        text = text[:4090] + "...\n[Truncated]"
    await cbq.message.reply(
        f"📋 **Results for** `{cbq.data.split('_', 1)[1]}`\n\n<pre>{text}</pre>",
        parse_mode="HTML"
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
@requires_premium
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

from pyrogram.errors import MessageNotModified

# ── Shared user_state for feedback, payment & file uploads ──
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
            "Type /cancel to abort."
        )
    elif data == "send_payment":
        user_state[user_id] = {"action": "awaiting_payment_proof"}
        await callback_query.message.edit_text(
            "💳 Send your payment proof (screenshot/photo) with amount in the caption.\n\n"
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


# ── URL removal flow ──
@app.on_message(filters.command("removeurl"))
@requires_premium
async def remove_url_request(client, message: Message):
    """ Ask user to upload a file for URL removal """
    user_state[message.from_user.id] = {"action": "awaiting_file"}
    await message.reply("📂 Please upload the file containing URLs, and I'll remove them!")

@app.on_message(filters.document)
async def process_file(client, message: Message):
    """ Process the uploaded file and strip out URLs """
    user_id = message.from_user.id

    # Only proceed if we asked for a file
    if user_state.get(user_id, {}).get("action") != "awaiting_file":
        return

    user_state.pop(user_id, None)  # clear that “awaiting_file” state

    # Download and read
    file_path = await message.download()
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Remove URLs (assumes URL is everything before the last two “:”-separated parts)
    cleaned = []
    for line in lines:
        parts = line.strip().split(":")
        if len(parts) >= 3:
            cleaned.append(f"{parts[-2]}:{parts[-1]}")
        else:
            cleaned.append(line.strip())

    # If nothing changed, tell the user
    if cleaned == lines:
        await message.reply("🤔 No URLs found to remove!")
        os.remove(file_path)
        return

    # Write out the result
    out_path = "results_removedurl.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned))

    # Send it back
    await client.send_document(
        chat_id=message.chat.id,
        document=out_path,
        caption="✅ Here’s your file with URLs stripped!"
    )

    # Clean up temp files
    os.remove(file_path)
    os.remove(out_path)

@app.on_message((filters.text | filters.photo | filters.video))
async def process_user_content(client, message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    if not state:
        return

    action = state["action"]
    content = message.text or message.caption or "[No message text]"

    try:
        user = await client.get_users(user_id)
        user_info = user.first_name + (f" {user.last_name}" if user.last_name else "")
        if user.username:
            user_info += f" (@{user.username})"
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
        await message.reply(f"❌ Failed to send: {e}")
    finally:
        user_state.pop(user_id, None)
        
app.run()
