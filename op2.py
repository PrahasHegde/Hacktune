"""
╔═══════════════════════════════════════════════════════════════════╗
║      AI LYRIC VIDEO GENERATOR  —  THEME-LOCKED EDITION           ║
║  Consistent abstract art • Story-driven • No random imagery       ║
╚═══════════════════════════════════════════════════════════════════╝

KEY FIX: Every Flux prompt is built from 4 locked layers:
  [STYLE ANCHOR] + [WORLD ANCHOR] + [PALETTE ANCHOR] + [SCENE BODY]
  
  The first 3 layers are identical across all 24 images — Flux cannot
  escape into random fire/generic imagery because the style, world, and
  palette are hard-stamped at the FRONT of every prompt.

USAGE:
  python lyric_video_gen.py                    # full run
  python lyric_video_gen.py --skip-llama       # reuse scene_prompts.json, fresh images
  python lyric_video_gen.py --use-cached-imgs  # render only, zero API calls
"""

import bisect
import json
import os
import re
import sys
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
import subprocess



# ── CLI flags ─────────────────────────────────────────────────────────────────
SKIP_LLAMA      = "--skip-llama"      in sys.argv
USE_CACHED_IMGS = "--use-cached-imgs" in sys.argv

# ═════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═════════════════════════════════════════════════════════════════
os.environ["FAL_KEY"] = "5c90f577-c8e2-4c1b-b110-ba476f731f00:2f23f9c6b5911fb5f527798f76f43e01"

JSON_PATH         = r"lyric_video_songs_and_data\song_667784.json"
AUDIO_PATH        = r"lyric_video_songs_and_data\song_667784.mp3"
OUTPUT_PATH       = "new_video.mp4"
CACHE_DIR         = Path("scene_cache")
FONT_PATH         = "Arial.ttf"
SCENE_PROMPT_FILE = "scene_prompts.json"

WIDTH, HEIGHT    = 1920, 1080
FPS              = 24
LLAMA_MODEL      = "llama3"
FAL_MODEL        = "fal-ai/flux/schnell"
PARALLEL_IMAGES  = 8
TARGET_SCENES    = 24
CROSSFADE_DUR    = 0.8
BEAT_ZOOM_STR    = 0.045
KEN_BURNS_ZOOM   = 0.07
FLUX_STEPS       = 4

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

def _make_vignette_mask(h, w, strength=0.46):
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt(((X - w/2)/(w/2))**2 + ((Y - h/2)/(h/2))**2)
    return (1.0 - np.clip(dist * strength, 0.0, 1.0)).astype(np.float32)[:, :, np.newaxis]

VIGNETTE_MASK = _make_vignette_mask(HEIGHT, WIDTH)

def _make_gradient_band(h, w, band_h):
    band = np.zeros((band_h, w, 4), dtype=np.uint8)
    for row in range(band_h):
        a = int(160 * (1.0 - row / band_h) ** 1.5)
        band[row, :] = [3, 3, 8, a]
    canvas = np.zeros((h, w, 4), dtype=np.uint8)
    canvas[h - band_h:] = band
    return canvas

GRADIENT_PIL  = Image.fromarray(_make_gradient_band(HEIGHT, WIDTH, int(HEIGHT * 0.30)), mode="RGBA")

_FONT_CACHE: dict = {}
def load_font(size):
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype(FONT_PATH, size)
        except OSError:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]

_SCENE_STARTS: list = []


# ═════════════════════════════════════════════════════════════════
#  STEP 1 — LLAMA: BUILD LOCKED ANCHORS + SCENE PROMPTS
# ═════════════════════════════════════════════════════════════════

