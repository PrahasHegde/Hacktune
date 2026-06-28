import json
import os
import numpy as np
from moviepy.editor import AudioFileClip, VideoClip
from PIL import Image, ImageDraw, ImageFont

# LOCAL FILE ENVIROMENT
JSON_PATH = "lyric_video_songs_and_data\song_666407.json"
AUDIO_PATH = "lyric_video_songs_and_data\song_666407.mp3"
OUTPUT_PATH = "lyric_video_output.mp4"
FONT_PATH = "Arial.ttf"

# CANVAS CONFIGURATION
WIDTH, HEIGHT = 1920, 1080
FPS = 24

# 1. Parse Data Layer
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

lyrics_timeline = data["lyrics_json"]
intensity_data = data["audio_analysis"]["intensity_sections"]["data"]

audio_clip = AudioFileClip(AUDIO_PATH)
TOTAL_DURATION = audio_clip.duration


# Helper: Fetch continuous variable parameters from metric blocks
def get_audio_metrics(t):
    """Linearly samples the closest 100ms chunk of audio tracking features."""
    target_index = int(t * 10)
    if target_index < len(intensity_data):
        return intensity_data[target_index]
    return {"energy_score": 0.15, "percussiveness": 0.1}


# 2. Sequential Graphic Frame Assembly Canvas
def generate_frame(t):
    # Base styling map layout properties
    metrics = get_audio_metrics(t)
    energy = metrics.get("energy_score", 0.15)
    percussive = metrics.get("percussiveness", 0.1)

    # Dynamic Audio Reactive Background: Base dark slate pulses lighter on heavy kicks
    bg_pulse = int(percussive * 22)
    img = Image.new("RGB", (WIDTH, HEIGHT), (16 + bg_pulse, 18 + bg_pulse, 24 + bg_pulse))
    draw = ImageDraw.Draw(img)

    # Loop through slide sequence arrays
    for slide in lyrics_timeline:
        slide_start = slide["start"]
        slide_end = slide["end"]

        if slide_start <= t <= slide_end:
            main_sentence = slide["text"]
            words_list = slide.get("words", [])

            # Audio Kinetic Sizing Calculations
            base_font_size = 65
            scaled_font_size = int(base_font_size + (energy * 45))

            try:
                font = ImageFont.truetype(FONT_PATH, scaled_font_size)
            except IOError:
                font = ImageFont.load_default()

            # --- TEXT HIGHLIGHT KARAOKE PIPELINE ---
            # If sub-token timeline metrics are populated, determine the current vocal token
            active_word_str = ""
            for word_obj in words_list:
                if word_obj["start"] <= t <= word_obj["end"]:
                    active_word_str = word_obj["word"]
                    break

            # Centralized anchoring calculations
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), main_sentence, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            else:
                text_w, text_h = draw.textsize(main_sentence, font=font)

            x_center = (WIDTH - text_w) // 2
            y_center = (HEIGHT - text_h) // 2

            # Visual Style Rule Selection: Glow red/orange accents if intense vocals occur
            if active_word_str:
                text_color = (255, 100 + int(energy * 155), 100) # Kinetic active text tint
            else:
                text_color = (235, 240, 250) # Standard slide text color

            draw.text((x_center, y_center), main_sentence, fill=text_color, font=font)

            # Optional Progress Line for Current Phrase Slide Slide
            slide_duration = slide_end - slide_start
            elapsed_slide = t - slide_start
            progress_ratio = min(1.0, max(0.0, elapsed_slide / slide_duration))

            # Render an audio-reactive tracking line bar element down below
            bar_w = int((WIDTH * 0.4) * progress_ratio)
            bar_x1 = (WIDTH - int(WIDTH * 0.4)) // 2
            bar_y = y_center + text_h + 80
            draw.line([(bar_x1, bar_y), (bar_x1 + bar_w, bar_y)], fill=(100, 210, 255), width=4)
            break

    return np.array(img)


# 3. Compile local binary containers
print("🎬 Initializing compilation environment using sub-segment data sets...")
video_clip = VideoClip(generate_frame, duration=TOTAL_DURATION)
video_clip = video_clip.set_audio(audio_clip)

print(f"🚀 Processing sequence and writing out file targets...")
video_clip.write_videofile(
    OUTPUT_PATH,
    fps=FPS,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="fast"
)

print(f"✨ Rendering process completed. Output targeting located here: {OUTPUT_PATH}")