"""
╔═══════════════════════════════════════════════════════════════════╗
║   AI LYRIC VIDEO GENERATOR  —  CLEAN FINAL EDITION                ║
║   Abstract art • Story-driven • Smooth transitions • Bug-free     ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import sys
# 🚨 BULLETPROOF EMOJI FIX: Forces Python to print emojis natively on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

import bisect
import json
import os
import re
import time
import urllib.request
import concurrent.futures
import numpy as np
import cv2
import ollama
import fal_client
from moviepy.editor import AudioFileClip, VideoClip
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# ── CLI flags ─────────────────────────────────────────────────────────────────
SKIP_LLAMA      = "--skip-llama"      in sys.argv
USE_CACHED_IMGS = "--use-cached-imgs" in sys.argv

# ═════════════════════════════════════════════════════════════════
#  CONFIGURATION (Connected to Streamlit via OS Environment)
# ═════════════════════════════════════════════════════════════════
os.environ["FAL_KEY"] = "5c90f577-c8e2-4c1b-b110-ba476f731f00:2f23f9c6b5911fb5f527798f76f43e01"

JSON_PATH         = os.getenv("HACKATUNE_SONG", r"lyric_video_songs_and_data\song_667784.json")
AUDIO_PATH        = os.getenv("HACKATUNE_AUDIO", r"lyric_video_songs_and_data\song_667784.mp3")
OUTPUT_PATH       = os.getenv("HACKATUNE_OUTPUT", "output_lyric_video.mp4")
CACHE_DIR         = Path("scene_cache")
FONT_PATH         = "Arial.ttf"
SCENE_PROMPT_FILE = "scene_prompts.json"

WIDTH, HEIGHT    = 1920, 1080
FPS              = 24
LLAMA_MODEL      = "llama3"
FAL_MODEL        = "fal-ai/flux/schnell"
PARALLEL_IMAGES  = 8

# Values pulled directly from Streamlit UI Sliders
TARGET_SCENES    = int(os.getenv("HACKATUNE_SCENES", 24))
CROSSFADE_DUR    = float(os.getenv("HACKATUNE_XFADE", 2.0))
FLUX_STEPS       = int(os.getenv("HACKATUNE_STEPS", 4))
KEN_BURNS_ZOOM   = 0.06
BEAT_ZOOM_STR    = 0.03

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ═════════════════════════════════════════════════════════════════
#  LOAD DATA
# ═════════════════════════════════════════════════════════════════
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

lyrics_timeline = data["lyrics_json"]
audio_analysis  = data["audio_analysis"]
intensity_data  = audio_analysis["intensity_sections"]["data"]
beats           = [b / 1000.0 for b in audio_analysis["beat_data"]["beat_positions"]]
audio_clip      = AudioFileClip(AUDIO_PATH)
TOTAL_DURATION  = audio_clip.duration

def get_audio_metrics(t: float) -> dict:
    idx = min(int(t * 10), len(intensity_data) - 1)
    return intensity_data[idx] if intensity_data else {"energy_score": 0.15, "percussiveness": 0.1}

# ═════════════════════════════════════════════════════════════════
#  PRE-BAKED RENDER ASSETS
# ═════════════════════════════════════════════════════════════════

def _make_vignette_mask(h, w, strength=0.50):
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt(((X - w/2)/(w/2))**2 + ((Y - h/2)/(h/2))**2)
    return (1.0 - np.clip(dist * strength, 0.0, 1.0)).astype(np.float32)[:, :, np.newaxis]

VIGNETTE_MASK = _make_vignette_mask(HEIGHT, WIDTH)

def _make_gradient_band(h, w, band_h):
    band = np.zeros((band_h, w, 4), dtype=np.uint8)
    for row in range(band_h):
        a = int(175 * (1.0 - row / band_h) ** 1.6)
        band[row, :] = [2, 2, 6, a]
    canvas = np.zeros((h, w, 4), dtype=np.uint8)
    canvas[h - band_h:] = band
    return canvas

GRADIENT_PIL = Image.fromarray(
    _make_gradient_band(HEIGHT, WIDTH, int(HEIGHT * 0.32)), mode="RGBA"
)

_FONT_CACHE: dict = {}
def load_font(size: int):
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype(FONT_PATH, size)
        except OSError:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]

_SCENE_STARTS: list = []

# ═════════════════════════════════════════════════════════════════
#  LOCKED ART STYLE
# ═════════════════════════════════════════════════════════════════
STYLE_LOCK = (
    "abstract expressionist fine art painting, "
    "thick expressive impasto oil brushstrokes, "
    "translucent colour field glazes layered over raw canvas texture, "
    "painterly and gestural, no photorealism, no photography, "
    "museum-quality fine art, emotionally charged abstraction"
)

STYLE_SUFFIX = (
    "wide cinematic 16:9 composition, dramatic painterly lighting, "
    "deep tonal range, expressive brushwork, emotionally resonant abstraction, "
    "consistent oil painting aesthetic"
)

BASE_NEGATIVE = (
    "photorealistic, photograph, camera, 3d render, cgi, hyperrealistic, "
    "stock photo, clipart, illustration, anime, cartoon, digital art, "
    "bar, pub, club, room, interior, building, street, road, city, "
    "person, face, hands, body, silhouette, figure, portrait, "
    "fire, flame, hearts, stars, roses, neon, bright colours, "
    "text, watermark, logo, signature, border, frame, "
    "geometric pattern, tiling, repetition, symmetry, "
    "ugly, deformed, blurry, noisy, low quality, oversaturated"
)

# ═════════════════════════════════════════════════════════════════
#  STEP 1 — LLAMA: STORY ANALYSIS + SCENE BODIES
# ═════════════════════════════════════════════════════════════════

def build_scene_prompts() -> list:
    if SKIP_LLAMA and os.path.exists(SCENE_PROMPT_FILE):
        print("📂 --skip-llama: loading cached scene_prompts.json …")
        with open(SCENE_PROMPT_FILE) as f:
            return json.load(f)

    if os.path.exists(SCENE_PROMPT_FILE):
        os.remove(SCENE_PROMPT_FILE)

    full_lyrics = "\n".join(s["text"] for s in lyrics_timeline)

    print("🦙 Pass 1A — Understanding the song …")
    r = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": f"""
