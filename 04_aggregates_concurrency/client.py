"""Phase 4 client: demonstrates optimistic concurrency.

Two members try to borrow the same book at the same instant. With version-based
locking on the Book aggregate, exactly one wins; the other gets 409.
"""

from __future__ import annotations

import sys
import uuid

import httpx


BASE_URL = "http://127.0.0.1:8004"


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    isbn = "9780134494166"
    member_a = f"alice_{suffix}"
    member_b = f"bob_{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        print("[step] adding two members")
        for m in (member_a, member_b):
            r = http.post("/members", json={"member_id": m, "name": m.split("_")[0].title()})
            assert r.status_code == 201, r.text

        print("[step] adding 'Clean Architecture' (2 copies, version 0)")
        r = http.post(
            "/books",
            json={"isbn": isbn, "title": "Clean Architecture", "total_copies": 2},
        )
        assert r.status_code in (201, 409), r.text

        r = http.get(f"/books/{isbn}")
        v0 = r.json()["version"]
        print(f"[info] initial version = {v0}")

        print("[step] firing two parallel borrows on the same book")
        r = http.post(
            "/admin/race_borrow",
            json={"member_a": member_a, "member_b": member_b, "isbn": isbn},
        )
        assert r.status_code == 200, r.text
        results = r.json()["results"]
        print(f"[info] results: {results}")

        statuses = sorted(item["status"] for item in results)
        assert statuses == ["concurrency_conflict", "ok"], (
            f"expected exactly one ok and one conflict, got {statuses}"
        )

        r = http.get(f"/books/{isbn}")
        body = r.json()
        print(f"[info] after race: available={body['available_copies']}, version={body['version']}")
        assert body["available_copies"] == 1, body
        assert body["version"] == v0 + 1, body

    print("[ok] phase 4 client done -- optimistic concurrency demonstrated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
