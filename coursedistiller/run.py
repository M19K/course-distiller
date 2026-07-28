"""CLI. Emits progress as JSON lines. Use --plan to crawl + estimate without transcribing."""
import argparse
import json

from .config import Config
from . import pipeline
from .estimate import format_plan


def main():
    ap = argparse.ArgumentParser(description="course-distiller: turn a course you own into a knowledge base")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--progress-file", default=None)
    ap.add_argument("--plan", action="store_true", help="crawl + estimate only, then stop (no transcription)")
    args = ap.parse_args()

    cfg = Config(args.config)
    pf = open(args.progress_file, "a") if args.progress_file else None

    def progress(**k):
        line = json.dumps(k)
        print(line, flush=True)
        if pf:
            pf.write(line + "\n"); pf.flush()
        if k.get("phase") == "plan":
            print("\n=== ESTIMATE ===\n" + format_plan(k) + "\n================\n", flush=True)

    pipeline.run(cfg, progress, plan_only=args.plan)


if __name__ == "__main__":
    main()
