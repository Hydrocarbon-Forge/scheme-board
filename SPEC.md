# Scheme Board — build spec

A local tool to capture, tag, score, connect, and visualize money-making / business ideas.
Built by the agent working in this directory. C6 verifies after.

## Product

1. A SQLite database of "schemes" (money-making ideas).
2. A Python (stdlib-only) HTTP API + static site server on port **8902**, bound **0.0.0.0**.
3. A browser site (vanilla JS, no build step) that visualizes everything as an interactive graph + list + stats.
4. An LLM analysis runner that, when a new idea lands, compares it against all existing ideas and records new connections, tags, and themes.

## Environment facts (verified — do not guess)

- Host: Linux, Python **3.14.7** (`python3`). `fastapi`/`flask`/`requests` are NOT installed. **Use stdlib only**: `sqlite3`, `urllib.request`, `http.server` (ThreadingHTTPServer), `json`. No pip installs, no node.
- Local LLM, OpenAI-compatible (llama.cpp), verified working:
  - `POST http://192.168.1.72:8080/v1/chat/completions`
  - `model`: `/home/nathan/Downloads/Qwen3.8-27B-NVFP4-MTP-HIGH.gguf` (exact string, it is a file path)
  - Body shape: `{"model": "<that path>", "messages": [{"role":"system",...},{"role":"user",...}], "temperature": 0.2, "max_tokens": 4096}`
  - Response: JSON `choices[0].message` with fields `content`, and possibly `reasoning_content`. The model is a reasoning model — `content` may be empty while `reasoning_content` carries the chain of thought. **Extract `content` if non-empty after stripping; else try `reasoning_content`; else HTTP 500.**
  - The model runs CPU-only and is slow (several tokens/sec). Requests for the full-DB analysis can take minutes. Use `timeout=600` on urllib.
  - JSON-in-prompt is unreliable on the first try: ask for ONLY a JSON array (no prose, no markdown), and parse defensively: strip code fences, find first `[`/`{` ... last `]`/`}`. On parse failure retry once with a stricter system prompt ("Output ONLY minified JSON. No prose."). If still failing, store `analysis_status='failed'` with the error and continue — never crash the pipeline.
- Frontend must work offline on the LAN: no CDN dependencies. No external fonts. One `site/index.html` + `site/app.js` + `site/style.css`.
- Port 8902 is currently free. Bind `0.0.0.0`.

## File layout (create exactly this)

```
scheme-board/
  SPEC.md            (this file — do not edit)
  C6_NOTES.md        (written by C6 — do not create or edit)
  server.py          (API + static file server)
  db.py              (sqlite schema + helpers; WAL mode)
  analyze.py         (LLM runner, importable + runnable as a script)
  seed.py            (inserts 10 sample ideas, tagged seeded=1)
  test_smoke.py      (end-to-end smoke test, exit 0 on success)
  run.sh             (starts server, logs to data/server.log)
  data/board.db      (created at first run)
  site/index.html site/app.js site/style.css
```

## Database schema (db.py creates it at import/startup, WAL mode)

