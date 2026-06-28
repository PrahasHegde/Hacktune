# 🎬 Hacktune — AI Cinematic Compositor

> **Professional-grade, AI-powered lyric video generator.** Feed it a song's JSON data and an MP3; it hands you back a cinematic music video with AI-generated artwork, smooth motion, and timed lyrics — fully automated.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Input Format](#input-format)
- [Render Settings](#render-settings)
- [Pipeline Stages](#pipeline-stages)
- [Output](#output)
- [CLI Flags](#cli-flags)
- [Known Issues & Tips](#known-issues--tips)

---

## Overview

Hacktune is a fully automated AI pipeline that turns raw song data into a studio-quality lyric video. It combines a local LLM (Llama 3) for creative direction, Fal.ai's Flux model for image generation, Manim for typographically animated subtitles, and MoviePy + OpenCV for final compositing — all wired together behind a polished Streamlit UI.

The result is a 1920×1080 MP4 with:

- AI-generated abstract expressionist artwork, one scene per lyric segment
- Ken Burns motion (slow zoom + pan) synchronized to detected beats
- Dynamic colour grading that reacts to audio energy
- Animated subtitle overlay rendered by Manim
- Smooth sigmoid crossfades between scenes

---

## How It Works

```
Song JSON + MP3
      │
      ▼
┌─────────────────────┐
│  Stage 1 — Llama 3  │  Reads lyrics → analyses theme, emotion, palette
│  Storyboard         │  → generates one visual prompt per scene
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Stage 2 — Fal.ai   │  Sends prompts to Flux Schnell in parallel
│  Image Generation   │  → downloads one 16:9 painting per scene
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Stage 3 — OpenCV   │  Composites scenes with Ken Burns, crossfades,
│  Background Render  │  beat-pulse zoom, vignette & colour grade
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Stage 4 — Manim    │  Renders word-by-word lyric animation as
│  Subtitle Layer     │  a transparent overlay at 1080p
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Stage 5 — MoviePy  │  Composites background + subtitle overlay
│  Final Composite    │  + audio → output_lyric_video.mp4
└─────────────────────┘
```

---

## Tech Stack

| Component | Purpose |
|---|---|
| **Streamlit** | Web UI — file uploads, settings, live log, video preview |
| **Ollama / Llama 3** | Local LLM for song analysis and scene prompt generation |
| **Fal.ai Flux Schnell** | Text-to-image for AI-generated scene artwork |
| **OpenCV + NumPy** | Ken Burns motion, crossfades, colour grading, vignette |
| **Manim** | Animated subtitle/lyric layer with transparent background |
| **MoviePy** | Final compositing of background video + overlay + audio |
| **Pillow (PIL)** | Font rendering, gradient bands, image manipulation |
| **Python concurrent.futures** | Parallel image generation (up to 8 workers) |

---

## Project Structure

```
Hacktune/
├── app.py                        # Streamlit UI — entry point
├── gen.py                        # Core pipeline (standalone CLI version)
├── gen_copy.py                   # Pipeline variant called by Streamlit
├── song_poster_scene.py          # Manim scene for subtitle animation
├── song_data.py                  # Song data helpers
├── sync.py                       # Audio sync utilities
├── main_c.py                     # Alternative main entry
├── fal_ai copy 2.py              # Fal.ai API experiments
├── Application_GUI               # GUI scaffold file
├── frame-and-flow                # Frame/flow notes
├── FrameAndFlow.pptx             # Architecture / design presentation
├── prompt_review.txt             # Prompt engineering notes
├── package.json                  # Node dependencies (if any)
├── lyric_video_songs_and_data/   # Sample song JSON + MP3 files
├── layout/                       # UI layout assets
├── media/                        # Manim render output directory
├── scene_cache/                  # Cached Fal.ai images (scene_000.png …)
└── __pycache__/                  # Python bytecode cache
```

---

## Prerequisites

- **Python 3.10+**
- **ffmpeg** installed and on your PATH (required by MoviePy and Manim)
- **Ollama** running locally with the `llama3` model pulled
- **Manim** (Community Edition) installed globally
- A **Fal.ai API key** (the project has a key hardcoded in `gen.py` — replace it with your own)
- `Arial.ttf` font available at the working directory (or system fonts path)

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/PrahasHegde/Hacktune.git
cd Hacktune

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install streamlit moviepy opencv-python-headless pillow numpy \
            fal-client ollama manim

# 4. Pull the Llama 3 model (requires Ollama to be running)
ollama pull llama3

# 5. Set your Fal.ai API key
# Either export it as an env variable:
export FAL_KEY="your-fal-ai-key-here"
# Or replace the hardcoded value near the top of gen.py:
# os.environ["FAL_KEY"] = "your-key-here"
```

---

## Configuration

Key constants near the top of `gen.py` control the pipeline behaviour:

| Constant | Default | Description |
|---|---|---|
| `WIDTH`, `HEIGHT` | `1920`, `1080` | Output resolution |
| `FPS` | `24` | Frames per second |
| `LLAMA_MODEL` | `"llama3"` | Ollama model name |
| `FAL_MODEL` | `"fal-ai/flux/schnell"` | Fal.ai image model |
| `PARALLEL_IMAGES` | `8` | Concurrent image generation threads |
| `TARGET_SCENES` | `24` | Number of scenes to generate |
| `FLUX_STEPS` | `4` | Inference steps for Flux (speed vs quality) |
| `CROSSFADE_DUR` | `2.0` | Crossfade duration in seconds |
| `BEAT_ZOOM_STR` | `0.03` | Beat-pulse zoom strength |
| `KEN_BURNS_ZOOM` | `0.06` | Ken Burns total zoom amount |

---

## Running the App

### Streamlit UI (recommended)

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

1. Upload a **song JSON file** (see [Input Format](#input-format) below)
2. Upload the corresponding **MP3 file**
3. Optionally expand **Render Settings** to adjust quality, scene count, crossfade, and Flux steps
4. Click **🚀 INITIALIZE RENDER** and watch the pipeline run live

### Command-Line (headless)

```bash
python gen.py
# or with flags:
python gen.py --skip-llama        # reuse cached scene_prompts.json
python gen.py --use-cached-imgs   # reuse cached scene images
```

---

## Input Format

The song JSON file must follow this structure (matching the Musixmatch-style audio analysis format):

```json
{
  "lyrics_json": [
    {
      "start": 4500,
      "end": 8200,
      "text": "Lyric line text here",
      "words": [
        { "start": 4500, "end": 5100, "text": "Lyric" },
        { "start": 5200, "end": 5800, "text": "line" }
      ]
    }
  ],
  "audio_analysis": {
    "intensity_sections": {
      "data": [
        { "energy_score": 0.22, "percussiveness": 0.15 }
      ]
    },
    "beat_data": {
      "beat_positions": [850, 1700, 2550]
    }
  }
}
```

Timestamps in `lyrics_json` are in **milliseconds**. `beat_positions` are also in milliseconds. `intensity_sections.data` is sampled at 10 Hz (one entry per 100 ms).

---

## Render Settings

These are available in the Streamlit UI sidebar:

| Setting | Range | Default | Notes |
|---|---|---|---|
| **Manim Quality** | 480p / 720p / 1080p | 1080p | Higher quality = slower render |
| **Scene Count** | 12–48 | 24 | More scenes = more API calls to Fal.ai |
| **Crossfade Duration** | 0.5–4.0 s | 2.0 s | Time for scene transitions |
| **Flux Inference Steps** | 4–20 | 4 | Higher = better images, slower |

---

## Pipeline Stages

The UI shows live progress through five stages:

1. **🧠 Llama Storyboard** — Ollama analyses the song and generates per-scene visual prompts locked to an abstract expressionist oil-painting style.

2. **🎨 Fal.ai Image Generation** — Flux Schnell generates all scene images in parallel (up to 8 at a time). Images are cached to `scene_cache/` so reruns are fast.

3. **🖼 Background Render** — OpenCV composites the images into a full-length video with Ken Burns motion, beat-reactive zoom pulses, sigmoid crossfades, and energy-driven colour grading.

4. **✍️ Manim Subtitle Layer** — Manim renders an animated word-by-word lyric overlay at 1080p with a transparent background (exported as `.mov`).

5. **✨ Final Composite** — MoviePy combines the background video, Manim overlay, and audio into the final `output_lyric_video.mp4`.

---

## Output

The finished file is saved as `output_lyric_video.mp4` (or to the path set via `HACKATUNE_OUTPUT` when launched from the Streamlit UI). It can be downloaded directly from the UI with the **⬇ DOWNLOAD STUDIO MASTER** button after the render completes.

Scene images are cached in `scene_cache/` — delete this directory to force regeneration on the next run.

---

## CLI Flags

| Flag | Effect |
|---|---|
| `--skip-llama` | Skip the Llama storyboard step and load `scene_prompts.json` from a previous run |
| `--use-cached-imgs` | Skip image generation and use all images already in `scene_cache/` |

Both flags can be combined to do a fast background-only re-render after assets are already generated.

---

## Known Issues & Tips

- **Fal.ai API key** — The key in the repo is a sample key. Replace it with your own before running, or set the `FAL_KEY` environment variable.
- **Font not found** — If `Arial.ttf` is missing, the compositor falls back to PIL's default bitmap font. Place `Arial.ttf` (or any TTF) in the project root and update `FONT_PATH` in `gen.py`.
- **Manim render fails** — Ensure `manim` is on your PATH and ffmpeg is installed. Run `manim --version` to verify.
- **Long render times** — A 24-scene 1080p render typically takes 10–30 minutes depending on hardware and API response times. Use `--use-cached-imgs` for iteration on the compositor without re-generating images.
- **Black overlay in composite** — If the Manim subtitle layer appears as a black rectangle, the `mask_color` fallback in MoviePy treats pure-black pixels as transparent. Ensure Manim renders with `--transparent`.

---

## License

No license file is currently included in this repository. All rights reserved by the author unless otherwise stated.
