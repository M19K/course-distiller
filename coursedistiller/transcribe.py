"""Video -> text -> distilled notes, via the provider layer (local or cloud)."""
import glob
import json
import os
import subprocess

from . import providers


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
                providers.transcribe_audio(cfg, apath, tpath)
            if os.path.exists(apath):
                os.remove(apath)  # transcript is saved; audio no longer needed
            transcript = open(tpath).read().strip()
            dist = providers.distill(cfg, transcript) if cfg.distill["enabled"] else transcript
            if dist:
                open(dpath, "w").write(dist)
                done += 1
        except Exception as e:
            progress(phase="transcribe", msg=f"skip {pid}: {str(e)[:60]}")
        progress(phase="transcribe", done=done, total=min(cap, len(todo)), msg=f"{done} videos")
    return done
