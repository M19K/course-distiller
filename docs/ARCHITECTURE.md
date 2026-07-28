# Architecture

CourseMind is a small orchestration layer (~500 lines) over battle-tested tools. The design
priorities were: **local-first, resumable, and correct on branching course structures.**

## Data flow

```
your browser ──▶ crawl.py ──▶ work/harvest_shards/*.json ──┬──▶ transcribe.py ──▶ work/transcripts/*.distilled.md
 (you log in)   (Playwright)   (one record per lesson)      ├──▶ (attachments) ──▶ extract.py ──▶ work/attachments_text/*.md
                                                             └──▶ compile.py ──▶ output/lessons/**/*.md ──▶ bundle.py ──▶ output/notebooklm/*.md
```

Each stage reads the previous stage's files and writes its own — so any stage can be re-run
independently, and a crash never loses completed work.

## Components

| Module | Responsibility |
|---|---|
| `config.py` | Loads `config.yaml` over defaults; resolves all paths and URL templates |
| `crawl.py` | Playwright browser + authenticated `fetch()`; graph-closure crawl; HTML→markdown parse; attachment download |
| `transcribe.py` | `yt-dlp` audio → Whisper (mlx or openai) → local-LLM distillation |
| `extract.py` | PDF/OCR/xlsx/pptx/docx → text |
| `compile.py` | Assembles records + transcripts + attachment text into per-lesson markdown |
| `bundle.py` | Concatenates per-section bundles for NotebookLM |
| `pipeline.py` / `run.py` | Orchestrator + CLI with a progress callback |
| `app.py` | Streamlit UI: config form → subprocess run → live progress → download |

## Key design decisions

**1. Crawl via authenticated `fetch()`, not page navigation.**
Once you're logged in, the browser can `fetch()` any same-origin lesson URL and get its full HTML
without navigating. That's an order of magnitude faster and gentler than clicking through every page,
and it reuses your session so there's no credential handling.

**2. Graph closure, not a flat list.**
Real courses branch — a lesson links to a "prep-work" section that isn't in the main menu. The crawler
treats the course as a **graph**: it seeds from the category listing, then follows in-lesson links,
adding any newly discovered lessons to the queue until the frontier is empty. (On the first real course,
this recovered ~370 lessons a flat crawl would have missed.)

**3. Local models, taking turns.**
Whisper and the LLM are both memory-hungry. Rather than hold both resident, the pipeline runs them
**sequentially** and lets Ollama unload the LLM between videos — which is what lets a 24 GB machine run a
20B model *and* Whisper without falling over. (Memory is the binding constraint; see the case study.)

**4. Resumability is a file-existence check.**
Every expensive step writes a marker file (`<id>.distilled.md`, `<stem>.md`). Re-running skips anything
already produced. A multi-hour transcription run can be interrupted and resumed with zero rework.

**5. The UI shells out to the CLI.**
Streamlit and Playwright's sync API don't share an event loop cleanly, so the UI launches the pipeline
as a **subprocess** and tails a JSON-lines progress file. This keeps the UI responsive and the core
runnable head-less.

## Fidelity contract

Load-bearing facts — **links, emails, forms, deadlines** — are always preserved **verbatim**. Only
prose and video transcripts are distilled (summarized), and full raw transcripts are retained on disk.
So nothing that matters operationally is ever paraphrased away.

## Extending to other platforms

The Kajabi/Wistia specifics live in two places: the URL template (`config.py`) and the HTML parser
(`crawl.py`'s `PARSE_JS`). A new platform is an adapter that provides those two — the rest of the
pipeline (transcribe → distill → extract → compile → bundle) is platform-agnostic.
