"""Phase 10 client: drives the event-sourced Loan and inspects its event stream."""

from __future__ import annotations

import sys
import uuid

import httpx


BASE_URL = "http://127.0.0.1:8010"


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    loan_id = f"loan-{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        print("[step] borrow (event 1: LoanCreatedV1)")
        r = http.post(
            "/es/loans/borrow",
            json={"loan_id": loan_id, "member_id": "gabe", "isbn": "9780262033848"},
        )
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["version"] == 1, s
        assert s["renewed_count"] == 0

        print("[step] renew twice (events 2 + 3: LoanRenewedV1)")
        for _ in range(2):
            r = http.post("/es/loans/renew", json={"loan_id": loan_id})
            assert r.status_code == 200, r.text
        s = r.json()
        assert s["renewed_count"] == 2, s

        print("[step] third renew should fail (max_renewals=2)")
        r = http.post("/es/loans/renew", json={"loan_id": loan_id})
        assert r.status_code == 409, r.text

        print("[step] return (event 4: LoanReturnedV2)")
        r = http.post("/es/loans/return", json={"loan_id": loan_id})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["returned_on"] is not None
        assert s["version"] == 4, s

        print("[step] state was rebuilt by replaying 4 events")
        r = http.get(f"/es/loans/{loan_id}")
        s = r.json()
        print(f"[info] final state: renewed={s['renewed_count']}, late_fee={s['late_fee_cents']}, version={s['version']}")
        assert s["renewed_count"] == 2
        assert s["version"] == 4

        print("[step] history endpoint shows the event stream")
        r = http.get(f"/es/loans/{loan_id}/history")
        events = r.json()["events"]
        types = [e["event_type"] for e in events]
        print(f"[info] event types in stream: {types}")
        assert types == ["LoanCreatedV1", "LoanRenewedV1", "LoanRenewedV1", "LoanReturnedV2"]

    print("[ok] phase 10 client done -- event sourcing round-trip verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
