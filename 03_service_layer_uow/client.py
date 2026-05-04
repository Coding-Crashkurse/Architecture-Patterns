"""Phase 3 client: same flow, now hitting endpoints that delegate to a service layer."""

from __future__ import annotations

import sys

import httpx


BASE_URL = "http://127.0.0.1:8003"


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as http:
        print("[step] adding member carol")
        r = http.post("/members", json={"member_id": "carol", "name": "Carol"})
        assert r.status_code in (201, 409), r.text

        print("[step] adding book 'PoEAA' (1 copy)")
        r = http.post(
            "/books",
            json={"isbn": "9780321127426", "title": "Patterns of Enterprise App Arch", "total_copies": 1},
        )
        assert r.status_code in (201, 409), r.text

        print("[step] carol borrows PoEAA")
        r = http.post("/borrow", json={"member_id": "carol", "isbn": "9780321127426"})
        assert r.status_code in (200, 409), r.text

        print("[step] availability is 0")
        r = http.get("/books/9780321127426")
        assert r.json()["available_copies"] == 0

        print("[step] carol returns PoEAA")
        r = http.post("/return", json={"member_id": "carol", "isbn": "9780321127426"})
        assert r.status_code == 200, r.text

    print("[ok] phase 3 client done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
