"""CLI entrypoint. Emits progress as JSON lines to stdout and (optionally) a progress file."""
import argparse
import json

from .config import Config
from . import pipeline


def main():
    ap = argparse.ArgumentParser(description="CourseMind: turn a course you own into a knowledge base")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--progress-file", default=None)
    args = ap.parse_args()

    cfg = Config(args.config)
    pf = open(args.progress_file, "a") if args.progress_file else None

    def progress(**k):
        line = json.dumps(k)
        print(line, flush=True)
        if pf:
            pf.write(line + "\n"); pf.flush()

    pipeline.run(cfg, progress)


if __name__ == "__main__":
    main()
