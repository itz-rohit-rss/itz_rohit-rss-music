import os
import io
import random
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped, AudioVideoPiped
from pytgcalls.types.input_stream.quality import HighQualityVideo
import yt_dlp
import aiohttp
from PIL import Image, ImageDraw, ImageFont

# Configs from Environment
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
STRING_SESSION = os.environ.get("STRING_SESSION")
OWNER_ID = int(os.environ.get("OWNER_ID", "7885190981"))
SUDO_USERS = [OWNER_ID]

bot = Client("rohit_music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("rohit_assistant", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
call_py = PyTgCalls(user)

# Active Tags Tracker & Scores
active_tags = {}
user_scores = {}

RANDOM_TAG_MESSAGES = [
    "Kahan so rahe ho sab? Active ho jao!",
    "Chalo sab online aao baat karte hain!",
    "Rohit Chauhan ka bot bol raha hai, hazir ho sab!",
    "Group me thoda sannata tod do dosto!",
    "Jalwa dekho aur online aao jaldi!"
]

def add_watermark(image_bytes: bytes) -> io.BytesIO:
    """Adds a bold branded 'रोहित चौहान' watermark bar on the song thumbnail"""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = image.size

        # Create overlay
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Highlight Banner at Bottom
        bar_height = int(height * 0.18)
        draw.rectangle([(0, height - bar_height), (width, height)], fill=(0, 0, 0, 190))
        
        # Border accent line (Royal Gold/Red highlight)
        draw.rectangle([(0, height - bar_height), (width, height - bar_height + 6)], fill=(255, 69, 0, 255))

        text = "👑 BOT OWNER: रोहित चौहान 👑"
        
        # Try finding a font or default
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(bar_height * 0.45))
        except:
            font = ImageFont.load_default()

        # Center text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (width - text_w) // 2
        text_y = height - bar_height + (bar_height - text_h) // 2

        draw.text((text_x, text_y), text, fill=(255, 215, 0, 255), font=font)

        final_img = Image.alpha_composite(image, overlay).convert("RGB")
        out = io.BytesIO()
        final_img.save(out, format="JPEG", quality=90)
        out.seek(0)
        return out
    except Exception as e:
        print(f"Watermark error: {e}")
        return io.BytesIO(image_bytes)

# --- START & INFO COMMANDS ---
@bot.on_message(filters.command(["start", "help"]))
async def start_handler(client, message):
    text = (
        "👑 **Welcome to Rohit Chauhan's Music & Management Bot!** 👑\n\n"
        "🎵 **Music Commands:**\n"
        "• `/play <song>` - Audio Play with Rohit Chauhan Branding\n"
        "• `/vplay <song>` - Video Play\n"
        "• `/skip` - Next Song\n"
        "• `/pose` - Pause playback\n"
        "• `/radumey` - Resume playback\n\n"
        "📢 **Tagging Commands:**\n"
        "• `/tagall <text>` - Tag members in batches of 5\n"
        "• `/tag <text>` - Tag members one by one\n"
        "• `/vctag <text>` - Invite all members to VC\n"
        "• `/cancel` - Stop ongoing tagging\n\n"
        "ℹ️ **Info & Support:**\n"
        "• `/owner` - Owner Details\n"
        "• `/sudolist` - Sudo & Owner Info"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url="https://t.me/itz_rohit_rss")],
        [InlineKeyboardButton("💬 Support Group", url="https://t.me/THW_WORLD")]
    ])
    await message.reply_text(text, reply_markup=buttons)

@bot.on_message(filters.command("owner"))
async def owner_handler(client, message):
    text = (
        "👑 **Owner Information:**\n\n"
        "👤 **Name:** रोहित चौहान\n"
        "🔗 **Telegram:** [@itz_rohit_rss](https://t.me/itz_rohit_rss)\n"
        "✨ **Status:** Asli Maalik & Jalwa Creator 🔥"
    )
    await message.reply_text(text, disable_web_page_preview=True)

@bot.on_message(filters.command("sudolist"))
async def sudo_handler(client, message):
    text = (
        "👑 **Owner & Sudo Team:**\n\n"
        "• **Creator / Super Owner:** रोहित चौहान ([@itz_rohit_rss](https://t.me/itz_rohit_rss))\n"
        "• **Sudo Privileges:** Full Bot Access & Server Controls"
    )
    await message.reply_text(text, disable_web_page_preview=True)

# --- PLAY & VIDEO PLAY ---
@bot.on_message(filters.command(["play", "vplay"]) & filters.group)
async def play_handler(client, message):
    is_video = message.command[0].lower() == "vplay"
    if len(message.command) < 2:
        return await message.reply_text("Bhai gaane ka naam ya YouTube link do!")

    query = " ".join(message.command[1:])
    m = await message.reply_text(f"🔎 **Khoj jaari hai:** `{query}`...")

    ydl_opts = {"format": "bestaudio/best" if not is_video else "best", "noplaylist": True, "quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            stream_url = info['url']
            title = info['title']
            thumb_url = info.get('thumbnail')
            duration = info.get('duration_string', 'Unknown')
        except Exception as e:
            return await m.edit(f"❌ Error: {e}")

    # Fetch thumbnail and apply Rohit Chauhan watermark
    caption = (
        f"👑 **रोहित चौहान Music Bot**\n\n"
        f"▶️ **Now Playing:** `{title}`\n"
        f"⏳ **Duration:** `{duration}`\n"
        f"👤 **Requested By:** {message.from_user.mention}\n\n"
        f"🔥 *Jalwa Rohit Chauhan Ka!*"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url="https://t.me/itz_rohit_rss"),
         InlineKeyboardButton("💬 Support", url="https://t.me/THW_WORLD")]
    ])

    try:
        if is_video:
            await call_py.join_group_call(message.chat.id, AudioVideoPiped(stream_url, HighQualityVideo()))
        else:
            await call_py.join_group_call(message.chat.id, AudioPiped(stream_url))
    except Exception as e:
        return await m.edit(f"VC join error: {e}")

    await m.delete()

    if thumb_url:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumb_url) as resp:
                if resp.status == 200:
                    raw_thumb = await resp.read()
                    watermarked_thumb = add_watermark(raw_thumb)
                    watermarked_thumb.name = "rohit_chauhan.jpg"
                    return await message.reply_photo(photo=watermarked_thumb, caption=caption, reply_markup=buttons)

    await message.reply_text(caption, reply_markup=buttons)

