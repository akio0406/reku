import os
import re
import json
import time
import random
import asyncio
import datetime
import pytz
import base64
import requests
from collections import Counter
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client

# --- Environment Variables ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- Supabase Client ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- App + Globals ---

# --- Supabase-based key functions ---
async def get_all_keys():
    res = supabase.table("reku_keys").select("*").execute()
    return res.data if res.data else []

async def get_key_entry(key):
    res = supabase.table("reku_keys").select("*").eq("key", key).limit(1).execute()
    return res.data[0] if res.data else None

async def insert_key_entry(key, expiry, owner_id):
    supabase.table("reku_keys").insert({"key": key, "expiry": expiry, "owner_id": owner_id}).execute()

async def update_key_redeemed_by(key, user_id):
    supabase.table("reku_keys").update({"redeemed_by": user_id}).eq("key", key).execute()

async def delete_key_entry(key):
    supabase.table("reku_keys").delete().eq("key", key).execute()



# --- Supabase Key Management (Final Version) ---
async def get_all_keys():
    res = supabase.table("reku_keys").select("*").execute()
    return res.data if res.data else []

async def get_key_entry(key):
    res = supabase.table("reku_keys").select("*").eq("key", key).limit(1).execute()
    return res.data[0] if res.data else None

async def insert_key_entry(key, expiry, owner_id, duration):
    supabase.table("reku_keys").insert({
        "key": key,
        "expiry": expiry,
        "owner_id": owner_id,
        "duration": duration,
        "created": datetime.datetime.now().isoformat()
    }).execute()

async def update_key_redeemed_by(key, user_id):
    supabase.table("reku_keys").update({"redeemed_by": user_id}).eq("key", key).execute()

async def delete_key_entry(key):
    supabase.table("reku_keys").delete().eq("key", key).execute()

async def get_user_key_info(user_id: int):
    keys = await get_all_keys()
    for key in keys:
        if str(key.get("redeemed_by")) == str(user_id):
            return key["key"], key
    return None, None

async def check_user_access(user_id: int):
        keys = await get_all_keys()
    for key in keys:
        if key["redeemed_by"] == user_id:
            return True
    return False


app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_state = {}
search_cooldowns = {}

# --- File Paths ---
KEYS_FILE = "keys.json"
PAYMENTS_FILE = "payments.json"
ACTIVITY_LOG_FILE = "user_activity.json"

