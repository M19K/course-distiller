"""Orchestrator. Two gated stages so the user can see the estimate before the expensive run:
  crawl_and_estimate  ->  (review the plan)  ->  finish
"""
from . import crawl as _crawl
from . import transcribe as _transcribe
from . import extract as _extract
from . import compile as _compile
from . import bundle as _bundle
from . import estimate as _estimate


def crawl_and_estimate(cfg, progress=lambda **k: None):
    _crawl.crawl(cfg, progress)                       # resumable: skips if already crawled
    plan = _estimate.estimate(cfg, progress)
    progress(phase="plan", **plan)
    return plan


def finish(cfg, progress=lambda **k: None):
    if cfg.video["enabled"]:
        _transcribe.transcribe(cfg, progress)
    if cfg.attachments["extract_text"]:
        _extract.extract(cfg, progress)
    _compile.compile_corpus(cfg, progress)
    _bundle.bundle(cfg, progress)
    progress(phase="done", msg=f"Done. Knowledge base ready in {cfg.output}")


def run(cfg, progress=lambda **k: None, plan_only=False):
    progress(phase="start", msg="Starting course-distiller")
    crawl_and_estimate(cfg, progress)
    if plan_only:
        progress(phase="plan_done", msg="Estimate ready — review before the full run")
        return
    finish(cfg, progress)
