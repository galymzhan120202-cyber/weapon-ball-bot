import os
import random
import re
import requests
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.http
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from moviepy import AudioFileClip, AudioArrayClip, CompositeAudioClip
import sys
import io
import json
import logging
import time
from dotenv import load_dotenv
import traceback
import glob

import numpy as np

from battle_sim import simulate_battle, build_battle_clip, build_sfx_array, generate_thumbnail, INTRO_SECONDS, SR as SFX_SR, WEAPON_POOL

# UTF-8 кодтеуін орнату консоль үшін
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# .env файлын жүктеу
load_dotenv()

# --- ПАРАМЕТРЛЕР (ОРТА АЙНЫМАЛАЛАРДАН) ---
base_dir = os.getenv('BASE_DIR', os.path.dirname(os.path.abspath(__file__)))
TELEGRAM_NOTIFY_TOKEN = os.getenv('TELEGRAM_NOTIFY_TOKEN', '')
TELEGRAM_NOTIFY_CHAT_ID = os.getenv('TELEGRAM_NOTIFY_CHAT_ID', '')

MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
RETRY_DELAY = int(os.getenv('RETRY_DELAY', '2'))
BATTLE_MAX_SECONDS = int(os.getenv('BATTLE_MAX_SECONDS', '28'))
BATTLE_MIN_SECONDS = int(os.getenv('BATTLE_MIN_SECONDS', '13'))

AVOID_REPEAT_LOOKBACK = int(os.getenv('AVOID_REPEAT_LOOKBACK', '12'))
AVOID_REPEAT_MAX_ATTEMPTS = int(os.getenv('AVOID_REPEAT_MAX_ATTEMPTS', '6'))

YOUTUBE_CATEGORY_ID = os.getenv('YOUTUBE_CATEGORY_ID', '20')  # 20 = Gaming
YOUTUBE_PRIVACY_STATUS = os.getenv('YOUTUBE_PRIVACY_STATUS', 'public')
YOUTUBE_MADE_FOR_KIDS = os.getenv('YOUTUBE_MADE_FOR_KIDS', 'false').lower() == 'true'

VIDEO_CODEC = os.getenv('VIDEO_CODEC', 'libx264')
AUDIO_CODEC = os.getenv('AUDIO_CODEC', 'aac')
VIDEO_FPS = int(os.getenv('VIDEO_FPS', '24'))
VIDEO_PRESET = os.getenv('VIDEO_PRESET', 'ultrafast')
VIDEO_WIDTH = int(os.getenv('VIDEO_WIDTH', '1080'))
VIDEO_HEIGHT = int(os.getenv('VIDEO_HEIGHT', '1920'))