def load_activity_log():
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_activity_log(data):
    with open(ACTIVITY_LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def log_user_activity(user_id, action, details=None):
    activities = load_activity_log()
    user_id = str(user_id)
    
    if user_id not in activities:
        activities[user_id] = []
    
    activities[user_id].append({
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "details": details
    })
    
    activities[user_id] = activities[user_id][-100:]
    save_activity_log(activities)

def load_payments():
    if os.path.exists(PAYMENTS_FILE):
        with open(PAYMENTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_payments(data):
    with open(PAYMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def parse_duration(duration_str):
    """Convert duration string (e.g., 30d, 1w, 12h) to timedelta"""
    try:
        if duration_str.endswith('d'):
            days = int(duration_str[:-1])
            return datetime.timedelta(days=days)
        elif duration_str.endswith('w'):
            weeks = int(duration_str[:-1])
            return datetime.timedelta(weeks=weeks)
        elif duration_str.endswith('h'):
            hours = int(duration_str[:-1])
            return datetime.timedelta(hours=hours)
        else:
            return None
    except ValueError:
        return None

def format_duration(duration_str):
    """Convert duration string to human-readable format"""
    if not duration_str or duration_str.lower() == "unknown":
        return "Unknown"
    
    try:
        if duration_str.endswith('d'):
            days = int(duration_str[:-1])
            if days == 1:
                return "1 day"
            return f"{days} days"
        elif duration_str.endswith('w'):
            weeks = int(duration_str[:-1])
            if weeks == 1:
                return "1 week"
            return f"{weeks} weeks"
        elif duration_str.endswith('h'):
            hours = int(duration_str[:-1])
            if hours == 1:
                return "1 hour"
            return f"{hours} hours"
        else:
            return duration_str
    except ValueError:
        return duration_str

async def await check_user_access(user_id):
        keys = await get_all_keys()
    user_id = str(user_id) 
    for info in keys.values():
        if str(info.get("redeemed_by")) == user_id:
            try:
                if datetime.datetime.fromisoformat(info["expiry"]) > datetime.datetime.now():
                    return True
            except ValueError:
                continue
    return False


@app.on_message(filters.command("redeem"))
async def redeem_key(client, message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("❌ Usage: /redeem <key>\nExample: /redeem ISAGI-ABC123XYZ")
    
    key = args[1].strip().upper()
    keys = await get_all_keys()
    
    if key not in keys:
        return await message.reply("❌ Invalid key! Please check your key and try again.")
    
    key_info = keys[key]

    if key_info.get("redeemed_by"):
        return await message.reply("❌ This key has already been redeemed!")

    try:
        expiry = datetime.datetime.fromisoformat(key_info["expiry"])
        if expiry < datetime.datetime.now():
            return await message.reply("⌛ This key has expired!")
    except ValueError:
        return await message.reply("⚠️ Key has invalid expiry date")
    existing_key, existing_info = get_user_key_info(message.from_user.id)
    if existing_key:
        return await message.reply(
            "⚠️ You already have an active subscription!\n\n"
            f"🔑 Current Key: {existing_key}\n"
            f"⏳ Expiry: {existing_info['expiry']}\n\n"
            "You can only have one active subscription at a time."
        )
    
    keys[key]["redeemed_by"] = str(message.from_user.id)
    # Supabase handles saving automatically
    
    human_duration = format_duration(key_info.get("duration", "Unknown"))
    
    await message.reply(
        f"🎉 Key redeemed successfully!\n\n"
        f"🔑 Key: `{key}`\n"
        f"⏳ Duration: {human_duration}\n"
        f"📅 Expires on: {expiry}\n\n"
        f"Enjoy your premium access! Use /search to start finding accounts."
    )

    try:
        user = await client.get_users(message.from_user.id)
        user_info = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        user_info += f" (@{user.username})" if user.username else ""
        
        await client.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🔑 Key Redeemed Notification\n"
                f"├─ Key: `{key}`\n"
                f"├─ User: {user_info}\n"
                f"├─ ID: `{message.from_user.id}`\n"
                f"└─ Expiry: {expiry}"
            )
        )
    except Exception:
        pass

@app.on_message(filters.command("myinfo"))
async def user_info(client, message):
    user_id = message.from_user.id
    key, info = get_user_key_info(user_id)
    
    if not key:
        return await message.reply("ℹ️ You don't have an active subscription")
    
    try:
        expiry = datetime.datetime.fromisoformat(info["expiry"])
        remaining = expiry - datetime.datetime.now()
        
        if remaining.days > 0:
            remaining_str = f"{remaining.days} days"
        else:
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            remaining_str = f"{hours}h {minutes}m"
        
        duration = format_duration(info.get("duration", "Unknown"))
        
        info_text = (
            "🔑 <b>Your Subscription Info</b>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"🎫 <b>Key:</b> <code>{key}</code>\n"
            f"⏳ <b>Expiry:</b> {info['expiry']}\n"
            f"🕒 <b>Remaining:</b> {remaining_str}\n"
            f"📅 <b>Duration:</b> {duration}\n"
            f"📅 <b>Activated:</b> {info.get('created', 'Unknown')}"
        )
        await message.reply_text(info_text, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

def get_log_files():
    return sorted([
        f for f in os.listdir()
        if re.fullmatch(r"logs\d+\.txt", f)
    ])

def aes_encrypt(text, password):
    key = password.ljust(32)[:32].encode('utf-8')
    cipher = AES.new(key, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
    iv = cipher.iv
    return base64.b64encode(iv + ct_bytes).decode('utf-8')

@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "🔥 <b>𝗕𝗢𝗧 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b> 🔥\n"
        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
        
        "🔹 <b>𝗚𝗘𝗡𝗘𝗥𝗔𝗟 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n"
        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
        "• /start - Check bot status\n"
        "• /help - Show this message\n"
        "• /redeem - Activate premium key\n"
        "• /payment - Submit payment proof\n"
        "• /myinfo - View subscription info\n"
        "• /feedback - Send suggestions\n\n"
        
        "🔹 <b>𝗦𝗘𝗔𝗥𝗖𝗛 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n"
        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
        "• /search - Find accounts\n"
        "• /dice - Random account reward\n"
        "• /countlines - Check database count\n\n"
        
        "🔹 <b>𝗙𝗜𝗟𝗘 𝗧𝗢𝗢𝗟𝗦</b>\n"
        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
        "• /removeurl - Clean combo files\n"
        "• /merge - Combine multiple files\n\n"
        
        "🔹 <b>𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n"
        "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
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

@app.on_callback_query(filters.regex("^redeem_help$"))
async def redeem_help(client, callback_query):
    help_text = (
        "🔑 How to Redeem Your Key:\n\n"
        "1. Purchase a key from our seller\n"
        "2. Type: /redeem YOUR_KEY_HERE\n"
        "3. Enjoy full access!\n\n"
        "Example: /redeem ISAGI-ABC123XYZ\n\n"
        "⚠️ Each key can only be used once"
    )
    try:
        await callback_query.answer()
        await callback_query.message.edit_text(
            help_text,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        await callback_query.message.reply_text(f"Error: {str(e)}")

@app.on_message(filters.command("users") & filters.user(ADMIN_ID))
async def list_users(client, message):
    keys = await get_all_keys()
    users = {}
    
    for key, info in keys.items():
        if info.get("redeemed_by"):
            user_id = info["redeemed_by"]
            try:
                expiry = datetime.datetime.fromisoformat(info["expiry"])
                remaining = expiry - datetime.datetime.now()
                
                if remaining.days > 0:
                    remaining_str = f"{remaining.days}d {remaining.seconds//3600}h"
                else:
                    remaining_str = f"{remaining.seconds//3600}h {(remaining.seconds%3600)//60}m"
                
                users[user_id] = {
                    "key": key,
                    "expiry": info["expiry"],
                    "remaining": remaining_str,
                    "active": remaining.total_seconds() > 0
                }
            except ValueError:
                continue
    
    if not users:
        return await message.reply("ℹ️ No users have redeemed any keys yet.")
    
    user_details = []
    for user_id, data in users.items():
        try:
            user = await client.get_users(int(user_id))
            username = f"@{user.username}" if user.username else "No username"
            name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        except:
            username = "Unknown"
            name = "Unknown"
        
        status = "🟢" if data["active"] else "🔴"
        user_details.append(
            f"{status} <b>User:</b> {name} ({username})\n"
            f"├─ <b>ID:</b> <code>{user_id}</code>\n"
            f"├─ <b>Key:</b> <code>{data['key']}</code>\n"
            f"├─ <b>Expires:</b> {data['expiry']}\n"
            f"└─ <b>Remaining:</b> {data['remaining']}\n"
        )
    
    message_text = "👥 <b>Redeemed Users:</b>\n\n" + "\n".join(user_details)
    if len(message_text) > 4096:
        parts = [message_text[i:i+4096] for i in range(0, len(message_text), 4096)]
        for part in parts:
            await message.reply(part, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply(message_text, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("generate") & filters.user(ADMIN_ID))
async def generate_key(client, message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("❌ Usage: `/generate <duration>`\nExamples:\n`/generate 30d` - 30 days\n`/generate 1w` - 1 week\n`/generate 12h` - 12 hours")
    
    duration_str = args[1]
    delta = parse_duration(duration_str)
    if not delta:
        return await message.reply("❌ Invalid duration format. Use:\n- `h` for hours\n- `d` for days\n- `w` for weeks\nExample: `/generate 30d`")
    
    expiry = (datetime.datetime.now() + delta).isoformat()
    key = "ISAGI-" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))
    keys = await get_all_keys()
    keys[key] = {
        "expiry": expiry,
        "redeemed_by": None,
        "created": datetime.datetime.now().isoformat(),
        "duration": duration_str
    }
    # Supabase handles saving automatically
    
    human_duration = format_duration(duration_str)
    await message.reply(
        f"✅ Key generated successfully!\n"
        f"🔑 Key: `{key}`\n"
        f"⏳ Duration: {human_duration}\n"
        f"📅 Expires on: {expiry}"
    )

@app.on_message(filters.command("masskey") & filters.user(ADMIN_ID))
async def mass_generate_keys(client, message):
    args = message.text.split()
    if len(args) < 3:
        return await message.reply(
            "❌ <b>Usage:</b> <code>/masskey &lt;duration&gt; &lt;quantity&gt; [prefix]</code>\n\n"
            "💡 <b>Examples:</b>\n"
            "<code>/masskey 30d 50</code> - 50 keys for 30 days\n"
            "<code>/masskey 1w 20 PREM-</code> - 20 keys for 1 week with 'PREM-' prefix",
            parse_mode=enums.ParseMode.HTML
        )
    
    duration_str = args[1]
    delta = parse_duration(duration_str)
    if not delta:
        return await message.reply(
            "❌ Invalid duration format. Use:\n"
            "- <code>h</code> for hours\n"
            "- <code>d</code> for days\n"
            "- <code>w</code> for weeks\n"
            "<b>Example:</b> <code>/masskey 30d 50</code>",
            parse_mode=enums.ParseMode.HTML
        )
    
    try:
        quantity = int(args[2])
        if quantity > 200:
            return await message.reply("❌ Maximum quantity is 200 keys at once")
        if quantity < 1:
            return await message.reply("❌ Quantity must be at least 1")
    except ValueError:
        return await message.reply("❌ Quantity must be a number")

    prefix = "ιsαgι-"
    if len(args) >= 4:
        prefix = args[3].strip() + "-"
        if len(prefix) > 10:
            return await message.reply("❌ Prefix too long (max 10 characters)")
    
    expiry = (datetime.datetime.now() + delta).isoformat()
    keys = await get_all_keys()

    confirm_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ GENERATE KEYS", callback_data=f"confirm_masskey_{quantity}_{duration_str}_{prefix}")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="cancel_masskey")]
    ])
    
    await message.reply(
        f"⚠️ <b>Confirm Mass Key Generation</b>\n\n"
        f"⏳ <b>Duration:</b> {format_duration(duration_str)}\n"
        f"🔢 <b>Quantity:</b> {quantity}\n"
        f"🔤 <b>Prefix:</b> {prefix}\n"
        f"📅 <b>Expiry:</b> {expiry}\n\n"
        "This will create <b>{quantity}</b> premium keys".format(quantity=quantity),
        reply_markup=confirm_keyboard,
        parse_mode=enums.ParseMode.HTML
    )

@app.on_callback_query(filters.regex("^confirm_masskey_"))
async def confirm_masskey(client, callback_query):
    parts = callback_query.data.split('_')
    if len(parts) < 4:
        await callback_query.answer("❌ Invalid data format", show_alert=True)
        return

    quantity_str = parts[2]
    duration_str = parts[3]
    prefix = '_'.join(parts[4:])  
    
    try:
        quantity = int(quantity_str)
    except ValueError:
        await callback_query.answer("❌ Invalid quantity value", show_alert=True)
        return

    delta = parse_duration(duration_str)
    expiry = (datetime.datetime.now() + delta).isoformat()
    keys = await get_all_keys()
    
    generated_keys = []
    for _ in range(quantity):
        key = prefix + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
        keys[key] = {
            "expiry": expiry,
            "redeemed_by": None,
            "created": datetime.datetime.now().isoformat(),
            "duration": duration_str
        }
        generated_keys.append(key)
    
    # Supabase handles saving automatically
    
    keys_formatted = "\n".join(generated_keys)
    human_duration = format_duration(duration_str)
    
    filename = f"keys_{quantity}_{duration_str}.txt"
    with open(filename, "w") as f:
        f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Duration: {human_duration}\n")
        f.write(f"Expiry: {expiry}\n\n")
        f.write(keys_formatted)
    
    try:
        await callback_query.message.delete()
        await client.send_document(
            chat_id=callback_query.message.chat.id,
            document=filename,
            caption=(
                f"✅ Successfully generated {quantity} keys\n"
                f"⏳ Duration: {human_duration}\n"
                f"📅 Expiry: {expiry}\n"
                f"🔤 Prefix: {prefix}\n\n"
                "⚠️ Store securely - keys are active immediately"
            )
        )
    finally:
        if os.path.exists(filename):
            os.remove(filename)

@app.on_callback_query(filters.regex("^cancel_masskey$"))
async def cancel_masskey(client, callback_query):
    await callback_query.message.edit_text("❌ Mass key generation cancelled")

@app.on_message(filters.command("remove") & filters.user(ADMIN_ID))
async def remove_license(client, message):
    args = message.text.split()
    if len(args) != 2:
        return await message.reply("❌ Usage: `/remove <key>`")
    
    try:
        key = args[1]
        keys = await get_all_keys()
        if key not in keys:
            return await message.reply("🚫 Key not found.")
        
        keys.pop(key)
        # Supabase handles saving automatically
        await message.reply(f"✅ Key `{key}` has been removed.")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_message(client, message):
    if len(message.command) < 2:
        return await message.reply("❌ Usage: /broadcast <message>")
    
    broadcast_text = message.text.split(maxsplit=1)[1]
    keys = await get_all_keys()
    users = set(str(info["redeemed_by"]) for info in keys.values() if info.get("redeemed_by"))
    
    if not users:
        return await message.reply("ℹ️ No users to broadcast to")
    
    await message.reply(f"📢 Starting broadcast to {len(users)} users...")
    
    success = 0
    failed = 0
    for user_id in users:
        try:
            await client.send_message(
                chat_id=int(user_id),
                text=f"📢 <b>Announcement from Admin:</b>\n{broadcast_text}",
                parse_mode=enums.ParseMode.HTML
            )
            success += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            failed += 1
            print(f"Failed to send to {user_id}: {str(e)}")
    
    await message.reply(
        f"📊 Broadcast completed:\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}"
    )

@app.on_message(filters.command("payment"))
async def payment_command(client, message):
    user_state[message.from_user.id] = {"action": "awaiting_payment_proof"}
    await message.reply(
        "💳 **Payment Process** 💳\n\n"
        "1. Send your payment proof (screenshot/photo)\n"
        "2. Include amount paid in the caption\n"
        "3. Your payment will be verified within 24 hours\n\n"
        "📝 Example caption:\n"
        "<code>Payment for Premium Access - ₱200</code>\n\n"
        "Type /cancel to abort."
    )

@app.on_message(
    (filters.photo | filters.document) & 
    filters.create(lambda _, __, m: m.from_user and user_state.get(m.from_user.id, {}).get("action") == "awaiting_payment_proof")
)
async def process_payment_proof(client, message):
    user_id = message.from_user.id
    
    try:
        user = await client.get_users(user_id)
        user_info = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        user_info += f" (@{user.username})" if user.username else ""
    except:
        user_info = f"User ID: {user_id}"
    
    payment_details = message.caption if message.caption else "No payment details provided"
    
    payment_id = f"PAY-{int(time.time())}-{random.randint(1000,9999)}"
    payments = load_payments()
    
    if message.photo:
        file_id = message.photo.file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        await message.reply("❌ Unsupported file type. Please send a photo or document.")
        return
    
    payments[payment_id] = {
        "user_id": user_id,
        "user_info": user_info,
        "file_id": file_id,
        "file_type": file_type,
        "details": payment_details,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "pending"
    }
    
    save_payments(payments)
    
    payment_msg = (
        f"💰 **New Payment Proof** ({payment_id})\n\n"
        f"👤 **From:** {user_info}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"📅 **Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📝 **Payment Details:**\n{payment_details}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"accept_pay_{payment_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_pay_{payment_id}")
        ],
        [InlineKeyboardButton("👀 View Proof", callback_data=f"view_pay_{payment_id}")]
    ])
    
    try:
        if message.photo:
            await client.send_photo(
                chat_id=ADMIN_ID,
                photo=file_id,
                caption=payment_msg,
                reply_markup=keyboard
            )
        elif message.document:
            await client.send_document(
                chat_id=ADMIN_ID,
                document=file_id,
                caption=payment_msg,
                reply_markup=keyboard
            )
        
        await message.reply(
            "✅ Payment proof sent to admin!\n\n"
            "Your payment will be verified within 24 hours. "
            "You'll receive a notification once processed."
        )
    except Exception as e:
        await message.reply(f"❌ Failed to send payment proof: {str(e)}")
    finally:
        user_state.pop(user_id, None)

