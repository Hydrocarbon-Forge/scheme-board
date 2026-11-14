<h1 align="center">Scheme Board</h1>

<p align="center"><b>Capture, tag, score, connect and visualize money-making ideas.</b></p>

<p align="center">
A small, self-hosted board for collecting business and side-hustle ideas, scoring them, and seeing how they relate. Python standard library and SQLite only.
</p>

<p align="center">
<a href="LICENSE"><img alt="license: MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
</p>

<p align="center">
<a href="#quick-start">Quick start</a> · <a href="#features">Features</a> · <a href="#how-it-works">How it works</a> · <a href="#testing">Testing</a> · <a href="#license">License</a>
</p>

---

## What it is

Scheme Board is a single-machine web app. `server.py` runs a JSON API and serves a static site from `site/`. Ideas are stored in SQLite. An optional runner, `analyze.py`, sends each new idea to an OpenAI-compatible chat endpoint, which fills in a summary, category, tags, scores, connections and themes. There is no frontend framework and no build step.

## Features

- **Ideas.** Create ideas through `POST /api/ideas` or the "+ New Idea" form. Title and raw description are required. Owner, category and initial status are optional.
- **Status lifecycle.** `raw`, `developed`, `testing`, `being_built`, `proven`, `dead`. Status can be changed from the list and the detail panel (both use `PATCH`).
- **Filters.** Category, status, free-text search and "hide seeded", shared across views.
- **List view.** One row per idea with category, status, owner, scores and age. Clicking a row opens a detail panel.
- **Map view.** Canvas force-directed graph. Node radius follows the opportunity score, and edges are coloured by connection type.
- **Stats view.** Counts by status and category, the top 10 opportunities, the themes table and recent analysis runs.
- **Opportunity score.** `ceiling + moat - capital - effort - risk`, using the 1 to 5 scores. It is only computed when all seven scores are present.
- **Auto refresh.** The UI reloads its data every 30 seconds. If the server cannot be reached, a banner is shown.
- **Sample data.** `seed.py` inserts 10 sample ideas marked as seeded. It skips the insert if the seeded ideas are already present.

> **Security:** the server has no authentication and binds to `0.0.0.0` on port 8902. Run it only on a network you trust.

## Quick start

Requirements: Python 3. The project uses the standard library only, so there is nothing to `pip install`.

```sh
cd scheme-board
python3 seed.py                     # optional: 10 sample ideas
python3 server.py                   # API and static site on port 8902
```

Open the board at `http://localhost:8902/static/index.html`.

The root path (`/`) and `/index.html` redirect to a separate console on port 8903. That console is not part of this repository.

`./run.sh` starts the same server in the foreground and appends its output to `data/server.log`.

### Optional: LLM analysis

`analyze.py` reads its endpoint and model name from the `LLM_ENDPOINT` and `LLM_MODEL` constants at the top of the file. Edit them to point at your own OpenAI-compatible chat server, then run:

```sh
python3 analyze.py --check          # connectivity check against the endpoint
python3 analyze.py                  # process pending analyses (default limit 5)
```

## How it works

| File | Role |
|---|---|
| `server.py` | HTTP API and static file server (`ThreadingHTTPServer`, port 8902) |
| `db.py` | SQLite schema (WAL mode), CRUD helpers, opportunity score and stats |
| `analyze.py` | Runs pending analyses through an OpenAI-compatible chat endpoint and writes the results back |
| `seed.py` | Inserts 10 sample ideas, marked `seeded` |
| `test_smoke.py` | End-to-end smoke test of the running API |
| `run.sh` | Starts `server.py` and appends its output to `data/server.log` |
| `site/` | `index.html`, `app.js` and `style.css`: the vanilla JS interface |
| `data/` | SQLite database (`board.db`) and log files |

**Data flow.** A new idea is stored with a `pending` row in `analysis_runs`. `analyze.py` picks up pending rows, asks the LLM for analysis, and then updates the idea, its connections and its themes. If the LLM output cannot be parsed, the run is marked `failed` and the error is recorded.

### API

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Health check; reports the database path |
| `GET /api/ideas` | List ideas. Query parameters: `status`, `category`, `tag`, `q`, `hide_seeded`, `limit`, `offset` |
| `POST /api/ideas` | Create an idea. Body: `title` and `raw` are required; `owner`, `category`, `tags`, `scores`, `status` are optional |
| `GET /api/ideas/{id}` | Get one idea |
| `PATCH /api/ideas/{id}` | Partial update |
| `DELETE /api/ideas/{id}` | Delete an idea |
| `GET /api/connections` | All connections between ideas |
| `GET /api/themes` | All themes |
| `GET /api/stats` | Counts, top opportunities and newest ideas |
| `GET /api/analysis?limit=20` | Recent analysis runs |

## Testing

With the server running on port 8902, run:

```sh
python3 test_smoke.py
```

The script exits with 0 on success and non-zero on failure. It creates, reads, updates and deletes a test idea, and checks the stats endpoint. It also reports whether `analyze.py` imports correctly; this is informational only.

## License

MIT. See [LICENSE](LICENSE).
