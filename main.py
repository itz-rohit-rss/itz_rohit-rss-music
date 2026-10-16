import os
import io
import sys
import glob
import time
import shutil
import random
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
import yt_dlp
import aiohttp
from PIL import Image, ImageDraw, ImageFont

# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

# --- 1. SYSTEM & NIX FFPROBE/FFMPEG AUTO-LINK ---
nix_candidate_dirs = [
    "/root/.nix-profile/bin",
    "/nix/var/nix/profiles/default/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin"
] + glob.glob("/nix/store/*ffmpeg*/bin") + glob.glob("/nix/store/*ffprobe*/bin")

current_path = os.environ.get("PATH", "")
for p in nix_candidate_dirs:
    if os.path.isdir(p) and p not in current_path:
        current_path = f"{p}:{current_path}"
os.environ["PATH"] = current_path

if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception as e:
        print(f"Static ffmpeg load note: {e}")

print(f"🔍 FFmpeg Path detected: {shutil.which('ffmpeg')}")
print(f"🔍 FFprobe Path detected: {shutil.which('ffprobe')}")

# --- 2. CONFIGS & CLIENT SETUP ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
STRING_SESSION = os.environ.get("STRING_SESSION")
OWNER_ID = int(os.environ.get("OWNER_ID", "7885190981"))
SUDO_USERS = [OWNER_ID]

START_IMG = "start.jpg" if os.path.exists("start.jpg") else "https://telegra.ph/file/0c9769399df3d854eb094.jpg"

bot = Client("rohit_music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("rohit_assistant", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
call_py = PyTgCalls(user)

active_tags = {}
user_scores = {}
registered_groups = set()

RANDOM_TAG_MESSAGES = [
    "Kahan so rahe ho sab? Active ho jao!",
    "Chalo sab online aao baat karte hain!",
    "Rohit Chauhan ka bot bol raha hai, hazir ho sab!",
    "Group me thoda sannata tod do dosto!",
    "Jalwa dekho aur online aao jaldi!"
]

def add_watermark(image_bytes: bytes) -> io.BytesIO:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = image.size

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        bar_height = max(int(height * 0.18), 50)
        draw.rectangle([(0, height - bar_height), (width, height)], fill=(0, 0, 0, 205))
        draw.rectangle([(0, height - bar_height), (width, height - bar_height + 5)], fill=(255, 69, 0, 255))

        text = "👑 BOT OWNER: ROHIT CHAUHAN (रोहित चौहान) 👑"
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(bar_height * 0.38))
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", int(bar_height * 0.38))
            except Exception:
                font = ImageFont.load_default()

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

def get_start_markup(bot_username: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Add me to your group ➕", url=f"https://t.me/{bot_username}?startgroup=true")],
        [InlineKeyboardButton("Help", callback_data="bot_help")],
        [
            InlineKeyboardButton("💬 Support", url="https://t.me/THW_WORLD"),
            InlineKeyboardButton("📢 Updates", url="https://t.me/+w9-FGr4xeIEyNWE1")
        ],
        [
            InlineKeyboardButton("👤 Owner", url="https://t.me/itz_rohit_rss"),
            InlineKeyboardButton("🏓 Ping", callback_data="bot_ping")
        ]
    ])

# --- 3. AUTO-LEAVE ON STREAM END ---
@call_py.on_update()
async def stream_update_handler(client, update):
    update_type = type(update).__name__
    if any(k in update_type for k in ["StreamAudioEnded", "StreamVideoEnded", "StreamEnded"]):
        chat_id = getattr(update, "chat_id", None)
        if chat_id:
            try:
                await client.leave_call(chat_id)
                for f in glob.glob(f"downloads/{chat_id}.*"):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
                await bot.send_message(
                    chat_id,
                    "⏹️ **Gaana khatam ho gaya! Assistant ne VC successfully leave kar diya.**"
                )
            except Exception as e:
                print(f"Auto-leave error: {e}")

# --- 4. HIGH-SPEED LOCAL AUDIO DOWNLOADER ---
async def fetch_local_audio(query: str, chat_id: int):
    # Purane files clean karein
    for f in glob.glob(f"downloads/{chat_id}.*"):
        try:
            os.remove(f)
        except Exception:
            pass

    loop = asyncio.get_event_loop()

    def download_job():
        is_link = query.startswith("http://") or query.startswith("https://")
        sources = [query] if is_link else [f"scsearch1:{query}", f"ytsearch1:{query}"]

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"downloads/{chat_id}.%(ext)s",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "geo_bypass": True,
        }
        if os.path.exists("cookies.txt"):
            ydl_opts["cookiefile"] = "cookies.txt"

        for target in sources:
            try:
                opts = dict(ydl_opts)
                if "ytsearch" in target or "youtube.com" in target or "youtu.be" in target:
                    opts["extractor_args"] = {
                        "youtube": {"player_client": ["android", "mweb", "web"]}
                    }

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(target, download=True)
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]

                    files = glob.glob(f"downloads/{chat_id}.*")
                    if files:
                        return {
                            "file_path": files[0],
                            "title": info.get("title", query),
                            "thumbnail": info.get("thumbnail"),
                            "duration": info.get("duration_string", "Unknown")
                        }
            except Exception as e:
                print(f"Download attempt failed for {target}: {e}")
                continue
        return None

    res = await loop.run_in_executor(None, download_job)
    if res:
        return res
    raise Exception("Gaana kisi bhi platform par nahi mila. Kripya gaane ka sahi naam likhein ya direct link dein.")

