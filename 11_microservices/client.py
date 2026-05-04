"""Phase 11 client: drives the three branch services exposed by docker-compose.

Assumes:
    docker compose up -d
has been run first. Branches are reachable on host ports 8011/8012/8013.
"""

from __future__ import annotations

import sys
import time
import uuid

import httpx


NORTH = "http://127.0.0.1:8011"
SOUTH = "http://127.0.0.1:8012"
WEST = "http://127.0.0.1:8013"


def wait_healthy(url: str) -> None:
    for _ in range(60):
        try:
            r = httpx.get(f"{url}/health", timeout=1.0)
            if r.status_code == 200:
                return
        except httpx.RequestError:
            pass
        time.sleep(1)
    raise RuntimeError(f"{url} never became healthy")


def main() -> int:
    suffix = uuid.uuid4().hex[:6]
    isbn = f"978000111{suffix[:3]}"

    print("[step] waiting for all three branches to be healthy")
    for url in (NORTH, SOUTH, WEST):
        wait_healthy(url)

    print("[step] register the book at north (3 copies)")
    r = httpx.post(f"{NORTH}/books", json={"isbn": isbn, "title": "Microservices Demo", "copies": 3})
    assert r.status_code == 201, r.text

    print("[step] confirm stock at north=3, south=0, west=0")
    assert httpx.get(f"{NORTH}/stock/{isbn}").json()["copies"] == 3
    assert httpx.get(f"{SOUTH}/stock/{isbn}").json()["copies"] == 0
    assert httpx.get(f"{WEST}/stock/{isbn}").json()["copies"] == 0

    print("[step] north ships 1 copy to south via /transfer/send")
    r = httpx.post(f"{NORTH}/transfer/send", json={"isbn": isbn, "to_branch": "south"})
    assert r.status_code == 200, r.text

    print("[step] new stock: north=2, south=1, west=0")
    assert httpx.get(f"{NORTH}/stock/{isbn}").json()["copies"] == 2
    assert httpx.get(f"{SOUTH}/stock/{isbn}").json()["copies"] == 1
    assert httpx.get(f"{WEST}/stock/{isbn}").json()["copies"] == 0

    print("[step] south borrows the local copy")
    r = httpx.post(f"{SOUTH}/borrow", json={"isbn": isbn})
    assert r.status_code == 200, r.text
    assert httpx.get(f"{SOUTH}/stock/{isbn}").json()["copies"] == 0

    print("[step] failed transfer: try shipping to a non-existent branch -> 400")
    r = httpx.post(f"{NORTH}/transfer/send", json={"isbn": isbn, "to_branch": "nowhere"})
    assert r.status_code == 400, r.text
    assert httpx.get(f"{NORTH}/stock/{isbn}").json()["copies"] == 2

    print("[ok] phase 11 client done -- three branches transacting over HTTP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
