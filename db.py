"""Database schema and helpers for Scheme Board.
Stdlib only, SQLite in WAL mode.
"""

from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DB_DIR / "board.db"

STATUSES = ["raw", "developed", "testing", "being_built", "proven", "dead"]
CATEGORIES = [
    "e_commerce",
    "digital_product",
    "service",
    "content_media",
    "ai_automation",
    "trading_investing",
    "real_world",
    "community",
    "other",
]
SCORE_KEYS = [
    "capital",
    "effort",
    "time_to_revenue",
    "ceiling",
    "difficulty",
    "moat",
    "risk",
]
CONNECTION_TYPES = ["parallel", "complements", "same_market", "competes", "extends"]


def get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    conn = get_db(db_path)
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ideas (
              id INTEGER PRIMARY KEY,
              title TEXT NOT NULL,
              raw TEXT NOT NULL,
              summary TEXT,
              owner TEXT,
              status TEXT NOT NULL DEFAULT 'raw' CHECK (status IN ('raw','developed','testing','being_built','proven','dead')),
              category TEXT,
              tags TEXT NOT NULL DEFAULT '[]',
              scores TEXT NOT NULL DEFAULT '{}',
              seeded INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS connections (
              id INTEGER PRIMARY KEY,
              idea_a INTEGER NOT NULL,
              idea_b INTEGER NOT NULL,
              ctype TEXT NOT NULL,
              strength REAL NOT NULL DEFAULT 0.5,
              note TEXT,
              UNIQUE (idea_a, idea_b, ctype)
            );

            CREATE TABLE IF NOT EXISTS themes (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT,
              idea_ids TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS analysis_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              idea_id INTEGER NOT NULL,
              status TEXT NOT NULL,
              error TEXT,
              ts TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
    conn.close()


def row_to_idea(row: sqlite3.Row | dict) -> dict:
    d = dict(row)
    # Parse tags
    raw_tags = d.get("tags")
    if isinstance(raw_tags, str):
        try:
            d["tags"] = json.loads(raw_tags)
        except Exception:
            d["tags"] = []
    elif not isinstance(raw_tags, list):
        d["tags"] = []

    # Parse scores
    raw_scores = d.get("scores")
    if isinstance(raw_scores, str):
        try:
            d["scores"] = json.loads(raw_scores)
        except Exception:
            d["scores"] = {}
    elif not isinstance(raw_scores, dict):
        d["scores"] = {}

    return d


def row_to_connection(row: sqlite3.Row | dict) -> dict:
    d = dict(row)
    a = d.get("idea_a")
    b = d.get("idea_b")
    return {
        "id": d.get("id"),
        "a": a,
        "b": b,
        "idea_a": a,
        "idea_b": b,
        "ctype": d.get("ctype"),
        "strength": float(d.get("strength", 0.5)),
        "note": d.get("note") or "",
    }


def row_to_theme(row: sqlite3.Row | dict) -> dict:
    d = dict(row)
    raw_ids = d.get("idea_ids")
    if isinstance(raw_ids, str):
        try:
            d["idea_ids"] = json.loads(raw_ids)
        except Exception:
            d["idea_ids"] = []
    elif not isinstance(raw_ids, list):
        d["idea_ids"] = []
    return d


def is_scores_complete(scores: dict) -> bool:
    if not isinstance(scores, dict):
        return False
    return all(
        k in scores and scores[k] is not None and isinstance(scores[k], (int, float))
        for k in SCORE_KEYS
    )


def compute_opportunity_score(scores: dict) -> Optional[int]:
    if not is_scores_complete(scores):
        return None
    try:
        return (
            int(scores["ceiling"])
            + int(scores["moat"])
            - int(scores["capital"])
            - int(scores["effort"])
            - int(scores["risk"])
        )
    except Exception:
        return None


# --- Ideas CRUD ---


def create_idea(
    title: str,
    raw: str,
    owner: Optional[str] = "C6",
    status: str = "raw",
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    scores: Optional[Dict[str, Any]] = None,
    seeded: int = 0,
    summary: Optional[str] = None,
    create_run: bool = True,
    db_path: Optional[Path] = None,
) -> dict:
    conn = get_db(db_path)
    tags_json = json.dumps(tags if tags is not None else [])
    scores_json = json.dumps(scores if scores is not None else {})

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO ideas (title, raw, summary, owner, status, category, tags, scores, seeded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                raw,
                summary,
                owner,
                status if status in STATUSES else "raw",
                category,
                tags_json,
                scores_json,
                1 if seeded else 0,
            ),
        )
        idea_id = cursor.lastrowid

        if create_run:
            conn.execute(
                """
                INSERT INTO analysis_runs (idea_id, status)
                VALUES (?, 'pending')
                """,
                (idea_id,),
            )

    conn.close()
    return get_idea(idea_id, db_path=db_path)  # type: ignore


def get_idea(idea_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    conn = get_db(db_path)
    cur = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    idea = row_to_idea(row)
    opp = compute_opportunity_score(idea["scores"])
    if opp is not None:
        idea["opportunity_score"] = opp
    return idea


def list_ideas(
    status: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    q: Optional[str] = None,
    hide_seeded: bool = False,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> Tuple[List[dict], int]:
    conn = get_db(db_path)
    conditions = []
    params: List[Any] = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if tag:
        conditions.append(
            "EXISTS (SELECT 1 FROM json_each(ideas.tags) WHERE lower(value) = lower(?))"
        )
        params.append(tag)
    if hide_seeded:
        conditions.append("seeded = 0")
    if q:
        like_pattern = f"%{q}%"
        conditions.append(
            "(title LIKE ? OR raw LIKE ? OR summary LIKE ? OR owner LIKE ?)"
        )
        params.extend([like_pattern, like_pattern, like_pattern, like_pattern])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_sql = f"SELECT COUNT(*) FROM ideas {where_clause}"
    total = conn.execute(count_sql, params).fetchone()[0]

    select_sql = f"SELECT * FROM ideas {where_clause} ORDER BY created_at DESC, id DESC"
    if limit is not None:
        select_sql += " LIMIT ?"
        params.append(limit)
        if offset is not None:
            select_sql += " OFFSET ?"
            params.append(offset)

    rows = conn.execute(select_sql, params).fetchall()
    conn.close()

    ideas = []
    for r in rows:
        idea = row_to_idea(r)
        opp = compute_opportunity_score(idea["scores"])
        if opp is not None:
            idea["opportunity_score"] = opp
        ideas.append(idea)
    return ideas, total


def update_idea(
    idea_id: int, db_path: Optional[Path] = None, **fields
) -> Optional[dict]:
    conn = get_db(db_path)
    allowed_cols = {
        "title",
        "raw",
        "summary",
        "owner",
        "status",
        "category",
        "tags",
        "scores",
        "seeded",
    }

    updates = []
    params = []
    for col, val in fields.items():
        if col not in allowed_cols:
            continue
        if col == "tags":
            val = json.dumps(val if isinstance(val, list) else [])
        elif col == "scores":
            val = json.dumps(val if isinstance(val, dict) else {})
        elif col == "status" and val not in STATUSES:
            continue
        updates.append(f"{col} = ?")
        params.append(val)

    if not updates:
        conn.close()
        return get_idea(idea_id, db_path=db_path)

    updates.append("updated_at = (datetime('now'))")
    params.append(idea_id)

    with conn:
        cursor = conn.execute(
            f"UPDATE ideas SET {', '.join(updates)} WHERE id = ?", params
        )
        if cursor.rowcount == 0:
            conn.close()
            return None

    conn.close()
    return get_idea(idea_id, db_path=db_path)


def delete_idea(idea_id: int, db_path: Optional[Path] = None) -> bool:
    conn = get_db(db_path)
    with conn:
        cur = conn.execute("SELECT id FROM ideas WHERE id = ?", (idea_id,))
        if not cur.fetchone():
            conn.close()
            return False

        conn.execute(
            "DELETE FROM connections WHERE idea_a = ? OR idea_b = ?",
            (idea_id, idea_id),
        )
        conn.execute("DELETE FROM analysis_runs WHERE idea_id = ?", (idea_id,))
        conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))

        # Remove from any theme's idea_ids
        themes = conn.execute("SELECT id, idea_ids FROM themes").fetchall()
        for t in themes:
            try:
                t_ids = json.loads(t["idea_ids"])
                if idea_id in t_ids:
                    t_ids = [x for x in t_ids if x != idea_id]
                    conn.execute(
                        "UPDATE themes SET idea_ids = ? WHERE id = ?",
                        (json.dumps(t_ids), t["id"]),
                    )
            except Exception:
                pass

    conn.close()
    return True


# --- Connections CRUD ---


def list_connections(db_path: Optional[Path] = None) -> List[dict]:
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT * FROM connections ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [row_to_connection(r) for r in rows]


def upsert_connection(
    idea_a: int,
    idea_b: int,
    ctype: str,
    strength: float = 0.5,
    note: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> dict:
    a, b = min(idea_a, idea_b), max(idea_a, idea_b)
    strength = max(0.0, min(1.0, float(strength)))
    conn = get_db(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO connections (idea_a, idea_b, ctype, strength, note)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(idea_a, idea_b, ctype) DO UPDATE SET
              strength = excluded.strength,
              note = excluded.note
            """,
            (a, b, ctype, strength, note or ""),
        )
        row = conn.execute(
            "SELECT * FROM connections WHERE idea_a = ? AND idea_b = ? AND ctype = ?",
            (a, b, ctype),
        ).fetchone()
    conn.close()
    return row_to_connection(row)


# --- Themes CRUD ---


def list_themes(db_path: Optional[Path] = None) -> List[dict]:
    conn = get_db(db_path)
    rows = conn.execute("SELECT * FROM themes ORDER BY id ASC").fetchall()
    conn.close()
    return [row_to_theme(r) for r in rows]


def upsert_theme(
    name: str,
    description: Optional[str] = None,
    idea_ids: Optional[List[int]] = None,
    db_path: Optional[Path] = None,
) -> dict:
    name_clean = name.strip()
    ids_to_add = set(idea_ids or [])
    conn = get_db(db_path)
    with conn:
        row = conn.execute(
            "SELECT * FROM themes WHERE lower(name) = lower(?)", (name_clean,)
        ).fetchone()
        if row:
            theme_id = row["id"]
            existing_ids = set()
            try:
                existing_ids = set(json.loads(row["idea_ids"]))
            except Exception:
                pass
            merged_ids = sorted(list(existing_ids.union(ids_to_add)))
            desc = description if description is not None else row["description"]
            conn.execute(
                "UPDATE themes SET description = ?, idea_ids = ? WHERE id = ?",
                (desc, json.dumps(merged_ids), theme_id),
            )
        else:
            merged_ids = sorted(list(ids_to_add))
            cursor = conn.execute(
                "INSERT INTO themes (name, description, idea_ids) VALUES (?, ?, ?)",
                (name_clean, description or "", json.dumps(merged_ids)),
            )
            theme_id = cursor.lastrowid

        res = conn.execute(
            "SELECT * FROM themes WHERE id = ?", (theme_id,)
        ).fetchone()
    conn.close()
    return row_to_theme(res)


# --- Analysis Runs CRUD ---


def create_analysis_run(
    idea_id: int,
    status: str = "pending",
    error: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    conn = get_db(db_path)
    with conn:
        cur = conn.execute(
            "INSERT INTO analysis_runs (idea_id, status, error) VALUES (?, ?, ?)",
            (idea_id, status, error),
        )
        run_id = cur.lastrowid
    conn.close()
    return run_id


def get_pending_runs(limit: int = 5, db_path: Optional[Path] = None) -> List[dict]:
    conn = get_db(db_path)
    rows = conn.execute(
        """
        SELECT * FROM analysis_runs
        WHERE status = 'pending'
        ORDER BY id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_analysis_run(
    run_id: int,
    status: str,
    error: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    conn = get_db(db_path)
    with conn:
        conn.execute(
            """
            UPDATE analysis_runs
            SET status = ?, error = ?, ts = (datetime('now'))
            WHERE id = ?
            """,
            (status, error, run_id),
        )
    conn.close()


def list_analysis_runs(
    limit: int = 20, db_path: Optional[Path] = None
) -> List[dict]:
    conn = get_db(db_path)
    rows = conn.execute(
        """
        SELECT r.id, r.idea_id, r.status, r.error, r.ts, i.title as idea_title
        FROM analysis_runs r
        LEFT JOIN ideas i ON r.idea_id = i.id
        ORDER BY r.ts DESC, r.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["title"] = d.get("idea_title") or f"Idea #{d['idea_id']}"
        out.append(d)
    return out


# --- Stats ---


def get_stats(db_path: Optional[Path] = None) -> dict:
    conn = get_db(db_path)

    # Total count
    total = conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]

    # By status (all 6 keys zero-filled)
    by_status = {s: 0 for s in STATUSES}
    status_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM ideas GROUP BY status"
    ).fetchall()
    for r in status_rows:
        if r["status"] in by_status:
            by_status[r["status"]] = r["cnt"]

    # By category
    by_category = {}
    cat_rows = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM ideas WHERE category IS NOT NULL GROUP BY category"
    ).fetchall()
    for r in cat_rows:
        by_category[r["category"]] = r["cnt"]

    # Seeded count
    seeded_count = conn.execute(
        "SELECT COUNT(*) FROM ideas WHERE seeded = 1"
    ).fetchone()[0]

    # All ideas for top opportunities & newest
    all_rows = conn.execute(
        "SELECT * FROM ideas ORDER BY created_at DESC, id DESC"
    ).fetchall()
    conn.close()

    all_ideas = [row_to_idea(r) for r in all_rows]

    # Top opportunities: complete scores only
    # ranked by ceiling + moat - capital - effort - risk (tie-break: higher moat first)
    scored_ideas = []
    for idea in all_ideas:
        scores = idea["scores"]
        if is_scores_complete(scores):
            opp = compute_opportunity_score(scores)
            idea_copy = dict(idea)
            idea_copy["opportunity_score"] = opp
            scored_ideas.append(idea_copy)

    # Sort: opportunity_score desc, moat desc, id asc
    scored_ideas.sort(
        key=lambda x: (
            -(x["opportunity_score"] if x["opportunity_score"] is not None else -999),
            -int(x["scores"].get("moat", 0)),
            x["id"],
        )
    )
    top_opportunities = scored_ideas[:10]

    # Newest: 5 ideas by created_at desc
    newest = all_ideas[:5]
    for n in newest:
        opp = compute_opportunity_score(n["scores"])
        if opp is not None:
            n["opportunity_score"] = opp

    return {
        "counts": {
            "total": total,
            "by_status": by_status,
            "by_category": by_category,
            "seeded_count": seeded_count,
        },
        "top_opportunities": top_opportunities,
        "newest": newest,
    }


# Auto-init schema on module import
init_db()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
