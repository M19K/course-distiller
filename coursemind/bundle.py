"""Consolidate per-section lesson markdown into one file per section -> notebooklm/.
NotebookLM caps source count, so a handful of section bundles beats hundreds of files."""
import glob
import os


def bundle(cfg, progress=lambda **k: None):
    os.makedirs(cfg.bundles, exist_ok=True)
    # include the protocols reference as a bundle so it uploads alongside
    proto = os.path.join(cfg.output, "PROTOCOLS.md")
    if os.path.exists(proto):
        open(os.path.join(cfg.bundles, "00 - Program Protocols & Navigation.md"), "w").write(open(proto).read())
    total = 0
    for grp in sorted(os.listdir(cfg.lessons)):
        d = os.path.join(cfg.lessons, grp)
        if not os.path.isdir(d):
            continue
        files = sorted(glob.glob(os.path.join(d, "*.md")))
        if not files:
            continue
        parts = [f"# {grp}\n\n_{len(files)} lessons, consolidated for NotebookLM._"]
        for f in files:
            parts.append("\n\n---\n\n" + open(f, encoding="utf-8", errors="replace").read().strip())
        open(os.path.join(cfg.bundles, grp.replace("/", "-") + ".md"), "w").write("\n".join(parts))
        total += len(files)
    progress(phase="bundle", msg=f"{total} lessons bundled -> {cfg.bundles}")
    return total
