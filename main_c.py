"""
main code 1------ works well
╔══════════════════════════════════════════════════════════╗
║       AI LYRIC VIDEO GENERATOR — ELEVATED EDITION       ║
║   Llama → Storyboard → Flux → Cinematic Compositor      ║
╚══════════════════════════════════════════════════════════╝

PIPELINE:
  1. Llama  — Global art direction + 45–50 stateful scene prompts
  2. Fal.ai — Flux image generation (always fresh, no skipping)
  3. OpenCV — Cinematic compositor: Ken Burns, beat-sync, crossfade
  4. PIL    — Dynamic typography engine with word-karaoke

USAGE:
  python lyric_video_gen.py                    # full run, always regenerates images
  python lyric_video_gen.py --skip-llama       # reuse scene_prompts.json, regenerate images
  python lyric_video_gen.py --use-cached-imgs  # reuse both prompts AND images (render only)
"""

import json
import os
import sys
import time
import urllib.request
import concurrent.futures
import numpy as np
import cv2
import ollama
import fal_client
from moviepy.editor import AudioFileClip, VideoClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

# ── CLI flags ──────────────────────────────────────────────────────────────────
SKIP_LLAMA      = "--skip-llama"      in sys.argv  # reuse scene_prompts.json
USE_CACHED_IMGS = "--use-cached-imgs" in sys.argv  # reuse existing scene_NNN.png files

# ═══════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════
os.environ["FAL_KEY"] = "5c90f577-c8e2-4c1b-b110-ba476f731f00:2f23f9c6b5911fb5f527798f76f43e01"

JSON_PATH  = r"lyric_video_songs_and_data\song_667778.json"
AUDIO_PATH = r"lyric_video_songs_and_data\song_667778.mp3"
OUTPUT_PATH = "output_lyric_video.mp4"
CACHE_DIR   = Path("scene_cache")          # generated images saved here
FONT_PATH   = "Arial.ttf"                  # swap for any TTF you like

WIDTH, HEIGHT   = 1920, 1080
FPS             = 30                        # 30 fps for smoother motion
LLAMA_MODEL     = "llama3"
FAL_MODEL       = "fal-ai/flux/dev"         # highest quality Flux
PARALLEL_IMAGES = 4                         # concurrent Fal.ai requests
CROSSFADE_DUR   = 0.6                       # seconds — elegant overlap
BEAT_ZOOM_STR   = 0.05                      # beat-pulse zoom strength
KEN_BURNS_ZOOM  = 0.08                      # per-scene drift amount

# Consistent colour palette fed to every Flux prompt
PALETTE_TAG = (
    "cohesive muted jewel-tone palette: dusty teal, warm amber, soft plum, "
    "ivory, charcoal outlines"
)

CACHE_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════
#  LOAD DATA
# ═══════════════════════════════════════════════════════════
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

lyrics_timeline = data["lyrics_json"]
audio_analysis  = data["audio_analysis"]
intensity_data  = audio_analysis["intensity_sections"]["data"]
beats = [b / 1000.0 for b in audio_analysis["beat_data"]["beat_positions"]]

audio_clip     = AudioFileClip(AUDIO_PATH)
TOTAL_DURATION = audio_clip.duration

def get_audio_metrics(t):
    idx = min(int(t * 10), len(intensity_data) - 1)
    return intensity_data[idx] if intensity_data else {"energy_score": 0.15, "percussiveness": 0.1}


# ═══════════════════════════════════════════════════════════
#  STEP 1 — LLAMA: GLOBAL ART DIRECTION + SCENE PROMPTS
# ═══════════════════════════════════════════════════════════

SCENE_PROMPT_FILE = "scene_prompts.json"

