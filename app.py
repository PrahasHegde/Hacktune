"""
AI Cinematic Compositor — Streamlit UI
Elegant dark-theme interface matching the reference design.

Run:
    streamlit run app.py
"""

import os
import time
import tempfile
import subprocess
from pathlib import Path
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Cinematic Compositor",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Imports ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: #0a0a0f !important;
    color: #e8e8f0 !important;
    font-family: 'Inter', sans-serif !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

/* ── Main container ── */
[data-testid="stAppViewContainer"] > .main {
    padding: 0 !important;
}
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── Top bar ── */
.top-bar {
    background: #0d0d14;
    border-bottom: 1px solid #1e1e2e;
    padding: 0 40px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
}
.top-bar-logo {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.15em;
    color: #ff4d6d;
    text-transform: uppercase;
}
.top-bar-status {
    font-size: 11px;
    color: #4a4a6a;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* ── Hero header ── */
.hero {
    text-align: center;
    padding: 52px 40px 40px;
    background: linear-gradient(180deg, #0d0d14 0%, #0a0a0f 100%);
    border-bottom: 1px solid #1a1a28;
}
.hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: clamp(28px, 4vw, 48px);
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #ff4d6d 0%, #ff8566 60%, #ffb347 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 10px;
    line-height: 1.1;
}
.hero-sub {
    font-size: 13px;
    color: #5a5a7a;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-weight: 400;
}

/* ── Two-column layout ── */
.layout-grid {
    display: grid;
    grid-template-columns: 420px 1fr;
    gap: 0;
    min-height: calc(100vh - 180px);
}
.left-panel {
    background: #0d0d14;
    border-right: 1px solid #1a1a28;
    padding: 36px 32px;
}
.right-panel {
    background: #0a0a0f;
    padding: 36px 40px;
}

/* ── Section labels ── */
.panel-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 18px;
    font-weight: 600;
    color: #e8e8f0;
    margin: 0 0 24px;
    letter-spacing: -0.01em;
}
.field-label {
    font-size: 11px;
    font-weight: 500;
    color: #5a5a7a;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    margin: 0 0 10px;
}

/* Streamlit file uploader override */
[data-testid="stFileUploader"] {
    background: #12121f !important;
    border: 1px solid #1e1e32 !important;
    border-radius: 10px !important;
    padding: 16px 18px !important;
    margin-bottom: 16px !important;
}
[data-testid="stFileUploader"] label {
    color: #5a5a7a !important;
    font-size: 11px !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] {
    color: #3a3a5a !important;
    font-size: 12px !important;
}
section[data-testid="stFileUploader"] > label {
    display: none;
}

/* ── Upload button inside uploader ── */
[data-testid="stFileUploader"] button {
    background: #1e1e32 !important;
    color: #c8c8e0 !important;
    border: 1px solid #2e2e48 !important;
    border-radius: 7px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 7px 16px !important;
    letter-spacing: 0.04em !important;
    transition: all 0.2s !important;
}
[data-testid="stFileUploader"] button:hover {
    background: #28283e !important;
    border-color: #ff4d6d66 !important;
    color: #fff !important;
}

