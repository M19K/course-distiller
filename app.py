"""course-distiller — local web UI (Streamlit).  Run:  streamlit run app.py

Everything happens on your machine. A browser opens for YOU to log in (the tool never sees your
password). API keys, if you use a cloud provider, are passed to the run as environment variables and
are never written to disk.
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
KEY_ENV = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
           "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
PHASES = [("login", "🔑 Log in"), ("map", "🗺️ Map structure"), ("harvest", "📄 Harvest lessons"),
          ("attachments", "📎 Download files"), ("estimate", "📊 Measure videos"),
          ("transcribe", "🎬 Transcribe"), ("extract", "🔍 Extract file text"),
          ("compile", "🧩 Compile"), ("bundle", "📦 Bundle")]

st.set_page_config(page_title="course-distiller", page_icon="🧠", layout="centered")
st.title("🧠 course-distiller")
st.caption("Turn a course you have access to into a private, LLM-queryable knowledge base — local or cloud, your choice.")


def launch(plan_only, env):
    open(PROGRESS, "w").close()
    args = [sys.executable, "-m", "coursedistiller.run", "--config", CONFIG, "--progress-file", PROGRESS]
    if plan_only:
        args.append("--plan")
    return subprocess.Popen(args, cwd=ROOT, env=env)


def stream(proc, box):
    """Block until proc ends, rendering live progress. Returns the last event per phase."""
    last = {}
    while True:
        if os.path.exists(PROGRESS):
            for line in open(PROGRESS):
                try:
                    e = json.loads(line); last[e.get("phase", "")] = e
                except Exception:
                    pass
        with box.container():
            for key, label in PHASES:
                e = last.get(key)
                if not e:
                    st.markdown(f"◻️ {label}")
                elif e.get("total"):
                    st.progress(min(1.0, e["done"] / max(1, e["total"])), text=f"{label} — {e.get('msg','')}")
                else:
                    st.markdown(f"🔄 {label} — {e.get('msg','')}")
            if last.get("login") and not any(last.get(p) for p in ("map", "harvest")):
                st.info("👉 A browser opened — log in to your course to continue.")
        if proc.poll() is not None:
            break
        time.sleep(1.0)
    return last


# ── config form ──────────────────────────────────────────────────────────────
st.subheader("1 · Configure")
c1, c2 = st.columns(2)
base_url = c1.text_input("Course base URL", placeholder="https://www.your-course.com")
product_slug = c2.text_input("Product slug", placeholder="my-course",
                             help="From a lesson URL: /products/<slug>/categories/…/posts/…")

st.markdown("**AI providers** — run locally (free, needs Ollama / Apple-Silicon) or via a cloud API key.")
p1, p2 = st.columns(2)
t_prov = p1.selectbox("Transcription", ["local", "groq", "openai"],
                      help="No GPU? Pick groq — cheap & fast Whisper in the cloud.")
t_key = p1.text_input("Transcription API key", type="password") if t_prov != "local" else ""
d_prov = p2.selectbox("Distillation", ["local", "openai", "anthropic", "gemini", "openrouter"])
d_key = p2.text_input("Distillation API key", type="password") if d_prov != "local" else ""

o1, o2, o3 = st.columns(3)
do_video = o1.toggle("Transcribe videos", value=True)
do_attach = o2.toggle("Extract file text", value=True)
max_videos = o3.number_input("Max videos (0 = all)", min_value=0, value=0, step=1)
with st.expander("Advanced (models)"):
    whisper_model = st.text_input("Local Whisper model", value="mlx-community/whisper-large-v3-turbo")
    d_model = st.text_input("Distill model (blank = provider default)", value="")


def build_env():
    env = dict(os.environ)
    if t_prov != "local" and t_key:
        env[KEY_ENV[t_prov]] = t_key
    if d_prov != "local" and d_key:
        env[KEY_ENV[d_prov]] = d_key
    return env


def write_config():
    yaml.safe_dump({
        "site": {"base_url": base_url, "product_slug": product_slug},
        "output_dir": "./output", "work_dir": "./work",
        "video": {"enabled": bool(do_video), "transcribe_provider": t_prov,
                  "whisper_model": whisper_model, "max_videos": int(max_videos)},
        "distill": {"enabled": True, "provider": d_prov, "model": d_model},
        "attachments": {"download": True, "extract_text": bool(do_attach), "ocr_fallback": True},
    }, open(CONFIG, "w"))


# ── step 2: analyze (crawl + estimate) ───────────────────────────────────────
st.subheader("2 · Analyze & estimate")
if st.button("🔎 Analyze course", type="primary", disabled=not (base_url and product_slug),
             use_container_width=True):
    os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
    write_config()
    st.session_state["env"] = build_env()
    last = stream(launch(True, st.session_state["env"]), st.empty())
    st.session_state["plan"] = last.get("plan")

if st.session_state.get("plan"):
    p = st.session_state["plan"]
    st.success("Estimate ready:")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Lessons", p.get("lessons", "—"))
    m2.metric("Videos", p.get("videos", "—"))
    m3.metric("Est. time", f"{p.get('est_minutes','—')} min")
    m4.metric("Est. cost", "free" if p.get("est_cost_usd", 0) == 0 else f"${p.get('est_cost_usd')}")
    st.caption(f"{p.get('audio_hours','?')} hrs of audio · transcription: {p.get('transcribe_provider')} · "
               f"distillation: {p.get('distill_provider')}")

    st.subheader("3 · Run")
    if st.button("🚀 Proceed with full run", type="primary", use_container_width=True):
        last = stream(launch(False, st.session_state.get("env", dict(os.environ))), st.empty())
        if last.get("done") or last.get("bundle"):
            st.success("✅ Done! Your knowledge base is ready.")
            bundles = os.path.join(ROOT, "output", "notebooklm")
            if os.path.isdir(bundles):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for f in sorted(os.listdir(bundles)):
                        z.write(os.path.join(bundles, f), arcname=f)
                st.download_button("⬇️ Download knowledge base (markdown)", buf.getvalue(),
                                   file_name="knowledge-base.zip", mime="application/zip",
                                   use_container_width=True)
                st.caption("Universal markdown — open in NotebookLM, Claude, ChatGPT, Obsidian, or grep.")
        else:
            st.error("The run stopped early. Check the terminal for details.")
