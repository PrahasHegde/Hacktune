#sucessfully got animated images but shit images

import json
import os
import urllib.request
import numpy as np
import cv2
import ollama
import fal_client
from moviepy.editor import AudioFileClip, VideoClip
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
os.environ["FAL_KEY"] = "5c90f577-c8e2-4c1b-b110-ba476f731f00:2f23f9c6b5911fb5f527798f76f43e01"
JSON_PATH = r"lyric_video_songs_and_data\song_666407.json"
AUDIO_PATH = r"lyric_video_songs_and_data\song_666407.mp3"
OUTPUT_PATH = "output_storyboard_video.mp4"
FONT_PATH = "Arial.ttf"
WIDTH, HEIGHT = 1920, 1080
FPS = 24
LLAMA_MODEL = "llama3" # Change to your preferred local model
CROSSFADE_DURATION = 0.8 # seconds of overlap between frames for elegance

# Load Synced Data
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

lyrics_timeline = data["lyrics_json"]
audio_analysis = data["audio_analysis"]
intensity_data = audio_analysis["intensity_sections"]["data"]
beats = [b / 1000.0 for b in audio_analysis["beat_data"]["beat_positions"]]

audio_clip = AudioFileClip(AUDIO_PATH)
TOTAL_DURATION = audio_clip.duration


def get_audio_metrics(t):
    """Helper to fetch continuous audio metrics at a specific timestamp."""
    idx = int(t * 10)
    if idx < len(intensity_data):
        return intensity_data[idx]
    return {"energy_score": 0.15, "percussiveness": 0.1}

# --- STEP 1: LOCAL LLAMA CONTEXT & STORYBOARD INFERENCE ---

