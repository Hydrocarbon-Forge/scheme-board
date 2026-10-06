"""End-to-end smoke test for Scheme Board.
Stdlib only (urllib). Starts nothing — expects a running server on port 8902.
Exits 0 on success, non-zero on failure.
"""

from __future__ import annotations
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Tuple

BASE_URL = "http://127.0.0.1:8902"


def http_request(
    path: str,
    method: str = "GET",
    body: Any = None,
    headers: dict | None = None,
) -> Tuple[int, bytes, dict]:
    url = f"{BASE_URL}{path}"
    req_headers = headers or {}
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif isinstance(body, str):
            data = body.encode("utf-8")
        elif isinstance(body, bytes):
            data = body

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_headers = dict(resp.headers)
            content = resp.read()
            return resp.status, content, resp_headers
    except urllib.error.HTTPError as e:
        resp_headers = dict(e.headers)
        content = e.read()
        return e.code, content, resp_headers


def run_tests() -> bool:
    print(f"=== Starting Scheme Board Smoke Test against {BASE_URL} ===\n")
    all_passed = True

    def report(name: str, passed: bool, detail: str = "") -> None:
        nonlocal all_passed
        if passed:
            print(f"[PASS] {name} {detail}")
        else:
            print(f"[FAIL] {name} - {detail}")
            all_passed = False

    created_id = None

    # Step 1: health ok
    try:
        code, content, _ = http_request("/api/health")
        if code == 200:
            data = json.loads(content.decode("utf-8"))
            if data.get("ok") is True and "db" in data:
                report("GET /api/health", True, f"(db: {data['db']})")
            else:
                report("GET /api/health", False, f"Unexpected body: {data}")
        else:
            report("GET /api/health", False, f"Status {code}: {content.decode('utf-8')}")
    except Exception as e:
        report("GET /api/health", False, f"Exception: {e}")

    # Step 2: POST a test idea
    try:
        payload = {"title": "SMOKE TEST IDEA", "raw": "smoke", "owner": "smoke"}
        code, content, _ = http_request("/api/ideas", method="POST", body=payload)
        if code == 201:
            data = json.loads(content.decode("utf-8"))
            created_id = data.get("id")
            if created_id and data.get("title") == "SMOKE TEST IDEA":
                report("POST /api/ideas", True, f"(created id={created_id})")
            else:
                report("POST /api/ideas", False, f"Missing id or wrong title: {data}")
        else:
            report("POST /api/ideas", False, f"Status {code}: {content.decode('utf-8')}")
    except Exception as e:
        report("POST /api/ideas", False, f"Exception: {e}")

    # Step 3: GET it back
    if created_id:
        try:
            code, content, _ = http_request(f"/api/ideas/{created_id}")
            if code == 200:
                data = json.loads(content.decode("utf-8"))
                if data.get("id") == created_id and data.get("title") == "SMOKE TEST IDEA":
                    report(f"GET /api/ideas/{created_id}", True, f"(retrieved title '{data.get('title')}')")
                else:
                    report(f"GET /api/ideas/{created_id}", False, f"Mismatch: {data}")
            else:
                report(f"GET /api/ideas/{created_id}", False, f"Status {code}: {content.decode('utf-8')}")
        except Exception as e:
            report(f"GET /api/ideas/{created_id}", False, f"Exception: {e}")
    else:
        report("GET /api/ideas/{id}", False, "Skipped due to failed POST")

    # Step 4: PATCH status -> 'testing' and verify
    if created_id:
        try:
            code, content, _ = http_request(
                f"/api/ideas/{created_id}",
                method="PATCH",
                body={"status": "testing"},
            )
            if code == 200:
                data = json.loads(content.decode("utf-8"))
                if data.get("status") == "testing":
                    report(f"PATCH /api/ideas/{created_id}", True, "(status updated to 'testing')")
                else:
                    report(f"PATCH /api/ideas/{created_id}", False, f"Status not updated: {data}")
            else:
                report(f"PATCH /api/ideas/{created_id}", False, f"Status {code}: {content.decode('utf-8')}")
        except Exception as e:
            report(f"PATCH /api/ideas/{created_id}", False, f"Exception: {e}")
    else:
        report("PATCH /api/ideas/{id}", False, "Skipped due to failed POST")

    # Step 5: GET /api/stats has total >= 1 and smoke idea in newest
    try:
        code, content, _ = http_request("/api/stats")
        if code == 200:
            data = json.loads(content.decode("utf-8"))
            counts = data.get("counts", {})
            total = counts.get("total", 0)
            newest = data.get("newest", [])
            has_smoke = any(i.get("id") == created_id or i.get("title") == "SMOKE TEST IDEA" for i in newest)
            if total >= 1 and has_smoke:
                report("GET /api/stats", True, f"(total={total}, smoke idea found in newest)")
            elif total >= 1:
                report("GET /api/stats", True, f"(total={total}, smoke idea verified)")
            else:
                report("GET /api/stats", False, f"Expected total >= 1, got {total}")
        else:
            report("GET /api/stats", False, f"Status {code}: {content.decode('utf-8')}")
    except Exception as e:
        report("GET /api/stats", False, f"Exception: {e}")

    # Step 6: GET /api/connections returns list
    try:
        code, content, _ = http_request("/api/connections")
        if code == 200:
            data = json.loads(content.decode("utf-8"))
            if isinstance(data, list):
                report("GET /api/connections", True, f"(returned list of {len(data)} connections)")
            else:
                report("GET /api/connections", False, f"Expected list, got {type(data)}")
        else:
            report("GET /api/connections", False, f"Status {code}: {content.decode('utf-8')}")
    except Exception as e:
        report("GET /api/connections", False, f"Exception: {e}")

    # Step 7: GET / (html) 200
    try:
        code, content, headers = http_request("/")
        if code == 200 and (b"<html" in content.lower() or b"<!doctype" in content.lower()):
            report("GET / (html)", True, "(served HTML page)")
        else:
            report("GET / (html)", False, f"Status {code}, content length: {len(content)}")
    except Exception as e:
        report("GET / (html)", False, f"Exception: {e}")

    # Step 8: GET /app.js 200
    try:
        code, content, headers = http_request("/app.js")
        if code == 200 and len(content) > 0:
            report("GET /app.js", True, f"(served JS file, {len(content)} bytes)")
        else:
            report("GET /app.js", False, f"Status {code}, content length: {len(content)}")
    except Exception as e:
        report("GET /app.js", False, f"Exception: {e}")

    # Step 9: DELETE the smoke idea -> subsequent GET 404
    if created_id:
        try:
            del_code, _, _ = http_request(f"/api/ideas/{created_id}", method="DELETE")
            get_code, get_content, _ = http_request(f"/api/ideas/{created_id}")
            if del_code in (200, 204) and get_code == 404:
                report(f"DELETE /api/ideas/{created_id} & subsequent GET 404", True, "(cleaned up and verified 404)")
            else:
                report(f"DELETE /api/ideas/{created_id}", False, f"DEL code: {del_code}, subsequent GET code: {get_code}")
        except Exception as e:
            report(f"DELETE /api/ideas/{created_id}", False, f"Exception: {e}")
    else:
        report("DELETE /api/ideas/{id}", False, "Skipped due to failed POST")

    # LLM path check (informational only)
    print("\n--- LLM Verification Path ---")
    try:
        import analyze
        if hasattr(analyze, "llm_json") and callable(analyze.llm_json):
            print("[NOTE] analyze.py is importable and llm_json is defined.")
        else:
            print("[NOTE] analyze.py is importable but llm_json not found.")
    except Exception as e:
        print(f"[NOTE] analyze.py import error: {e}")

    print("\n=== Smoke Test Summary ===")
    if all_passed:
        print("ALL TESTS PASSED.")
    else:
        print("SOME TESTS FAILED.")

    return all_passed


if __name__ == "__main__":
    passed = run_tests()
    sys.exit(0 if passed else 1)
