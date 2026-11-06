import os
import io
import sys
import glob
import time
import shutil
import random
import asyncio
import textwrap
import urllib.request
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

# --- 2. FAST RELIABLE TEMPLATE & COOKIES FETCHER ---
TEMPLATE_PATH = "template.jpg"
CDN_TEMPLATE_URL = "https://raw.githubusercontent.com/itz-rohit-rss/itz_rohit-rss-music/main/template.jpg"

def fetch_required_assets():
    # 1. Cookies fetch
    cookies_url = os.environ.get("COOKIES_URL")
    if cookies_url:
        try:
            req = urllib.request.Request(cookies_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')
                with open("cookies.txt", "w", encoding="utf-8") as f:
                    f.write(content)
            print("✅ YouTube cookies.txt successfully updated from COOKIES_URL!")
        except Exception as e:
            print(f"⚠️ Cookies download warning: {e}")

    # 2. Ensure template.jpg exists & is valid
    is_valid = False
    if os.path.exists(TEMPLATE_PATH) and os.path.getsize(TEMPLATE_PATH) > 20000:
        try:
            with Image.open(TEMPLATE_PATH) as test_img:
                test_img.verify()
            is_valid = True
            print("✅ Local template.jpg verified!")
        except Exception:
            is_valid = False

    if not is_valid:
        print("⏳ Fetching fresh template.jpg from CDN...")
        try:
            req = urllib.request.Request(CDN_TEMPLATE_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                if len(data) > 20000:
                    with open(TEMPLATE_PATH, "wb") as f:
                        f.write(data)
                    print(f"✅ Template successfully saved to disk ({len(data)} bytes)!")
        except Exception as err:
            print(f"CDN fetch warning: {err}")

fetch_required_assets()

# --- 3. CONFIGS & CLIENT SETUP ---
raw_api_id = os.environ.get("API_ID", "35744976").replace('"', '').replace("'", "").strip()
API_ID = int(raw_api_id) if raw_api_id.isdigit() else 35744976

API_HASH = os.environ.get("API_HASH", "459c0a59bdca46c1069916ef20ce70c9").replace('"', '').replace("'", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").replace('"', '').replace("'", "").strip()

raw_string = os.environ.get("STRING_SESSION") or os.environ.get("SESSION1", "")
STRING_SESSION = raw_string.replace('"', '').replace("'", "").strip()

raw_owner = os.environ.get("OWNER_ID", "7885190981").replace('"', '').replace("'", "").strip()
OWNER_ID = int(raw_owner) if raw_owner.isdigit() else 7885190981

START_IMG = "start.jpg" if os.path.exists("start.jpg") else "https://telegra.ph/file/0c9769399df3d854eb094.jpg"

bot = Client("rohit_music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("rohit_assistant", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
call_py = PyTgCalls(user)

active_tags = {}
user_scores = {}
registered_groups = set()
autoplay_enabled = {}
last_playing_query = {}
is_paused_dict = {}

RANDOM_TAG_MESSAGES = [
    "Kahan so rahe ho sab? Active ho jao!",
    "Chalo sab online aao baat karte hain!",
    "Rohit Chauhan ka bot bol raha hai, hazir ho sab!",
    "Group me thoda sannata tod do dosto!",
    "Jalwa dekho aur online aao jaldi!"
]

# --- BULLETPROOF 2-BOX TEMPLATE POSTER GENERATOR ---
def create_custom_poster(thumb_bytes: bytes, song_title: str) -> io.BytesIO:
    if not os.path.exists(TEMPLATE_PATH) or os.path.getsize(TEMPLATE_PATH) < 20000:
        fetch_required_assets()

    base_img = Image.open(TEMPLATE_PATH).convert("RGB")
    if base_img.size != (2048, 2048):
        base_img = base_img.resize((2048, 2048), Image.Resampling.LANCZOS)

    # 1. Left Box (Thumbnail Frame: x: 95-705, y: 1490-1930)
    lx1, ly1, lx2, ly2 = 95, 1490, 705, 1930
    box_w = lx2 - lx1
    box_h = ly2 - ly1

    if thumb_bytes:
        try:
            song_thumb = Image.open(io.BytesIO(thumb_bytes)).convert("RGB")
            song_thumb = song_thumb.resize((box_w, box_h), Image.Resampling.LANCZOS)
            base_img.paste(song_thumb, (lx1, ly1))
        except Exception as e:
            print(f"Paste thumb error: {e}")

    # 2. Right Box (Song Name Frame: x: 880-1870, y: 1635-1925)
    rx1, ry1, rx2, ry2 = 880, 1635, 1870, 1925
    text_box_w = rx2 - rx1
    text_box_h = ry2 - ry1

    draw = ImageDraw.Draw(base_img)
    draw.rectangle([(rx1, ry1), (rx2, ry2)], fill=(12, 4, 4))

    font_size = 65
    font = None
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arialbd.ttf",
        "arial.ttf"
    ]:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    clean_title = song_title.replace(".mp3", "").strip()
    lines = textwrap.wrap(clean_title, width=22)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1][:19] + "..."

    line_spacing = 80
    total_text_h = len(lines) * line_spacing
    cur_y = ry1 + (text_box_h - total_text_h) // 2

    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
        except Exception:
            lw = len(line) * (font_size // 2)

        cur_x = rx1 + (text_box_w - lw) // 2
        draw.text((cur_x + 3, cur_y + 3), line, fill=(0, 0, 0), font=font)
        draw.text((cur_x, cur_y), line, fill=(255, 215, 0), font=font)
        cur_y += line_spacing

    final_img = base_img.resize((1280, 1280), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    final_img.save(out, format="JPEG", quality=90)
    out.seek(0)
    return out

def get_start_markup(bot_username: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD ME TO YOUR GROUP", url=f"https://t.me/{bot_username}?startgroup=true")],
        [
            InlineKeyboardButton("💬 SUPPORT ↗", url="https://t.me/THW_WORLD"),
            InlineKeyboardButton("👑 OWNER", url="https://t.me/itz_rohit_rss")
        ],
        [
            InlineKeyboardButton("📢 UPDATES ↗", url="https://t.me/+w9-FGr4xeIEyNWE1"),
            InlineKeyboardButton("🌐 LANGUAGE", callback_data="bot_lang")
        ],
        [
            InlineKeyboardButton("🛠 HELP AND COMMAND ♡", callback_data="bot_help")
        ],
        [
            InlineKeyboardButton("🏓 PING", callback_data="bot_ping"),
            InlineKeyboardButton("👤 SOURCE", callback_data="bot_source")
        ]
    ])

def get_player_buttons(chat_id: int):
    ap_status = "ON 🟢" if autoplay_enabled.get(chat_id, False) else "OFF 🔴"
    pause_text = "▶️ Resume" if is_paused_dict.get(chat_id, False) else "⏸ Pause"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pause_text, callback_data=f"playctrl_pause:{chat_id}"),
            InlineKeyboardButton("⏹ Stop", callback_data=f"playctrl_stop:{chat_id}"),
            InlineKeyboardButton("⏭ Skip", callback_data=f"playctrl_skip:{chat_id}")
        ],
        [
            InlineKeyboardButton(f"🔄 Auto-Play: {ap_status}", callback_data=f"playctrl_autoplay:{chat_id}")
        ],
        [
            InlineKeyboardButton("👑 Owner", url="https://t.me/itz_rohit_rss"),
            InlineKeyboardButton("💬 Support", url="https://t.me/THW_WORLD"),
            InlineKeyboardButton("📢 Updates", url="https://t.me/+w9-FGr4xeIEyNWE1")
        ]
    ])