def build_scene_prompts() -> list:

    # 1. DEFINE A STABLE ART STYLE (Stays the same)
    # Locked Artistic DNA
    ART_STYLE = "ethereal abstract expressionist oil painting, thick impasto brushstrokes, translucent glazes, museum-grade aesthetic"
    WORLD_ENV = "a dreamlike landscape of shifting forms, soft mist, and ethereal light beams"

    if SKIP_LLAMA and os.path.exists(SCENE_PROMPT_FILE):
        print("📂 --skip-llama: loading cached scene_prompts.json …")
        with open(SCENE_PROMPT_FILE) as f:
            return json.load(f)

    if os.path.exists(SCENE_PROMPT_FILE):
        os.remove(SCENE_PROMPT_FILE)

    full_lyrics = "\n".join(s["text"] for s in lyrics_timeline)

    # ── PASS 1A: Extract the song's core story and meaning ───────────────
    print("🦙 Pass 1A — Understanding the song …")

    story_prompt = f"""
Read these song lyrics carefully and answer in plain prose:

LYRICS:
{full_lyrics}

Answer these questions in 2–3 sentences each:
1. THEME: What is this song fundamentally about? What is the core emotion or message?
2. JOURNEY: How does the emotion change from start to end? What is the turning point?
3. IMAGERY: What natural or abstract imagery does the lyric language suggest? 
   (e.g. water and drowning, empty rooms, tangled threads, crumbling walls)
   Be specific to THIS song's actual words. Do NOT invent generic symbols.
4. MOOD: Describe the overall visual mood in 5 adjectives.

Output only your answers. Label each section: THEME / JOURNEY / IMAGERY / MOOD.
"""
    r = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": story_prompt}])
    song_analysis = r["message"]["content"].strip()
    print(f"\n🎵 Song Analysis:\n{song_analysis}\n{'─'*60}\n")

    # ── PASS 1B: Design the locked visual world ────────────────────────────
    print("🦙 Pass 1B — Designing locked visual world …")

    world_prompt = f"""
You are designing the complete visual world for a {TARGET_SCENES}-frame abstract art music video.

SONG ANALYSIS:
{song_analysis}

FULL LYRICS:
{full_lyrics}

Design a VISUAL WORLD that will be used for EVERY single frame of this video.
The world must:
- Be directly inspired by THIS song's actual themes and imagery
- Have a single consistent environment/setting that all scenes take place in
- Use abstract art (NOT photorealistic, NOT generic stock imagery)
- Never use generic symbols like fire, hearts, stars unless directly in the lyrics

Output EXACTLY these 5 labelled sections. Be specific and concrete:

STYLE_ANCHOR:
One sentence describing the exact art style (e.g. "Japanese sumi-e ink wash painting 
with sparse brushstrokes on aged paper, heavy negative space, ink bleeding into mist").
This is pasted into every Flux prompt. Make it a strong visual style keyword string.

WORLD_ANCHOR:
One sentence describing the single recurring environment all scenes exist within
(e.g. "a vast flooded salt flat at dusk reflecting a bruised purple sky, 
shallow water barely covering cracked earth, horizon dissolving into haze").
This is pasted into every Flux prompt. Specific, painterly, atmospheric.

PALETTE_ANCHOR:
Name exactly 5 colours as a comma-separated list with hex codes
(e.g. "deep indigo #1A1040, dusty rose #C4846B, pale ivory #F2EDE4, 
slate grey #7A8591, muted gold #B8960C").
These are the ONLY colours in every image. List them as a prompt-ready string.

CHARACTER_ANCHOR:
If the song has a clear human protagonist, describe them in one sentence with:
gender, approximate age, skin tone, hair, and exact clothing.
Write "NONE — pure environmental abstract storytelling" if no character needed.

BANNED_ELEMENTS:
List 8–10 specific visual elements that must NEVER appear because they are
generic/unrelated to this specific song (e.g. "fire, flames, explosions, hearts,
roses, stars, generic cityscapes, random animals").
These go into the negative prompt for every image.

Output only these 5 labelled sections. No extra text.
"""
    r = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": world_prompt}])
    world_design = r["message"]["content"].strip()
    print(f"\n🌍 Visual World:\n{world_design}\n{'─'*60}\n")

    # Parse the 5 anchors from Llama's output
    def extract_section(text, label):
        pattern = rf"{label}:\s*\n?(.*?)(?=\n[A-Z_]{{3,}}:|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    STYLE_ANCHOR     = extract_section(world_design, "STYLE_ANCHOR")
    WORLD_ANCHOR     = extract_section(world_design, "WORLD_ANCHOR")
    PALETTE_ANCHOR   = extract_section(world_design, "PALETTE_ANCHOR")
    CHARACTER_ANCHOR = extract_section(world_design, "CHARACTER_ANCHOR")
    BANNED_ELEMENTS  = extract_section(world_design, "BANNED_ELEMENTS")

    # Fallback if parsing fails
    if not STYLE_ANCHOR:
        STYLE_ANCHOR = "abstract fine-art illustration, painterly, non-photographic"
    if not WORLD_ANCHOR:
        WORLD_ANCHOR = "atmospheric painterly landscape"
    if not PALETTE_ANCHOR:
        PALETTE_ANCHOR = "deep blue, muted gold, soft grey, ivory, dark charcoal"
    if not BANNED_ELEMENTS:
        BANNED_ELEMENTS = "fire, flames, hearts, stars, generic symbols"

    has_character = "NONE" not in CHARACTER_ANCHOR.upper() and CHARACTER_ANCHOR.strip()

    print(f"🎨 STYLE  : {STYLE_ANCHOR[:80]} …")
    print(f"🌍 WORLD  : {WORLD_ANCHOR[:80]} …")
    print(f"🎨 PALETTE: {PALETTE_ANCHOR[:80]} …")
    print(f"👤 CHAR   : {CHARACTER_ANCHOR[:60]} …")
    print(f"🚫 BANNED : {BANNED_ELEMENTS[:80]} …\n")

    # ── Build the 3-part LOCKED PREFIX stamped into every Flux prompt ─────
    # This is the key fix: Flux sees the same style+world+palette at the
    # FRONT of every prompt. It cannot drift because the anchor is immovable.
    LOCKED_PREFIX = (
        "Art style: ethereal abstract expressionist oil painting, "
        "thick impasto brushstrokes, translucent glazes, museum-quality. "
        "Setting: a dreamlike landscape of shifting forms, mist, and light. "
    )

    LOCKED_SUFFIX = (
        " cinematic 16:9 composition, dramatic lighting, emotionally evocative, "
        "expressive texture, depth and scale."
    )

    # REVISED NEGATIVE PROMPT: Explicitly ban bars and geometric tiling
    NEGATIVE_PROMPT = (
        "photorealistic, 3d render, low quality, blurry, text, watermark, "
        "low resolution, messy, generic bars, geometric tiling, bright cartoon, "
        "basic clipart, symmetric, faces, low fidelity, distorted."
    )

    # ── Expand lyrics → TARGET_SCENES ────────────────────────────────────
    expanded = []
    repeats  = max(1, round(TARGET_SCENES / len(lyrics_timeline)))
    for slide in lyrics_timeline:
        dur     = slide["end"] - slide["start"]
        seg_dur = dur / repeats
        for k in range(repeats):
            expanded.append({
                "start":   slide["start"] + k * seg_dur,
                "end":     slide["start"] + (k + 1) * seg_dur,
                "text":    slide["text"],
                "words":   slide.get("words", []),
                "sub_idx": k,
            })

    # ── PASS 2: ONE batched call — scene bodies only ──────────────────────
    # Each scene body is SHORT (30–40 words) because the locked prefix/suffix
    # already provide 60% of the prompt. Shorter bodies = less chance to drift.
    print(f"🦙 Pass 2 — Generating {len(expanded)} scene bodies in ONE batch call …")

    scene_manifest = []
    for i, slide in enumerate(expanded):
        mid_t    = (slide["start"] + slide["end"]) / 2
        metrics  = get_audio_metrics(mid_t)
        energy   = metrics.get("energy_score", 0.15)
        pct      = int((i / len(expanded)) * 100)
        e_label  = "HIGH" if energy > 0.28 else ("LOW" if energy < 0.18 else "MID")
        arc      = ("opening/raw" if pct < 25 else
                    "building/tension" if pct < 50 else
                    "peak/climax" if pct < 75 else "resolving/closing")
        next_txt = expanded[i+1]["text"] if i+1 < len(expanded) else "(song ends)"
        scene_manifest.append(
            f'{i+1}. [energy:{e_label}|arc:{arc}] "{slide["text"]}" → "{next_txt}"'
        )

    manifest_text = "\n".join(scene_manifest)

    char_instruction = (
        f"If this scene includes a human, they must match exactly: {CHARACTER_ANCHOR}"
        if has_character else
        "No human characters — use only environment, light, abstract forms, and symbolic objects."
    )

    batch_prompt = f"""
You are writing the SCENE BODY for {len(expanded)} frames of an abstract art music video.

THE VISUAL WORLD IS ALREADY ESTABLISHED AND LOCKED:
- Art style: {STYLE_ANCHOR}
- Setting: {WORLD_ANCHOR}
- Palette: {PALETTE_ANCHOR}
- {char_instruction}

SONG ANALYSIS:
{song_analysis}

SCENE MANIFEST (energy level and arc position for each scene):
{manifest_text}

YOUR TASK:
Write exactly {len(expanded)} scene body descriptions, one per scene.
Return ONLY a valid JSON array of strings.
Format: ["scene 1 body", "scene 2 body", ...]

Rules for each scene body (30–45 words ONLY):
1. MEANING — translate THIS lyric's emotional meaning into a specific visual
   moment within the established world. What is happening in the scene?
   What light, texture, form, or movement communicates the emotion?
2. SPECIFIC — describe exactly what fills the frame. No vague words like
   "beautiful", "mysterious", "emotional". Name specific visual elements.
3. STORY — scenes must flow. Each scene should feel like the next moment
   after the previous one. The world EVOLVES, it never restarts randomly.
4. ENERGY — HIGH energy: dense composition, strong contrast, dynamic forms.
   LOW energy: sparse, wide, still, negative space dominant.
5. DO NOT mention: the art style, the setting, the palette — those are
   already in the prefix. Just describe WHAT IS IN THE SCENE.
6. DO NOT use generic imagery. No fire unless lyrics mention it.
   No hearts, no stars. Only imagery directly tied to THIS song's meaning.
7. OUTPUT — raw scene body text only inside JSON strings. No labels, no
   numbering, no meta-commentary.

Output ONLY the JSON array. Start with [ and end with ].
"""

    r2 = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": batch_prompt}])
    raw_response = r2["message"]["content"].strip()

    # Robust JSON extraction
    json_str = raw_response
    # Strip markdown fences
    if "```" in json_str:
        parts = json_str.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            if part.startswith("["):
                json_str = part
                break

    # Find the JSON array boundaries
    start = json_str.find("[")
    end   = json_str.rfind("]")
    if start != -1 and end != -1:
        json_str = json_str[start:end+1]

    try:
        raw_bodies = json.loads(json_str)
        if not isinstance(raw_bodies, list):
            raise ValueError("not a list")
        print(f"✅ Batch parse OK — {len(raw_bodies)} scene bodies")
    except Exception as e:
        print(f"⚠️  JSON parse failed ({e}) — extracting line by line …")
        raw_bodies = []
        for line in raw_response.split("\n"):
            line = line.strip().strip(",").strip('"').strip("'")
            if 15 < len(line) < 300:
                raw_bodies.append(line)
        print(f"   Recovered {len(raw_bodies)} bodies via fallback")

    # Pad/trim
    while len(raw_bodies) < len(expanded):
        raw_bodies.append(raw_bodies[-1] if raw_bodies else "abstract forms shift in the established world")
    raw_bodies = raw_bodies[:len(expanded)]

    # ── Assemble final scene objects ──────────────────────────────────────
    scene_prompts = []
    for i, slide in enumerate(expanded):
        # THE KEY FIX: LOCKED_PREFIX + scene body + LOCKED_SUFFIX
        # Flux sees the same style/world/palette anchor in every single image
        for i, slide in enumerate(expanded):
        # By separating the "Style" (Locked) from the "Moment" (Lyrics), 
        # Flux will change the content while keeping the brushwork identical.
            full_prompt = (
                f"{LOCKED_PREFIX} "
                f"SUBJECT: A visual representation of the lyric: '{slide['text']}'. "
                f"ACTION: {raw_bodies[i]}. "
                "Cinematic composition, emotional depth, expressive texture."
            )

        scene_prompts.append({
            "start":    slide["start"],
            "end":      slide["end"],
            "text":     slide["text"],
            "words":    slide["words"],
            "prompt":   full_prompt,
            "negative": NEGATIVE_PROMPT,
            "body":     raw_bodies[i],   # stored for debugging
        })
        print(f"  ✅ {i+1:02d}/{len(expanded)}  \"{slide['text'][:45].strip()}\" …")
        print(f"       → {raw_bodies[i][:70]} …")

    with open(SCENE_PROMPT_FILE, "w", encoding="utf-8") as f:
        json.dump(scene_prompts, f, indent=2, ensure_ascii=False)

    # Also save a human-readable prompt review file
    review_path = "prompt_review.txt"
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(f"LOCKED PREFIX:\n{LOCKED_PREFIX}\n\n")
        f.write(f"LOCKED SUFFIX:\n{LOCKED_SUFFIX}\n\n")
        f.write(f"NEGATIVE PROMPT:\n{NEGATIVE_PROMPT}\n\n")
        f.write("─" * 60 + "\n\n")
        for i, sp in enumerate(scene_prompts):
            f.write(f"SCENE {i+1:02d}: \"{sp['text']}\"\n")
            f.write(f"FULL PROMPT:\n{sp['prompt']}\n\n")

    print(f"\n💾 {len(scene_prompts)} scenes saved → {SCENE_PROMPT_FILE}")
    print(f"📄 Full prompts saved for review → {review_path}")
    return scene_prompts