MUSIC_VOLUME = float(os.getenv('MUSIC_VOLUME', '0.15'))
SFX_VOLUME = float(os.getenv('SFX_VOLUME', '0.9'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(base_dir, 'debug.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

STRONG_HASHTAG_POOL = [
    "#shorts", "#weaponfight", "#ballfight", "#battle", "#satisfying",
    "#physics", "#fyp", "#viral", "#versus", "#whowins", "#simulation",
]

TITLE_TEMPLATES_2 = [
    "{names} — Who Wins?",
    "{names}! Weapon Ball Fight",
    "Ultimate Battle: {names}",
    "{names} — Physics Battle #shorts",
    "Can {a} beat {b}? Weapon Ball Fight",
]

TITLE_TEMPLATES_MULTI = [
    "{names} — Battle Royale!",
    "{n}-Way Weapon Ball Fight: {names}",
    "Only One Survives: {names}",
    "{names} — Who Wins the Melee?",
]

DESCRIPTION_TEMPLATES = [
    "{names} — full physics weapon ball battle!\n"
    "Winner: {winner} 🏆\n\n"
    "Fully generated battle, zero footage, zero copyright risk. New fight every upload.",

    "⚔️🔥 {names} just went head to head in a totally random physics arena!\n\n"
    "🏆 Winner: {winner}\n\n"
    "No script, no real footage — just pure chaotic physics. New battle every day!",

    "Only ONE weapon walks away... 💥\n\n"
    "{names}\n"
    "🏆 {winner} takes the win!\n\n"
    "Every matchup, every arena, every outcome — 100% randomly generated.",

    "🎲 Random matchup. Zero rules. One winner.\n\n"
    "{names} → {winner} wins!\n\n"
    "New chaos every single upload — who do you think should've won?",

    "{names} threw down in the arena and only {winner} made it out. 🏆\n\n"
    "Fully code-generated battle — no scripts, no stock footage, no copyright risk.",
]


def pick_rotating_tags(count=6):
    return ' '.join(random.sample(STRONG_HASHTAG_POOL, min(count, len(STRONG_HASHTAG_POOL))))


def build_title_and_description(fighter_names, winner_name):
    names_joined = " vs ".join(fighter_names)
    if len(fighter_names) == 2:
        template = random.choice(TITLE_TEMPLATES_2)
        title = template.format(names=names_joined, a=fighter_names[0], b=fighter_names[1])[:95]
    else:
        template = random.choice(TITLE_TEMPLATES_MULTI)
        title = template.format(names=names_joined, n=len(fighter_names))[:95]

    weapon_tags = ' '.join(f"#{name.lower().replace(' ', '')}" for name in fighter_names[:3])
    hashtags = f"{weapon_tags} {pick_rotating_tags()}"
    body = random.choice(DESCRIPTION_TEMPLATES).format(names=names_joined, winner=winner_name)
    description = f"{body}\n\n{hashtags}"
    tags = list(fighter_names) + ["weapon ball", "battle", "physics simulation", "shorts"]
    return title, description, tags


def build_duck_envelope(n_samples, sr, battle, depth=0.35, attack=0.03, release=0.35):
    """A volume-multiplier curve that dips briefly on every clash so the
    music visibly 'gives way' to the hit, then recovers — the ducking effect
    real editors add by hand. 1.0 = full volume, `depth` = volume during a hit."""
    env = np.ones(n_samples, dtype=np.float32)
    a_n, r_n = max(1, int(attack * sr)), max(1, int(release * sr))
    attack_ramp = np.linspace(1.0, depth, a_n, dtype=np.float32)
    release_ramp = np.linspace(depth, 1.0, r_n, dtype=np.float32)

    for frame_idx in battle["hit_frame_flags"]:
        t = INTRO_SECONDS + frame_idx / battle["fps"]
        pos = int(t * sr)

        a0, a1 = max(0, pos), min(n_samples, pos + a_n)
        if a1 > a0:
            env[a0:a1] = np.minimum(env[a0:a1], attack_ramp[: a1 - a0])

        r0, r1 = max(0, pos + a_n), min(n_samples, pos + a_n + r_n)
        if r1 > r0:
            env[r0:r1] = np.minimum(env[r0:r1], release_ramp[: r1 - r0])

    return env


def retry_with_backoff(func, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"⚠️ Сәтсіз (әрекет {attempt + 1}/{max_retries}): {str(e)[:100]}")
                logger.info(f"⏳ {wait_time} сек. күте тұр...")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ {max_retries} әрекеттен кейін сәтсіз")
                raise


def send_telegram(message: str):
    if not TELEGRAM_NOTIFY_TOKEN or not TELEGRAM_NOTIFY_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_NOTIFY_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TELEGRAM_NOTIFY_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass


def ensure_directories_exist():
    music_dir = os.path.join(base_dir, 'music')
    if not os.path.exists(music_dir):
        raise FileNotFoundError(f"❌ Папқа жоқ: {music_dir}")
    logger.info("✓ Барлық папқалар дайын")


MUSIC_QUERIES = [
    "action", "electronic beat", "intense", "energetic", "combat",
    "epic battle", "adrenaline", "dubstep", "aggressive", "cinematic action",
]


def _try_fetch_openverse_music(query, min_duration_sec):
    response = requests.get(
        "https://api.openverse.org/v1/audio/",
        params={"q": query, "category": "music", "license": "cc0,by", "page_size": 20},
        timeout=15,
        headers={"User-Agent": "WeaponBallBot/1.0 (automated background music fetch)"}
    )
    response.raise_for_status()
    results = response.json().get("results", [])

    min_duration_ms = (min_duration_sec + 5) * 1000
    candidates = [
        r for r in results
        if r.get("duration") and r["duration"] >= min_duration_ms and r.get("url")
    ]
    if not candidates:
        logger.warning(f"⚠️ Openverse: '{query}' бойынша лайықты трек табылмады")
        return None

    track = random.choice(candidates)
    dest = os.path.join(base_dir, "music", "_openverse_temp.mp3")

    dl_response = requests.get(track["url"], stream=True, timeout=30)
    dl_response.raise_for_status()

    with open(dest, "wb") as f:
        for chunk in dl_response.iter_content(chunk_size=1024 * 256):
            f.write(chunk)

    if os.path.getsize(dest) < 10_000:
        raise Exception("Жүктелген музыка тым кіші")

    license_type = (track.get("license") or "").lower()
    attribution = None
    if license_type and license_type != "cc0":
        creator = track.get("creator", "Unknown artist")
        title = track.get("title", "Untitled")
        source_url = track.get("foreign_landing_url") or track.get("url")
        attribution = f'Music: "{title}" by {creator} ({license_type.upper()}) — {source_url}'

    logger.info(f"✓ Openverse-тен музыка жүктелді (сұрау: '{query}', лицензия: {license_type or 'белгісіз'})")
    return dest, attribution


def fetch_openverse_music(min_duration_sec):
    tried_queries = random.sample(MUSIC_QUERIES, min(4, len(MUSIC_QUERIES)))
    for query in tried_queries:
        try:
            result = _try_fetch_openverse_music(query, min_duration_sec)
            if result:
                return result
        except Exception as e:
            logger.warning(f"⚠️ Openverse қатесі ('{query}'): {str(e)[:100]}")

    logger.warning("⚠️ Openverse: барлық сұраныстар сәтсіз, локал fallback қолданылады")
    return None


def get_local_music_attribution(filename):
    attribution_file = os.path.join(base_dir, "music", "fallback_attribution.json")
    if not os.path.exists(attribution_file):
        return None
    try:
        with open(attribution_file, "r", encoding="utf-8") as f:
            entries = json.load(f)
        for entry in entries:
            if entry.get("file") == filename and (entry.get("license") or "").lower() != "cc0":
                return (
                    f'Music: "{entry.get("title", "Untitled")}" by '
                    f'{entry.get("creator", "Unknown artist")} '
                    f'({entry.get("license", "by").upper()}) — {entry.get("foreign_landing_url", "")}'
                )
    except Exception:
        return None
    return None


def get_recent_channel_titles(max_results=15):
    scopes = ["https://www.googleapis.com/auth/youtube"]
    token_file = os.path.join(base_dir, "youtube_token.json")

    if not os.path.exists(token_file):
        return []

    try:
        credentials = Credentials.from_authorized_user_file(token_file, scopes)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
        channels_response = youtube.channels().list(part="contentDetails", mine=True).execute()
        items = channels_response.get("items", [])
        if not items:
            return []

        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        playlist_response = youtube.playlistItems().list(
            part="snippet", playlistId=uploads_playlist_id, maxResults=max_results
        ).execute()

        titles = [item["snippet"]["title"] for item in playlist_response.get("items", [])]
        logger.info(f"✓ Соңғы {len(titles)} видео атауы алынды")
        return titles

    except Exception as e:
        logger.warning(f"⚠️ Соңғы видео атауларын алу сәтсіз: {str(e)[:100]}")
        return []


_ALL_WEAPON_NAMES = [w["name"] for w in WEAPON_POOL]


def _weapon_set_from_title(title):
    """Extracts which weapon names are mentioned in a video title, using
    word-boundary matching so e.g. "Hammer" doesn't false-match inside
    "Warhammer"."""
    found = set()
    for name in _ALL_WEAPON_NAMES:
        if re.search(r'\b' + re.escape(name) + r'\b', title, re.IGNORECASE):
            found.add(name)
    return frozenset(found)


def get_recent_matchups(max_results=12):
    """Returns the set of weapon-matchups (as frozensets of names) seen in
    the channel's most recent uploads, so a freshly generated battle can be
    checked against them and re-rolled if it's an exact repeat."""
    titles = get_recent_channel_titles(max_results)
    matchups = [_weapon_set_from_title(t) for t in titles]
    return [m for m in matchups if len(m) >= 2]


def upload_to_youtube(video_path, title, description, tags=None, thumbnail_path=None):
    logger.info("📤 YouTube-ке жүктеу басталуда...")

    scopes = ["https://www.googleapis.com/auth/youtube"]
    client_file = os.path.join(base_dir, "client_secrets.json")
    token_file = os.path.join(base_dir, "youtube_token.json")

    credentials = None

    try:
        if os.path.exists(token_file):
            try:
                credentials = Credentials.from_authorized_user_file(token_file, scopes)
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    with open(token_file, 'w') as f:
                        f.write(credentials.to_json())
                logger.info("✓ Сохраненные учетные данные загружены")
            except Exception as e:
                logger.warning(f"⚠️ Токен мәселесі: {e}")
                credentials = None

        if credentials is None:
            try:
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    client_file, scopes
                )
                credentials = flow.run_local_server(
                    port=0,
                    open_browser=True,
                    authorization_prompt_message='Браузерде OAuth логинін орындаңыз: {url}',
                    success_message='✓ Аутентификация сәтті! Терезесін жабыңыз.'
                )
                with open(token_file, 'w') as f:
                    f.write(credentials.to_json())
                logger.info("✓ Жаңа OAuth токены сақталды")
            except Exception as e:
                logger.error(f"❌ OAuth қатесі: {e}")
                raise

        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": YOUTUBE_CATEGORY_ID,
                "tags": tags or ["weapon ball", "battle", "shorts"]
            },
            "status": {
                "privacyStatus": YOUTUBE_PRIVACY_STATUS,
                "selfDeclaredMadeForKids": YOUTUBE_MADE_FOR_KIDS
            }
        }

        logger.info(f"📤 Файл жүктелуде: {os.path.basename(video_path)}")

        media = googleapiclient.http.MediaFileUpload(video_path, chunksize=1024 * 1024, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"  Прогресс: {progress}%")

        video_id = response['id']
        logger.info(f"\n✅ ЖЕҢІС! Видео YouTube-та жүктелді!")
        logger.info(f"   ID: {video_id}")
        logger.info(f"   URL: https://youtube.com/shorts/{video_id}")

        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=googleapiclient.http.MediaFileUpload(thumbnail_path)
                ).execute()
                logger.info("✓ Custom thumbnail орнатылды")
            except Exception as e:
                # Thumbnail-ды орнату толық "youtube" scope + арнаның телефон
                # нөмірімен расталуын талап етеді (YouTube шектеуі, API-мен
                # айналып өту мүмкін емес). Талап орындалмаса 403 қайтарады —
                # бұл видео жүктелуін тоқтатпайды, тек warning ретінде логталады.
                logger.warning(f"⚠️ Thumbnail орнату сәтсіз (video жүктелді): {str(e)[:200]}")

        return video_id

    except Exception as e:
        logger.error(f"❌ Жүктеу қатесі: {e}")
        raise


