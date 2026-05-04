"""Phase 2 client. Same flow as Phase 1, but data now persists in SQLite."""

from __future__ import annotations

import sys

import httpx


BASE_URL = "http://127.0.0.1:8002"


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as http:
        print("[step] adding member bob")
        r = http.post("/members", json={"member_id": "bob", "name": "Bob"})
        assert r.status_code in (201, 409), r.text  # 409 if re-running

        print("[step] adding book 'DDD' (1 copy)")
        r = http.post(
            "/books",
            json={"isbn": "9780321125217", "title": "Domain-Driven Design", "total_copies": 1},
        )
        assert r.status_code in (201, 409), r.text

        print("[step] bob borrows DDD")
        r = http.post("/borrow", json={"member_id": "bob", "isbn": "9780321125217"})
        assert r.status_code in (200, 409), r.text  # 409 if already borrowed in prior run

        print("[step] DDD now unavailable")
        r = http.get("/books/9780321125217")
        assert r.json()["available_copies"] == 0

        print("[step] bob returns DDD")
        r = http.post("/return", json={"member_id": "bob", "isbn": "9780321125217"})
        assert r.status_code == 200, r.text

    print("[ok] phase 2 client done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