@app.on_message(filters.command("payments") & filters.user(ADMIN_ID))
async def list_payments(client, message):
    payments = load_payments()
    if not payments:
        return await message.reply("ℹ️ No pending payments found.")
    
    pending = {pid: data for pid, data in payments.items() if data["status"] == "pending"}
    
    if not pending:
        return await message.reply("ℹ️ No pending payments found.")
    
    response = "📋 **Pending Payments**\n\n"
    for pid, data in pending.items():
        response += (
            f"🔹 **ID:** `{pid}`\n"
            f"👤 **User:** {data['user_info']}\n"
            f"🆔 **User ID:** `{data['user_id']}`\n"
            f"📅 **Date:** {data['timestamp']}\n"
            f"📝 **Details:** {data['details']}\n\n"
        )
    
    await message.reply(response, parse_mode=enums.ParseMode.HTML)

@app.on_callback_query(filters.regex("^accept_pay_"))
async def accept_payment(client, callback_query):
    payment_id = callback_query.data.split("_", 2)[2]
    payments = load_payments()
    
    if payment_id not in payments:
        await callback_query.answer("❌ Payment not found!", show_alert=True)
        return
    
    payment = payments[payment_id]
    if payment["status"] != "pending":
        await callback_query.answer("⚠️ Payment already processed!", show_alert=True)
        return
    
    user_state[callback_query.from_user.id] = {
        "action": "awaiting_key_duration",
        "payment_id": payment_id
    }
    
    await callback_query.answer()
    await callback_query.message.reply(
        f"✅ Accepting payment {payment_id}\n\n"
        "Please send the key duration (e.g., 30d, 1w, 24h):\n"
        "- Use `d` for days\n"
        "- Use `w` for weeks\n"
        "- Use `h` for hours\n\n"
        "Example: `30d` for 30 days"
    )

