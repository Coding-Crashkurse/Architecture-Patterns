"""Phase 7 client: verifies that domain events flow through Outbox -> Redis -> Inbox -> external sink."""

from __future__ import annotations

import sys
import time
import uuid

import httpx


BASE_URL = "http://127.0.0.1:8007"


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    isbn = "9780321356680"
    member = f"erin_{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        before = len(http.get("/notifications").json()["external_via_redis"])

        print("[step] register member + book")
        r = http.post("/members", json={"member_id": member, "name": "Erin"})
        assert r.status_code == 201, r.text
        r = http.post("/books", json={"isbn": isbn, "title": "Effective Java", "total_copies": 1})
        assert r.status_code in (201, 409), r.text

        print("[step] borrow + return -- expect events through outbox/redis/inbox")
        assert http.post("/borrow", json={"member_id": member, "isbn": isbn}).status_code == 200
        assert http.post("/return", json={"member_id": member, "isbn": isbn}).status_code == 200

        external = []
        for _ in range(40):
            external = http.get("/notifications").json()["external_via_redis"]
            if len(external) - before >= 2:
                break
            time.sleep(0.1)

        new_external = external[before:]
        types = [n["type"] for n in new_external]
        print(f"[info] external (post-relay) types: {types}")
        assert "BookBorrowed" in types, types
        assert "BookReturned" in types, types

    print("[ok] phase 7 client done -- outbox + inbox round-trip verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
