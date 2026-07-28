"""Assemble harvested records + transcripts + attachment text into a markdown corpus.
Groups lessons by their course section (category). Writes lessons/, _INDEX.md, PROTOCOLS.md."""
import glob
import json
import os
import re
from collections import defaultdict


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", (t or "").lower()).strip("-")[:60] or "lesson"


def _clean_title(r):
    t = (r.get("title") or "").strip()
    if not t:
        for line in (r.get("content") or "").split("\n"):
            if line.strip():
                t = line.strip(); break
    return re.sub(r"\s+", " ", t)[:120] or ("post-" + r["pid"])


def _order(r):
    t = _clean_title(r); m = re.match(r"\s*\(?(\d+)(?:\.(\d+))?", t)
    return (int(m.group(1)) if m else 999, int(m.group(2)) if (m and m.group(2)) else 0, t)


def compile_corpus(cfg, progress=lambda **k: None):
    recs = {}
    for f in sorted(glob.glob(os.path.join(cfg.shards, "*.json"))):
        for r in json.load(open(f)):
            pid = r["pid"]
            if pid not in recs or len(r.get("content", "")) > len(recs[pid].get("content", "")):
                recs[pid] = r
    records = list(recs.values())

    # attachment extracted-text index
    atx = {}
    for tf in glob.glob(os.path.join(cfg.attachments_text, "*.md")):
        atx[_norm(os.path.splitext(os.path.basename(tf))[0])] = tf

    def attach_text(name):
        k = _norm(os.path.splitext(name)[0])
        if not k:
            return None
        if k in atx:
            return atx[k]
        for kk, vv in atx.items():
            if kk and (kk.startswith(k[:24]) or k.startswith(kk[:24])):
                return vv
        return None

    groups = defaultdict(list)
    for r in records:
        groups[r.get("catTitle") or "Uncategorized"].append(r)

    os.makedirs(cfg.lessons, exist_ok=True)
    index = ["# Course Knowledge Base — Lesson Index\n", f"_{len(records)} lessons across {len(groups)} sections._\n"]
    proto = {"emails": set(), "forms": set(), "ext": set()}

    for grp in sorted(groups):
        lessons = sorted(groups[grp], key=_order)
        gdir = os.path.join(cfg.lessons, _slug(grp) or "section")
        os.makedirs(gdir, exist_ok=True)
        index.append(f"\n## {grp}  ({len(lessons)} lessons)\n")
        for i, r in enumerate(lessons, 1):
            title = _clean_title(r)
            fn = f"{i:03d}-{_slug(title)}.md"
            url = cfg.post_url(r["cat"], r["pid"])
            ext = [l for l in r.get("links", []) if not l.get("internal")]
            intl = [l for l in r.get("links", []) if l.get("internal")]
            L = ["---", f"title: {json.dumps(title)}", f"section: {json.dumps(grp)}", f"pid: {r['pid']}",
                 f"url: {url}", f"has_video: {str(bool(r.get('wistia'))).lower()}",
                 f"attachments: {len(r.get('attachments', []))}", "---", "", f"# {title}", ""]
            L.append((r.get("content") or "").strip() or "_(no text body — see video/attachments)_")
            if r.get("wistia"):
                dp = os.path.join(cfg.transcripts, r["pid"] + ".distilled.md")
                L.append("\n## Video")
                L.append("\n### Transcript (distilled)\n\n" + open(dp, encoding="utf-8", errors="replace").read().strip()
                         if os.path.exists(dp) else "\n_transcript pending_")
            if ext:
                L.append("\n## Resource Links"); L += [f"- [{l['t']}]({l['h']})" for l in ext]
            if r.get("attachments"):
                L.append("\n## Attachments")
                for a in r["attachments"]:
                    L.append(f"- **{a['name']}** — `{a['url']}`")
                    tf = attach_text(a["name"])
                    if tf:
                        L.append(f"\n### Extracted text — {a['name']}\n\n"
                                 + open(tf, encoding="utf-8", errors="replace").read().strip()[:200000] + "\n")
            if intl:
                L.append("\n## Related lessons"); L += [f"- {l['t']}" for l in intl[:20]]
            open(os.path.join(gdir, fn), "w").write("\n".join(L))
            index.append(f"- [{title}]({_slug(grp)}/{fn})" + ("  [video]" if r.get("wistia") else "")
                         + ("  [files]" if r.get("attachments") else ""))
            for l in ext:
                proto["ext"].add(l["h"])
                if "google.com/forms" in l["h"].lower() or "forms.gle" in l["h"].lower():
                    proto["forms"].add(l["h"])
            for m in re.finditer(r"[\w.+-]+@[\w-]+\.[\w.-]+", r.get("content", "")):
                proto["emails"].add(m.group(0))

    open(os.path.join(cfg.output, "_INDEX.md"), "w").write("\n".join(index))
    P = ["# Program Navigation & Protocols\n", "_Auto-aggregated across all lessons._\n", "## Contacts (emails in text)"]
    P += [f"- {c}" for c in sorted(proto["emails"])] or ["- (none)"]
    P += ["\n## Forms"] + ([f"- {u}" for u in sorted(proto["forms"])] or ["- (none)"])
    P += ["\n## All external resource links"] + [f"- {u}" for u in sorted(proto["ext"])]
    open(os.path.join(cfg.output, "PROTOCOLS.md"), "w").write("\n".join(P))
    progress(phase="compile", msg=f"{len(records)} lessons compiled into {len(groups)} sections")
    return len(records), len(groups)