```sql
CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  raw TEXT NOT NULL,                -- original raw description as given
  summary TEXT,                     -- one-paragraph normalized description (LLM or human)
  owner TEXT,                       -- who pitched it
  status TEXT NOT NULL DEFAULT 'raw' CHECK (status IN ('raw','developed','testing','being_built','proven','dead')),
  category TEXT,                    -- primary category (from taxonomy below)
  tags TEXT NOT NULL DEFAULT '[]',  -- JSON array of lowercase tags
  scores TEXT NOT NULL DEFAULT '{}',-- JSON object, see below
  seeded INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS connections (
  id INTEGER PRIMARY KEY,
  idea_a INTEGER NOT NULL, idea_b INTEGER NOT NULL,
  ctype TEXT NOT NULL,              -- parallel | complements | same_market | competes | extends
  strength REAL NOT NULL DEFAULT 0.5,-- 0..1
  note TEXT,                        -- one sentence why
  UNIQUE (idea_a, idea_b, ctype)
);
CREATE TABLE IF NOT EXISTS themes (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  idea_ids TEXT NOT NULL DEFAULT '[]' -- JSON array
);
CREATE TABLE IF NOT EXISTS analysis_runs (
  idea_id INTEGER NOT NULL,
  status TEXT NOT NULL,             -- pending | running | done | failed
  error TEXT,
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`ideas` UNIQUE-ish constraint on title is NOT required (duplicates are legal).

### Score fields (all 1..5 integers, null until scored)

- `capital` — capital required (5 = needs a lot)
- `effort` — effort required (5 = huge)
- `time_to_revenue` — months to first dollar (5 = slow)
- `ceiling` — revenue ceiling (5 = big)
- `difficulty` — technical/business difficulty (5 = hard)
- `moat` — defensibility if it works (5 = strong)
- `risk` — downside risk (5 = could lose a lot)

Stored as JSON in `ideas.scores`.

### Category taxonomy (closed set, LLM may also add new ones — lowercase snake_case)

`e_commerce, digital_product, service, content_media, ai_automation, trading_investing, real_world, community, other`

## API (server.py — stdlib only, ThreadingHTTPServer, port 8902)

JSON everywhere. CORS: add `Access-Control-Allow-Origin: *` and handle OPTIONS.

- `GET /api/ideas?status=&category=&tag=&q=&limit=&offset=` → list of idea objects (scores/tags parsed into JSON objects) with `total` count.
- `GET /api/ideas/{id}` → one idea.
- `POST /api/ideas` → body `{title, raw, owner?, status?, category?, tags?, scores?}`. Creates idea, inserts `analysis_runs (status='pending')`. Response: the created idea (201).
- `PATCH /api/ideas/{id}` → partial update of any column (tags/scores accepted as JSON objects, serialized to TEXT on write; `updated_at` bumped).
- `DELETE /api/ideas/{id}` → removes idea, its connections, analysis_runs (204).
- `GET /api/connections` → all edges: `{a, b, ctype, strength, note}`.
- `GET /api/themes` → all themes with idea_ids parsed.
- `GET /api/stats` → computed:
  - `counts`: total, by_status (all 6 keys, zero-filled), by_category, seeded_count
  - `top_opportunities`: top 10 ideas where scores are complete, ranked by `ceiling + moat - capital - effort - risk` (tie-break: higher moat first)
  - `newest`: last 5 ideas by created_at desc
- `GET /api/analysis?limit=20` → recent analysis_runs joined with idea title.
- `GET /` and `/static/*` → serves `site/` (`/` = index.html).
- `GET /api/health` → `{ok: true, db: <path>}`.

Every idea JSON object is: `{id, title, raw, summary, owner, status, category, tags[], scores{}, seeded, created_at, updated_at}`.

## Analysis runner (analyze.py)

`python3 analyze.py` — the CLI C6 (or a cron) invokes. Behavior:

1. Pick `analysis_runs` rows with `status='pending'` (oldest first, max 5 per run).
2. Mark `running`, run the LLM pass, set `done` or `failed` (+error).
3. Build the LLM prompt:
   - system: "You are a business analyst for a small team collecting money-making ideas. You will receive ONE new idea and ALL existing ideas (id, title, summary, category, tags). Respond with ONLY a JSON array of objects. No prose, no markdown."
   - Each object exactly: `{"idea_id": <int, the NEW idea's id>, "summary": "<≤40 word summary>", "category": "<taxonomy value>", "tags": ["lowercase", "..."], "scores": {"capital":1,"effort":1,"time_to_revenue":1,"ceiling":1,"difficulty":1,"moat":1,"risk":1}, "connections": [{"a": <new idea id or existing id>, "b": <other id>, "ctype": "parallel|complements|same_market|competes|extends", "strength": 0.0-1.0, "note": "<≤25 words why>"}, ...], "themes": [{"name": "<short theme name>", "description": "<≤30 words>", "new_idea": true|false}]}`
   - user: the new idea's title+raw+summary, then a numbered list of existing ideas as `"<id> | <category> | <title> | <summary> | tags: <tags>"`. Cap the list at the 40 most recent existing ideas; note if truncated.
   - If the DB has < 2 ideas, run with only the new idea (no connections possible).
4. Validate the parsed JSON: coerce types, clamp scores to 1..5 (drop missing fields), clamp strength to 0..1, ensure a<b for the stored edge (swap if needed), ctype in the allowed set. Discard malformed objects rather than crashing.
5. Write results: update the idea row (summary, category, tags, scores — only overwrite fields the LLM actually returned), upsert connections (UNIQUE on (a,b,ctype) — update strength/note if present), upsert themes (merge idea_ids if a theme with the same name exists; only add the new idea's id to existing themes when `new_idea` is true or the LLM's theme id list includes it — simplest correct rule: theme key = name, union idea ids).
6. Log each run's outcome to stdout (which idea, what changed, error if failed).

Make the LLM call function `llm_json(system, user)` reusable. Import-safe (main guard).

## Frontend (site/ — dark theme, forge/orange palette #FF8C42 accents, readable, no frameworks)

One page, three tabs: **Map**, **List**, **Stats**. Shared filter bar: category select, status select, text search, "hide seeded" checkbox. Filters apply across tabs.

- **Map**: canvas-based force-directed graph (write a small force sim yourself: repulsion + edge springs + centering, ~60 lines; run N ticks on load and on data change, no continuous animation needed — a few frames of settling is fine). Nodes = ideas: color by category (fixed palette map), radius = 8 + opportunity_score/2 (ideas without complete scores: radius 10), seeded ideas dashed circle outline. Edges = connections, line width by strength, color by ctype (parallel=#FF8C42, complements=#4CC9F0, same_market=#B5E48C, competes=#F25C54, extends=#B185DB). Hover node → tooltip with title + category; click node → right-side detail panel: title, owner, status (editable via select → PATCH), category, tags (click tag to filter), raw text, summary, all 7 scores as bars 1-5, connections list (each link clickable → jump to that node), themes it belongs to.
- **List** (THE primary view — users want a simple list of every idea with a way to mark progress): one row per idea: title, category chip, **status chip (color-coded, editable inline via a <select> with all 6 lifecycle values → PATCH)**, owner, tags, top-3 scores inline, age (created), updated. Rows group naturally by most-recently-updated; add a "sort: updated/created/score" control. Status legend in the tab header: `raw → developed → testing → being_built → proven | dead`. Row click → same detail panel. "New idea" button → modal form (title, description, owner, optional category) → POST → refresh all tabs.
- **Stats**:
  - counts by status (6 chips) and by category (chips with counts)
  - "opportunity ranking" table: top 10 by the same score formula as /api/stats, with the computed number and the 7 score bars
  - connections by type (5 bars)
  - themes table (name, description, idea count, clickable names)
  - recent analysis runs (idea title, status, time, error snippet)
- Data loading: on load fetch ideas + connections + themes + stats; refresh every 30s; refresh after any mutation. If fetch fails show a red "server unreachable" banner, keep last data.
- Mobile-friendly enough to read on a phone (list tab first on narrow screens).

## Seed (seed.py)

Insert **10** distinct, plausible, varied sample ideas (owner 'C6', seeded=1). Vary: status (at least one of each of raw/developed/testing/being_built), category (at least 5 of the 9), tags, and scores — half the seeds have complete scores, half partial/null scores. Titles should sound like real side-hustle / business schemes (e.g. an AI content repurposing agency, a niche job-board, a print-on-demand niche, a local service arbitrage, a paid community, a data-scraping lead-gen tool, a used-goods flip, a short-video licensing, a subscription box for a niche hobby, a white-label course). Give each a realistic `raw` paragraph (2-4 sentences). Do NOT run the analyzer on seeds — just insert.

## Smoke test (test_smoke.py)

Stdlib only (urllib). Starts nothing — expects a running server (C6 starts it). Steps: health ok; POST a test idea (title "SMOKE TEST IDEA", raw "smoke", owner "smoke") → 201 + id; GET it back; PATCH status → 'testing' and verify; GET /api/stats has total ≥ 1 and the smoke idea present in newest; GET /api/connections returns list; GET / (html) 200; GET /app.js 200; DELETE the smoke idea → subsequent GET 404. Print PASS/FAIL per step, exit 0 only if all pass.

Also verify the LLM path WITHOUT depending on it for exit status: if `analyze.py` is importable and `llm_json` is defined, print a note. (C6 runs a real single-idea LLM check separately.)

## run.sh

```
#!/bin/sh
cd "$(dirname "$0")"
exec python3 server.py >> data/server.log 2>&1
```

## Acceptance checklist (agent self-checks before finishing)

1. `python3 db.py` and `python3 seed.py` run clean twice (idempotent-ish; second seed run should be a no-op or print "already seeded").
2. Server starts, all endpoints respond per spec (curl sweep).
3. `python3 test_smoke.py` exits 0.
4. `python3 analyze.py --check` (add a `--check` flag: does ONE LLM call with a trivial prompt, prints the parsed result) works against the real endpoint.
5. No external dependencies import anywhere (`python3 -c "import server, db, analyze, seed"` clean).
6. Report: files created, endpoints verified, the one-idea LLM check output, anything skipped.

## Style

- Python: clean, typed where cheap, no over-abstraction. Keep functions short.
- Site: dark bg (#0E1116), panel #171C24, accent #FF8C42, text #E8EAED. Chips, bars, clean typography (system font stack). No icon libraries — use unicode.
- Do NOT create a README (C6 writes C6_NOTES.md). Do NOT start any server on any port other than 8902, and if starting one for tests, kill it before finishing.
