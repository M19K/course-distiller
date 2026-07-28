"""Configuration loader: merges config.yaml over sane defaults and exposes paths."""
import os
import yaml

DEFAULTS = {
    "site": {"base_url": "", "product_slug": ""},
    "output_dir": "./output",
    "work_dir": "./work",
    "crawl": {"pace_ms": 250, "top_categories": []},
    "video": {"enabled": True, "transcribe_provider": "local",
              "whisper_model": "mlx-community/whisper-large-v3-turbo", "priority": [], "max_videos": 0},
    "distill": {"enabled": True, "provider": "local", "ollama_url": "http://localhost:11434",
                "model": "", "reasoning": "low", "max_tokens": 2000, "chunk_chars": 9000},
    "attachments": {"download": True, "extract_text": True, "ocr_fallback": True},
    "fidelity": {"keep_full_transcripts": True},
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class Config:
    def __init__(self, path="config.yaml"):
        data = yaml.safe_load(open(path)) if os.path.exists(path) else {}
        self.d = _merge(DEFAULTS, data or {})
        if not self.site["base_url"] or not self.site["product_slug"]:
            raise ValueError("config: site.base_url and site.product_slug are required")
        for p in (self.work, self.output, self.shards, self.audio, self.transcripts,
                  self.attachments_dir, self.attachments_text, self.lessons, self.bundles):
            os.makedirs(p, exist_ok=True)

    # section access
    def __getattr__(self, k):
        d = object.__getattribute__(self, "d")
        if k in d:
            return d[k]
        raise AttributeError(k)

    # convenience paths
    @property
    def work(self): return os.path.abspath(self.d["work_dir"])
    @property
    def output(self): return os.path.abspath(self.d["output_dir"])
    @property
    def shards(self): return os.path.join(self.work, "harvest_shards")
    @property
    def audio(self): return os.path.join(self.work, "audio")
    @property
    def transcripts(self): return os.path.join(self.work, "transcripts")
    @property
    def attachments_dir(self): return os.path.join(self.work, "attachments")
    @property
    def attachments_text(self): return os.path.join(self.work, "attachments_text")
    @property
    def lessons(self): return os.path.join(self.output, "lessons")
    @property
    def bundles(self): return os.path.join(self.output, "notebooklm")

    def post_url(self, cat, pid):
        return (f"{self.site['base_url'].rstrip('/')}/products/{self.site['product_slug']}"
                f"/categories/{cat}/posts/{pid}")

    def category_url(self, cat):
        return (f"{self.site['base_url'].rstrip('/')}/products/{self.site['product_slug']}"
                f"/categories/{cat}")

    @property
    def product_url(self):
        return f"{self.site['base_url'].rstrip('/')}/products/{self.site['product_slug']}"
