"""Phase 8 client: drives both write and read paths, verifies CQRS read shapes."""

from __future__ import annotations

import sys
import uuid
from datetime import date

import httpx


BASE_URL = "http://127.0.0.1:8008"


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    isbn_a = "9780132350884"
    isbn_b = "9780201633610"
    member = f"frida_{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        print("[step] write path: register member + 2 books")
        r = http.post("/members", json={"member_id": member, "name": "Frida"})
        assert r.status_code == 201, r.text
        for isbn, title, copies in [
            (isbn_a, "Clean Code", 2),
            (isbn_b, "Design Patterns", 1),
        ]:
            r = http.post("/books", json={"isbn": isbn, "title": title, "total_copies": copies})
            assert r.status_code in (201, 409), r.text

        print("[step] read path: GET /views/available_books")
        r = http.get("/views/available_books")
        titles = [b["title"] for b in r.json()["books"]]
        print(f"[info] available titles include: {titles[:5]}...")
        assert "Clean Code" in titles
        assert "Design Patterns" in titles

        print("[step] write: borrow Design Patterns -> 0 copies left")
        r = http.post("/borrow", json={"member_id": member, "isbn": isbn_b})
        assert r.status_code == 200, r.text

        print("[step] read: Design Patterns no longer in available_books")
        r = http.get("/views/available_books")
        titles = [b["title"] for b in r.json()["books"]]
        assert "Design Patterns" not in titles, titles

        print("[step] read: member history shows the loan")
        r = http.get(f"/views/member_history/{member}")
        history = r.json()["history"]
        assert any(h["isbn"] == isbn_b for h in history), history
        print(f"[info] member history rows: {len(history)}")

    print("[ok] phase 8 client done -- read paths bypassed the domain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