def get_global_and_scene_prompts():
    print("🦙 Pass 1: Feeding entire lyric sheet to local Llama for global context...")
    
    # Reconstruct full lyrics for context
    full_lyrics_text = "\n".join([slide["text"] for slide in lyrics_timeline])
    
    context_prompt = f"""
You are an award-winning animated music video director.
Your task is NOT to describe images.
Your task is to design ONE COMPLETE music video.

Study the complete lyrics below together with the implied emotional journey.
Determine:
1. The emotional progression of the song from beginning to end.
2. How the energy changes throughout the song (e.g., calm, aggressive, reflective).
3. Design ONE coherent visual story that follows those emotional changes. The visuals must continuously evolve instead of restarting every lyric.
4. Choose ONE recurring setting (e.g., quiet town, floating islands, rainy city, sketch notebook). Do NOT change settings randomly.
5. Design ONE recurring main character. The character must remain visually identical throughout every scene. 
   Use: sketch-like appearance, hand drawn outlines, simple proportions, expressive body language, minimal facial features, clean silhouette. Do NOT describe photorealism.
6. Choose 3-6 recurring visual motifs (e.g., paper birds, rain, light particles, leaves). They should appear naturally throughout the video.
7. Describe the animation style. The figures should look: simple, sketchy, lightly colored, hand drawn, artsy, and cartoonish. Avoid AI-art appearance, hyperrealism, CGI, detailed faces, and complex textures.
8. Describe camera language (cinematic movement like slow dolly, tracking, wide establishing shots).
9. Explain how scene transitions should naturally connect. Every scene should feel like the previous scene continued.
10. Explain how the visuals should react to the music. Low energy = slower camera, wider framing. High energy = dynamic composition.

Lyrics:
{full_lyrics_text}

Return ONE concise style guide that future prompts can reuse.
Do not use bullet points. Do not output anything except the style guide.
"""
    
    response = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": context_prompt}])
    global_style_guide = response["message"]["content"].strip()
    print(f"\n🎨 Llama Established Style Guide:\n{global_style_guide}\n")
    
    print("🦙 Pass 2: Generating stateful, connected image prompts for each lyric scene...")
    scene_prompts = []
    previous_prompt = "None. This is the opening shot. Introduce the recurring main character and setting in a wide shot."
    
    for idx, slide in enumerate(lyrics_timeline):
        scene_text = slide["text"]
        
        # Calculate Anticipation and Intensity data for the AI Director
        next_text = lyrics_timeline[idx+1]["text"] if idx + 1 < len(lyrics_timeline) else "Fading out. End of song."
        mid_time = (slide["start"] + slide["end"]) / 2
        metrics = get_audio_metrics(mid_time)
        energy_score = metrics.get("energy_score", 0.15)
        energy_state = "HIGH/Intense" if energy_score > 0.28 else ("LOW/Calm" if energy_score < 0.18 else "MEDIUM/Building")

        director_prompt = f"""
You are storyboarding a single connected shot of a highly stylized 2D animated music video.

Global Style Guide:
{global_style_guide}

Previous Shot (CONTINUE SEAMLESSLY FROM THIS):
{previous_prompt}

Current Lyrics: "{scene_text}"
Upcoming Lyrics: "{next_text}"
Current Musical Energy: {energy_state} (Score: {energy_score:.2f})

Task:
Read the Current Lyrics and identify the deep meaning (literal or metaphorical). Translate that meaning into ONE image prompt representing the NEXT SHOT of this connected story.

Requirements:
- The same character must continue from the previous scene in a logical way. Do NOT jump to random close-ups of faces.
- The environment must evolve naturally. Never restart the story.
- The camera should continue moving from previous shots.
- The visual tone must be artsy, cartoonish, and match BOTH the global style guide and the {energy_state} musical energy.
- Characters must remain: simple, sketchy, hand drawn, minimal facial features. Avoid photorealism and 3D completely.
- Describe exactly what the camera sees. Do not explain your thought process.

Output only the raw image prompt under 80 words. No conversational text.
"""
        
        scene_resp = ollama.chat(model=LLAMA_MODEL, messages=[{"role": "user", "content": director_prompt}])
        clean_prompt = scene_resp["message"]["content"].strip().replace('"', '')
        
        # Save this prompt to feed into the next loop iteration (Stateful Memory)
        previous_prompt = clean_prompt
        
        # ENFORCING STRICT ART STYLE FOR FLUX:
        # Prepending and appending heavy stylistic anchors so Flux cannot drift into photorealism
        final_prompt = f"Highly stylized 2D animated cartoon art style, hand-drawn sketch style, flat flat colors, clean outlines. {clean_prompt}. Artsy masterpiece, consistent character design, continuous narrative frame, no photorealism, no CGI, 8k resolution"
        
        scene_prompts.append({
            "start": slide["start"],
            "end": slide["end"],
            "text": scene_text,
            "words": slide.get("words", []),
            "prompt": final_prompt
        })
        print(f"🎬 Scene {idx+1}/{len(lyrics_timeline)} Prompt Ready.")
        
    return scene_prompts

# --- STEP 2: GENERATE STATIC IMAGES VIA FAL.AI (FLUX) ---

def fetch_ai_keyframes(scenes):
    print("\n🎨 Contacting Fal.ai to generate master storyboard frames...")
    image_paths = []
    
    for i, scene in enumerate(scenes):
        img_filename = f"scene_{i}.png"
        
        if not os.path.exists(img_filename):
            print(f"   ⚡ Generating image {i+1}/{len(scenes)} via Flux...")
            try:
                result = fal_client.subscribe(
                    "fal-ai/flux/dev", # Updated to flux/dev for highest quality
                    arguments={
                        "prompt": scene["prompt"],
                        "width": 1024,
                        "height": 576, # 16:9 aspect ratio
                    }
                )
                img_url = result["images"][0]["url"]
                urllib.request.urlretrieve(img_url, img_filename)
            except Exception as e:
                print(f"   ❌ Error generating scene {i}: {e}")
                img = Image.new("RGB", (WIDTH, HEIGHT), (20, 20, 25))
                img.save(img_filename)
        else:
            print(f"   ⏭️ Using existing cached image for scene {i+1}")
            
        image_paths.append(img_filename)
    return image_paths

# Execute Llama Storyboard and Flux Generation
processed_scenes = get_global_and_scene_prompts()
scene_images = fetch_ai_keyframes(processed_scenes)


# --- STEP 3: ADVANCED INTERPOLATION COMPOSITOR ---

