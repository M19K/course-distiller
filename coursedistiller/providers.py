"""Provider layer: transcription and distillation, LOCAL or CLOUD.

API keys are read from environment variables only (never from config files):
  GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY
"""
import json
import os
import urllib.request

# sensible, cheap defaults per provider — override with config `model`
DISTILL_DEFAULT_MODEL = {
    "local": "gpt-oss:20b", "openai": "gpt-4o-mini", "anthropic": "claude-3-5-haiku-latest",
    "gemini": "gemini-1.5-flash", "openrouter": "openai/gpt-4o-mini",
}
TRANSCRIBE_CLOUD = {  # provider -> (endpoint, model)
    "groq": ("https://api.groq.com/openai/v1/audio/transcriptions", "whisper-large-v3"),
    "openai": ("https://api.openai.com/v1/audio/transcriptions", "whisper-1"),
}
_ENV = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def _key(provider):
    k = os.environ.get(_ENV.get(provider, ""), "")
    if not k:
        raise RuntimeError(f"{provider}: set {_ENV.get(provider)} in your environment")
    return k


# ─────────────────────────── transcription ───────────────────────────
def transcribe_audio(cfg, audio_path, out_txt):
    prov = cfg.video.get("transcribe_provider", "local")
    if prov == "local":
        _whisper_local(cfg, audio_path, out_txt)
    elif prov in TRANSCRIBE_CLOUD:
        _whisper_cloud(prov, audio_path, out_txt)
    else:
        raise ValueError(f"unknown transcribe_provider: {prov}")


def _whisper_local(cfg, audio, out_txt):
    model = cfg.video["whisper_model"]
    try:  # Apple Silicon fast path
        import mlx_whisper
        open(out_txt, "w").write(mlx_whisper.transcribe(audio, path_or_hf_repo=model)["text"]); return
    except Exception:
        pass
    import whisper
    open(out_txt, "w").write(whisper.load_model(model if "/" not in model else "small").transcribe(audio)["text"])


def _whisper_cloud(provider, audio, out_txt):
    import requests
    url, model = TRANSCRIBE_CLOUD[provider]
    with open(audio, "rb") as f:
        r = requests.post(url, headers={"Authorization": f"Bearer {_key(provider)}"},
                          files={"file": f}, data={"model": model, "response_format": "text"}, timeout=900)
    r.raise_for_status()
    open(out_txt, "w").write(r.text if r.headers.get("content-type", "").startswith("text") else r.json()["text"])


# ─────────────────────────── distillation ───────────────────────────
_PROMPT = ("Distill this course video transcript into tight markdown study notes. Capture key concepts, "
           "frameworks, step-by-step methods, concrete examples, and any resources/links/action items "
           "mentioned VERBATIM. Omit filler and repetition. Output only the notes.")


def distill(cfg, text):
    prov = cfg.distill.get("provider", "local")
    model = cfg.distill.get("model") or DISTILL_DEFAULT_MODEL.get(prov, "")
    chunks = [text[i:i + cfg.distill["chunk_chars"]] for i in range(0, len(text), cfg.distill["chunk_chars"])] or [""]
    outs = []
    for i, ch in enumerate(chunks):
        part = f" (Part {i+1}/{len(chunks)})" if len(chunks) > 1 else ""
        prompt = f"{_PROMPT}{part}\n\nTRANSCRIPT:\n{ch}"
        out = ""
        for _ in range(2):
            try:
                out = (_ollama(cfg, prompt) if prov == "local" else _cloud_llm(prov, model, prompt, cfg)).strip()
                if out:
                    break
            except Exception as e:
                out = ""
                last = e
        outs.append(out)
    return "\n\n".join(o for o in outs if o).strip()


def _ollama(cfg, prompt):
    req = {"model": cfg.distill.get("model") or "gpt-oss:20b", "stream": False,
           "think": cfg.distill.get("reasoning", "low"),
           "options": {"num_predict": cfg.distill["max_tokens"], "temperature": 0.2}, "prompt": prompt}
    resp = urllib.request.urlopen(cfg.distill["ollama_url"].rstrip("/") + "/api/generate",
                                  json.dumps(req).encode(), timeout=400)
    return json.loads(resp.read()).get("response", "")


def _cloud_llm(provider, model, prompt, cfg):
    import requests
    mx = cfg.distill["max_tokens"]
    if provider in ("openai", "openrouter"):
        url = ("https://api.openai.com/v1/chat/completions" if provider == "openai"
               else "https://openrouter.ai/api/v1/chat/completions")
        r = requests.post(url, headers={"Authorization": f"Bearer {_key(provider)}"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": mx, "temperature": 0.2}, timeout=400)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]
    if provider == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": _key(provider), "anthropic-version": "2023-06-01"},
                          json={"model": model, "max_tokens": mx,
                                "messages": [{"role": "user", "content": prompt}]}, timeout=400)
        r.raise_for_status(); return r.json()["content"][0]["text"]
    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={_key(provider)}"
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=400)
        r.raise_for_status(); return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise ValueError(f"unknown distill provider: {provider}")
