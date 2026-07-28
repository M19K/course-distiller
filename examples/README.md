# Worked example

A concrete run, start to finish — so you know what to expect before pointing it at a real course.

## 1. Configure

Copy the sample config and edit the two `site` values for the course *you* have access to:

```bash
cp examples/demo-config.yaml config.yaml
# edit config.yaml: site.base_url and site.product_slug
```

Find those two values from any lesson URL of your course:

```
https://learn.example-academy.com / products / product-management-101 / categories / 4408 / posts / 91422
└────────── base_url ───────────┘            └──── product_slug ────┘
```

Notice `max_videos: 3` in the sample — a good habit: transcribe a few videos first, confirm the output
looks right, then set it to `0` for the full run.

## 2. Run

```bash
python -m coursedistiller.run --config config.yaml
# ...or the web UI: streamlit run app.py
```

A browser opens — log in to your course, and it takes over from there. You'll see progress like:

```
{"phase": "map", "done": 12, "total": 34, "msg": "212 posts found"}
{"phase": "harvest", "done": 180, "total": 340, "msg": "180 lessons"}
{"phase": "transcribe", "done": 3, "total": 3, "msg": "3 videos"}
{"phase": "extract", "done": 18, "total": 18, "msg": "16 extracted"}
{"phase": "done", "msg": "Done. Knowledge base ready in ./output"}
```

## 3. Output you should expect

```
output/
├── _INDEX.md                         # clickable map of every lesson
├── PROTOCOLS.md                      # all contacts, forms, links aggregated
├── lessons/
│   ├── module-1-getting-started/
│   │   ├── 001-welcome.md
│   │   └── 002-the-framework.md
│   └── module-2-discovery/
│       └── ...
└── notebooklm/                       # ← upload THIS folder to one NotebookLM notebook
    ├── 00 - Program Protocols & Navigation.md
    ├── module-1-getting-started.md
    └── module-2-discovery.md
```

Drop the whole `notebooklm/` folder into a single NotebookLM notebook and start asking questions.

## 4. What a compiled lesson looks like

See [`sample-lesson.md`](sample-lesson.md) for a representative output — one lesson with its portal
text, distilled video transcript, extracted attachment text, and verbatim links all in one file.
