"""Phase 9 client: runs the saga happy path AND the compensation path."""

from __future__ import annotations

import sys
import uuid

import httpx


BASE_URL = "http://127.0.0.1:8009"


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    isbn = f"978000000{suffix[:4]}"
    transfer_ok = f"t-ok-{suffix}"
    transfer_fail = f"t-fail-{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        print("[step] register a book in the catalog (so isbn validates)")
        r = http.post("/books", json={"isbn": isbn, "title": "Saga Demo Book", "total_copies": 0})
        assert r.status_code in (201, 409), r.text

        print("[step] seed branch stock: north=2, south=0, west=0")
        for branch, copies in [("north", 2), ("south", 0), ("west", 0)]:
            r = http.post(
                "/admin/seed_branch_stock",
                json={"isbn": isbn, "branch": branch, "copies": copies},
            )
            assert r.status_code == 201, r.text

        print("[step] HAPPY PATH: transfer 1 copy north -> south")
        r = http.post(
            "/transfer",
            json={
                "transfer_id": transfer_ok,
                "isbn": isbn,
                "from_branch": "north",
                "to_branch": "south",
                "simulate_receive_failure": False,
            },
        )
        assert r.status_code == 200, r.text
        state = r.json()["state"]
        print(f"[info] transfer state immediately after request: {state}")

        # bus dispatches synchronously, so by the time /transfer returns, the saga is done
        r = http.get(f"/transfer/{transfer_ok}")
        assert r.json()["state"] == "received", r.json()
        assert http.get(f"/branch_stock/north/{isbn}").json()["copies"] == 1
        assert http.get(f"/branch_stock/south/{isbn}").json()["copies"] == 1
        print("[info] north=1, south=1 -- copy moved")

        print("[step] FAILURE PATH: transfer with simulated receive failure -> compensation")
        r = http.post(
            "/transfer",
            json={
                "transfer_id": transfer_fail,
                "isbn": isbn,
                "from_branch": "north",
                "to_branch": "west",
                "simulate_receive_failure": True,
            },
        )
        assert r.status_code == 200, r.text

        r = http.get(f"/transfer/{transfer_fail}")
        body = r.json()
        print(f"[info] failed transfer state: {body['state']}, reason: {body.get('failure_reason')}")
        assert body["state"] == "compensated", body
        # north must end up back at 1 because compensation returned the shipped copy
        assert http.get(f"/branch_stock/north/{isbn}").json()["copies"] == 1
        assert http.get(f"/branch_stock/west/{isbn}").json()["copies"] == 0
        print("[info] compensation restored north stock to 1, west stayed at 0")

    print("[ok] phase 9 client done -- saga happy + compensation paths verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
