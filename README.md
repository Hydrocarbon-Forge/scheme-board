# Scheme Board

Capture, tag, score, connect, and visualize money-making ideas.

**Live:** http://192.168.1.201:8902 (LAN) — served by `scheme-board.service` (systemd user service, `Restart=always`, linger on).

## Intake
Discord `#ideas` channel (under `operations`) — post an idea / ping C6. C6 asks a few
questions, then the idea lands on the board. The local LLM (`192.168.1.72:8080`,
Qwen3.8-27B) tags it, scores it (capital / effort / time_to_revenue / ceiling /
difficulty / moat / risk, 1-5), and records **connections** to existing ideas
(parallel / complements / same_market / competes / extends, with strength + note)
and **themes**. A 5-minute cron auto-runs any pending analysis, so connections are
drawn automatically.

## Views
- **List** (primary) — every idea with progress: `raw → developed → testing → being_built → proven` (or `dead`), inline status edit, filters (category / status / hide seeded), sort.
- **Map** — canvas graph; node size = opportunity score, edges = connections.
- **Stats** — status distribution, category distribution, top opportunities (score = ceiling + moat − capital − effort − risk).

## Ops
| Piece | Location |
|---|---|
| DB | `data/board.db` (SQLite) |
| API server | `python3 server.py` → `:8902`, systemd `scheme-board.service` |
| LLM analysis | `python3 analyze.py` (cron every 5 min, log `data/analyze.log`) |
| Seed data | `python3 seed.py` (idempotent; 10 starter ideas) |
| Smoke test | `python3 test_smoke.py` (needs server up) |
| Interpreter | `/home/bsmt-pc/.local/bin/python-scheme` (symlink; stdlib only) |

### API
`GET /api/health`, `GET /api/ideas?status=&category=`, `POST /api/ideas`
(`{title, raw, owner}`), `GET /api/ideas/{id}`, `PATCH /api/ideas/{id}`
(`{status?}`), `DELETE /api/ideas/{id}`, `GET /api/connections`,
`GET /api/stats`. Static site at `/` (+ `/app.js`, `/style.css`, `/static/…`).

## History
Built 2026-10-04 by antigravity (`ag y`, gemini-3.8-flash-high) from `SPEC.md`.