# --- 5. START & HELP HANDLERS ---
@bot.on_message(filters.command(["start"]))
async def start_handler(client, message):
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        registered_groups.add(message.chat.id)
        return await message.reply_text(
            f"Hey {message.from_user.mention}!\n👑 **Rohit Chauhan Music Bot** is active in this group!"
        )

    bot_me = await client.get_me()
    caption = (
        f"Hey {message.from_user.mention},\n"
        f"This is **Rohit Chauhan Music !! 🧿** !\n\n"
        f"A music player bot with some awesome and useful features.\n\n"
        f"Click on the help button for more info."
    )
    reply_markup = get_start_markup(bot_me.username)

    try:
        await message.reply_photo(photo=START_IMG, caption=caption, reply_markup=reply_markup)
    except Exception as e:
        print(f"Photo send error: {e}")
        await message.reply_text(caption, reply_markup=reply_markup)

@bot.on_callback_query(filters.regex(r"^bot_"))
async def bot_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data

    if data == "bot_help":
        help_text = (
            "🛠 **Commands List:**\n\n"
            "🎵 **Music Player:**\n"
            "• `/play <song>` - VC me high quality gaana chalaye\n"
            "• `/stop` ya `/leavevc` - VC leave karein & gaana band karein\n"
            "• `/pose` - Pause playback\n"
            "• `/radumey` - Resume playback\n\n"
            "🤖 **Assistant Management:**\n"
            "• `/userbotjoin` - Assistant ko group me invite/join karayein\n"
            "• `/userbotleave` - Assistant ko group se leave karayein\n\n"
            "📢 **Tagging & Groups:**\n"
            "• `/tagall <text>` - Sabhi ko 5-5 ke batch me tag karein\n"
            "• `/tag <text>` - Single-single members mention\n"
            "• `/vctag <text>` - Members ko VC invite karein\n"
            "• `/cancel` - Tagging rokne ke liye\n\n"
            "👑 **Owner / Info:**\n"
            "• `/owner` - Maalik ki details\n"
            "• `/sudolist` - Admin controls"
        )
        back_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="bot_back")]
        ])
        await callback_query.edit_message_caption(caption=help_text, reply_markup=back_markup)

    elif data == "bot_back":
        bot_me = await client.get_me()
        caption = (
            f"Hey {callback_query.from_user.mention},\n"
            f"This is **Rohit Chauhan Music !! 🧿** !\n\n"
            f"A music player bot with some awesome and useful features.\n\n"
            f"Click on the help button for more info."
        )
        await callback_query.edit_message_caption(caption=caption, reply_markup=get_start_markup(bot_me.username))

    elif data == "bot_ping":
        start_ping = time.time()
        m = await client.send_message(callback_query.message.chat.id, "🏓 Pinging...")
        delta = round((time.time() - start_ping) * 1000)
        await m.delete()
        await callback_query.answer(f"🏓 Pong: {delta}ms | Server active! 🔥", show_alert=True)