@app.on_message(filters.text & filters.user(ADMIN_ID) & 
                filters.create(lambda _, __, m: user_state.get(m.from_user.id, {}).get("action") == "awaiting_key_duration"))
async def process_key_duration(client, message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    
    if not state or state.get("action") != "awaiting_key_duration":
        return
    
    payment_id = state["payment_id"]
    payments = load_payments()
    
    if payment_id not in payments:
        await message.reply("❌ Payment not found!")
        user_state.pop(user_id, None)
        return
    
    duration_str = message.text.strip()
    delta = parse_duration(duration_str)
    
    if not delta:
        await message.reply("❌ Invalid duration format. Please try again.")
        return
    
    payment = payments[payment_id]
    expiry = (datetime.datetime.now() + delta).isoformat()
    key = "ISAGI-" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))
    
    keys = await get_all_keys()
    keys[key] = {
        "expiry": expiry,
        "redeemed_by": str(payment["user_id"]),
        "created": datetime.datetime.now().isoformat(),
        "duration": duration_str
    }
    # Supabase handles saving automatically
    
    payments[payment_id]["status"] = "accepted"
    payments[payment_id]["key"] = key
    save_payments(payments)
    
    human_duration = format_duration(duration_str)
    
    try:
        await client.send_message(
            chat_id=payment["user_id"],
            text=(
                "🎉 **Payment Accepted!**\n\n"
                f"✅ Your payment ({payment_id}) has been verified\n"
                f"🔑 Your premium key: `{key}`\n"
                f"⏳ Duration: {human_duration}\n\n"
                "Use /redeem to activate your subscription!\n"
                "Thank you for your purchase! 🎁"
            )
        )
    except Exception:
        pass
    
    try:
        await client.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.id,
            caption=callback_query.message.caption + f"\n\n✅ ACCEPTED\n🔑 Key: `{key}`\n⏳ Duration: {human_duration}",
            reply_markup=None
        )
    except Exception:
        pass
    
    await message.reply(f"✅ Payment accepted! Key sent to user.")
    user_state.pop(user_id, None)

@app.on_callback_query(filters.regex("^reject_pay_"))
async def reject_payment(client, callback_query):
    payment_id = callback_query.data.split("_", 2)[2]
    payments = load_payments()
    
    if payment_id not in payments:
        await callback_query.answer("❌ Payment not found!", show_alert=True)
        return
    
    payment = payments[payment_id]
    if payment["status"] != "pending":
        await callback_query.answer("⚠️ Payment already processed!", show_alert=True)
        return
    
    user_state[callback_query.from_user.id] = {
        "action": "awaiting_reject_reason",
        "payment_id": payment_id
    }
    
    await callback_query.answer()
    await callback_query.message.reply(
        f"❌ Rejecting payment {payment_id}\n\n"
        "Please send the reason for rejection (this will be sent to the user):"
    )

@app.on_message(filters.text & filters.user(ADMIN_ID) & 
                filters.create(lambda _, __, m: user_state.get(m.from_user.id, {}).get("action") == "awaiting_reject_reason"))
async def process_reject_reason(client, message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    
    if not state or state.get("action") != "awaiting_reject_reason":
        return
    
    payment_id = state["payment_id"]
    payments = load_payments()
    
    if payment_id not in payments:
        await message.reply("❌ Payment not found!")
        user_state.pop(user_id, None)
        return
    
    reason = message.text
    payment = payments[payment_id]
    
    payments[payment_id]["status"] = "rejected"
    payments[payment_id]["reason"] = reason
    save_payments(payments)
    
    try:
        await client.send_message(
            chat_id=payment["user_id"],
            text=(
                "❌ **Payment Rejected**\n\n"
                f"Your payment ({payment_id}) was rejected by admin.\n"
                f"📝 Reason: {reason}\n\n"
                "Please contact admin if you believe this is a mistake."
            )
        )
    except Exception:
        pass
    
    try:
        await client.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.id,
            caption=callback_query.message.caption + f"\n\n❌ REJECTED\nReason: {reason}",
            reply_markup=None
        )
    except Exception:
        pass
    
    await message.reply(f"✅ Payment {payment_id} rejected. User notified.")
    user_state.pop(user_id, None)