def build_scene_prompts():
    """Two-pass Llama pipeline: global style guide → 45-50 scene image prompts."""

    if SKIP_LLAMA and os.path.exists(SCENE_PROMPT_FILE):
        print("📂 --skip-llama: reusing existing scene_prompts.json …")
        with open(SCENE_PROMPT_FILE) as f:
            return json.load(f)

    if not SKIP_LLAMA and os.path.exists(SCENE_PROMPT_FILE):
        print("🗑️  Removing old scene_prompts.json — running fresh Llama pass …")
        os.remove(SCENE_PROMPT_FILE)

    # ── PASS 1: Global Style Guide ──────────────────────────────────────────
    print("🦙 Pass 1 — Building global art direction …")
    full_lyrics = "\n".join(s["text"] for s in lyrics_timeline)

    guide_prompt = f"""
You are a legendary animated music video director (think Spider-Man: Into the Spider-Verse, Gorillaz, Arcane).
Study these complete lyrics and design ONE unified visual story.

LYRICS:
{full_lyrics}

Produce a concise STYLE GUIDE covering:

WORLD: One specific recurring setting (e.g., "a crumbling watercolor city at dusk") — never change it.
CHARACTER: One recurring protagonist. Describe: silhouette, clothing colours, signature prop/gesture.
  Style mandate: hand-drawn, sketchy outlines, flat fills, minimal facial features, expressive body language.
  NO photorealism. NO 3-D renders. NO hyperrealistic faces.
MOTIFS: 4–6 visual symbols that recur and evolve (e.g., paper cranes, flickering lamp posts, ink blots).
PALETTE: {PALETTE_TAG}
ANIMATION STYLE: Describe exactly (e.g., "Studio-Ghibli-meets-graphic-novel: loose ink lines, watercolour washes, bold negative space").
CAMERA LANGUAGE: Default motion per energy level (low energy = slow push-in / wide; high energy = dynamic diagonal, Dutch tilt).
TRANSITION LOGIC: How each shot connects spatially to the previous (camera continues its path; environment evolves, never resets).
ENERGY MAP: Brief emotional arc: verse 1 feel → chorus feel → bridge feel → outro feel.

Write only the guide. No lists. No bullet points. Flowing prose, under 400 words.
"""
    r = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": guide_prompt}])
    style_guide = r["message"]["content"].strip()
    print(f"\n🎨 Style Guide established:\n{style_guide}\n{'─'*60}\n")

    # ── PASS 2: Per-Scene Prompts (targeting 45–50 scenes) ─────────────────
    print("🦙 Pass 2 — Generating per-scene image prompts …")

    # Expand short slides into sub-scenes for a richer 45–50 frame count
    expanded = []
    target = 48
    total_slides = len(lyrics_timeline)
    repeats = max(1, round(target / total_slides))

    for slide in lyrics_timeline:
        dur = slide["end"] - slide["start"]
        seg_dur = dur / repeats
        for k in range(repeats):
            expanded.append({
                "start": slide["start"] + k * seg_dur,
                "end":   slide["start"] + (k + 1) * seg_dur,
                "text":  slide["text"],
                "words": slide.get("words", []),
                "sub_idx": k,
                "sub_total": repeats,
            })

    scene_prompts = []
    previous_desc = (
        "Opening shot: wide establishing view of the main world, "
        "golden-hour light, character barely visible in the distance."
    )

    for i, slide in enumerate(expanded):
        metrics     = get_audio_metrics((slide["start"] + slide["end"]) / 2)
        energy      = metrics.get("energy_score", 0.15)
        perc        = metrics.get("percussiveness", 0.1)
        energy_label = (
            "HIGH-ENERGY/intense/dynamic"   if energy > 0.28 else
            "LOW-ENERGY/calm/introspective" if energy < 0.18 else
            "MID-ENERGY/building/emotional"
        )
        next_text = expanded[i + 1]["text"] if i + 1 < len(expanded) else "(song ends)"

        director_prompt = f"""
You are storyboarding frame {i+1} of {len(expanded)} of a 2D animated music video.

STYLE GUIDE:
{style_guide}

PREVIOUS SHOT:
{previous_desc}

NOW SHOWING LYRICS: "{slide['text']}"
UPCOMING LYRICS: "{next_text}"
MUSICAL ENERGY: {energy_label} | Percussiveness: {perc:.2f}
SUB-SCENE: {slide['sub_idx']+1} of {slide['sub_total']} within this lyric block

TASK:
Write ONE image generation prompt (max 75 words) for the NEXT FRAME.

Hard rules:
- Same character, same world — evolve spatially, never restart.
- Match camera to energy: {energy_label}.
- Sub-scene {slide['sub_idx']+1}/{slide['sub_total']}: {
    'Wide or establishing angle — open the lyric moment.' if slide['sub_idx'] == 0 else
    'Continue camera motion, reveal more of the scene or character emotion.' if slide['sub_idx'] == 1 else
    'Close in on a motif or emotional beat, prepare transition to next lyric.'
}
- Art style: hand-drawn, sketchy, flat colour, ink outlines, no photorealism.
- Describe ONLY what the camera sees. No meta-commentary.

Output only the raw prompt. Nothing else.
"""

        r = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": director_prompt}])
        raw = r["message"]["content"].strip().strip('"')

        # ── Flux-hardened final prompt ──────────────────────────────────────
        final_prompt = (
            f"Animated 2D illustration, hand-drawn ink lines, flat watercolour fills, "
            f"{PALETTE_TAG}, no photorealism, no 3D, no CGI, no realistic faces. "
            f"{raw}. "
            f"Consistent character design, continuous narrative frame, artsy graphic-novel aesthetic, "
            f"ultra-detailed background, cinematic composition, 16:9."
        )

        scene_prompts.append({
            "start":  slide["start"],
            "end":    slide["end"],
            "text":   slide["text"],
            "words":  slide["words"],
            "prompt": final_prompt,
        })
        previous_desc = raw
        print(f"  ✅ Scene {i+1:02d}/{len(expanded)} — {slide['text'][:50]} …")

    with open(SCENE_PROMPT_FILE, "w") as f:
        json.dump(scene_prompts, f, indent=2)

    print(f"\n💾 {len(scene_prompts)} scene prompts saved to {SCENE_PROMPT_FILE}")
    return scene_prompts