/* ── Primary CTA button ── */
.stButton > button[kind="primary"],
.stButton > button {
    background: linear-gradient(135deg, #ff4d6d, #ff7043) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    padding: 14px 32px !important;
    width: 100% !important;
    margin-top: 12px !important;
    transition: all 0.2s !important;
    box-shadow: 0 4px 24px rgba(255, 77, 109, 0.25) !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    box-shadow: 0 6px 32px rgba(255, 77, 109, 0.45) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active {
    transform: translateY(0) !important;
}

/* ── Progress / status ── */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #ff4d6d, #ff7043) !important;
    border-radius: 4px !important;
}
[data-testid="stProgress"] {
    background: #1a1a2a !important;
    border-radius: 4px !important;
}

/* ── Video player ── */
[data-testid="stVideo"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid #1a1a28 !important;
    background: #08080f !important;
}
video {
    border-radius: 12px !important;
    width: 100% !important;
}

/* ── Download button ── */
.download-bar {
    background: #0d0d14;
    border-top: 1px solid #1a1a28;
    padding: 20px 40px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 16px;
}
[data-testid="stDownloadButton"] button {
    background: #12121f !important;
    color: #c8c8e0 !important;
    border: 1px solid #2e2e48 !important;
    border-radius: 8px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    padding: 12px 28px !important;
    transition: all 0.2s !important;
}
[data-testid="stDownloadButton"] button:hover {
    border-color: #ff4d6d66 !important;
    color: #fff !important;
    background: #1e1e32 !important;
}

/* ── Divider ── */
.subtle-divider {
    border: none;
    border-top: 1px solid #1a1a28;
    margin: 28px 0;
}

/* ── Stage pills ── */
.stage-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #12121f;
    border: 1px solid #1e1e32;
    border-radius: 20px;
    padding: 5px 14px 5px 10px;
    font-size: 11px;
    color: #5a5a7a;
    letter-spacing: 0.06em;
    margin-bottom: 10px;
}
.stage-pill.active {
    border-color: #ff4d6d44;
    color: #ff8566;
    background: #1e1224;
}
.stage-pill.done {
    border-color: #1e3a26;
    color: #66c87a;
    background: #0e1e14;
}

