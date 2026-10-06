"""LLM analysis runner for Scheme Board.
Processes pending analysis runs, compares new ideas with existing ideas,
and extracts summaries, tags, categories, scores, connections, and themes.
Stdlib only (urllib.request, json).
"""

from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from db import (
    CATEGORIES,
    CONNECTION_TYPES,
    SCORE_KEYS,
    get_db,
    get_idea,
    get_pending_runs,
    init_db,
    list_ideas,
    update_analysis_run,
    update_idea,
    upsert_connection,
    upsert_theme,
)

LLM_ENDPOINT = "http://192.168.1.72:8080/v1/chat/completions"
LLM_MODEL = "/home/nathan/Downloads/Qwen3.8-27B-NVFP4-MTP-HIGH.gguf"
LLM_TIMEOUT = 600


def extract_json_from_text(text: str) -> Any:
    """Defensively parses JSON from LLM text output."""
    raw = text.strip()
    # Strip markdown code fences if present
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    matches = fence_pattern.findall(raw)
    if matches:
        raw = matches[0].strip()

    # Try direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Find outermost '[' or '{'
    first_bracket = raw.find("[")
    first_brace = raw.find("{")

    start = -1
    end = -1
    if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
        start = first_bracket
        end = raw.rfind("]")
    elif first_brace != -1:
        start = first_brace
        end = raw.rfind("}")

    if start != -1 and end != -1 and end > start:
        snippet = raw[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON substring: {e}. Raw: {raw[:300]}")

    raise ValueError(f"No JSON array or object found in response: {raw[:300]}")


def _query_llm(system: str, user: str, timeout: int = LLM_TIMEOUT) -> str:
    """Internal helper to make the HTTP POST to the local LLM endpoint."""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        LLM_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp_data = json.loads(resp.read().decode("utf-8"))

    choices = resp_data.get("choices", [])
    if not choices:
        raise RuntimeError("LLM response contained no choices")

    msg = choices[0].get("message", {})
    content = (msg.get("content") or "").strip()
    if content:
        return content

    reasoning = (msg.get("reasoning_content") or "").strip()
    if reasoning:
        return reasoning

    raise RuntimeError("LLM response contained neither content nor reasoning_content")


def llm_json(system: str, user: str) -> Any:
    """Makes an LLM call and returns parsed JSON.
    Retries once with a stricter system prompt on parse failure.
    """
    raw_response = _query_llm(system, user)
    try:
        return extract_json_from_text(raw_response)
    except Exception as first_err:
        strict_system = (
            system
            + "\n\nCRITICAL REQUIREMENT: Output ONLY valid, minified JSON. Do not include any explanation, markdown, code blocks, or prose."
        )
        try:
            retry_raw = _query_llm(strict_system, user)
            return extract_json_from_text(retry_raw)
        except Exception as second_err:
            raise RuntimeError(
                f"LLM JSON parsing failed after retry: {second_err} (Initial error: {first_err})"
            )


def validate_and_clean_result(item: dict, new_idea_id: int) -> dict:
    """Validates and coerces the fields returned by the LLM for a given idea."""
    cleaned: Dict[str, Any] = {}

    # Summary
    if "summary" in item and isinstance(item["summary"], str) and item["summary"].strip():
        cleaned["summary"] = item["summary"].strip()

    # Category
    if "category" in item and isinstance(item["category"], str):
        cat = item["category"].strip().lower()
        if cat in CATEGORIES or re.match(r"^[a-z0-9_]+$", cat):
            cleaned["category"] = cat

    # Tags
    if "tags" in item and isinstance(item["tags"], list):
        valid_tags = []
        for t in item["tags"]:
            if isinstance(t, str) and t.strip():
                valid_tags.append(t.strip().lower())
        if valid_tags:
            cleaned["tags"] = sorted(list(set(valid_tags)))

    # Scores
    if "scores" in item and isinstance(item["scores"], dict):
        valid_scores = {}
        for k in SCORE_KEYS:
            val = item["scores"].get(k)
            if val is not None and isinstance(val, (int, float)):
                try:
                    int_val = int(round(val))
                    if 1 <= int_val <= 5:
                        valid_scores[k] = int_val
                except Exception:
                    pass
        if valid_scores:
            cleaned["scores"] = valid_scores

    # Connections
    cleaned_conns = []
    if "connections" in item and isinstance(item["connections"], list):
        for c in item["connections"]:
            if not isinstance(c, dict):
                continue
            try:
                a = int(c.get("a"))
                b = int(c.get("b"))
                ctype = str(c.get("ctype", "")).strip().lower()
                strength = float(c.get("strength", 0.5))
                note = str(c.get("note", "")).strip()

                if a == b:
                    continue
                if ctype not in CONNECTION_TYPES:
                    continue
                strength = max(0.0, min(1.0, strength))

                cleaned_conns.append(
                    {
                        "idea_a": min(a, b),
                        "idea_b": max(a, b),
                        "ctype": ctype,
                        "strength": strength,
                        "note": note[:250],
                    }
                )
            except Exception:
                continue
    cleaned["connections"] = cleaned_conns

    # Themes
    cleaned_themes = []
    if "themes" in item and isinstance(item["themes"], list):
        for th in item["themes"]:
            if not isinstance(th, dict):
                continue
            name = str(th.get("name", "")).strip()
            if not name:
                continue
            desc = str(th.get("description", "")).strip()
            new_idea_flag = bool(th.get("new_idea", True))

            # Include new idea id if flagged or if explicitly included
            ids = [new_idea_id] if new_idea_flag else []
            if "idea_ids" in th and isinstance(th["idea_ids"], list):
                for x in th["idea_ids"]:
                    try:
                        ids.append(int(x))
                    except Exception:
                        pass
            cleaned_themes.append(
                {"name": name, "description": desc, "idea_ids": list(set(ids))}
            )
    cleaned["themes"] = cleaned_themes

    return cleaned


def analyze_idea(new_idea: dict, db_path: Optional[Path] = None) -> dict:
    """Analyzes a single idea against existing ideas in the database."""
    idea_id = new_idea["id"]

    # Fetch other existing ideas (cap at 40 most recent)
    all_ideas, _ = list_ideas(limit=50, db_path=db_path)
    existing = [i for i in all_ideas if i["id"] != idea_id][:40]

    system_prompt = (
        "You are a business analyst for a small team collecting money-making ideas. "
        "You will receive ONE new idea and ALL existing ideas (id, title, summary, category, tags). "
        "Respond with ONLY a JSON array of objects. No prose, no markdown."
    )

    user_lines = [
        f"NEW IDEA:",
        f"id: {new_idea['id']}",
        f"title: {new_idea.get('title', '')}",
        f"raw: {new_idea.get('raw', '')}",
        f"summary: {new_idea.get('summary') or 'None'}",
        "",
        "EXISTING IDEAS IN DATABASE:",
    ]

    if not existing:
        user_lines.append("(No other ideas in database yet.)")
    else:
        for idx, ex in enumerate(existing, 1):
            ex_summary = ex.get("summary") or ex.get("raw", "")[:100]
            ex_tags = ", ".join(ex.get("tags") or [])
            user_lines.append(
                f"{idx}. {ex['id']} | {ex.get('category') or 'unassigned'} | {ex.get('title')} | {ex_summary} | tags: {ex_tags}"
            )
        if len(all_ideas) > len(existing) + 1:
            user_lines.append(
                f"(Note: {len(all_ideas) - 1 - len(existing)} older ideas truncated from prompt.)"
            )

    user_lines.append(
        "\nProvide your analysis as a JSON array with one object for this new idea:\n"
        "[{\n"
        f'  "idea_id": {new_idea["id"]},\n'
        '  "summary": "<<=40 word summary>",\n'
        '  "category": "<one of e_commerce, digital_product, service, content_media, ai_automation, trading_investing, real_world, community, other>",\n'
        '  "tags": ["lowercase_tag1", "tag2"],\n'
        '  "scores": {"capital": 1-5, "effort": 1-5, "time_to_revenue": 1-5, "ceiling": 1-5, "difficulty": 1-5, "moat": 1-5, "risk": 1-5},\n'
        f'  "connections": [{{"a": {new_idea["id"]}, "b": <existing_id>, "ctype": "parallel|complements|same_market|competes|extends", "strength": 0.0-1.0, "note": "<<=25 words why>"}}],\n'
        '  "themes": [{"name": "<short theme name>", "description": "<<=30 words>", "new_idea": true}]\n'
        "}]"
    )

    user_prompt = "\n".join(user_lines)

    result_json = llm_json(system_prompt, user_prompt)
    if isinstance(result_json, list) and result_json:
        target_obj = result_json[0]
    elif isinstance(result_json, dict):
        # In case the model returned {"idea_id": ...} or {"ideas": [...]}
        if "ideas" in result_json and isinstance(result_json["ideas"], list) and result_json["ideas"]:
            target_obj = result_json["ideas"][0]
        else:
            target_obj = result_json
    else:
        raise ValueError(f"Unexpected JSON shape from LLM: {type(result_json)}")

    return validate_and_clean_result(target_obj, idea_id)


def run_pending(limit: int = 5, db_path: Optional[Path] = None) -> int:
    """Picks pending analysis runs (up to limit) and analyzes each."""
    pending = get_pending_runs(limit=limit, db_path=db_path)
    if not pending:
        print("No pending analysis runs found.")
        return 0

    print(f"Found {len(pending)} pending run(s).")
    processed = 0

    for run in pending:
        run_id = run["id"]
        idea_id = run["idea_id"]
        print(f"\n--- Processing run #{run_id} for Idea #{idea_id} ---")

        update_analysis_run(run_id, status="running", db_path=db_path)
        idea = get_idea(idea_id, db_path=db_path)
        if not idea:
            err = f"Idea #{idea_id} not found in database."
            print(f"FAILED: {err}")
            update_analysis_run(run_id, status="failed", error=err, db_path=db_path)
            continue

        try:
            analysis = analyze_idea(idea, db_path=db_path)

            # Update idea fields returned by LLM
            update_fields: Dict[str, Any] = {}
            if "summary" in analysis:
                update_fields["summary"] = analysis["summary"]
            if "category" in analysis:
                update_fields["category"] = analysis["category"]
            if "tags" in analysis:
                # Merge or overwrite tags
                existing_tags = set(idea.get("tags") or [])
                new_tags = set(analysis["tags"])
                update_fields["tags"] = sorted(list(existing_tags.union(new_tags)))
            if "scores" in analysis:
                existing_scores = dict(idea.get("scores") or {})
                existing_scores.update(analysis["scores"])
                update_fields["scores"] = existing_scores

            if update_fields:
                update_idea(idea_id, db_path=db_path, **update_fields)

            # Upsert connections
            for conn in analysis.get("connections", []):
                upsert_connection(
                    conn["idea_a"],
                    conn["idea_b"],
                    conn["ctype"],
                    conn["strength"],
                    conn["note"],
                    db_path=db_path,
                )

            # Upsert themes
            for th in analysis.get("themes", []):
                upsert_theme(
                    th["name"],
                    th["description"],
                    th["idea_ids"],
                    db_path=db_path,
                )

            update_analysis_run(run_id, status="done", error=None, db_path=db_path)
            processed += 1
            print(
                f"SUCCESS: Idea #{idea_id} '{idea.get('title')}' analyzed."
                f"\n  Updated fields: {list(update_fields.keys())}"
                f"\n  Connections added/updated: {len(analysis.get('connections', []))}"
                f"\n  Themes updated: {len(analysis.get('themes', []))}"
            )
        except Exception as e:
            err_msg = str(e)
            print(f"FAILED: Error analyzing Idea #{idea_id}: {err_msg}")
            update_analysis_run(run_id, status="failed", error=err_msg, db_path=db_path)

    return processed


def check_llm() -> None:
    """Verifies connectivity to the LLM with a single trivial prompt."""
    print("Checking LLM connectivity at:", LLM_ENDPOINT)
    print("Model:", LLM_MODEL)
    system = "You are a JSON generator. Respond with ONLY a JSON array. No prose, no markdown."
    user = 'Return a JSON array containing exactly one object: [{"status": "ok", "message": "LLM check passed", "check": 1}]'
    res = llm_json(system, user)
    print("Parsed LLM Response:")
    print(json.dumps(res, indent=2))
    print("\nLLM check PASSED.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheme Board LLM Analysis Runner")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run a quick connectivity check against the LLM endpoint and exit.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max number of pending runs to process (default: 5)",
    )
    args = parser.parse_args()

    init_db()

    if args.check:
        check_llm()
        sys.exit(0)

    run_pending(limit=args.limit)


if __name__ == "__main__":
    main()