# ═══════════════════════════════════════════════════════════
#  STEP 2 — FAL.AI: PARALLEL IMAGE GENERATION
# ═══════════════════════════════════════════════════════════

def generate_single_image(args):
    """
    Always calls Fal.ai UNLESS --use-cached-imgs flag is set AND the file exists.
    On a normal run (no flags) it ALWAYS generates fresh images.
    """
    i, scene = args
    img_path = CACHE_DIR / f"scene_{i:03d}.png"

    # Only skip if the user explicitly asked to reuse cached images
    if USE_CACHED_IMGS and img_path.exists():
        print(f"  ⏭️  Scene {i:03d} — reusing cached image (--use-cached-imgs)")
        return str(img_path)

    # Delete any stale file so we always write a fresh one
    if img_path.exists():
        img_path.unlink()

    print(f"\n  🚀 FAL.AI CALL — Scene {i:03d}/{len(scene['prompt'][:40])}…")
    print(f"     Prompt: {scene['prompt'][:120]} …")

    for attempt in range(3):
        try:
            print(f"     ⚡ Attempt {attempt + 1}/3 — sending to {FAL_MODEL} …")
            result = fal_client.subscribe(
                FAL_MODEL,
                arguments={
                    "prompt":              scene["prompt"],
                    "width":               1024,
                    "height":              576,
                    "num_inference_steps": 35,
                    "guidance_scale":      7.5,
                },
            )
            url = result["images"][0]["url"]
            print(f"     ✅ Image received — downloading from Fal CDN …")
            urllib.request.urlretrieve(url, str(img_path))
            print(f"     💾 Saved → {img_path}")
            return str(img_path)

        except Exception as e:
            wait = 2 ** attempt
            print(f"     ❌ Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                print(f"     ⏳ Retrying in {wait}s …")
                time.sleep(wait)

    # All attempts failed — write a visible error placeholder
    print(f"     ⚠️  All attempts failed for scene {i:03d} — using placeholder.")
    img = Image.new("RGB", (1024, 576), (30, 10, 10))
    draw = ImageDraw.Draw(img)
    draw.text((20, 260), f"Scene {i:03d} — generation failed", fill=(200, 80, 80))
    img.save(str(img_path))
    return str(img_path)


def fetch_all_images(scenes):
    """
    Dispatch all scene prompts to Fal.ai.
    Default: always regenerates every image.
    Pass --use-cached-imgs to skip scenes that already have a file on disk.
    """
    mode = "REUSING CACHED" if USE_CACHED_IMGS else "GENERATING FRESH (calling Fal.ai)"
    print(f"\n{'═'*60}")
    print(f"  IMAGE GENERATION — {mode}")
    print(f"  Total scenes : {len(scenes)}")
    print(f"  Parallel jobs: {PARALLEL_IMAGES}")
    print(f"  Fal.ai model : {FAL_MODEL}")
    print(f"{'═'*60}\n")

    CACHE_DIR.mkdir(exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_IMAGES) as pool:
        paths = list(pool.map(generate_single_image, enumerate(scenes)))

    generated = sum(1 for p in paths if Path(p).exists())
    print(f"\n✅ Image generation complete — {generated}/{len(scenes)} images ready.")
    return paths


# ═══════════════════════════════════════════════════════════
#  STEP 3 — CINEMATIC COMPOSITOR
# ═══════════════════════════════════════════════════════════

IMAGE_CACHE: dict = {}

def get_cached_image(path: str) -> np.ndarray:
    if path not in IMAGE_CACHE:
        img = cv2.imread(path)
        if img is None:
            img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        IMAGE_CACHE[path] = cv2.resize(img, (WIDTH, HEIGHT))
    return IMAGE_CACHE[path]


def get_beat_pulse(t: float) -> float:
    """Return zoom-pulse intensity (0–1) decaying after nearest beat."""
    recent = [b for b in beats if b <= t]
    if not recent:
        return 0.0
    since = t - recent[-1]
    if since < 0.18:
        return BEAT_ZOOM_STR * (1.0 - since / 0.18)
    return 0.0


def apply_ken_burns(img: np.ndarray, elapsed: float, duration: float,
                    beat_pulse: float, direction: int = 1) -> np.ndarray:
    """
    Smooth Ken Burns: slow drift + beat-sync pulse.
    direction: +1 = zoom-in, -1 = zoom-out (alternates per scene).
    """
    progress = np.clip(elapsed / max(duration, 0.01), 0, 1)
    drift    = 1.0 + direction * KEN_BURNS_ZOOM * progress
    zoom     = drift + beat_pulse
    zoom     = max(zoom, 1.0)

    h, w = img.shape[:2]
    nw, nh = int(w * zoom), int(h * zoom)
    zoomed  = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)

    # Horizontal pan: drift left on zoom-in, right on zoom-out
    pan_x = int((nw - w) * progress * 0.4)
    x1    = ((nw - w) // 2) + (direction * pan_x)
    y1    = (nh - h) // 2
    x1    = np.clip(x1, 0, nw - w)
    y1    = np.clip(y1, 0, nh - h)

    return zoomed[y1:y1+h, x1:x1+w]


def add_vignette(img: np.ndarray, strength: float = 0.55) -> np.ndarray:
    """Subtle cinematic vignette."""
    h, w = img.shape[:2]
    Y, X  = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    dist   = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
    mask   = 1 - np.clip(dist * strength, 0, 1)
    mask   = mask[:, :, np.newaxis]
    return (img * mask).astype(np.uint8)


def add_film_grain(img: np.ndarray, t: float, intensity: float = 8.0) -> np.ndarray:
    """Subtle animated film grain for organic feel."""
    rng   = np.random.default_rng(int(t * FPS))
    noise = rng.integers(-int(intensity), int(intensity), img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


# ── Typography ─────────────────────────────────────────────

def load_font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def draw_lyrics(draw: ImageDraw.ImageDraw, scene: dict, t: float,
                energy: float, width: int, height: int):
    """
    Animated word-karaoke: active word glows warm amber,
    rest of line stays cool white.  Font scales with energy.
    """
    font_size  = int(62 + energy * 50)
    font       = load_font(font_size)
    shadow_fnt = load_font(font_size + 2)

    sentence  = scene["text"]
    words_obj = scene.get("words", [])

    # Which word is active right now?
    active_word = ""
    for w in words_obj:
        if w["start"] <= t <= w["end"]:
            active_word = w["word"].strip()
            break

    # ── Measure full line ──────────────────────────────────
    bbox = draw.textbbox((0, 0), sentence, font=font)
    tw   = bbox[2] - bbox[0]
    th   = bbox[3] - bbox[1]
    base_x = (width - tw) // 2
    base_y = int(height * 0.80)

    # ── Drop shadow ───────────────────────────────────────
    for dx, dy in [(3, 3), (4, 4), (-1, 3)]:
        draw.text((base_x + dx, base_y + dy), sentence,
                  fill=(0, 0, 0, 160), font=shadow_fnt)

    # ── Word-level coloring ───────────────────────────────
    # Draw the full line in white, then overdraw the active word in amber
    draw.text((base_x, base_y), sentence, fill=(235, 235, 245), font=font)

    if active_word:
        # Find active word's pixel offset within line
        before = sentence[: sentence.lower().find(active_word.lower())]
        if before is not None:
            bx = draw.textbbox((0, 0), before, font=font)
            offset_x = bx[2] - bx[0]
            ax = draw.textbbox((0, 0), active_word, font=font)
            aw = ax[2] - ax[0]

            # Warm amber glow
            for glow in [6, 4, 2]:
                draw.text(
                    (base_x + offset_x - glow // 2, base_y - glow // 2),
                    active_word,
                    fill=(255, 200, 50, max(40, 80 - glow * 10)),
                    font=font,
                )
            draw.text((base_x + offset_x, base_y), active_word,
                      fill=(255, 220, 80), font=font)


# ── Main Frame Function ────────────────────────────────────

def make_frame(t: float, scenes: list, image_paths: list) -> np.ndarray:
    """Render a single video frame at time t."""

    # Find active scene
    active_idx = 0
    for idx, scene in enumerate(scenes):
        if scene["start"] <= t < scene["end"]:
            active_idx = idx
            break
    # Clamp to last scene past the end
    if t >= scenes[-1]["start"]:
        active_idx = len(scenes) - 1

    scene     = scenes[active_idx]
    elapsed   = t - scene["start"]
    scene_dur = scene["end"] - scene["start"]
    direction = 1 if active_idx % 2 == 0 else -1   # alternate zoom direction

    beat_pulse = get_beat_pulse(t)
    metrics    = get_audio_metrics(t)
    energy     = metrics.get("energy_score", 0.15)

    # ── Background: Ken Burns on current frame ─────────────
    curr_img = get_cached_image(image_paths[active_idx])
    bg       = apply_ken_burns(curr_img, elapsed, scene_dur, beat_pulse, direction)

    # ── Crossfade with previous scene ─────────────────────
    if active_idx > 0 and elapsed < CROSSFADE_DUR:
        alpha     = elapsed / CROSSFADE_DUR          # 0 → 1
        prev_sc   = scenes[active_idx - 1]
        prev_dur  = prev_sc["end"] - prev_sc["start"]
        prev_img  = get_cached_image(image_paths[active_idx - 1])
        prev_el   = prev_dur + elapsed               # continue motion past scene end
        prev_dir  = 1 if (active_idx - 1) % 2 == 0 else -1
        prev_bg   = apply_ken_burns(prev_img, prev_el, prev_dur, beat_pulse, prev_dir)

        bg = cv2.addWeighted(prev_bg, 1.0 - alpha, bg, alpha, 0)

    # ── Post-processing ────────────────────────────────────
    bg = add_vignette(bg, strength=0.50)
    bg = add_film_grain(bg, t, intensity=6.0)

    # ── Colour grade: subtle warm push on high energy ──────
    if energy > 0.25:
        warm_amt  = min(int((energy - 0.25) * 60), 25)
        bg[:, :, 0] = np.clip(bg[:, :, 0].astype(int) + warm_amt, 0, 255)  # R
        bg[:, :, 2] = np.clip(bg[:, :, 2].astype(int) - warm_amt // 2, 0, 255)  # B

    # ── Typography overlay ─────────────────────────────────
    pil_img = Image.fromarray(bg)

    # Dark gradient band at bottom for readability
    overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
    grad_h  = int(HEIGHT * 0.28)
    for row in range(grad_h):
        alpha_val = int(140 * (1 - row / grad_h))
        overlay.paste(
            (5, 5, 10, alpha_val),
            (0, HEIGHT - grad_h + row, WIDTH, HEIGHT - grad_h + row + 1),
        )
    pil_img = Image.alpha_composite(pil_img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(pil_img, "RGBA")
    draw_lyrics(draw, scene, t, energy, WIDTH, HEIGHT)

    return np.array(pil_img)


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("═" * 60)
    print("  AI LYRIC VIDEO GENERATOR — ELEVATED EDITION")
    print("═" * 60)
    print(f"  Flags active:")
    print(f"    --skip-llama      : {'YES — reusing scene_prompts.json' if SKIP_LLAMA else 'NO  — running fresh Llama storyboard'}")
    print(f"    --use-cached-imgs : {'YES — reusing images from scene_cache/' if USE_CACHED_IMGS else 'NO  — ALL images will be sent to Fal.ai'}")
    print("═" * 60 + "\n")

    # Step 1: Storyboard
    scenes = build_scene_prompts()
    print(f"\n📋 Total scenes: {len(scenes)}")

    # Step 2: Images
    image_paths = fetch_all_images(scenes)

    # Pre-load all images into RAM for fast rendering
    print("\n📦 Pre-loading images into RAM …")
    for p in image_paths:
        get_cached_image(p)

    # Step 3: Render
    print(f"\n🎬 Rendering {TOTAL_DURATION:.1f}s video at {FPS} fps …")
    frame_fn = lambda t: make_frame(t, scenes, image_paths)
    video    = VideoClip(frame_fn, duration=TOTAL_DURATION)
    video    = video.set_audio(audio_clip)

    video.write_videofile(
        OUTPUT_PATH,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        audio_bitrate="320k",
        threads=os.cpu_count() or 4,
        preset="slow",           # slow = better quality, still fast enough
        ffmpeg_params=["-crf", "18"],   # near-lossless quality
    )

    print(f"\n✨ Done!  →  {OUTPUT_PATH}")
    print(f"   Scenes: {len(scenes)} | Duration: {TOTAL_DURATION:.1f}s | FPS: {FPS}")