# In-memory image cache for fast frame-by-frame rendering
IMAGE_CACHE = {}
def get_cached_image(path):
    if path not in IMAGE_CACHE:
        img = cv2.imread(path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        IMAGE_CACHE[path] = cv2.resize(img, (WIDTH, HEIGHT))
    return IMAGE_CACHE[path]

def get_beat_zoom(t):
    recent_beats = [b for b in beats if b <= t]
    if not recent_beats:
        return 1.0
    time_since_beat = t - recent_beats[-1]
    if time_since_beat < 0.15:
        decay = 1.0 - (time_since_beat / 0.15)
        return 0.04 * decay 
    return 0.0

def process_ken_burns(img, elapsed_time, duration, beat_zoom):
    """Applies smooth zoom interpolation to a single image frame."""
    progress = elapsed_time / max(duration, 0.1)
    base_zoom = 1.0 + (0.07 * progress) # Continuous 7% slow zoom
    total_zoom = base_zoom + beat_zoom
    
    h, w = img.shape[:2]
    nw, nh = int(w * total_zoom), int(h * total_zoom)
    zoomed = cv2.resize(img, (nw, nh))
    x1, y1 = (nw - w) // 2, (nh - h) // 2
    return zoomed[y1:y1+h, x1:x1+w]

def make_final_frame(t):
    active_idx = 0
    current_scene = processed_scenes[0]
    
    # Identify active scene
    for idx, scene in enumerate(processed_scenes):
        if scene["start"] <= t <= scene["end"]:
            active_idx = idx
            current_scene = scene
            break
            
    beat_z = get_beat_zoom(t)
    scene_dur = current_scene["end"] - current_scene["start"]
    elapsed = t - current_scene["start"]
    
    # Process current frame
    curr_img = get_cached_image(scene_images[active_idx])
    bg_frame = process_ken_burns(curr_img, elapsed, scene_dur, beat_z)
    
    # --- CINEMATIC CROSSFADE INTERPOLATION ---
    if active_idx > 0 and elapsed < CROSSFADE_DURATION:
        alpha = elapsed / CROSSFADE_DURATION # 0.0 (mostly old) to 1.0 (all new)
        
        prev_scene = processed_scenes[active_idx - 1]
        prev_dur = prev_scene["end"] - prev_scene["start"]
        prev_elapsed = prev_dur + elapsed 
        
        prev_img = get_cached_image(scene_images[active_idx - 1])
        prev_frame = process_ken_burns(prev_img, prev_elapsed, prev_dur, beat_z)
        
        bg_frame = cv2.addWeighted(prev_frame, 1.0 - alpha, bg_frame, alpha, 0)
    
    # --- TYPOGRAPHY ENGINE ---
    img = Image.fromarray(bg_frame)
    overlay = Image.new('RGBA', img.size, (5, 5, 10, 100))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(img)
    
    metrics = get_audio_metrics(t)
    energy = metrics.get("energy_score", 0.15)
    
    main_sentence = current_scene["text"]
    words_list = current_scene.get("words", [])
    
    font_size = int(65 + (energy * 45))
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
        
    active_word = ""
    for w_obj in words_list:
        if w_obj["start"] <= t <= w_obj["end"]:
            active_word = w_obj["word"]
            break
            
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), main_sentence, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    else:
        tw, th = draw.textsize(main_sentence, font=font)
        
    x = (WIDTH - tw) // 2
    y = int(HEIGHT * 0.8)
    
    # Text Shadows and Highlights
    draw.text((x+4, y+4), main_sentence, fill=(0,0,0), font=font)
    text_color = (255, 200, 50) if active_word else (240, 240, 245)
    draw.text((x, y), main_sentence, fill=text_color, font=font)
    
    return np.array(img)

# --- RENDER TIMELINE ---
print("\n🎬 Rendering the interpolated master timeline...")
final_video = VideoClip(make_final_frame, duration=TOTAL_DURATION)
final_video = final_video.set_audio(audio_clip)

final_video.write_videofile(
    OUTPUT_PATH,
    fps=FPS,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="medium"
)

print(f"✨ Video processing seamlessly completed! Output saved to: {OUTPUT_PATH}")