"""Phase 6 client: demonstrates the Reservation chain.

Alice borrows the only copy. Bob, denied a borrow, reserves it instead. Alice returns.
The bus chain (BookReturned event -> FulfillReservation command) borrows the book on Bob's behalf.
"""

from __future__ import annotations

import sys
import uuid

import httpx


BASE_URL = "http://127.0.0.1:8006"


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    isbn = "9780201835953"
    alice = f"alice_{suffix}"
    bob = f"bob_{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        print("[step] register members + book (1 copy)")
        for m, n in [(alice, "Alice"), (bob, "Bob")]:
            r = http.post("/members", json={"member_id": m, "name": n})
            assert r.status_code == 201, r.text
        r = http.post("/books", json={"isbn": isbn, "title": "Mythical Man-Month", "total_copies": 1})
        assert r.status_code in (201, 409), r.text

        print("[step] alice borrows the last copy")
        r = http.post("/borrow", json={"member_id": alice, "isbn": isbn})
        assert r.status_code == 200, r.text

        print("[step] bob tries to borrow -> 409 OutOfStock")
        r = http.post("/borrow", json={"member_id": bob, "isbn": isbn})
        assert r.status_code == 409, r.text

        print("[step] bob reserves it instead")
        r = http.post("/reserve", json={"member_id": bob, "isbn": isbn})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "reserved"

        print("[step] alice returns the book -> chain fires")
        r = http.post("/return", json={"member_id": alice, "isbn": isbn})
        assert r.status_code == 200, r.text

        print("[step] bob now has the loan automatically")
        r = http.get(f"/loans/{bob}")
        loans = r.json()["active_loans"]
        assert any(loan["isbn"] == isbn for loan in loans), loans
        print(f"[info] bob's active loans: {loans}")

        types = [n["type"] for n in http.get("/notifications").json()["notifications"]]
        print(f"[info] notification types observed: {types}")
        for required in ("BookBorrowed", "BookReturned", "BookReserved", "ReservationFulfilled"):
            assert required in types, f"missing {required} in {types}"

    print("[ok] phase 6 client done -- command/event chain executed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
