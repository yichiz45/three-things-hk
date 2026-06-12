# Three Things — Hong Kong

A weekly English-language cultural brief: three things worth your time in Hong Kong,
machine-gathered, human-judged. Curated by [ASP — A Singular Project](https://asingularproject.com).

The pipeline is deliberately boring: a scheduled script gathers what Hong Kong's
cultural institutions publish, an AI pre-filter drafts a shortlist, and a human editor
makes the final three calls. The taste is the product; the automation just clears the desk.

## Architecture

```
sources.yaml ──► scripts/fetch.py ──► data/events.json
                                          │
                 ANTHROPIC_API_KEY        ▼
                 scripts/curate.py ──► data/shortlist.json
                                          │   (machine drafts ~15 candidates)
                          editor, weekly  ▼   (~10 minutes, GitHub web editor)
                                     docs/picks.json
                                          │
                          GitHub Pages    ▼
                                     docs/index.html
```

## Setup (one-time, ~15 minutes)

1. **Create a GitHub repo** and push this folder.
2. **Add the API key**: repo → Settings → Secrets and variables → Actions →
   New repository secret → name `ANTHROPIC_API_KEY`.
3. **Enable Pages**: Settings → Pages → Deploy from branch → branch `main`, folder `/docs`.
4. **Test the pipeline**: Actions tab → "Weekly fetch & curate" → Run workflow.
   Check `data/shortlist.json` after it finishes.

It then runs every Monday at 10:00 HKT automatically.

## Weekly workflow (the 10-minute editor pass)

1. Monday morning: open `data/shortlist.json` — the machine's ~15 candidates with draft blurbs.
2. Pick three. Rewrite the blurbs in your own voice (the drafts are scaffolding, not copy).
3. Edit `docs/picks.json` in the GitHub web editor: update `week_of`, bump `issue`, paste your picks. Overflow weeks: put extra items in the optional `more` array — they render as a compact list under the three tickets.
4. Commit. The site updates itself.

## Local run

```
pip install -r requirements.txt
python scripts/fetch.py
ANTHROPIC_API_KEY=sk-... python scripts/curate.py
```

## Adding sources

Edit `sources.yaml`. Three source types are supported: `jsonld` (schema.org Event data
embedded in pages — most modern venue sites), `ics` (calendar feeds), `rss`. A failing
source is logged and skipped; it never breaks the run. Venue sites change their markup
without notice — if a source starts returning 0 events, check whether the URL or page
structure moved.

## Editorial line

In: curatorial intent, specificity to Hong Kong, relevance to people who think about
culture professionally. Out: mall activations, tourist-board energy, anything whose
description is pure marketing. One sentence per pick, no exclamation marks.