# ═════════════════════════════════════════════════════════════════
#  STEP 2 — FAL.AI: PARALLEL IMAGE GENERATION
# ═════════════════════════════════════════════════════════════════

def generate_single_image(args: tuple) -> str:
    i, scene = args
    img_path = CACHE_DIR / f"scene_{i:03d}.png"

    if USE_CACHED_IMGS and img_path.exists():
        return str(img_path)

    print(f" 🚀 Generating Scene {i:03d}...")
    
    try:
        # FIX: Force landscape_16_9 preset. 
        # Manual width/height (1920, 1080) can confuse the model into 
        # tiling imagery. This preset forces the model to layout the scene.
        result = fal_client.subscribe(
            FAL_MODEL,
            arguments={
                "prompt": scene["prompt"],
                "negative_prompt": "alley, brick walls, photorealistic, identical, repetitive, watermark, text, low quality, 3d render, cgi",
                "image_size": "landscape_16_9", 
                "num_inference_steps": 8, 
                "guidance_scale": 4.5,
            },
        )
        url = result["images"][0]["url"]
        urllib.request.urlretrieve(url, str(img_path))
        return str(img_path)
    except Exception as e:
        print(f" ❌ Error on scene {i}: {e}")
        return None

    img = Image.new("RGB", (1024, 576), (18, 8, 8))
    ImageDraw.Draw(img).text((16, 270), f"Scene {i:03d} failed", fill=(160, 50, 50))
    img.save(str(img_path))
    return str(img_path)