@bot.on_message(filters.command("owner"))
async def owner_handler(client, message):
    text = (
        "👑 **Owner Information:**\n\n"
        "👤 **Name:** Rohit Chauhan (रोहित चौहान)\n"
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

# --- 6. ASSISTANT JOIN / LEAVE COMMANDS ---
@bot.on_message(filters.command(["userbotjoin", "joinassistant"]) & filters.group)
async def join_assistant_handler(client, message):
    chat_id = message.chat.id
    m = await message.reply_text("⏳ **Assistant ko group me join karaya ja raha hai...**")
    try:
        try:
            invite_link = await client.export_chat_invite_link(chat_id)
        except Exception:
            invite_link = (await client.get_chat(chat_id)).invite_link

        if not invite_link:
            return await m.edit("❌ **Bot ko invite link banane ki permission nahi hai.** Bot ko Admin banayein.")

        await user.join_chat(invite_link)
        await m.edit("✅ **Assistant successfully group me join ho gaya hai!**")
    except Exception as e:
        await m.edit(f"❌ Join error: {e}")

@bot.on_message(filters.command(["userbotleave", "leaveassistant"]) & filters.group)
async def leave_assistant_handler(client, message):
    chat_id = message.chat.id
    try:
        try:
            await call_py.leave_call(chat_id)
        except Exception:
            pass
        await user.leave_chat(chat_id)
        await message.reply_text("👋 **Assistant ne group successfully leave kar diya!**")
    except Exception as e:
        await message.reply_text(f"❌ Leave error: {e}")

# --- 7. PLAY & VC CONTROLS ---
@bot.on_message(filters.command(["play", "vplay"]) & filters.group)
async def play_handler(client, message):
    registered_groups.add(message.chat.id)
    is_video = message.command[0].lower() == "vplay"
    if len(message.command) < 2:
        return await message.reply_text("Bhai gaane ka naam do! Example: `/play radhe radhe barsane wali`")

    query = " ".join(message.command[1:])
    m = await message.reply_text(f"🔎 **Gaana khoj kar prepare kiya ja raha hai:** `{query}`...")

    try:
        track = await fetch_local_audio(query, message.chat.id)
    except Exception as e:
        return await m.edit(f"❌ Error: {e}")

    caption = (
        f"👑 **रोहित चौहान Music Bot**\n\n"
        f"▶️ **Now Playing:** `{track['title']}`\n"
        f"⏳ **Duration:** `{track['duration']}`\n"
        f"👤 **Requested By:** {message.from_user.mention}\n\n"
        f"🔥 *Jalwa Rohit Chauhan Ka!*"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url="https://t.me/itz_rohit_rss"),
         InlineKeyboardButton("💬 Support", url="https://t.me/THW_WORLD")]
    ])

    try:
        stream = MediaStream(track["file_path"], video_flags=MediaStream.Flags.IGNORE if not is_video else None)
        await call_py.play(message.chat.id, stream)
        try:
            await call_py.unmute_stream(message.chat.id)
        except Exception:
            pass
    except Exception as e:
        try:
            await call_py.leave_call(message.chat.id)
        except Exception:
            pass
        return await m.edit(f"VC join error: {e}")

    await m.delete()

    if track.get("thumbnail"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(track["thumbnail"], timeout=10) as resp:
                    if resp.status == 200:
                        raw_thumb = await resp.read()
                        watermarked_thumb = add_watermark(raw_thumb)
                        watermarked_thumb.name = "rohit_chauhan.jpg"
                        return await message.reply_photo(photo=watermarked_thumb, caption=caption, reply_markup=buttons)
        except Exception:
            pass

    await message.reply_text(caption, reply_markup=buttons)

@bot.on_message(filters.command(["stop", "skip", "leave", "leavevc", "end"]) & filters.group)
async def stop_handler(client, message):
    try:
        await call_py.leave_call(message.chat.id)
    except Exception:
        pass

    for f in glob.glob(f"downloads/{message.chat.id}.*"):
        try:
            os.remove(f)
        except Exception:
            pass

    await message.reply_text("⏹️ **Gaana stop kar diya aur Assistant VC se leave ho gaya!**")

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

# --- 8. TAGGING SYSTEM ---
@bot.on_message(filters.command(["tagall", "tag", "vctag"]) & filters.group)
async def tag_handler(client, message):
    registered_groups.add(message.chat.id)
    cmd = message.command[0].lower()
    chat_id = message.chat.id

    if chat_id in active_tags:
        return await message.reply_text("⚠️ Pehle se hi ek tagging chal rahi hai! Rokane ke liye `/cancel` likhein.")

    if len(message.command) > 1:
        custom_text = " ".join(message.command[1:])
    else:
        if cmd == "vctag":
            custom_text = "🔊 Sabhi log jaldi Voice Chat (VC) me join ho jao!"
        else:
            custom_text = random.choice(RANDOM_TAG_MESSAGES)

    active_tags[chat_id] = True
    await message.reply_text("🚀 Tagging shuru ho gayi hai...")

    members = []
    async for m in client.get_chat_members(chat_id):
        if not m.user.is_bot and not m.user.is_deleted:
            members.append(m.user)

    if cmd in ["tagall", "vctag"]:
        for i in range(0, len(members), 5):
            if chat_id not in active_tags:
                break
            batch = members[i:i+5]
            mentions = " ".join([f"[{u.first_name}](tg://user?id={u.id})" for u in batch])
            await client.send_message(chat_id, f"📢 {custom_text}\n\n{mentions}")
            await asyncio.sleep(2.5)
    else:
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

# --- 9. PUZZLE / QUIZ HOURLY TASK ---
PUZZLES = [
    {"q": "Puzzle: Is box me kaunsa naam likha hai?\n\n[ R O H I T ]", "opts": ["ROHIT", "MOHIT", "VIKAS", "AJAY"], "ans": "ROHIT"},
    {"q": "Group ka Asli Boss kaun hai?", "opts": ["रोहित चौहान", "Koi Aur", "Bot", "Admin"], "ans": "रोहित चौहान"},
    {"q": "Fast Math: 10 + 20 × 2 kitna hota hai?", "opts": ["50", "60", "40", "30"], "ans": "50"},
]

async def hourly_puzzle_loop():
    while True:
        await asyncio.sleep(3600)
        if not registered_groups:
            continue

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

        for chat_id in list(registered_groups):
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

# --- 10. BOT LAUNCH ---
async def start_services():
    await bot.start()
    await user.start()
    
    try:
        async for dialog in user.get_dialogs(limit=30):
            pass
    except Exception:
        pass

    try:
        await call_py.start()
    except Exception as e:
        print(f"PyTgCalls startup note: {e}")

    print("🔥 Rohit Chauhan's Custom Bot is LIVE & Dominating! 🔥")
    asyncio.create_task(hourly_puzzle_loop())
    await idle()
    await bot.stop()
    await user.stop()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
