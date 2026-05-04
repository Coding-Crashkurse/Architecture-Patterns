"""Phase 5 client: borrow + return triggers domain events; handlers add notifications."""

from __future__ import annotations

import sys
import uuid

import httpx


BASE_URL = "http://127.0.0.1:8005"


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    isbn = "9780201485677"
    member = f"dave_{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=5.0) as http:
        before = len(http.get("/notifications").json()["notifications"])

        print("[step] adding member + book (1 copy)")
        r = http.post("/members", json={"member_id": member, "name": "Dave"})
        assert r.status_code == 201, r.text
        r = http.post(
            "/books",
            json={"isbn": isbn, "title": "Refactoring", "total_copies": 1},
        )
        assert r.status_code in (201, 409), r.text

        print("[step] borrowing -> should fire BookBorrowed AND BookRunningLow")
        r = http.post("/borrow", json={"member_id": member, "isbn": isbn})
        assert r.status_code == 200, r.text

        print("[step] returning -> should fire BookReturned")
        r = http.post("/return", json={"member_id": member, "isbn": isbn})
        assert r.status_code == 200, r.text

        notifs = http.get("/notifications").json()["notifications"]
        new = notifs[before:]
        types = [n["type"] for n in new]
        print(f"[info] new notifications: {types}")

        assert "BookBorrowed" in types, types
        assert "BookRunningLow" in types, types
        assert "BookReturned" in types, types

    print("[ok] phase 5 client done -- domain events flowed through the bus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
