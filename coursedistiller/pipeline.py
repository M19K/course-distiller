"""End-to-end orchestrator: crawl -> transcribe -> extract -> compile -> bundle."""
from . import crawl as _crawl
from . import transcribe as _transcribe
from . import extract as _extract
from . import compile as _compile
from . import bundle as _bundle


def run(cfg, progress=lambda **k: None):
    progress(phase="start", msg="Starting course-distiller")
    _crawl.crawl(cfg, progress)
    if cfg.video["enabled"]:
        _transcribe.transcribe(cfg, progress)
    if cfg.attachments["extract_text"]:
        _extract.extract(cfg, progress)
    _compile.compile_corpus(cfg, progress)
    _bundle.bundle(cfg, progress)
    progress(phase="done", msg=f"Done. Knowledge base ready in {cfg.output}")
