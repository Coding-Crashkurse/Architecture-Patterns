"""Phase 1 client: drives the server via real HTTP and asserts the flow."""

from __future__ import annotations

import sys

import httpx


BASE_URL = "http://127.0.0.1:8001"


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as http:
        print("[step] adding member alice")
        r = http.post("/members", json={"member_id": "alice", "name": "Alice"})
        assert r.status_code == 201, r.text

        print("[step] adding book 'Clean Code' (2 copies)")
        r = http.post(
            "/books",
            json={"isbn": "9780132350884", "title": "Clean Code", "total_copies": 2},
        )
        assert r.status_code == 201, r.text
        assert r.json()["available_copies"] == 2

        print("[step] alice borrows Clean Code")
        r = http.post("/borrow", json={"member_id": "alice", "isbn": "9780132350884"})
        assert r.status_code == 200, r.text

        print("[step] availability dropped to 1")
        r = http.get("/books/9780132350884")
        assert r.json()["available_copies"] == 1

        print("[step] alice returns Clean Code")
        r = http.post("/return", json={"member_id": "alice", "isbn": "9780132350884"})
        assert r.status_code == 200, r.text

        print("[step] availability back to 2")
        r = http.get("/books/9780132350884")
        assert r.json()["available_copies"] == 2

        print("[step] borrowing a nonexistent book is 404")
        r = http.post("/borrow", json={"member_id": "alice", "isbn": "9999999999"})
        assert r.status_code == 404, r.text

    print("[ok] phase 1 client done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
