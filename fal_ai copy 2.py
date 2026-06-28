import time

FAL_KEY="5c90f577-c8e2-4c1b-b110-ba476f731f00:2f23f9c6b5911fb5f527798f76f43e01"


## This is used to create a video from a series of images, 
# slow it down, and then interpolate frames to make it smoother. To have a video playing in the background!

import os
import requests
import fal_client
from moviepy import VideoFileClip, concatenate_videoclips

os.environ["FAL_KEY"] = "5c90f577-c8e2-4c1b-b110-ba476f731f00:2f23f9c6b5911fb5f527798f76f43e01"

# ------------------------------------
# Deine Bild-URLs
# ------------------------------------

image_urls = [
    "https://www.image2url.com/r2/default/images/1782598704431-78e98437-b3fd-49ad-8c12-92b85fa3a16e.png",
    "https://www.image2url.com/r2/default/images/1782603686743-59b83e00-6398-4324-b772-6b08817678e1.png",
    "https://www.image2url.com/r2/default/images/1782631466403-a9b41eb3-b881-4b6a-9db3-6d103baf97bd.png",
    "https://www.image2url.com/r2/default/images/1782631421164-9ed5cbec-212d-4496-8451-845a50e72a48.png",
    "https://www.image2url.com/r2/default/images/1782631518779-9c95c7f3-4143-4006-b656-5122ed3e5e40.png",
    "https://www.image2url.com/r2/default/images/1782631572075-99bc1c3f-338e-4897-b63c-d99c23b185db.png"    
]

PROMPT = ""

os.makedirs("videos", exist_ok=True)


# ------------------------------------
# Callback
# ------------------------------------

def on_queue_update(update):
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(log["message"])


# ------------------------------------
# Downloadfunktion
# ------------------------------------

def download_video(url, filename):
    r = requests.get(url, stream=True)
    r.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


# ------------------------------------
# Videos generieren
# ------------------------------------

video_files = []

for i in range(len(image_urls) - 1):

    print(f"Generating video {i+1}/{len(image_urls)-1}")

    result = fal_client.subscribe(
        "fal-ai/veo3.1/first-last-frame-to-video",
        arguments={
            "prompt": PROMPT,
            "first_frame_url": image_urls[i],
            "last_frame_url": image_urls[i + 1]
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    # ggf. anpassen falls Response anders aussieht
    video_url = result["video"]["url"]

    filename = f"videos/video_{i}.mp4"

    print("Downloading:", filename)
    download_video(video_url, filename)

    video_files.append(filename)


# ------------------------------------
# Videos zusammenfügen
# ------------------------------------
# ------------------------------------
# Videos zusammenfügen
# ------------------------------------

clips = [VideoFileClip(v) for v in video_files]

final = concatenate_videoclips(clips, method="compose")

# Zuerst normales Video speichern
final.write_videofile(
    "final.mp4",
    codec="libx264",
    audio_codec="aac",
    fps=clips[0].fps
)

# Alle Clips schließen
for clip in clips:
    clip.close()

final.close()

time.sleep(1)  # API safety buffer
# ------------------------------------
# Video verlangsamen
# ------------------------------------

import subprocess

def slow_video(input_file, output_file, factor=3.0):
    subprocess.run([
        "ffmpeg",
        "-y",
        "-i", input_file,
        "-filter:v", f"setpts={factor}*PTS",
        "-an",
        output_file
    ], check=True)

# Jetzt die gespeicherte Datei verwenden!
slow_video("final.mp4", "final_slow.mp4", factor=3.0)

print("Fertig!")
print("Normales Video: final.mp4")
print("Verlangsamtes Video: final_slow.mp4")