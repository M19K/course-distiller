"""Pre-flight estimate: how long will this take, and (for cloud providers) what will it cost?

Reads each video's real duration from Wistia, then projects time + cost for the chosen providers.
Rough by design — meant to set expectations, not to bill. Rates are approximate (2025) and editable.
"""
import concurrent.futures
import glob
import json
import os
import urllib.request

# audio-realtime multiplier: wall_seconds ≈ audio_seconds / SPEED
TRANSCRIBE_SPEED = {"local": 8, "groq": 25, "openai": 15}
# transcription cost, USD per hour of audio
TRANSCRIBE_USD_PER_HR = {"local": 0.0, "groq": 0.04, "openai": 0.36}
# distillation cost, USD per 1M tokens (input, output)
DISTILL_USD_PER_MTOK = {"local": (0.0, 0.0), "openai": (0.15, 0.60), "anthropic": (0.80, 4.0),
                        "gemini": (0.075, 0.30), "openrouter": (0.15, 0.60)}


def _duration(wid):
    try:
        r = urllib.request.urlopen(f"https://fast.wistia.com/embed/medias/{wid}.json", timeout=15)
        return json.load(r).get("media", {}).get("duration", 0) or 0
    except Exception:
        return 0


def estimate(cfg, progress=lambda **k: None):
    recs = {}
    for f in sorted(glob.glob(os.path.join(cfg.shards, "*.json"))):
        for r in json.load(open(f)):
            recs[r["pid"]] = r
    vids = [r for r in recs.values() if r.get("wistia")]

    durs = []
    if cfg.video["enabled"] and vids:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for i, d in enumerate(ex.map(lambda r: _duration(r["wistia"]), vids)):
                durs.append(d)
                progress(phase="estimate", done=i + 1, total=len(vids), msg="measuring video lengths")
    audio_sec = sum(durs)
    audio_hr = audio_sec / 3600

    tp = cfg.video.get("transcribe_provider", "local")
    dp = cfg.distill.get("provider", "local")
    video_on = bool(cfg.video["enabled"])
    distill_on = bool(cfg.distill["enabled"])

    transcribe_min = (audio_sec / TRANSCRIBE_SPEED.get(tp, 8)) / 60 if video_on else 0
    t_cost = audio_hr * TRANSCRIBE_USD_PER_HR.get(tp, 0) if video_on else 0

    in_tok = audio_sec * 2.2                    # ~2.2 transcript tokens per second of speech
    out_tok = in_tok * 0.35                      # distillation ~3:1
    ci, co = DISTILL_USD_PER_MTOK.get(dp, (0, 0)) if (video_on and distill_on) else (0, 0)
    d_cost = in_tok / 1e6 * ci + out_tok / 1e6 * co
    distill_min = (len(vids) * 0.5) if (video_on and distill_on and dp == "local") else 0

    plan = {
        "lessons": len(recs), "videos": len(vids), "audio_hours": round(audio_hr, 1),
        "transcribe_provider": tp, "distill_provider": dp,
        "est_minutes": int(round(transcribe_min + distill_min + 2)),  # +2 for crawl/compile
        "est_cost_usd": round(t_cost + d_cost, 2),
    }
    return plan


def format_plan(p):
    hrs = p["est_minutes"] / 60
    time_str = f"~{p['est_minutes']} min" if p["est_minutes"] < 90 else f"~{hrs:.1f} hours"
    cost_str = "free (all local)" if p["est_cost_usd"] == 0 else f"~${p['est_cost_usd']:.2f}"
    return (f"{p['lessons']} lessons · {p['videos']} videos · {p['audio_hours']} hrs of audio\n"
            f"Transcription: {p['transcribe_provider']}   Distillation: {p['distill_provider']}\n"
            f"Estimated time: {time_str}   Estimated cost: {cost_str}")