def fetch_all_images(scenes: list) -> list:
    mode = "CACHED" if USE_CACHED_IMGS else f"FAL.AI — {FAL_MODEL} ({FLUX_STEPS} steps, {PARALLEL_IMAGES} workers)"
    print(f"\n{'═'*65}")
    print(f"  {mode}")
    print(f"  Scenes: {len(scenes)}")
    print(f"{'═'*65}\n")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_IMAGES) as pool:
        paths = list(pool.map(generate_single_image, enumerate(scenes)))

    ok = sum(1 for p in paths if Path(p).stat().st_size > 5_000)
    print(f"\n✅ {ok}/{len(scenes)} images ready.")
    return paths


# ═════════════════════════════════════════════════════════════════
#  STEP 3 — CINEMATIC COMPOSITOR
# ═════════════════════════════════════════════════════════════════

IMAGE_CACHE: dict = {}


def get_cached_image(path: str) -> np.ndarray:
    if path not in IMAGE_CACHE:
        img = cv2.imread(path)
        if img is None:
            img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        IMAGE_CACHE[path] = cv2.resize(img, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
    return IMAGE_CACHE[path]


def get_beat_pulse(t: float) -> float:
    idx = bisect.bisect_right(beats, t) - 1
    if idx < 0:
        return 0.0
    since = t - beats[idx]
    if since < 0.20:
        return BEAT_ZOOM_STR * (1.0 - since / 0.20)
    return 0.0


def apply_ken_burns(img, elapsed, duration, beat_pulse, direction):
    progress = float(np.clip(elapsed / max(duration, 0.01), 0.0, 1.0))
    zoom     = float(max(1.0 + direction * KEN_BURNS_ZOOM * progress + beat_pulse, 1.001))
    h, w     = img.shape[:2]
    nw, nh   = int(w * zoom), int(h * zoom)
    zoomed   = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pan_x    = int((nw - w) * progress * 0.30)
    x1       = int(np.clip(((nw - w) // 2) + direction * pan_x, 0, nw - w))
    y1       = int(np.clip((nh - h) // 2, 0, nh - h))
    return zoomed[y1:y1+h, x1:x1+w]


def apply_colour_grade(img, energy):
    img = img.copy().astype(np.int32)
    if energy > 0.25:
        amt          = min(int((energy - 0.25) * 60), 24)
        img[:, :, 0] = np.clip(img[:, :, 0] + amt,      0, 255)
        img[:, :, 2] = np.clip(img[:, :, 2] - amt // 2, 0, 255)
    elif energy < 0.15:
        grey = img.mean(axis=2, keepdims=True)
        img  = np.clip(img * 0.78 + grey * 0.22 + np.array([0, 3, 12]), 0, 255)
    return img.astype(np.uint8)


def draw_lyrics(draw, scene, t, energy, width, height):
    font_size = int(58 + energy * 46)
    font      = load_font(font_size)
    sentence  = scene["text"]
    words_obj = scene.get("words", [])

    active_word = ""
    for w in words_obj:
        if w["start"] <= t <= w["end"]:
            active_word = w["word"].strip()
            break

    bbox = draw.textbbox((0, 0), sentence, font=font)
    tw   = bbox[2] - bbox[0]
    bx   = (width - tw) // 2
    by   = int(height * 0.815)

    for dx, dy, alpha in [(4, 4, 190), (2, 2, 110), (-1, 2, 60)]:
        draw.text((bx + dx, by + dy), sentence, fill=(0, 0, 0, alpha), font=font)
    draw.text((bx, by), sentence, fill=(230, 230, 245), font=font)

    if active_word:
        pos = sentence.lower().find(active_word.lower())
        if pos >= 0:
            pre_bbox = draw.textbbox((0, 0), sentence[:pos], font=font)
            word_x   = bx + (pre_bbox[2] - pre_bbox[0])
            for radius, a in [(8, 28), (5, 52), (3, 85)]:
                draw.text((word_x - radius//2, by - radius//2),
                          active_word, fill=(255, 195, 40, a), font=font)
            draw.text((word_x, by), active_word, fill=(255, 222, 75), font=font)


def find_active_scene(t):
    idx = bisect.bisect_right(_SCENE_STARTS, t) - 1
    return max(0, idx)


def make_frame(t, scenes, image_paths):
    # Ensure the global list is used to find the active scene index
    # We map time 't' to the correct scene index
    idx = bisect.bisect_right(_SCENE_STARTS, t) - 1
    active_idx = max(0, min(idx, len(scenes) - 1))
    
    scene = scenes[active_idx]
    
    # Calculate progression within this specific scene
    elapsed = t - scene["start"]
    scene_dur = max(scene["end"] - scene["start"], 0.1)
    direction = 1 if active_idx % 2 == 0 else -1

    # Load and process the current image
    curr_img = get_cached_image(image_paths[active_idx])
    bg = apply_ken_burns(curr_img, elapsed, scene_dur, get_beat_pulse(t), direction)

    # Transition logic (Sigmoid easing)
    if active_idx > 0 and elapsed < CROSSFADE_DUR:
        x = (elapsed / CROSSFADE_DUR) * 10 - 5
        alpha = 1 / (1 + np.exp(-x))
        
        prev_img = get_cached_image(image_paths[active_idx - 1])
        prev_dir = 1 if (active_idx - 1) % 2 == 0 else -1
        prev_bg = apply_ken_burns(prev_img, (scenes[active_idx-1]["end"] - scenes[active_idx-1]["start"]) + elapsed, 
                                  max(scenes[active_idx-1]["end"] - scenes[active_idx-1]["start"], 0.1), 
                                  get_beat_pulse(t), prev_dir)
        bg = cv2.addWeighted(prev_bg, 1.0 - alpha, bg, alpha, 0)

    # Apply aesthetics
    energy = get_audio_metrics(t).get("energy_score", 0.15)
    bg = apply_colour_grade(bg, energy)
    bg = (bg.astype(np.float32) * VIGNETTE_MASK).clip(0, 255).astype(np.uint8)

    # Noise for high energy
    if energy > 0.20:
        rng = np.random.default_rng(int(t * FPS))
        noise = rng.integers(-4, 4, bg.shape, dtype=np.int16)
        bg = np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    pil = Image.fromarray(bg).convert("RGBA")
    pil.alpha_composite(GRADIENT_PIL)
    pil = pil.convert("RGB")

    draw = ImageDraw.Draw(pil, "RGBA")
    draw_lyrics(draw, scene, t, energy, WIDTH, HEIGHT)

    return np.array(pil)


def run_manim_overlay():
    print("🎬 Rendering Typography Layer via Manim...")
    
    # Create a copy of current environment variables
    env = os.environ.copy()
    # Force Manim to use the correct song file
    env["HACKATUNE_SONG"] = os.path.abspath(JSON_PATH) 
    
    cmd = [
        "manim", "-ql", "--transparent", 
        "song_poster_scene.py", "SongPoster"
    ]
    # Pass the custom environment to the subprocess
    subprocess.run(cmd, env=env, check=True)
    return "media/videos/song_poster_scene/480p15/SongPoster.webm"

# ═════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # 0. SETUP ENVIRONMENT
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    print("═" * 65)
    print(" 🚀 HACKATUNE: INTEGRATED ART + TYPOGRAPHY PIPELINE")
    print("═" * 65)

    try:
        from moviepy.editor import VideoFileClip, CompositeVideoClip
    except ImportError:
        print("❌ Error: 'moviepy' not found. Run 'pip install moviepy'.")
        sys.exit(1)

    t0 = time.time()

    # 1. GENERATE BACKGROUND ART (The "World" Layer)
    scenes = build_scene_prompts()
    image_paths = fetch_all_images(scenes)
    
    print("\n📦 Pre-loading background assets …")
    for p in image_paths:
        get_cached_image(p)

    print(f"\n🎬 Rendering Background Video ({TOTAL_DURATION:.1f}s) …")
    base_video_clip = VideoClip(lambda t: make_frame(t, scenes, image_paths), duration=TOTAL_DURATION)
    base_video_clip = base_video_clip.set_audio(audio_clip)
    base_video_clip.write_videofile(
        OUTPUT_PATH, fps=FPS, codec="libx264", audio_codec="aac",
        bitrate="6000k", threads=os.cpu_count(), preset="faster"
    )

    # 2. GENERATE TYPOGRAPHY OVERLAY (Manim Layer)
    print("\n🎨 Generating Procedural Typography Overlay …")
    typo_path = None
    try:
        # Use subprocess to call manim. Ensure manim is in your PATH.
        subprocess.run([
            "manim", "-ql", "--transparent", 
            "song_poster_scene.py", "SongPoster"
        ], check=True)
        # Note: Manim output paths vary by version/OS. Adjust this path to match your render output.
        typo_path = r"media/videos/song_poster_scene/480p15/SongPoster.mov"
    except Exception as e:
        print(f"⚠️ Manim rendering skipped or failed: {e}")

    # 3. COMPOSITE EVERYTHING
    if typo_path and os.path.exists(typo_path):
        print("\n✨ Composing Final Masterpiece …")
        base_video = VideoFileClip(OUTPUT_PATH)
        
        # 'has_mask=True' is good, but for .mov with alpha, we might need a direct mask
        typo_video = VideoFileClip(typo_path, has_mask=True)
        
        # Ensure duration sync
        typo_video = typo_video.set_duration(min(base_video.duration, typo_video.duration))
        
        # Composite
        final = CompositeVideoClip([base_video, typo_video])
        final.write_videofile("FINAL_SONG_PRODUCTION.mp4", codec="libx264", audio_codec="aac")
        print("\n✅ Final production complete: FINAL_SONG_PRODUCTION.mp4")
    else:
        print("\n✅ Background production complete (no overlay):", OUTPUT_PATH)

    print(f"\n⏱️ Total pipeline time: {(time.time() - t0)/60:.1f} minutes.")