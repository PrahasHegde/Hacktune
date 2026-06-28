import json
import os
import urllib.request
import numpy as np
import fal_client
import cv2 
from moviepy.editor import VideoFileClip, AudioFileClip, VideoClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont

# --- 1. CONFIGURATION ---
JSON_PATH = "lyrics.json"
AUDIO_PATH = "song.mp3"
OUTPUT_PATH = "final_fal_music_video.mp4"
FONT_PATH = "Arial.ttf" 
WIDTH, HEIGHT = 1920, 1080
FPS = 24

# --- 2. LOAD DATA ---
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

lyrics_timeline = data["lyrics_json"]
audio_analysis = data["audio_analysis"]
intensity_data = audio_analysis["intensity_sections"]["data"]
segments = audio_analysis["segment_data"]
beats = [b / 1000.0 for b in audio_analysis["beat_data"]["beat_positions"]]

audio_clip = AudioFileClip(AUDIO_PATH)
TOTAL_DURATION = audio_clip.duration


# --- PHASE 1: THE FAL.AI DIRECTOR ---

def generate_segment_clips():
    print("🤖 Booting Fal.ai Director Engine...")
    clips = []
    
    # The visual identity of your music video
    base_style = "A gritty urban cinematic scene, dark, intense, moody lighting, highly detailed, 4k"
    
    for i, seg in enumerate(segments):
        label = seg["label"]
        start, end = seg["start"], seg["end"]
        target_duration = end - start
        
        # We cap duration requests to standard Kling limits (usually 5 or 10 seconds)
        # If a segment is longer, MoviePy will automatically loop it during composition
        api_duration = "5" if target_duration <= 5 else "10"
        
        # Dynamic Prompt Engineering based on the song's structure
        if label == "chorus":
            prompt = f"{base_style}, fast motion, a young man heavily bandaged looking stressed, fast camera tracking, chaotic"
        elif label == "verse":
            prompt = f"{base_style}, slow pan, a young man looking at medical bills on a table, depressed"
        else:
            prompt = f"{base_style}, establishing shot, misty environment, slow cinematic zoom"
            
        clip_filename = f"fal_segment_{i}.mp4"
        
        # If we haven't generated this clip yet, call the Fal API
        if not os.path.exists(clip_filename):
            print(f"🎬 Action! Directing Fal.ai to generate [{label}] segment...")
            print(f"   Prompt: {prompt}")
            
            try:
                # Using Kling 1.6 for cinematic text-to-video
                result = fal_client.subscribe(
                    "fal-ai/kling-video/v1.6/standard/text-to-video",
                    arguments={
                        "prompt": prompt,
                        "duration": api_duration,
                        "aspect_ratio": "16:9"
                    }
                )
                video_url = result["video"]["url"]
                print(f"   ✅ Video generated! Downloading to {clip_filename}...")
                urllib.request.urlretrieve(video_url, clip_filename)
            except Exception as e:
                print(f"   ❌ Fal API Error on segment {i}: {e}")
                continue # Skip to next segment if API fails
        else:
            print(f"⏭️  Using cached AI clip for [{label}]: {clip_filename}")

        # Load the newly downloaded clip into MoviePy
        if os.path.exists(clip_filename):
            clip = VideoFileClip(clip_filename).resize(newsize=(WIDTH, HEIGHT))
            
            # If the generated AI clip is shorter than your song segment, loop it smoothly
            if clip.duration < target_duration:
                clip = clip.loop(duration=target_duration)
            else:
                clip = clip.subclip(0, target_duration)
                
            clips.append(clip)

    print("🧩 Stitching AI scenes into the master timeline...")
    return concatenate_videoclips(clips)

# Execute Phase 1
bg_master_clip = generate_segment_clips()


# --- PHASE 2 & 3: BEAT-SYNC EDITING & COMPOSITING ---

def get_audio_metrics(t):
    target_index = int(t * 10)
    if target_index < len(intensity_data):
        return intensity_data[target_index]
    return {"energy_score": 0.15, "percussiveness": 0.1}

def get_beat_zoom(t):
    """Creates an aggressive camera 'pump' effect on hard beats."""
    recent_beats = [b for b in beats if b <= t]
    if not recent_beats:
        return 1.0
        
    time_since_beat = t - recent_beats[-1]
    
    # 150ms beat decay window
    if time_since_beat < 0.15:
        decay = 1.0 - (time_since_beat / 0.15)
        return 1.0 + (0.06 * decay) # 6% zoom punch
    return 1.0

def make_final_frame(t):
    # 1. Grab the AI Generated Background
    # Wrap in try/except in case of minor floating point rounding errors at the very end of the track
    try:
        bg_frame = bg_master_clip.get_frame(t)
    except:
        bg_frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    
    # 2. Apply Beat-Sync Camera Pump
    zoom = get_beat_zoom(t)
    if zoom > 1.0:
        h, w = bg_frame.shape[:2]
        new_w, new_h = int(w * zoom), int(h * zoom)
        zoomed_frame = cv2.resize(bg_frame, (new_w, new_h))
        x1, y1 = (new_w - w) // 2, (new_h - h) // 2
        bg_frame = zoomed_frame[y1:y1+h, x1:x1+w]

    img = Image.fromarray(bg_frame)
    
    # 3. Add a cinematic vignette overlay so white lyrics pop
    overlay = Image.new('RGBA', img.size, (10, 15, 20, 110)) 
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(img)
    
    # 4. Audio-Reactive Typography
    metrics = get_audio_metrics(t)
    energy = metrics.get("energy_score", 0.15)
    
    for slide in lyrics_timeline:
        if slide["start"] <= t <= slide["end"]:
            main_sentence = slide["text"]
            words_list = slide.get("words", [])

            base_font_size = 75
            scaled_font_size = int(base_font_size + (energy * 60))

            try:
                font = ImageFont.truetype(FONT_PATH, scaled_font_size)
            except IOError:
                font = ImageFont.load_default()

            # Karaoke logic
            active_word_str = ""
            for word_obj in words_list:
                if word_obj["start"] <= t <= word_obj["end"]:
                    active_word_str = word_obj["word"]
                    break

            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), main_sentence, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            else:
                text_w, text_h = draw.textsize(main_sentence, font=font)

            x_center = (WIDTH - text_w) // 2
            y_center = int(HEIGHT * 0.78) # Lower Third

            # Heavy Drop Shadow
            draw.text((x_center + 4, y_center + 4), main_sentence, fill=(0,0,0), font=font)

            # Paint the text: Glow red if the word is actively being spoken
            text_color = (255, 70, 70) if active_word_str else (250, 250, 255)
            draw.text((x_center, y_center), main_sentence, fill=text_color, font=font)
            break

    return np.array(img)

# --- EXECUTION ---
print("🎬 Compositing audio, AI video, and kinetic lyrics...")
final_video = VideoClip(make_final_frame, duration=bg_master_clip.duration)
final_video = final_video.set_audio(audio_clip.subclip(0, bg_master_clip.duration))

print("🚀 Final Render! (This handles CPU-based frame mapping, grab a coffee)")
final_video.write_videofile(
    OUTPUT_PATH,
    fps=FPS,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="medium"
)

print(f"✨ Masterpiece Complete! Saved to {OUTPUT_PATH}")