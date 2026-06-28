import json
import numpy as np
import cv2
import random
import os
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoClip, AudioFileClip

def run_pipeline(json_path, audio_path, output_path, font_path="Arial.ttf"):
    # Load Data
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Config
    W, H = 1920, 1080
    FPS = 24 # Reduced to 24 for smoother motion and faster render
    DURATION = data["audio_analysis"]["duration"]
    beats = [b / 1000.0 for b in data["audio_analysis"]["beat_data"]["beat_positions"]]
    energy_sections = data["audio_analysis"]["intensity_sections"]["data"]
    lyrics = data["lyrics_json"]
    font_cache = {}

    def get_dynamic_font(size):
        size = max(40, min(size, 300))
        if size not in font_cache:
            try:
                font_cache[size] = ImageFont.truetype(font_path, size)
            except:
                font_cache[size] = ImageFont.load_default()
        return font_cache[size]

    def get_energy(t):
        idx = min(int(t * 10), len(energy_sections) - 1)
        return energy_sections[idx]["energy_score"]

    def make_frame(t):
        energy = get_energy(t)
        
        # PUMP EFFECT
        past_beats = [b for b in beats if b <= t]
        time_since_beat = t - past_beats[-1] if past_beats else 1.0
        pump = 1.0 + (0.06 * np.exp(-time_since_beat * 15)) if time_since_beat < 0.2 else 1.0
        
        # Draw base
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        new_w, new_h = int(W * pump), int(H * pump)
        resized = cv2.resize(frame, (new_w, new_h))
        frame = resized[(new_h-H)//2:(new_h+H)//2, (new_w-W)//2:(new_w+W)//2]
        
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        
        # SUBTITLES
        phrase = next((p for p in lyrics if p["start"] <= t <= p["end"] + 0.3), None)
        if phrase:
            font_size = int(90 + (min(energy * 2.5, 1.0) ** 2) * 200)
            font = get_dynamic_font(font_size)
            words = phrase["words"]
            active_idx = next((i for i, w in enumerate(words) if w["start"] <= t <= w["end"]), -1)
            
            full_text = " ".join([w["word"] for w in words])
            text_w = draw.textlength(full_text, font=font)
            curr_x = (W - text_w) / 2
            start_y = (H - font_size) // 2
            
            for i, w in enumerate(words):
                color = (255, 220, 80) if i == active_idx else (255, 255, 255)
                # Text with slight drop shadow
                draw.text((curr_x+4, start_y+4), w["word"], font=font, fill=(0,0,0))
                draw.text((curr_x, start_y), w["word"], font=font, fill=color)
                curr_x += draw.textlength(w["word"] + " ", font=font)

        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    video = VideoClip(make_frame, duration=DURATION)
    video = video.set_audio(AudioFileClip(audio_path))
    video.write_videofile(output_path, fps=FPS, codec="libx264")