# --- 4. HIGH-SPEED AUDIO ENGINE ---
async def fetch_local_audio(query: str, chat_id: int):
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
    raise Exception("Gaana nahi mila. Kripya doosra naam ya link dein.")

# Auto-play Trigger
async def trigger_autoplay(chat_id: int):
    prev_query = last_playing_query.get(chat_id, "romantic hindi songs")
    recommend_seeds = [
        f"{prev_query} mix",
        f"{prev_query} mashup",
        f"trending bollywood songs",
        f"best hindi hits"
    ]
    next_query = random.choice(recommend_seeds)
    try:
        track = await fetch_local_audio(next_query, chat_id)
        stream = MediaStream(track["file_path"])
        await call_py.play(chat_id, stream)
        try:
            await call_py.unmute_stream(chat_id)
        except Exception:
            pass
        is_paused_dict[chat_id] = False
        last_playing_query[chat_id] = track["title"]

        caption = (
            f"👑 **रोहित चौहान VIP Music Bot**\n\n"
            f"🔄 **Auto-Play Triggered (Next Song):**\n"
            f"▶️ **Song:** `{track['title']}`\n"
            f"⏳ **Duration:** `{track['duration']}`\n\n"
            f"🔥 *Non-Stop Music Active!*"
        )
        buttons = get_player_buttons(chat_id)

        poster = None
        if track.get("thumbnail"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(track["thumbnail"], timeout=10) as resp:
                        if resp.status == 200:
                            raw_thumb = await resp.read()
                            poster = create_custom_poster(raw_thumb, track['title'])
            except Exception:
                pass

        if poster:
            poster.name = f"poster_{int(time.time())}.jpg"
            await bot.send_photo(chat_id, photo=poster, caption=caption, reply_markup=buttons)
        else:
            await bot.send_message(chat_id, caption, reply_markup=buttons)
    except Exception as e:
        print(f"Auto-play next error: {e}")
        try:
            await call_py.leave_call(chat_id)
        except Exception:
            pass

# --- 5. AUTO-LEAVE & AUTO-PLAY LISTENER ---
@call_py.on_update()
async def stream_update_handler(client, update):
    update_type = type(update).__name__
    if any(k in update_type for k in ["StreamAudioEnded", "StreamVideoEnded", "StreamEnded"]):
        chat_id = getattr(update, "chat_id", None)
        if chat_id:
            if autoplay_enabled.get(chat_id, False):
                await bot.send_message(chat_id, "🔄 **Gaana samapt hua! Auto-play agla song chala raha hai...**")
                await trigger_autoplay(chat_id)
            else:
                try:
                    await client.leave_call(chat_id)
                    for f in glob.glob(f"downloads/{chat_id}.*"):
                        try:
                            os.remove(f)
                        except Exception:
                            pass
                    await bot.send_message(chat_id, "⏹️ **Gaana samapt! Assistant ne VC successfully leave kar diya.**")
                except Exception as e:
                    print(f"Auto-leave error: {e}")

# --- 6. START & CALLBACK HANDLERS ---
@bot.on_message(filters.command(["start"]))
async def start_handler(client, message):
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        registered_groups.add(message.chat.id)
        return await message.reply_text(
            f"Hey {message.from_user.mention}!\n👑 **Rohit Chauhan VIP Music Bot** is active in this group!"
        )

    bot_me = await client.get_me()
    caption = (
        f"👋 **ʜᴇʏ** {message.from_user.mention} ❞\n"
        f"⦿ **ᴛʜɪs ɪs** 『 **ʀᴏʜɪᴛ ᴄʜᴀᴜʜᴀɴ ᴍᴜsɪᴄ** 』⚡✨\n\n"
        f"➳ **ᴀ ғᴀsᴛ & ᴘᴏᴡᴇʀғᴜʟ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴜsɪᴄ ᴘʟᴀʏᴇʀ ʙᴏᴛ** 🎵 **ᴡɪᴛʜ sᴏᴍᴇ ᴀᴡᴇsᴏᴍᴇ ᴠɪᴘ ғᴇᴀᴛᴜʀᴇs.**\n\n"
        f"⚙️ ⦿ **ᴛᴀᴘ ʜᴇʟᴘ ᴛᴏ ᴇxᴘʟᴏʀᴇ ᴄᴏᴍᴍᴀɴᴅs.**"
    )
    reply_markup = get_start_markup(bot_me.username)

    try:
        await message.reply_photo(photo=START_IMG, caption=caption, reply_markup=reply_markup)
    except Exception as e:
        print(f"Photo send error: {e}")
        await message.reply_text(caption, reply_markup=reply_markup)

@bot.on_callback_query()
async def all_callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    chat_id = callback_query.message.chat.id

    if data == "bot_help":
        help_text = (
            "🛠 **VIP Music & Management Commands:**\n\n"
            "🎵 **Music Player:**\n"
            "• `/play <song>` - VC me 320kbps gaana play karein\n"
            "• `/stop` ya `/leavevc` - VC leave karein & playback stop\n"
            "• `/pose` - Song pause karein\n"
            "• `/radumey` - Song resume karein\n\n"
            "🤖 **Assistant Management:**\n"
            "• `/userbotjoin` - Assistant group me auto-join karega\n"
            "• `/userbotleave` - Assistant group se leave karega\n\n"
            "📢 **Smart Tagging:**\n"
            "• `/tagall <text>` - 5-5 members mention\n"
            "• `/tag <text>` - One-by-one mention\n"
            "• `/vctag <text>` - Sabhi ko VC invite alert\n"
            "• `/cancel` - Tagging turant rokein\n\n"
            "👑 **Info:**\n"
            "• `/owner` - Asli Maalik details (@itz_rohit_rss)"
        )
        back_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 BACK", callback_data="bot_back")]
        ])
        await callback_query.edit_message_caption(caption=help_text, reply_markup=back_markup)
        return await callback_query.answer()

    elif data == "bot_back":
        bot_me = await client.get_me()
        caption = (
            f"👋 **ʜᴇʏ** {callback_query.from_user.mention} ❞\n"
            f"⦿ **ᴛʜɪs ɪs** 『 **ʀᴏʜɪᴛ ᴄʜᴀᴜʜᴀɴ ᴍᴜsɪᴄ** 』⚡✨\n\n"
            f"➳ **ᴀ ғᴀsᴛ & ᴘᴏᴡᴇʀғᴜʟ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴜsɪᴄ ᴘʟᴀʏᴇʀ ʙᴏᴛ** 🎵 **ᴡɪᴛʜ sᴏᴍᴇ ᴀᴡᴇsᴏᴍᴇ ᴠɪᴘ ғᴇᴀᴛᴜʀᴇs.**\n\n"
            f"⚙️ ⦿ **ᴛᴀᴘ ʜᴇʟᴘ ᴛᴏ ᴇxᴘʟᴏʀᴇ ᴄᴏᴍᴍᴀɴᴅs.**"
        )
        await callback_query.edit_message_caption(caption=caption, reply_markup=get_start_markup(bot_me.username))
        return await callback_query.answer()

    elif data == "bot_lang":
        return await callback_query.answer("🌐 Language: Default (Hindi / English)!", show_alert=True)

    elif data == "bot_source":
        return await callback_query.answer("👑 Exclusively built for Rohit Chauhan (@itz_rohit_rss)!", show_alert=True)

    elif data == "bot_ping":
        start_ping = time.time()
        delta = round((time.time() - start_ping) * 1000)
        return await callback_query.answer(f"🏓 VIP Pong: {delta}ms | Server Fast! 🔥", show_alert=True)

    # Player Controls Callbacks
    elif data.startswith("playctrl_"):
        action, target_cid_str = data.split(":")
        target_cid = int(target_cid_str)

        if action == "playctrl_pause":
            try:
                await call_py.pause_stream(target_cid)
                is_paused_dict[target_cid] = True
                await callback_query.edit_message_reply_markup(reply_markup=get_player_buttons(target_cid))
                return await callback_query.answer("⏸ Playback Paused!", show_alert=False)
            except Exception as e:
                return await callback_query.answer(f"Error: {e}", show_alert=True)

        elif action == "playctrl_resume":
            try:
                await call_py.resume_stream(target_cid)
                is_paused_dict[target_cid] = False
                await callback_query.edit_message_reply_markup(reply_markup=get_player_buttons(target_cid))
                return await callback_query.answer("▶️ Playback Resumed!", show_alert=False)
            except Exception as e:
                return await callback_query.answer(f"Error: {e}", show_alert=True)

        elif action == "playctrl_stop":
            try:
                await call_py.leave_call(target_cid)
            except Exception:
                pass
            autoplay_enabled[target_cid] = False
            for f in glob.glob(f"downloads/{target_cid}.*"):
                try:
                    os.remove(f)
                except Exception:
                    pass
            await callback_query.answer("⏹ Playback stopped & VC left!", show_alert=True)
            return await callback_query.message.edit_text("⏹️ **Gaana stop kar diya aur Assistant VC se bahar aa gaya!**")

        elif action == "playctrl_skip":
            await callback_query.answer("⏭ Skipping track...", show_alert=False)
            if autoplay_enabled.get(target_cid, False):
                await trigger_autoplay(target_cid)
            else:
                try:
                    await call_py.leave_call(target_cid)
                except Exception:
                    pass
                await callback_query.message.edit_text("⏭️ **Song skip kar diya gaya! (Auto-play off tha)**")

        elif action == "playctrl_autoplay":
            current_status = autoplay_enabled.get(target_cid, False)
            autoplay_enabled[target_cid] = not current_status
            new_text = "ON 🟢" if autoplay_enabled[target_cid] else "OFF 🔴"
            await callback_query.edit_message_reply_markup(reply_markup=get_player_buttons(target_cid))
            return await callback_query.answer(f"🔄 Auto-Play: {new_text}", show_alert=True)

