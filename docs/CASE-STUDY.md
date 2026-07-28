# Case study: course-distiller

*A product write-up — the problem, the decisions, the trade-offs, and the outcome.*

## The problem I kept hitting

I enroll in online courses to level up, but the best ones are **video-and-PDF-heavy** — hours of
recordings and slide decks locked behind a login. That format is great for *watching* and terrible for
*learning on my terms*: I can't search it, can't ask it "what was the framework for X," and can't
review it at 3× speed the night before an interview. Modern tools like NotebookLM answer questions over
text beautifully — but only if you already have the text. The content existed; the *access pattern* was
broken.

**The job to be done:** *"Help me actually retain and retrieve what a course teaches, on my schedule,
without re-watching everything."*

## The insight

The value isn't downloading the course — plenty of tools do that. The value is **transforming** it:
turning passive video into *distilled, searchable notes* and merging it with the text and attachments
into one knowledge base an LLM can reason over. Download is a commodity; **distillation is the product.**

## Scoping — what I chose to build (and not build)

Rather than boil the ocean, I made explicit calls:

| Decision | Choice | Why |
|---|---|---|
| **Fidelity vs. usability** | *Distill* video transcripts, keep full transcripts on disk as backup | Verbatim 1.5-hr transcripts are unusable for study; distilled notes are the value. Zero-loss fallback removes the risk. |
| **Cost model** | 100% local (Whisper + a local LLM), **$0 API** | A pipeline that costs $50 per course won't get used. Local-first also keeps paid content private. |
| **Coverage vs. speed** | **Prioritize** the modules that matter first; defer low-signal recordings | Shipped usable value in hours, not days. Prioritization > completeness. |
| **Interface** | Local web UI over a raw CLI | The tool is only useful if a non-engineer can run it. |

Each of these is a *product* decision, not a technical one — trading fidelity, cost, coverage, and
effort against what the user actually needs.

## The hard part wasn't the happy path — it was verifying I hadn't silently failed

An unattended pipeline's biggest risk is **silent incompleteness**: it *looks* done while quietly
missing things. So I built a verification pass, and it earned its keep. On the first real run, my initial
attachment scan reported "15 lessons have files." A full audit revealed the truth: **94 lessons had
attachments — I'd been silently missing ~80.** Catching that was the difference between a corpus that
*felt* complete and one that *was*.

**Takeaway:** "the demo works" is not "the product is correct." Instrumenting for the failure you can't
see is a core product responsibility, not a QA afterthought.

## Trade-offs I accepted (and named)

- **Distillation is lossy** — mitigated by retaining full transcripts, but a real trade-off.
- **Local compute is the constraint** — transcription is memory-bound; long courses take time. I chose
  *free + private + slower* over *fast + paid + exposed*.
- **Platform coverage is narrow** — I built for the platform I needed first, with a clear seam for
  adapters, rather than a shallow "supports everything" that works nowhere well.

## Outcome

On its first real target — a ~700-lesson course — course-distiller produced a complete, verified,
queryable knowledge base: **every lesson's text, ~170 distilled video transcripts, ~140 attachment files
with their text extracted, and all links/contacts/forms** — for **$0**, entirely on-device, ready to
query in NotebookLM.

## What I'd do next

1. **Platform adapters** — generalize beyond Kajabi/Wistia (Teachable, Thinkific, Skool).
2. **Incremental sync** — re-run to pick up only new lessons.
3. **Quality signal** — surface a per-course "coverage %" so the user knows what, if anything, is thin.
4. **Distraction-free study mode** — spaced-repetition prompts generated from the distilled notes.

## Why this is a product-management artifact, not just code

It started from a **user problem**, not a technology. It required **scoping** under real constraints
(cost, compute, time), **naming trade-offs** instead of pretending they didn't exist, and **verifying
outcomes** rather than trusting the happy path. The code is the artifact; the *judgment* is the point.