Read these song lyrics and answer in plain prose. Label each section clearly.

LYRICS:
{full_lyrics}

THEME: What is this song fundamentally about? Core emotion or message? (2–3 sentences)
JOURNEY: How does the emotion shift from start to end? What is the turning point? (2–3 sentences)
ABSTRACT_IMAGERY: What abstract visual language fits this song? Describe in terms of: colour temperature (warm/cool), movement (turbulent/still), texture (rough/smooth), density (dense/sparse), light quality (harsh/diffuse). Do NOT name real places, objects, or people. Pure abstract visual language only.
PALETTE: Suggest 5 specific paint colours (with hex codes) that match this song's emotional temperature. Choose colours that work together as a harmonious painting series. Format: "colour-name #HEXCODE, ..."
BANNED: List 10 visual elements that would be WRONG for this song's emotion.
"""}])
    song_analysis = r["message"]["content"].strip()
    print(f"\n🎵 Song Analysis:\n{song_analysis}\n{'─'*60}\n")

    palette_match = re.search(r"PALETTE[:\s]*(.*?)(?=\n[A-Z]+:|$)", song_analysis, re.DOTALL)
    song_palette  = palette_match.group(1).strip() if palette_match else "deep midnight blue #1a1a3e, muted gold #c4a44a, warm ivory #f0ebe0, charcoal #2d2d2d, dusty rose #b07070"

    banned_match  = re.search(r"BANNED[:\s]*(.*?)(?=\n[A-Z]+:|$)", song_analysis, re.DOTALL)
    song_banned   = banned_match.group(1).strip() if banned_match else ""

    full_negative = f"{BASE_NEGATIVE}, {song_banned}" if song_banned else BASE_NEGATIVE
    PALETTE_LOCK = f"colour palette restricted to: {song_palette}"
    LOCKED_PREFIX = f"{STYLE_LOCK}. {PALETTE_LOCK}. "

    print(f"🎨 Style  : {STYLE_LOCK[:70]} …")
    print(f"🎨 Palette: {song_palette[:70]} …")
    print(f"🚫 Banned : {song_banned[:70]} …\n")

    expanded = []
    repeats  = max(1, round(TARGET_SCENES / len(lyrics_timeline)))
    for slide in lyrics_timeline:
        dur     = slide["end"] - slide["start"]
        seg_dur = dur / repeats
        for k in range(repeats):
            expanded.append({
                "start": slide["start"] + k * seg_dur,
                "end":   slide["start"] + (k + 1) * seg_dur,
                "text":  slide["text"],
                "words": slide.get("words", []),
            })

    print(f"🦙 Pass 2 — Generating {len(expanded)} scene bodies in one call …")
    manifest_lines = []
    for i, slide in enumerate(expanded):
        mid_t   = (slide["start"] + slide["end"]) / 2
        energy  = get_audio_metrics(mid_t).get("energy_score", 0.15)
        pct     = int((i / len(expanded)) * 100)
        e_label = "HIGH" if energy > 0.28 else ("LOW" if energy < 0.18 else "MID")
        arc     = ("opening" if pct < 25 else "building" if pct < 50 else "peak" if pct < 75 else "resolving")
        nxt     = expanded[i+1]["text"] if i+1 < len(expanded) else "(song ends)"
        manifest_lines.append(f'{i+1}. [energy:{e_label}|arc:{arc}] "{slide["text"]}" → "{nxt}"')

    r2 = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": f"""