@app.on_callback_query(filters.regex("^view_pay_"))
async def view_payment(client, callback_query):
    payment_id = callback_query.data.split("_", 2)[2]
    payments = load_payments()
    
    if payment_id not in payments:
        await callback_query.answer("❌ Payment not found!", show_alert=True)
        return
    
    payment = payments[payment_id]
    
    try:
        if payment["file_type"] == "photo":
            await client.send_photo(
                chat_id=ADMIN_ID,
                photo=payment["file_id"],
                caption=f"🔄 Resent payment proof: {payment_id}"
            )
        else:
            await client.send_document(
                chat_id=ADMIN_ID,
                document=payment["file_id"],
                caption=f"🔄 Resent payment proof: {payment_id}"
            )
        await callback_query.answer("✅ Payment proof resent to chat", show_alert=True)
    except Exception as e:
        await callback_query.answer(f"❌ Error: {str(e)}", show_alert=True)

@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
    user_id = message.from_user.id
    state_action = user_state.get(user_id, {}).get("action")
    
    if state_action == "awaiting_payment_proof":
        user_state.pop(user_id, None)
        await message.reply("🚫 Payment submission cancelled.")
    elif state_action == "awaiting_reject_reason":
        user_state.pop(user_id, None)
        await message.reply("🚫 Payment rejection cancelled.")
    elif state_action == "awaiting_key_duration":
        user_state.pop(user_id, None)
        await message.reply("🚫 Key duration input cancelled.")
    elif state_action == "awaiting_encrypt_file":
        user_state.pop(user_id, None)
        await message.reply("🚫 File encryption cancelled.")
    elif state_action == "awaiting_feedback":
        user_state.pop(user_id, None)
        await message.reply("🚫 Feedback submission cancelled.")
    elif state_action == "awaiting_file":
        user_state.pop(user_id, None)
        await message.reply("🚫 File processing cancelled.")
    elif state_action == "awaiting_dedup_file":
        user_state.pop(user_id, None)
        await message.reply("🚫 Deduplication cancelled.")
    elif state_action == "awaiting_roblox_file":
        user_state.pop(user_id, None)
        await message.reply("🚫 Roblox username check cancelled.")
    elif state_action == "awaiting_merge_files":
        user_state.pop(user_id, None)
        await message.reply("🚫 File merge cancelled.")
    else:
        await message.reply("ℹ️ No active operation to cancel.")