# --- VC CONTROLS ---
@bot.on_message(filters.command("pose") & filters.group)
async def pause_handler(client, message):
    try:
        await call_py.pause_stream(message.chat.id)
        await message.reply_text("⏸️ **Playback Pause kar diya gaya hai.**")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@bot.on_message(filters.command("radumey") & filters.group)
async def resume_handler(client, message):
    try:
        await call_py.resume_stream(message.chat.id)
        await message.reply_text("▶️ **Playback dobara Resume ho gaya!**")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@bot.on_message(filters.command(["skip", "next", "stop"]) & filters.group)
async def stop_handler(client, message):
    try:
        await call_py.leave_group_call(message.chat.id)
        await message.reply_text("⏹️ **Gaana Stop/Skip kar diya gaya hai.**")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

# --- TAGGING SYSTEM ---
@bot.on_message(filters.command(["tagall", "tag", "vctag"]) & filters.group)
async def tag_handler(client, message):
    cmd = message.command[0].lower()
    chat_id = message.chat.id

    if chat_id in active_tags:
        return await message.reply_text("⚠️ Pehle se hi ek tagging chal rahi hai! Rokane ke liye `/cancel` likhein.")

    # Custom or random message
    if len(message.command) > 1:
        custom_text = " ".join(message.command[1:])
    else:
        if cmd == "vctag":
            custom_text = "🔊 Sabhi log jaldi Voice Chat (VC) me join ho jao!"
        else:
            custom_text = random.choice(RANDOM_TAG_MESSAGES)

    active_tags[chat_id] = True
    await message.reply_text(f"🚀 Tagging shuru ho gayi hai...")

    members = []
    async for m in client.get_chat_members(chat_id):
        if not m.user.is_bot and not m.user.is_deleted:
            members.append(m.user)

    if cmd == "tagall" or cmd == "vctag":
        # 5-5 ke groups me tag
        for i in range(0, len(members), 5):
            if chat_id not in active_tags:
                break
            batch = members[i:i+5]
            mentions = " ".join([f"[{u.first_name}](tg://user?id={u.id})" for u in batch])
            await client.send_message(chat_id, f"📢 {custom_text}\n\n{mentions}")
            await asyncio.sleep(2.5)
    else:
        # Single single tag
        for u in members:
            if chat_id not in active_tags:
                break
            mention = f"[{u.first_name}](tg://user?id={u.id})"
            await client.send_message(chat_id, f"👉 {custom_text} - {mention}")
            await asyncio.sleep(2)

    active_tags.pop(chat_id, None)

@bot.on_message(filters.command("cancel") & filters.group)
async def cancel_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_tags:
        active_tags.pop(chat_id, None)
        await message.reply_text("🛑 **Tagging rok di gayi hai!**")
    else:
        await message.reply_text("Koi active tagging nahi chal rahi thi.")

# --- PUZZLE / QUIZ HOURLY TASK ---
PUZZLES = [
    {"q": "इस तस्वीर में छुपा कोड क्या है: [ R O H I T ]", "opts": ["ROHIT", "MOHIT", "VIKAS", "AJAY"], "ans": "ROHIT"},
    {"q": "Group ka Super Boss kaun hai?", "opts": ["रोहित चौहान", "Koi Aur", "Bot", "Admin"], "ans": "रोहित चौहान"},
    {"q": "10 + 20 × 2 kitna hota hai?", "opts": ["50", "60", "40", "30"], "ans": "50"},
]

async def hourly_puzzle_loop():
    while True:
        await asyncio.sleep(3600)  # Har 1 ghante baad
        # Select puzzle
        p = random.choice(PUZZLES)
        buttons = []
        row = []
        for opt in p["opts"]:
            cb_data = f"puz_correct:{opt}" if opt == p["ans"] else "puz_wrong"
            row.append(InlineKeyboardButton(opt, callback_data=cb_data))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        for chat_id in list(active_tags.keys()):
            try:
                await bot.send_message(
                    chat_id,
                    f"🧩 **PUZZLE TIME (हर 1 घंटे में):**\n\n{p['q']}\n\n*सही जवाब देने वाले को 10 Points मिलेंगे!*",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except Exception:
                pass

@bot.on_callback_query(filters.regex(r"^puz_"))
async def puzzle_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data.startswith("puz_correct"):
        user_scores[user_id] = user_scores.get(user_id, 0) + 10
        await callback_query.answer(f"🎉 Sahi Jawab! Aapko +10 points mile. Total: {user_scores[user_id]} pts!", show_alert=True)
    else:
        await callback_query.answer("❌ Galat Jawab! Agli baar try karein.", show_alert=True)

# --- BOT LAUNCH ---
async def main():
    await user.start()
    await call_py.start()
    await bot.start()
    print("🔥 Rohit Chauhan's Custom Bot is LIVE & Dominating! 🔥")
    asyncio.create_task(hourly_puzzle_loop())
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
  
