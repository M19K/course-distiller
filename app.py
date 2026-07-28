"""course-distiller — local web UI (Streamlit).

Run:  streamlit run app.py
Everything happens on your machine. A browser window opens for YOU to log in to
your course; the tool never sees your password.
"""
import io
import json
import os
import subprocess
import sys
import time
import zipfile

import streamlit as st
import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "config.yaml")
PROGRESS = os.path.join(ROOT, "work", "progress.jsonl")

PHASES = [
    ("login", "🔑 Log in"), ("map", "🗺️ Map structure"), ("harvest", "📄 Harvest lessons"),
    ("attachments", "📎 Download files"), ("transcribe", "🎬 Transcribe video"),
    ("extract", "🔍 Extract file text"), ("compile", "🧩 Compile corpus"), ("bundle", "📦 Bundle"),
]

st.set_page_config(page_title="course-distiller", page_icon="🧠", layout="centered")
st.title("🧠 course-distiller")
st.caption("Turn any course you have access to into a private, LLM-queryable knowledge base — locally, for $0.")

with st.expander("How it works / before you start", expanded=False):
    st.markdown(
        "1. Enter your course's URL and options below.\n"
        "2. Hit **Start** — a browser window opens. **You** log in to your course there "
        "(the tool never sees your password).\n"
        "3. It crawls the lessons, transcribes videos (local Whisper), extracts PDFs, and distills "
        "everything into markdown.\n"
        "4. Download the result and drop it into NotebookLM or query it with any LLM.\n\n"
        "> Only use this on content you're legitimately entitled to access."
    )

st.subheader("Configure")
c1, c2 = st.columns(2)
base_url = c1.text_input("Course base URL", placeholder="https://www.your-course.com")
product_slug = c2.text_input("Product slug", placeholder="my-course",
                             help="From the URL: /products/<slug>/categories/…/posts/…")
c3, c4, c5 = st.columns(3)
do_video = c3.toggle("Transcribe videos", value=True)
do_attach = c4.toggle("Extract file text", value=True)
max_videos = c5.number_input("Max videos (0 = all)", min_value=0, value=0, step=1)
with st.expander("Advanced (models)"):
    whisper_model = st.text_input("Whisper model", value="mlx-community/whisper-large-v3-turbo")
    ollama_model = st.text_input("Ollama distill model", value="gpt-oss:20b")

start = st.button("🚀 Start extraction", type="primary", disabled=not (base_url and product_slug),
                  use_container_width=True)

if start:
    cfg = {
        "site": {"base_url": base_url, "product_slug": product_slug},
        "output_dir": "./output", "work_dir": "./work",
        "video": {"enabled": bool(do_video), "whisper_model": whisper_model, "max_videos": int(max_videos)},
        "distill": {"enabled": True, "model": ollama_model},
        "attachments": {"download": True, "extract_text": bool(do_attach), "ocr_fallback": True},
    }
    os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
    yaml.safe_dump(cfg, open(CONFIG, "w"))
    open(PROGRESS, "w").close()  # truncate
    st.session_state["proc"] = subprocess.Popen(
        [sys.executable, "-m", "coursedistiller.run", "--config", CONFIG, "--progress-file", PROGRESS],
        cwd=ROOT)
    st.session_state["running"] = True

if st.session_state.get("running"):
    st.divider()
    st.subheader("Progress")
    box = st.empty()
    proc = st.session_state["proc"]
    last = {}
    while True:
        if os.path.exists(PROGRESS):
            for line in open(PROGRESS):
                try:
                    e = json.loads(line)
                    last[e.get("phase", "")] = e
                except Exception:
                    pass
        with box.container():
            for key, label in PHASES:
                e = last.get(key)
                if not e:
                    st.markdown(f"◻️ {label}")
                    continue
                total, done = e.get("total"), e.get("done")
                if total:
                    st.progress(min(1.0, done / max(1, total)), text=f"{label} — {e.get('msg','')}")
                else:
                    st.markdown(f"🔄 {label} — {e.get('msg','')}")
            if key := last.get("login"):
                if not any(last.get(p) for p, _ in PHASES[1:]):
                    st.info("👉 A browser opened — log in to your course to continue.")
        if proc.poll() is not None:
            break
        time.sleep(1.0)

    st.session_state["running"] = False
    if last.get("done") or last.get("bundle"):
        st.success("✅ Done! Your knowledge base is ready.")
        bundles = os.path.join(ROOT, "output", "notebooklm")
        if os.path.isdir(bundles):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(os.listdir(bundles)):
                    z.write(os.path.join(bundles, f), arcname=f)
            st.download_button("⬇️ Download knowledge base (NotebookLM bundles)", buf.getvalue(),
                               file_name="knowledge-base.zip", mime="application/zip",
                               use_container_width=True)
            st.caption(f"{len(os.listdir(bundles))} bundles — upload them all to one NotebookLM notebook.")
    else:
        st.error("The run stopped before finishing. Check the terminal output for details.")