@app.on_message(filters.command("deleteallkeys") & filters.user(ADMIN_ID))
async def delete_all_keys(client, message):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 YES, DELETE ALL KEYS", callback_data="confirm_delete_all_keys")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="cancel_delete_all_keys")]
    ])
    
    await message.reply(
        "⚠️ <b>DANGER: Delete ALL Keys?</b>\n\n"
        "This will PERMANENTLY remove all generated keys from the system.\n"
        "All active subscriptions will be immediately terminated!\n\n"
        "Are you absolutely sure you want to proceed?",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

@app.on_callback_query(filters.regex("^confirm_delete_all_keys$"))
async def confirm_delete_all_keys(client, callback_query):
    keys = await get_all_keys()
    key_count = len(keys)

    if os.path.exists(KEYS_FILE):
        os.remove(KEYS_FILE)
    
    await callback_query.message.edit_text(
        f"🔥 <b>ALL KEYS DELETED!</b>\n\n"
        f"✅ Successfully removed {key_count} keys\n"
        f"🗑️ Database file has been permanently erased",
        parse_mode=enums.ParseMode.HTML
    )

    for key, info in keys.items():
        user_id = info.get("redeemed_by")
        if user_id:
            try:
                await client.send_message(
                    chat_id=user_id,
                    text="⚠️ <b>SUBSCRIPTION TERMINATED</b>\n\n"
                         "Your premium access has been revoked because the admin deleted all keys.\n"
                         "Contact support if you believe this is a mistake.",
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                pass

@app.on_callback_query(filters.regex("^cancel_delete_all_keys$"))
async def cancel_delete_all_keys(client, callback_query):
    await callback_query.message.edit_text("❌ Key deletion cancelled")

@app.on_message(filters.command("removeurl") & filters.create(lambda _, __, m: await check_user_access(m.from_user.id)))
async def remove_url_request(client, message: Message):
    user_state[message.from_user.id] = {"action": "awaiting_file"}
    await message.reply("📂 Send me the file. I'll remove the URLs!")

@app.on_message(filters.document & filters.create(lambda _, __, m: user_state.get(m.from_user.id, {}).get("action") == "awaiting_file"))
async def process_remove_url(client, message: Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    
    if not state or state.get("action") != "awaiting_file":
        return
    
    try:
        file_path = await message.download()
        
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        cleaned = []
        for line in lines:
            line = line.strip()
            if line:
                parts = line.split(":")
                if len(parts) >= 3:
                    cleaned.append(f"{parts[-2]}:{parts[-1]}")
                else:
                    cleaned.append(line)

        if cleaned == [line.strip() for line in lines if line.strip()]:
            await message.reply("🤔 There were no URLs to remove!")
            return

        cleaned_path = "results_removedurl.txt"
        with open(cleaned_path, "w", encoding="utf-8") as f:
            f.write("\n".join(cleaned))

        await client.send_document(
            chat_id=message.chat.id,
            document=cleaned_path,
            caption="✅ URLs removed from the file!"
        )
        
    except Exception as e:
        await message.reply(f"❌ Error processing file: {str(e)}")
    finally:
        user_state.pop(user_id, None)
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        if 'cleaned_path' in locals() and os.path.exists(cleaned_path):
            os.remove(cleaned_path)

@app.on_message(filters.command("countlines"))
async def count_lines(client, message: Message):
    args = message.text.split()
    if len(args) != 2:
        return await message.reply("❌ Usage: /countlines <category>\nExample: /countlines roblox")
    
    category = args[1].lower()
    log_files = get_log_files()
    total_lines = 0
    
    for log in log_files:
        try:
            with open(log, "r", encoding="utf-8", errors="ignore") as file:
                for line in file:
                    if category in line.lower():
                        total_lines += 1
        except Exception as e:
            continue
    
    await message.reply(f"📊 Total lines for '{category}': {total_lines}")

@app.on_message(filters.command("dice") & filters.create(lambda _, __, m: await check_user_access(m.from_user.id)))
async def dice_game(client, message):
    dice_roll = random.randint(1, 6)
    
    rewards = {
        1: "roblox",
        2: "mobilelegends",
        3: "garena.com",
        4: "100082",
        5: "gaslite",
        6: "riotgames.com"
    }
    
    keyword = rewards[dice_roll]
    await message.reply(f"🎲 You rolled a {dice_roll}! Searching for: {keyword}")
    
    log_files = get_log_files()
    used_lines = set()
    
    if os.path.exists("no_dupes_don't_delete.txt"):
        with open("no_dupes_don't_delete.txt", "r", encoding="utf-8") as f:
            used_lines = set(line.strip() for line in f)
    
    found_lines = []
    for log in log_files:
        try:
            with open(log, "r", encoding="utf-8", errors="ignore") as file:
                for line in file:
                    line = line.strip()
                    if keyword.lower() in line.lower() and line not in used_lines:
                        found_lines.append(":".join(line.split(":")[-2:]))
        except Exception:
            continue
    
    if not found_lines:
        await message.reply("❌ No accounts found for your reward. Try again!")
        return
    
    reward_count = min(random.randint(1, 3), len(found_lines))
    reward_accounts = random.sample(found_lines, reward_count)
    
    with open("no_dupes_don't_delete.txt", "a", encoding="utf-8") as f:
        for acc in reward_accounts:
            f.write(acc + "\n")
    
    response = (
        f"🎁 <b>You won {reward_count} {keyword} account(s):</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
    )
    for acc in reward_accounts:
        response += f"<code>{acc}</code>\n"
    
    await message.reply(response, parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command("merge") & filters.create(lambda _, __, m: await check_user_access(m.from_user.id)))
async def merge_command(client, message):
    user_state[message.from_user.id] = {
        "action": "awaiting_merge_files", 
        "files": [],
        "file_names": [],
        "timestamp": time.time()
    }
    
    await message.reply(
        "📂 **File Merge Started**\n\n"
        "Please send me the .txt files you want to merge (one by one).\n\n"
        "✅ **Supported Actions:**\n"
        "- Send multiple .txt files\n"
        "- Type /done when finished\n"
        "- Type /cancel to abort\n\n"
        "⚠️ **Note:** Files will be deduplicated automatically"
    )

@app.on_message(
    filters.document & 
    filters.create(lambda _, __, m: user_state.get(m.from_user.id, {}).get("action") == "awaiting_merge_files")
)
async def process_merge_file(client, message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    
    if not state or time.time() - state["timestamp"] > 600:
        user_state.pop(user_id, None)
        return await message.reply("⌛ Merge session expired. Please start again with /merge")
    
    if not message.document.file_name.lower().endswith('.txt'):
        return await message.reply("❌ Only .txt files are supported for merging")
    
    try:
        file_path = await message.download()
        state["files"].append(file_path)
        state["file_names"].append(message.document.file_name)
        
        await message.reply(
            f"✅ Added {message.document.file_name}\n"
            f"📁 Total files: {len(state['files'])}\n\n"
            "Send more files or type /done when finished"
        )
    except Exception as e:
        await message.reply(f"❌ Error processing file: {str(e)}")

@app.on_message(filters.command("done") & filters.create(lambda _, __, m: user_state.get(m.from_user.id, {}).get("action") == "awaiting_merge_files"))
async def finish_merge(client, message):
    user_id = message.from_user.id
    if user_id not in user_state:
        return await message.reply("❌ No merge session active. Start with /merge")
    
    state = user_state[user_id]
    files = state["files"]
    file_names = state["file_names"]
    
    if len(files) < 2:
        for file_path in files:
            if os.path.exists(file_path):
                os.remove(file_path)
        user_state.pop(user_id, None)
        return await message.reply("❌ You need at least 2 files to merge")
    
    try:
        await message.reply("⏳ Merging files...")
        
        merged_content = []
        line_counts = {}
        
        for i, file_path in enumerate(files):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    merged_content.extend(lines)
                    line_counts[file_names[i]] = len(lines)
            except Exception as e:
                line_counts[file_names[i]] = f"Error: {str(e)}"
                continue
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        
        if not merged_content:
            user_state.pop(user_id, None)
            return await message.reply("❌ No valid content found in the files")
        
        seen = set()
        unique_content = []
        duplicates_removed = 0
        
        for line in merged_content:
            if line not in seen:
                seen.add(line)
                unique_content.append(line)
            else:
                duplicates_removed += 1
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        merged_filename = f"merged_{timestamp}.txt"
        
        with open(merged_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(unique_content))
        
        stats = ["📊 **Merge Statistics**\n"]
        stats.append(f"📂 **Files Processed:** {len(files)}")
        
        for filename, count in line_counts.items():
            if isinstance(count, int):
                stats.append(f"├─ {filename}: {count} lines")
            else:
                stats.append(f"├─ {filename}: {count}")
        
        stats.append(f"📝 **Total Lines:** {len(merged_content)}")
        stats.append(f"✨ **Unique Lines:** {len(unique_content)}")
        stats.append(f"🚫 **Duplicates Removed:** {duplicates_removed}")
        
        await message.reply_document(
            document=merged_filename,
            caption="\n".join(stats)
        )
        
    except Exception as e:
        await message.reply(f"❌ Merge failed: {str(e)}")
    finally:
        if user_id in user_state:
            user_state.pop(user_id, None)
        if 'merged_filename' in locals() and os.path.exists(merged_filename):
            os.remove(merged_filename)

@app.on_message(filters.command("feedback"))
async def feedback_command(client, message):
    if not message.from_user:
        return await message.reply("❌ This command can only be used by users.")
    
    user_state[message.from_user.id] = {"action": "awaiting_feedback"}
    await message.reply(
        "📣 Please send your feedback (text, photo, or video).\n\n"
        "You can include:\n"
        "- Bug reports\n"
        "- Feature requests\n"
        "- General feedback\n\n"
        "Type /cancel to abort."
    )

@app.on_message(
    (filters.text | filters.photo | filters.video) & 
    filters.create(lambda _, __, m: m.from_user and m.from_user.id in user_state and user_state[m.from_user.id].get("action") == "awaiting_feedback")
)
async def process_feedback(client, message):
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    feedback_content = ""
    
    if message.text:
        feedback_content = message.text
    elif message.photo or message.video:
        feedback_content = message.caption if message.caption else "[Media feedback]"
    
    try:
        user = await client.get_users(user_id)
        user_info = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        user_info += f" (@{user.username})" if user.username else ""
    except:
        user_info = f"User ID: {user_id}"
    
    feedback_msg = (
        "📬 **New Feedback**\n\n"
        f"👤 **From:** {user_info}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"📅 **Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"💬 **Feedback:**\n{feedback_content}"
    )
    
    try:
        if message.photo:
            await client.send_photo(
                chat_id=ADMIN_ID,
                photo=message.photo.file_id,
                caption=feedback_msg
            )
        elif message.video:
            await client.send_video(
                chat_id=ADMIN_ID,
                video=message.video.file_id,
                caption=feedback_msg
            )
        else:
            await client.send_message(
                chat_id=ADMIN_ID,
                text=feedback_msg
            )
        
        await message.reply("✅ Your feedback has been sent to the admin. Thank you!")
    except Exception as e:
        await message.reply(f"❌ Failed to send feedback: {str(e)}")
    finally:
        user_state.pop(user_id, None)

def restricted(_, __, message: Message):
    user_id = message.from_user.id

    if await check_user_access(user_id):
        return True

    if user_id == ADMIN_ID:
        return True

    now = time.time()
    if user_id in search_cooldowns and now - search_cooldowns[user_id] < 60:
        return False

    search_cooldowns[user_id] = now
    return True

# --- SEARCH COMMAND ---
@app.on_message(filters.command("search") & filters.create(restricted))
async def ask_keyword(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Roblox", callback_data="keyword_roblox")],
        [InlineKeyboardButton("🔥 Mobile Legends", callback_data="keyword_mobilelegends")],
        [InlineKeyboardButton("💳 Codashop", callback_data="keyword_codashop")],
        [InlineKeyboardButton("🛡 Garena", callback_data="expand_garena")],
        [InlineKeyboardButton("🌐 Social Media", callback_data="expand_socmeds")],
        [InlineKeyboardButton("✉️ Email Providers", callback_data="expand_emails")],
        [InlineKeyboardButton("🎮 Gaming", callback_data="expand_gaming")]
    ])
    await message.reply("🔎 Choose a category:", reply_markup=keyboard)

# --- CATEGORY EXPANSIONS ---
@app.on_callback_query(filters.regex("^expand_garena$"))
async def expand_garena_options(client, callback_query):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Garena.com", callback_data="keyword_garena.com")],
        [InlineKeyboardButton("🔐 100082", callback_data="keyword_100082")],
        [InlineKeyboardButton("🔐 100055", callback_data="keyword_100055")],
        [InlineKeyboardButton("🛡 Authgop", callback_data="keyword_authgop.garena.com")],
        [InlineKeyboardButton("🔐 Gaslite", callback_data="keyword_gaslite")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    await callback_query.message.edit_text("🛡 Garena Sub-keywords:", reply_markup=keyboard)

@app.on_callback_query(filters.regex("^expand_socmeds$"))
async def expand_socmeds(client, callback_query):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Facebook", callback_data="keyword_facebook.com")],
        [InlineKeyboardButton("📸 Instagram", callback_data="keyword_instagram.com")],
        [InlineKeyboardButton("📱 WhatsApp", callback_data="keyword_whatsapp.com")],
        [InlineKeyboardButton("🐦 Twitter", callback_data="keyword_twitter.com")],
        [InlineKeyboardButton("💬 Discord", callback_data="keyword_discord.com")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    await callback_query.message.edit_text("🌐 Social Media Options:", reply_markup=keyboard)

@app.on_callback_query(filters.regex("^expand_emails$"))
async def expand_emails(client, callback_query):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📧 Gmail", callback_data="keyword_google.com")],
        [InlineKeyboardButton("📧 Yahoo", callback_data="keyword_yahoo.com")],
        [InlineKeyboardButton("📧 Outlook", callback_data="keyword_outlook.com")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    await callback_query.message.edit_text("✉️ Email Provider Options:", reply_markup=keyboard)

@app.on_callback_query(filters.regex("^expand_gaming$"))
async def expand_gaming(client, callback_query):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Riot", callback_data="keyword_riotgames.com")],
        [InlineKeyboardButton("🎮 Battle.net", callback_data="keyword_battle.net")],
        [InlineKeyboardButton("🎮 Minecraft", callback_data="keyword_minecraft.net")],
        [InlineKeyboardButton("🎮 Supercell", callback_data="keyword_supercell.com")],
        [InlineKeyboardButton("🎮 Wargaming", callback_data="keyword_wargaming.net")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ])
    await callback_query.message.edit_text("🎮 Gaming Options:", reply_markup=keyboard)

@app.on_callback_query(filters.regex("^back_to_main$"))
async def back_to_main_menu(client, callback_query):
    await ask_keyword(client, callback_query.message)

# --- KEYWORD SELECTED ---
@app.on_callback_query(filters.regex("^keyword_"))
async def ask_format(client, callback_query):
    keyword = callback_query.data.split("_", 1)[1]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ User:Pass Only", callback_data=f"format_{keyword}_userpass")],
        [InlineKeyboardButton("🌍 Include URLs", callback_data=f"format_{keyword}_full")]
    ])
    await callback_query.message.edit_text(
        f"🔎 Keyword: `{keyword}`\nChoose output format:",
        reply_markup=keyboard
    )

# --- SUPABASE SEARCH ---
@app.on_callback_query(filters.regex("^format_"))
async def perform_search(client, callback_query):
    _, keyword, fmt = callback_query.data.split("_", 2)
    include_urls = fmt == "full"
    await callback_query.answer("🔍 Searching...", show_alert=False)
    msg = await callback_query.message.edit_text(f"🔍 Searching `{keyword}`...")

    try:
        res = supabase.table("reku").select("line").ilike("line", f"%{keyword}%").execute()
        entries = [row["line"] for row in res.data] if res.data else []
    except Exception as e:
        await msg.edit_text(f"❌ Supabase error: {str(e)}")
        return

    if not entries:
        await msg.edit_text("❌ No matches found.")
        return

    results = set()
    for line in entries:
        if not include_urls:
            parts = line.split(":")
            if len(parts) >= 2:
                line = ":".join(parts[-2:])
        results.add(line.strip())

    existing_lines = []
    os.makedirs("Generated", exist_ok=True)
    result_filename = f"{keyword}_{int(time.time())}.txt"
    result_path = os.path.join("Generated", result_filename)

    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            existing_lines = [line.strip() for line in f]

    line_counts = Counter(existing_lines)
    filtered = [r for r in results if line_counts[r] < 2]
    for r in filtered:
        line_counts[r] += 1

    if not filtered:
        await msg.edit_text("❌ No new valid results (limit reached per line).")
        return

    selected = random.sample(filtered, min(len(filtered), random.randint(100, 120)))
    with open(result_path, "w", encoding="utf-8") as f:
        for line in selected:
            f.write(f"{line}\n")

    preview = "\n".join(selected[:5]) + ("\n..." if len(selected) > 5 else "")
    label = "🌍 Full (URLs)" if include_urls else "✅ User:Pass only"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download Results", callback_data=f"download_results_{result_filename}")],
        [InlineKeyboardButton("📋 Copy Code", callback_data=f"copy_code_{result_filename}_{keyword}")]
    ])

    await msg.edit_text(
        f"🔎 **Results for:** `{keyword}`\n"
        f"📄 **Format:** {label}\n"
        f"📌 **Results:** `{len(selected)}`\n\n"
        f"🔹 **Preview:**\n```\n{preview}\n```",
        reply_markup=keyboard
    )

# --- DOWNLOAD RESULTS ---
@app.on_callback_query(filters.regex("^download_results_"))
async def download_results_file(client, callback_query):
    filename = callback_query.data.split("_", 2)[2]
    filepath = os.path.join("Generated", filename)
    if not os.path.exists(filepath):
        await callback_query.answer("❌ File not found!", show_alert=True)
        return
    await client.send_document(
        chat_id=callback_query.message.chat.id,
        document=filepath,
        caption="📄 Here are your results."
    )

# --- COPY RESULTS TEXT ---
@app.on_callback_query(filters.regex("^copy_code_"))
async def copy_results_text(client, callback_query):
    parts = callback_query.data.split("_", 3)
    filename = parts[2]
    keyword = parts[3]
    filepath = os.path.join("Generated", filename)
    if not os.path.exists(filepath):
        await callback_query.answer("❌ File not found!", show_alert=True)
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if len(content) > 4096:
        content = content[:4090] + "...\n[Truncated]"
    await callback_query.message.reply(
        f"🔎 <b>Results for:</b> <code>{keyword}</code>\n\n<pre>{content}</pre>",
        parse_mode="HTML"
    )

@app.on_message(filters.command("useractivity") & filters.user(ADMIN_ID))
async def user_activity_command(client, message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("❌ Usage: /useractivity <user_id> [limit]\nExample: /useractivity 123456789 10")
    
    try:
        target_id = int(args[1])
        limit = int(args[2]) if len(args) > 2 else 20
    except ValueError:
        return await message.reply("❌ Invalid user ID or limit. Must be numbers.")
    
    activities = load_activity_log()
    user_activities = activities.get(str(target_id), [])
    
    if not user_activities:
        return await message.reply(f"ℹ️ No activities found for user ID: {target_id}")
    
    try:
        user = await client.get_users(target_id)
        user_info = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        user_info += f" (@{user.username})" if user.username else ""
    except:
        user_info = f"User ID: {target_id}"
    
    response = [f"📊 Activity log for {user_info} (Last {limit} activities):\n"]
    
    for activity in user_activities[-limit:]:
        timestamp = datetime.datetime.fromisoformat(activity["timestamp"]).strftime("%Y-%m-%d %H:%M")
        action = activity["action"]
        details = activity.get("details", {})
        
        if action == "search":
            response.append(
                f"🔍 [{timestamp}] Searched: {details.get('keyword')}\n"
                f"   - Format: {details.get('format')}"
            )
        elif action == "redeem":
            response.append(
                f"🔑 [{timestamp}] Redeemed key: {details.get('key')}\n"
                f"   - Duration: {details.get('duration')}"
            )
        else:
            response.append(f"⚙️ [{timestamp}] {action.capitalize()}")
    
    response_text = "\n\n".join(response)
    
    if len(response_text) > 4096:
        parts = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
        for part in parts:
            await message.reply(part)
    else:
        await message.reply(response_text)

@app.on_message(filters.command("activeusers") & filters.user(ADMIN_ID))
async def active_users_command(client, message):
    activities = load_activity_log()
    keys = await get_all_keys()
    
    active_users = {}
    
    for key, info in keys.items():
        if info.get("redeemed_by"):
            user_id = info["redeemed_by"]
            try:
                expiry = datetime.datetime.fromisoformat(info["expiry"])
                if expiry > datetime.datetime.now():
                    active_users[user_id] = {
                        "key": key,
                        "expiry": info["expiry"],
                        "last_activity": None
                    }
            except ValueError:
                continue
    
    for user_id, data in active_users.items():
        user_activities = activities.get(user_id, [])
        if user_activities:
            last_activity = user_activities[-1]
            data["last_activity"] = {
                "action": last_activity["action"],
                "timestamp": last_activity["timestamp"]
            }
    
    if not active_users:
        return await message.reply("ℹ️ No active users found.")
    
    response = ["👥 Active Users and Their Last Activity:\n"]
    
    for user_id, data in active_users.items():
        try:
            user = await client.get_users(int(user_id))
            username = f"@{user.username}" if user.username else "No username"
            name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        except:
            username = "Unknown"
            name = "Unknown"
        
        response.append(
            f"👤 {name} ({username})\n"
            f"🆔 ID: {user_id}\n"
            f"🔑 Key: {data['key']}\n"
            f"⏳ Expires: {data['expiry']}"
        )
        
        if data["last_activity"]:
            last_action = data["last_activity"]["action"]
            last_time = datetime.datetime.fromisoformat(data["last_activity"]["timestamp"]).strftime("%Y-%m-%d %H:%M")
            response.append(f"   ⏱ Last activity: {last_action} at {last_time}")
        else:
            response.append("   ⏱ No recorded activity")
        
        response.append("")     
    response_text = "\n".join(response)
    
    if len(response_text) > 4096:
        parts = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
        for part in parts:
            await message.reply(part)
    else:
        await message.reply(response_text)

def restricted(_, __, message: Message):
    """Check if user has access to use the command"""
    user_id = message.from_user.id
    if await check_user_access(user_id):
        return True
    if user_id == ADMIN_ID:
        return True
    now = time.time()
    if user_id in search_cooldowns:
        last_search = search_cooldowns[user_id]
        if now - last_search < 60:
            return False
    
    search_cooldowns[user_id] = now
    return True

from collections import defaultdict

# Match the search UI buttons
KEYWORDS = [
    "roblox",
    "mobilelegends",
    "codashop",
    "garena.com",
    "100082",
    "100055",
    "authgop.garena.com",
    "gaslite",
    "facebook.com",
    "instagram.com",
    "whatsapp.com",
    "twitter.com",
    "discord.com",
    "google.com",
    "yahoo.com",
    "outlook.com",
    "riotgames.com",
    "battle.net",
    "minecraft.net",
    "supercell.com",
    "wargaming.net"
]

@app.on_message(filters.command("checklines"))
async def check_lines(_, message: Message):
    try:
        counts = defaultdict(int)

        # Query line count for each keyword
        for keyword in KEYWORDS:
            query = supabase.table("reku").select("line", count="exact").ilike("line", f"%{keyword}%")
            res = query.execute()
            counts[keyword] = res.count or 0

        # Build result box
        lines = []
        lines.append("╔══════════════════════════════╗")
        lines.append("║     🔍 LINES STATUS CHECK     ║")
        lines.append("╠══════════════════════════════╣")

        for keyword in KEYWORDS:
            label = keyword[:20].ljust(20)
            count = str(counts[keyword]).rjust(4)
            lines.append(f"║ {label} {count} lines")

        lines.append("╚══════════════════════════════╝")
        await message.reply_text("\n".join(lines))
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

app.run()