# --- 7. ASSISTANT JOIN / LEAVE COMMANDS ---
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

# --- 8. PLAY COMMAND & VC STREAM ---
@bot.on_message(filters.command(["play", "vplay"]) & filters.group)
async def play_handler(client, message):
    registered_groups.add(message.chat.id)
    is_video = message.command[0].lower() == "vplay"
    if len(message.command) < 2:
        return await message.reply_text("Bhai gaane ka naam do! Example: `/play shiv tandav`")

    query = " ".join(message.command[1:])
    last_playing_query[message.chat.id] = query
    m = await message.reply_text(f"⚡ **VIP Audio Engine buffering:** `{query}`...")

    try:
        track = await fetch_local_audio(query, message.chat.id)
    except Exception as e:
        return await m.edit(f"❌ Error: {e}")

    caption = (
        f"👑 **रोहित चौहान VIP Music Bot**\n\n"
        f"▶️ **Now Playing:** `{track['title']}`\n"
        f"⏳ **Duration:** `{track['duration']}`\n"
        f"👤 **Requested By:** {message.from_user.mention}\n\n"
        f"🔥 *Jalwa Rohit Chauhan Ka!*"
    )
    buttons = get_player_buttons(message.chat.id)

    try:
        stream = MediaStream(track["file_path"], video_flags=MediaStream.Flags.IGNORE if not is_video else None)
        await call_py.play(message.chat.id, stream)
        try:
            await call_py.unmute_stream(message.chat.id)
        except Exception:
            pass
        is_paused_dict[message.chat.id] = False
    except Exception as e:
        try:
            await call_py.leave_call(message.chat.id)
        except Exception:
            pass
        return await m.edit(f"VC join error: {e}")

    await m.delete()

    poster = None
    if track.get("thumbnail"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(track["thumbnail"], timeout=10) as resp:
                    if resp.status == 200:
                        raw_thumb = await resp.read()
                        poster = create_custom_poster(raw_thumb, track["title"])
        except Exception as err:
            print(f"Poster creation err: {err}")

    if poster:
        # Unique timestamp filename to break Telegram photo caching
        poster.name = f"poster_{int(time.time())}.jpg"
        await message.reply_photo(photo=poster, caption=caption, reply_markup=buttons)
    else:
        await message.reply_text(caption, reply_markup=buttons)

@bot.on_message(filters.command(["stop", "skip", "leave", "leavevc", "end"]) & filters.group)
async def stop_handler(client, message):
    try:
        await call_py.leave_call(message.chat.id)
    except Exception:
        pass
    autoplay_enabled[message.chat.id] = False
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
        is_paused_dict[message.chat.id] = True
        await message.reply_text("⏸️ **Playback Pause kar diya gaya hai.**")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@bot.on_message(filters.command("radumey") & filters.group)
async def resume_handler(client, message):
    try:
        await call_py.resume_stream(message.chat.id)
        is_paused_dict[message.chat.id] = False
        await message.reply_text("▶️ **Playback dobara Resume ho gaya!**")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

# --- 9. TAGGING SYSTEM ---
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

    print("🔥 Rohit Chauhan's Custom VIP Bot is LIVE & Dominating! 🔥")
    await idle()
    await bot.stop()
    await user.stop()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
