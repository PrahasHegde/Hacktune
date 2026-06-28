import json
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoClip, AudioFileClip

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
with open("lyric_video_songs_and_data\song_666407.json", "r") as f:
    data = json.load(f)

audio_path = "lyric_video_songs_and_data\song_666407.mp3"
font_path = "font.ttf" 
output_path = "final_output_improved.mp4"

W, H = 1920, 1080
FPS = 30
DURATION = data["audio_analysis"]["duration"]
beats = [b / 1000.0 for b in data["audio_analysis"]["beat_data"]["beat_positions"]]
energy_sections = data["audio_analysis"]["intensity_sections"]["data"]
lyrics = data["lyrics_json"]
font_cache = {}

# ==========================================
# 2. IMPROVED REACTIVE LOGIC
# ==========================================

def get_dynamic_font(size):
    size = max(40, min(size, 300)) # Clamping sizes
    if size not in font_cache:
        try:
            font_cache[size] = ImageFont.truetype(font_path, size)
        except:
            font_cache[size] = ImageFont.load_default()
    return font_cache[size]

def get_energy(t):
    # Using a slightly smoothed energy look-ahead for punchier text
    idx = min(int(t * 10), len(energy_sections) - 1)
    return energy_sections[idx]["energy_score"]

def make_frame(t):
    # --- PHASE 5: BEAT PUMPING (SHAKE) ---
    past_beats = [b for b in beats if b <= t]
    last_beat = past_beats[-1] if past_beats else 0
    time_since_beat = t - last_beat
    
    zoom = 1.0
    if time_since_beat < 0.2:
        # Faster, sharper "kick" pulse
        intensity = np.exp(-time_since_beat * 10) 
        zoom = 1.0 + (0.04 * intensity)
        
    new_w, new_h = int(W * zoom), int(H * zoom)
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    x, y = (new_w - W) // 2, (new_h - H) // 2
    frame = resized[y:y+H, x:x+W]
    
    # --- PHASE 6: ELASTIC TYPOGRAPHY ---
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    
    phrase = next((p for p in lyrics if p["start"] <= t <= p["end"] + 0.3), None)
    
    if phrase:
        energy = get_energy(t)
        
        # ELASTIC MATH:
        # Base size 90 + energy spike (amplified).
        # We use a non-linear curve (energy**2) to ensure the text 
        # only "pops" on significant hits, not during steady parts.
        font_size = int(90 + (min(energy * 2.5, 1.0) ** 2) * 200)
        font = get_dynamic_font(font_size)
        
        words = phrase["words"]
        active_idx = next((i for i, w in enumerate(words) if w["start"] <= t <= w["end"]), -1)
        
        # Calculate centering
        full_text = " ".join([w["word"] for w in words])
        text_w = draw.textlength(full_text, font=font)
        start_x = (W - text_w) / 2
        start_y = (H - font_size) // 2
        
        curr_x = start_x
        for i, word in enumerate(words):
            # Highlight active word with a "glow" color
            color = (255, 255, 0) if i == active_idx else (255, 255, 255)
            
            # Text shadow for better readability
            draw.text((curr_x + 3, start_y + 3), word["word"], font=font, fill=(0,0,0))
            draw.text((curr_x, start_y), word["word"], font=font, fill=color)
            
            curr_x += draw.textlength(word["word"] + " ", font=font)

    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

# ==========================================
# 3. RENDER
# ==========================================
video = VideoClip(make_frame, duration=DURATION)
video = video.set_audio(AudioFileClip(audio_path))
video.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")