"""Video -> text -> distilled notes.  yt-dlp (audio) -> Whisper -> local LLM (Ollama)."""
import glob
import json
import os
import re
import subprocess
import urllib.request


def _load_records(cfg):
    recs = {}
    for f in sorted(glob.glob(os.path.join(cfg.shards, "*.json"))):
        for r in json.load(open(f)):
            pid = r["pid"]
            if pid not in recs or len(r.get("content", "")) > len(recs[pid].get("content", "")):
                recs[pid] = r
    return recs


def _priority_index(title, priority):
    for i, key in enumerate(priority):
        if key.lower() in (title or "").lower():
            return i
    return len(priority)


def _whisper(cfg, audio, out_txt):
    model = cfg.video["whisper_model"]
    try:  # Apple Silicon fast path
        import mlx_whisper
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=model)
        open(out_txt, "w").write(r["text"]); return
    except Exception:
        pass
    import whisper  # openai-whisper fallback
    r = whisper.load_model(model if "/" not in model else "small").transcribe(audio)
    open(out_txt, "w").write(r["text"])


def _distill(cfg, text):
    chunks = [text[i:i + cfg.distill["chunk_chars"]] for i in range(0, len(text), cfg.distill["chunk_chars"])] or [""]
    outs = []
    for i, ch in enumerate(chunks):
        prompt = ("Distill this course video transcript into tight markdown study notes. Capture key "
                  "concepts, frameworks, step-by-step methods, concrete examples, and any resources/links/"
                  "action items mentioned VERBATIM. Omit filler and repetition. Output only the notes."
                  + (f" (Part {i+1}/{len(chunks)})" if len(chunks) > 1 else "") + "\n\nTRANSCRIPT:\n" + ch)
        req = {"model": cfg.distill["model"], "stream": False, "think": cfg.distill["reasoning"],
               "options": {"num_predict": cfg.distill["max_tokens"], "temperature": 0.2}, "prompt": prompt}
        out = ""
        for _ in range(2):
            try:
                resp = urllib.request.urlopen(cfg.distill["ollama_url"].rstrip("/") + "/api/generate",
                                              json.dumps(req).encode(), timeout=400)
                out = json.loads(resp.read()).get("response", "").strip()
                if out:
                    break
            except Exception:
                out = ""
        outs.append(out)
    return "\n\n".join(o for o in outs if o).strip()


def transcribe(cfg, progress=lambda **k: None):
    recs = _load_records(cfg)
    work = [r for r in recs.values() if r.get("wistia")]
    work.sort(key=lambda r: (_priority_index(r.get("catTitle", ""), cfg.video["priority"]), r.get("title", "")))
    todo = [r for r in work if not os.path.exists(os.path.join(cfg.transcripts, r["pid"] + ".distilled.md"))]
    cap = cfg.video["max_videos"] or len(todo)
    done = 0
    for r in todo[:cap]:
        pid, wid = r["pid"], r["wistia"]
        apath = os.path.join(cfg.audio, pid + ".mp3")
        tpath = os.path.join(cfg.transcripts, pid + ".txt")
        dpath = os.path.join(cfg.transcripts, pid + ".distilled.md")
        try:
            if not os.path.exists(tpath):
                if not os.path.exists(apath):
                    subprocess.run(["yt-dlp", "-f", "mp4-224p/worst", "-x", "--audio-format", "mp3", "--no-warnings",
                                    "-o", os.path.join(cfg.audio, pid + ".%(ext)s"), f"wistia:{wid}"],
                                   check=True, capture_output=True, timeout=600)
                _whisper(cfg, apath, tpath)
            if os.path.exists(apath) and not cfg.fidelity["keep_full_transcripts"]:
                os.remove(apath)
            elif os.path.exists(apath):
                os.remove(apath)  # audio always removable; the .txt transcript is kept
            transcript = open(tpath).read().strip()
            dist = _distill(cfg, transcript) if cfg.distill["enabled"] else transcript
            if dist:
                open(dpath, "w").write(dist)
                done += 1
        except Exception as e:
            progress(phase="transcribe", msg=f"skip {pid}: {str(e)[:60]}")
        progress(phase="transcribe", done=done, total=min(cap, len(todo)), msg=f"{done} videos")
    return done