/* ── Preview placeholder ── */
.preview-placeholder {
    background: #08080f;
    border: 1px solid #1a1a28;
    border-radius: 12px;
    aspect-ratio: 16/9;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: #2a2a3a;
}
.preview-placeholder-icon {
    font-size: 36px;
    opacity: 0.4;
}
.preview-placeholder-text {
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* ── Selectbox / inputs ── */
[data-testid="stSelectbox"] > div > div {
    background: #12121f !important;
    border: 1px solid #1e1e32 !important;
    border-radius: 8px !important;
    color: #c8c8e0 !important;
    font-size: 13px !important;
}
[data-testid="stSelectbox"] label, [data-testid="stSlider"] label {
    font-size: 11px !important;
    color: #5a5a7a !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
    background: #ff4d6d !important;
    border-color: #ff4d6d !important;
}
[data-testid="stExpander"] {
    background: #12121f !important;
    border: 1px solid #1e1e32 !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    color: #8888aa !important;
    font-size: 12px !important;
    letter-spacing: 0.06em !important;
    font-weight: 500 !important;
}
</style>
""", unsafe_allow_html=True)


# ── Top bar & Hero ───────────────────────────────────────────────────────────
st.markdown("""
<div class="top-bar">
    <span class="top-bar-logo">⬡ Hackatune</span>
    <span class="top-bar-status">AI Cinematic Compositor v2.0</span>
</div>
<div class="hero">
    <h1 class="hero-title">AI CINEMATIC COMPOSITOR</h1>
    <p class="hero-sub">Professional-grade audio-reactive rendering</p>
</div>
""", unsafe_allow_html=True)

# ── Session state init ────────────────────────────────────────────────────────
for key, default in {
    "render_started": False,
    "render_done": False,
    "output_path": None,
    "log_lines": [],
    "stage": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Two-column body ──────────────────────────────────────────────────────────
left, right = st.columns([420, 700], gap="small")

# ════════════════════════════════════════════════════════
#  LEFT PANEL — Asset Pipeline
# ════════════════════════════════════════════════════════
with left:
    st.markdown('<p class="panel-title">Asset Pipeline</p>', unsafe_allow_html=True)

    st.markdown('<p class="field-label">Upload JSON Data</p>', unsafe_allow_html=True)
    json_file = st.file_uploader("json_upload", type=["json"], label_visibility="collapsed")

    st.markdown('<p class="field-label" style="margin-top:8px;">Upload Audio (MP3)</p>', unsafe_allow_html=True)
    mp3_file = st.file_uploader("mp3_upload", type=["mp3"], label_visibility="collapsed")

    st.markdown('<hr class="subtle-divider">', unsafe_allow_html=True)

    with st.expander("⚙  RENDER SETTINGS", expanded=False):
        quality = st.selectbox("Manim Quality", ["-ql (480p · Fast)", "-qm (720p · Medium)", "-qh (1080p · Slow)"], index=2)
        target_scenes = st.slider("Scene Count", 12, 48, 24, step=4)
        crossfade     = st.slider("Crossfade Duration (s)", 0.5, 4.0, 2.0, step=0.5)
        flux_steps    = st.slider("Flux Inference Steps", 4, 20, 4, step=2)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    render_ready = json_file is not None and mp3_file is not None
    btn_label    = "🚀  INITIALIZE RENDER" if not st.session_state.render_started else "⏳  RENDERING …"

    if st.button(btn_label, disabled=not render_ready or st.session_state.render_started):
        st.session_state.render_started = True
        st.session_state.render_done    = False
        st.session_state.log_lines      = []
        st.session_state.output_path    = None
        st.rerun()

    if not render_ready and not st.session_state.render_started:
        st.markdown('<p style="font-size:11px;color:#3a3a5a;text-align:center;margin-top:8px;letter-spacing:0.06em;">Upload both files to enable render</p>', unsafe_allow_html=True)

    # ── Pipeline stage indicators ──
    stage_placeholder = st.empty()
    
    def update_stages():
        stages = [
            ("llama",     "🧠", "Llama Storyboard"),
            ("images",    "🎨", "Fal.ai Image Generation"),
            ("render",    "🖼 ", "Background Render"),
            ("manim",     "✍️ ", "Manim Subtitle Layer"),
            ("composite", "✨", "Final Composite"),
        ]
        current = st.session_state.stage
        stage_order = [s[0] for s in stages]
        
        html = "<div style='height:24px'></div><p class='field-label'>Pipeline Stages</p>"
        for key_, icon, label in stages:
            if current is None: cls, dot = "", "⬜"
            elif key_ == current: cls, dot = "active", "🟠"
            elif stage_order.index(key_) < (stage_order.index(current) if current in stage_order else 99): cls, dot = "done", "🟢"
            else: cls, dot = "", "⬜"
            html += f'<div class="stage-pill {cls}"><span>{dot}</span>{icon} {label}</div><br>'
        stage_placeholder.markdown(html, unsafe_allow_html=True)

    if st.session_state.render_started or st.session_state.render_done:
        update_stages()

# ════════════════════════════════════════════════════════
#  RIGHT PANEL — Live Preview
# ════════════════════════════════════════════════════════
with right:
    st.markdown('<p class="panel-title">Live Preview</p>', unsafe_allow_html=True)
    preview_placeholder = st.empty()

    if st.session_state.render_done and st.session_state.output_path and Path(st.session_state.output_path).exists():
        with open(st.session_state.output_path, "rb") as f:
            preview_placeholder.video(f.read())
    else:
        preview_placeholder.markdown("""
        <div class="preview-placeholder">
            <div class="preview-placeholder-icon">▶</div>
            <div class="preview-placeholder-text">Output appears here after render</div>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.render_started or st.session_state.render_done:
        st.markdown("<div style='height:20px'></div><p class='field-label'>Render Log</p>", unsafe_allow_html=True)
        log_box = st.empty()

        def refresh_log():
            lines = st.session_state.log_lines[-30:]
            html  = "<div style='background:#08080f;border:1px solid #1a1a28;border-radius:8px;padding:16px 18px;font-family:monospace;font-size:11px;line-height:1.9;max-height:220px;overflow-y:auto;'>"
            for ln in lines:
                col = "#66c87a" if "✅" in ln else "#ff8566" if "🚀" in ln or "🎨" in ln else "#ffb347" if "⚠" in ln else "#ff6b6b" if "❌" in ln else "#4a4a6a"
                html += f'<div style="color:{col}">{ln}</div>'
            html += "</div>"
            log_box.markdown(html, unsafe_allow_html=True)

        refresh_log()

    if st.session_state.render_done and st.session_state.output_path and Path(st.session_state.output_path).exists():
        st.markdown("<div style='height:16px'></div><hr class='subtle-divider'>", unsafe_allow_html=True)
        dl_col1, dl_col2 = st.columns([1, 1])
        with dl_col2:
            with open(st.session_state.output_path, "rb") as f:
                st.download_button(label="⬇  DOWNLOAD STUDIO MASTER", data=f, file_name="cinematic_output.mp4", mime="video/mp4")

# ════════════════════════════════════════════════════════
#  RENDER PIPELINE (Live Streaming)
# ════════════════════════════════════════════════════════
if st.session_state.render_started and not st.session_state.render_done:
    
    tmp = tempfile.mkdtemp()
    json_path = os.path.join(tmp, "song.json")
    mp3_path  = os.path.join(tmp, "song.mp3")

    with open(json_path, "wb") as f: f.write(json_file.getvalue())
    with open(mp3_path, "wb") as f:  f.write(mp3_file.getvalue())

    output_path = os.path.join(tmp, "output_lyric_video.mp4")
    
    q_map = {"-ql (480p · Fast)": "-ql", "-qm (720p · Medium)": "-qm", "-qh (1080p · Slow)": "-qh"}
    
    run_env = os.environ.copy()
    run_env["PYTHONIOENCODING"] = "utf-8"
    run_env["HACKATUNE_SONG"]   = json_path
    run_env["HACKATUNE_AUDIO"]  = mp3_path
    run_env["HACKATUNE_OUTPUT"] = output_path
    run_env["HACKATUNE_SCENES"] = str(target_scenes)
    run_env["HACKATUNE_XFADE"]  = str(crossfade)
    run_env["HACKATUNE_STEPS"]  = str(flux_steps)
    run_env["MANIM_QUALITY"]    = q_map.get(quality, "-qh")

    progress_bar = st.progress(5, text="Initialising …")

    gen_script = Path(__file__).parent / "gen_copy.py"
    
    if gen_script.exists():
        st.session_state.stage = "llama"
        update_stages()
        
        # 🚨 Bulletproof Subprocess: Raw Bytes Mode
        process = subprocess.Popen(
            ["python", str(gen_script)],
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # No text=True, no universal_newlines=True to ensure raw bytes
        )

        # 🚨 Bulletproof Decode: Replace broken bytes instead of crashing
        for raw_line in process.stdout:
            line = raw_line.decode("utf-8", errors="replace")
            clean_line = line.strip()
            
            if not clean_line: continue
            
            st.session_state.log_lines.append(clean_line)
            refresh_log()

            # Dynamic UI Updates based on terminal output
            if "IMAGE GENERATION" in clean_line:
                st.session_state.stage = "images"
                progress_bar.progress(25, text="🎨 Generating images via Fal.ai …")
                update_stages()
            elif "Rendering background art" in clean_line:
                st.session_state.stage = "render"
                progress_bar.progress(55, text="🖼  Rendering background video …")
                update_stages()
            elif "Running Manim" in clean_line:
                st.session_state.stage = "manim"
                progress_bar.progress(75, text="✍️  Rendering Manim subtitle layer …")
                update_stages()
            elif "Compositing with MoviePy" in clean_line:
                st.session_state.stage = "composite"
                progress_bar.progress(90, text="✨ Compositing final video …")
                update_stages()

        process.wait()

        if Path(output_path).exists():
            st.session_state.output_path = output_path
            st.session_state.log_lines.append("✅ Render complete!")
        elif Path("output_lyric_video.mp4").exists():
            st.session_state.output_path = "output_lyric_video.mp4"
            st.session_state.log_lines.append("✅ Output found locally!")
        else:
            st.session_state.log_lines.append("❌ Output file not found. Check gen.py configuration.")
    else:
        st.session_state.log_lines.append("⚠️  gen.py not found in same directory.")
        time.sleep(2)

    progress_bar.progress(100, text="✅ Complete")
    st.session_state.render_done = True
    st.session_state.render_started = False
    st.rerun()