You are writing abstract painting descriptions for {len(expanded)} frames of a music video.

SONG ANALYSIS:
{song_analysis}

THE STYLE IS ALREADY LOCKED. Every image will be an abstract expressionist oil painting.
You only need to describe WHAT ABSTRACT FORMS AND COLOURS fill each frame.

SCENE LIST:
{chr(10).join(manifest_lines)}

Write exactly {len(expanded)} scene descriptions as a JSON array of strings.
Each string: 30–45 words describing ONLY abstract visual elements — no real places, no people, no objects, no named things.

Return ONLY the JSON array. Start with [ end with ].
"""}])

    raw = r2["message"]["content"].strip()
    start_i = raw.find("[")
    end_i   = raw.rfind("]")
    if start_i != -1 and end_i != -1:
        raw = raw[start_i:end_i+1]
    if "```" in raw:
        raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()

    try:
        bodies = json.loads(raw)
        if not isinstance(bodies, list):
            raise ValueError("not a list")
        print(f"✅ Batch parse OK — {len(bodies)} scene bodies")
    except Exception as e:
        print(f"⚠️  JSON parse failed ({e}) — line-split fallback …")
        bodies = [line.strip().strip('",').strip("'") for line in r2["message"]["content"].split("\n") if 20 < len(line.strip().strip('",')) < 350]
        print(f"   Recovered {len(bodies)} bodies")

    while len(bodies) < len(expanded):
        bodies.append(bodies[-1] if bodies else "broad translucent glazes of colour drifting across pale canvas")
    bodies = bodies[:len(expanded)]

    scene_prompts = []
    for i, slide in enumerate(expanded):
        full_prompt = f"{LOCKED_PREFIX}{bodies[i]}. {STYLE_SUFFIX}"
        scene_prompts.append({
            "start":    slide["start"],
            "end":      slide["end"],
            "text":     slide["text"],
            "words":    slide["words"],
            "prompt":   full_prompt,
            "negative": full_negative,
            "body":     bodies[i],
        })
        print(f"  ✅ {i+1:02d}/{len(expanded)}  \"{slide['text'][:45]}\"")

    with open(SCENE_PROMPT_FILE, "w", encoding="utf-8") as f:
        json.dump(scene_prompts, f, indent=2, ensure_ascii=False)

    return scene_prompts

# ═════════════════════════════════════════════════════════════════
#  STEP 2 — FAL.AI: PARALLEL IMAGE GENERATION
# ═════════════════════════════════════════════════════════════════

def generate_single_image(args: tuple) -> str:
    i, scene = args
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    img_path = CACHE_DIR / f"scene_{i:03d}.png"

    if USE_CACHED_IMGS and img_path.exists():
        print(f"  ⏭️  Scene {i:03d} — cached")
        return str(img_path)

    if img_path.exists():
        img_path.unlink()

    print(f"  🚀 Scene {i:03d} → Fal.ai …")
    
    for attempt in range(3):
        try:
            result = fal_client.subscribe(
                FAL_MODEL,
                arguments={
                    "prompt":              scene["prompt"],
                    "negative_prompt":     scene["negative"],
                    "image_size":          "landscape_16_9",
                    "num_inference_steps": FLUX_STEPS,
                    "guidance_scale":      3.5,
                },
            )
            url = result["images"][0]["url"]
            urllib.request.urlretrieve(url, str(img_path))
            print(f"  ✅ Scene {i:03d} saved")
            return str(img_path)

        except Exception as e:
            wait = 2 ** attempt
            print(f"  ❌ Scene {i:03d} attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(wait)

    placeholder = Image.new("RGB", (1024, 576), (180, 40, 40))
    draw = ImageDraw.Draw(placeholder)
    try:
        font = load_font(40)
    except:
        font = ImageFont.load_default()
    draw.text((20, 250), f"Scene {i:03d}\nGENERATION FAILED\nCheck Fal.ai API Key / Credits", fill=(255, 255, 255), font=font)
    placeholder.save(str(img_path))
    return str(img_path)

def fetch_all_images(scenes: list) -> list:
    mode = "CACHED" if USE_CACHED_IMGS else f"FAL.AI ({FAL_MODEL}, {FLUX_STEPS} steps, {PARALLEL_IMAGES} workers)"
    print(f"\n{'═'*65}")
    print(f"  IMAGE GENERATION — {mode}")
    print(f"{'═'*65}\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_IMAGES) as pool:
        paths = list(pool.map(generate_single_image, enumerate(scenes)))

    valid_paths = []
    for i, p in enumerate(paths):
        if p is None or not Path(p).exists():
            placeholder_path = str(CACHE_DIR / f"scene_{i:03d}.png")
            img = Image.new("RGB", (1024, 576), (180, 40, 40))
            img.save(placeholder_path)
            valid_paths.append(placeholder_path)
        else:
            valid_paths.append(p)

    return valid_paths

# ═════════════════════════════════════════════════════════════════
#  STEP 3 — CINEMATIC COMPOSITOR
# ═════════════════════════════════════════════════════════════════

IMAGE_CACHE: dict = {}

def get_cached_image(path: str) -> np.ndarray:
    if path not in IMAGE_CACHE:
        try:
            pil_img = Image.open(path).convert("RGB")
            img = np.array(pil_img)
        except Exception:
            img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            img[:, :, 0] = 150 
        
        IMAGE_CACHE[path] = cv2.resize(img, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
    return IMAGE_CACHE[path]

def get_beat_pulse(t: float) -> float:
    idx = bisect.bisect_right(beats, t) - 1
    if idx < 0:
        return 0.0
    since = t - beats[idx]
    if since < 0.18:
        return BEAT_ZOOM_STR * (1.0 - since / 0.18)
    return 0.0

def apply_ken_burns(img: np.ndarray, elapsed: float, duration: float,
                    beat_pulse: float, direction: int) -> np.ndarray:
    progress = float(np.clip(elapsed / max(duration, 0.01), 0.0, 1.0))
    
    if direction == 1:
        zoom = 1.0 + KEN_BURNS_ZOOM * progress
    else:
        zoom = 1.0 + KEN_BURNS_ZOOM * (1.0 - progress)
        
    zoom = float(max(zoom + beat_pulse, 1.0))
    
    h, w   = img.shape[:2]
    nw, nh = int(w * zoom), int(h * zoom)
    zoomed = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    
    pan_x  = int((nw - w) * progress * 0.25)
    x1     = int(np.clip(((nw - w) // 2) + direction * pan_x, 0, max(0, nw - w)))
    y1     = int(np.clip((nh - h) // 2, 0, max(0, nh - h)))
    
    return zoomed[y1:y1 + h, x1:x1 + w]

def apply_colour_grade(img: np.ndarray, energy: float) -> np.ndarray:
    out = img.copy().astype(np.int32)
    if energy > 0.25:
        amt        = min(int((energy - 0.25) * 55), 22)
        out[:,:,0] = np.clip(out[:,:,0] + amt,      0, 255)
        out[:,:,2] = np.clip(out[:,:,2] - amt // 2, 0, 255)
    elif energy < 0.15:
        grey = out.mean(axis=2, keepdims=True)
        out  = np.clip(out * 0.80 + grey * 0.20 + np.array([0, 2, 10]), 0, 255)
    return out.astype(np.uint8)

def make_frame(t: float, scenes: list, image_paths: list) -> np.ndarray:
    idx        = bisect.bisect_right(_SCENE_STARTS, t) - 1
    active_idx = max(0, min(idx, len(scenes) - 1))

    scene     = scenes[active_idx]
    elapsed   = t - scene["start"]
    scene_dur = max(scene["end"] - scene["start"], 0.1)
    direction = 1 if active_idx % 2 == 0 else -1
    beat      = get_beat_pulse(t)
    energy    = get_audio_metrics(t).get("energy_score", 0.15)

    curr_img = get_cached_image(image_paths[active_idx])
    bg       = apply_ken_burns(curr_img, elapsed, scene_dur, beat, direction)

    if active_idx > 0 and 0 <= elapsed < CROSSFADE_DUR:
        x     = (elapsed / CROSSFADE_DUR) * 10.0 - 5.0
        alpha = float(1.0 / (1.0 + np.exp(-x)))

        prev_sc   = scenes[active_idx - 1]
        prev_dur  = max(prev_sc["end"] - prev_sc["start"], 0.1)
        prev_dir  = 1 if (active_idx - 1) % 2 == 0 else -1
        prev_img  = get_cached_image(image_paths[active_idx - 1])

        prev_elapsed = prev_dur + elapsed
        prev_bg      = apply_ken_burns(prev_img, prev_elapsed, prev_dur, beat, prev_dir)

        bg = cv2.addWeighted(prev_bg, 1.0 - alpha, bg, alpha, 0)

    bg = apply_colour_grade(bg, energy)
    bg = (bg.astype(np.float32) * VIGNETTE_MASK).clip(0, 255).astype(np.uint8)

    if energy > 0.22:
        rng   = np.random.default_rng(int(t * FPS))
        noise = rng.integers(-4, 4, bg.shape, dtype=np.int16)
        bg    = np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    pil = Image.fromarray(bg).convert("RGBA")
    pil.alpha_composite(GRADIENT_PIL)
    pil = pil.convert("RGB")

    return np.array(pil)

# ═════════════════════════════════════════════════════════════════
#  MANIM SUBTITLE COMPOSITOR
# ═════════════════════════════════════════════════════════════════

def find_manim_output(scene_name: str = "SongPoster") -> str | None:
    base = Path("media") / "videos" / "song_poster_scene"
    if not base.exists():
        return None
    for quality_dir in sorted(base.iterdir(), reverse=True):
        if not quality_dir.is_dir():
            continue
        for ext in ("mov", "webm", "mp4", "avi"):
            candidate = quality_dir / f"{scene_name}.{ext}"
            if candidate.exists() and candidate.stat().st_size > 10_000:
                return str(candidate)
    return None

def render_manim_subtitles(song_json: str, output_webm: str) -> bool:
    import subprocess
    env = os.environ.copy()
    env["HACKATUNE_SONG"] = os.path.abspath(song_json)

    cmd = [
        "manim",
        os.getenv("MANIM_QUALITY", "-qh"),  
        "--format=mov",      
        "--transparent",     
        "song_poster_scene.py",
        "SongPoster",
    ]

    print(f"\n🎬 Running Manim: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, env=env, capture_output=False, text=True, timeout=1800)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Manim error: {e}")
        return False

def composite_with_moviepy(background_mp4: str, overlay_webm: str, output_mp4: str, audio_mp3: str) -> bool:
    try:
        from moviepy.editor import AudioFileClip, CompositeVideoClip, VideoFileClip
        import moviepy.video.fx.all as vfx

        print(f"\n✨ Compositing with MoviePy …")
        bg  = VideoFileClip(background_mp4)
        ovl = VideoFileClip(overlay_webm, has_mask=True)

        ovl = ovl.fx(vfx.mask_color, color=[0, 0, 0], thr=10, s=2)

        if (ovl.w, ovl.h) != (bg.w, bg.h):
            ovl = ovl.resize((bg.w, bg.h))

        if ovl.duration > bg.duration:
            ovl = ovl.subclip(0, bg.duration)

        comp = CompositeVideoClip([bg, ovl])
        comp = comp.set_audio(AudioFileClip(audio_mp3))

        comp.write_videofile(
            output_mp4,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="256k",
            bitrate="6000k",
            preset="faster",
            ffmpeg_params=["-crf", "18"],
            threads=os.cpu_count() or 4,
        )

        bg.close()
        ovl.close()
        comp.close()
        return True

    except Exception as e:
        print(f"❌ MoviePy composite failed: {e}")
        return False

def _fallback_add_audio(video_path: str, audio_path: str, output_path: str) -> None:
    from moviepy.editor import AudioFileClip, VideoFileClip
    print(f"\n🔊 Adding audio via MoviePy …")
    try:
        vid = VideoFileClip(video_path)
        aud = AudioFileClip(audio_path)
        out = vid.set_audio(aud)
        out.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            bitrate="6000k",
            preset="faster",
        )
        vid.close()
        aud.close()
    except Exception as e:
        print(f"❌ Fallback failed: {e}")

# ═════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t0 = time.time()

    scenes = build_scene_prompts()
    
    _SCENE_STARTS.clear()
    _SCENE_STARTS.extend(s["start"] for s in scenes)

    image_paths = fetch_all_images(scenes)

    print("\n📦 Pre-loading images into RAM …")
    for p in image_paths:
        get_cached_image(p)

    BG_PATH = "background_art.mp4"
    print(f"\n🖼  Rendering background art → {BG_PATH}")

    def frame_fn(t):
        return make_frame(t, scenes, image_paths)

    bg_video = VideoClip(frame_fn, duration=TOTAL_DURATION)
    bg_video.write_videofile(
        BG_PATH,
        fps=FPS,
        codec="libx264",
        audio_codec=None,
        bitrate="6000k",
        threads=os.cpu_count() or 4,
        preset="faster",
        ffmpeg_params=["-crf", "20"],
    )

    print(f"\n🎨 Rendering Manim subtitle overlay …")
    manim_ok = render_manim_subtitles(JSON_PATH, "manim_overlay.mov")

    manim_webm = find_manim_output("SongPoster") if manim_ok else None

    FINAL_PATH = OUTPUT_PATH
    if manim_webm and Path(manim_webm).exists():
        composite_ok = composite_with_moviepy(BG_PATH, manim_webm, FINAL_PATH, AUDIO_PATH)
        if not composite_ok:
            _fallback_add_audio(BG_PATH, AUDIO_PATH, FINAL_PATH)
    else:
        _fallback_add_audio(BG_PATH, AUDIO_PATH, FINAL_PATH)

    print(f"\n✨ COMPLETE in {(time.time() - t0)/60:.1f} min")
    print(f"  Output : {FINAL_PATH}")