def cleanup_temp_files():
    temp_patterns = [
        os.path.join(base_dir, "TEMP_MPY_*.mp4"),
        os.path.join(base_dir, "music", "_openverse_temp.mp3"),
    ]
    for pattern in temp_patterns:
        for temp_file in glob.glob(pattern):
            try:
                os.remove(temp_file)
                logger.debug(f"  Қалдық өшірілді: {os.path.basename(temp_file)}")
            except Exception:
                pass


def generate_video(skip_upload: bool = False, n_fighters: int = None):
    try:
        logger.info("🎬 Weapon Ball видео құру процессі басталды")

        ensure_directories_exist()
        cleanup_temp_files()

        recent_matchups = get_recent_matchups(AVOID_REPEAT_LOOKBACK)

        seed = random.randint(1, 2**31 - 1)
        battle = simulate_battle(
            w=VIDEO_WIDTH, h=VIDEO_HEIGHT, seed=seed, fps=VIDEO_FPS,
            max_seconds=BATTLE_MAX_SECONDS, min_seconds=BATTLE_MIN_SECONDS,
            n_fighters=n_fighters,
        )
        fighter_names = [f["name"] for f in battle["fighters"]]

        attempts = 1
        while frozenset(fighter_names) in recent_matchups and attempts < AVOID_REPEAT_MAX_ATTEMPTS:
            seed = random.randint(1, 2**31 - 1)
            battle = simulate_battle(
                w=VIDEO_WIDTH, h=VIDEO_HEIGHT, seed=seed, fps=VIDEO_FPS,
                max_seconds=BATTLE_MAX_SECONDS, min_seconds=BATTLE_MIN_SECONDS,
                n_fighters=n_fighters,
            )
            fighter_names = [f["name"] for f in battle["fighters"]]
            attempts += 1
        if attempts > 1:
            logger.info(f"🔁 Қайталанатын матчап аттап өтілді ({attempts} әрекет)")

        winner_name = battle["winner_name"]
        logger.info(f"⚔️ Шайқас ({battle['n_fighters']}): {' vs '.join(fighter_names)} — жеңімпаз: {winner_name}")

        video_title, video_description, video_tags = build_title_and_description(
            fighter_names, winner_name
        )
        logger.info(f"🏷️ Тақырып: {video_title}")

        thumbnail_path = os.path.join(base_dir, "thumbnail.jpg")
        try:
            generate_thumbnail(battle, thumbnail_path)
            logger.info("✓ Custom thumbnail дайын")
        except Exception as e:
            logger.warning(f"⚠️ Thumbnail генерациясы сәтсіз: {e}")
            thumbnail_path = None

        battle_clip = None
        music_clip = None
        sfx_clip = None
        final_video = None

        try:
            battle_clip = build_battle_clip(battle)
            duration = battle_clip.duration

            # SFX (соққы дыбыстары, толығымен синтезделген)
            sfx_array, sfx_sr = build_sfx_array(battle)
            sfx_clip = AudioArrayClip(sfx_array, fps=sfx_sr).subclipped(0, duration)
            audio_tracks = [sfx_clip.with_volume_scaled(SFX_VOLUME)]

            # Фон музыка
            music_path = None
            music_attribution = None
            try:
                music_result = fetch_openverse_music(duration)
                if music_result:
                    music_path, music_attribution = music_result
                if not music_path:
                    music_folder = os.path.join(base_dir, "music")
                    music_files = [
                        f for f in os.listdir(music_folder)
                        if f.endswith(('.mp3', '.wav')) and not f.startswith('_openverse')
                    ]
                    if music_files:
                        chosen_music_file = random.choice(music_files)
                        music_path = os.path.join(music_folder, chosen_music_file)
                        music_attribution = get_local_music_attribution(chosen_music_file)
            except Exception as e:
                logger.warning(f"⚠️ Музыка таңдау қатесі: {e}")

            if music_path:
                music_clip = AudioFileClip(music_path)
                if music_clip.duration < duration:
                    loops_needed = int(duration / music_clip.duration) + 1
                    from moviepy import concatenate_audioclips
                    music_clip = concatenate_audioclips([music_clip] * loops_needed)
                music_clip = music_clip.subclipped(0, duration).with_volume_scaled(MUSIC_VOLUME)

                try:
                    music_array = music_clip.to_soundarray(fps=SFX_SR)
                    if music_array.ndim == 1:
                        music_array = np.stack([music_array, music_array], axis=1)
                    envelope = build_duck_envelope(len(music_array), SFX_SR, battle)
                    music_clip = AudioArrayClip(music_array * envelope[:, None], fps=SFX_SR)
                except Exception as e:
                    logger.warning(f"⚠️ Ducking қатесі, ducking-сіз жалғастырылады: {e}")

                audio_tracks.append(music_clip)
                if music_attribution:
                    video_description += f"\n\n{music_attribution}"
                logger.info(f"🎵 Музыка таңдалды: {os.path.basename(music_path)}")
            else:
                logger.warning("⚠️ Фон музыкасы табылмады, тек SFX қолданылады")

            final_audio = CompositeAudioClip(audio_tracks)
            final_video = battle_clip.with_audio(final_audio)

            final_output = os.path.join(base_dir, "final_shorts.mp4")
            logger.info(f"\n⏳ Видео құрылуда ({VIDEO_CODEC}, {VIDEO_FPS}fps, {duration:.1f}с)...")

            try:
                final_video.write_videofile(
                    final_output,
                    codec=VIDEO_CODEC,
                    audio_codec=AUDIO_CODEC,
                    fps=VIDEO_FPS,
                    preset=VIDEO_PRESET,
                    logger=None
                )
            except Exception as write_error:
                logger.warning(f"⚠️ Видео жазу қатесі: {write_error}")
                logger.info("   Резервтік кодек қолданылуда...")
                final_video.write_videofile(
                    final_output,
                    codec="mpeg4",
                    audio_codec="libmp3lame",
                    fps=VIDEO_FPS,
                    preset='ultrafast'
                )

            logger.info(f"✓ Видео дайын: {final_output}")

            if not skip_upload:
                video_id = retry_with_backoff(lambda: upload_to_youtube(final_output, video_title, video_description, video_tags, thumbnail_path))
                video_url = f"https://youtube.com/shorts/{video_id}"
                send_telegram(
                    f"✅ <b>Жаңа Weapon Ball видео жүктелді!</b>\n"
                    f"⚔️ <b>{' vs '.join(fighter_names)}</b>\n"
                    f"🏆 Жеңімпаз: {winner_name}\n"
                    f"🔗 {video_url}"
                )
            else:
                logger.info("✓ Видео сақталды (жүктеу өтіп кетті)")

        finally:
            try:
                if battle_clip:
                    battle_clip.close()
                if music_clip:
                    music_clip.close()
                if sfx_clip:
                    sfx_clip.close()
                if final_video:
                    final_video.close()
                logger.info("✓ Ресурстар босатылды")
            except Exception:
                pass

    except Exception as e:
        logger.error(f"❌ Қате: {e}")
        logger.debug(traceback.format_exc())
        send_telegram(f"❌ <b>Weapon Ball видео жасауда қате шықты!</b>\n<code>{str(e)[:300]}</code>")
        raise


if __name__ == "__main__":
    try:
        generate_video()
    except Exception as e:
        logger.error(f"Программа сәтсіз аяқталды: {e}")
