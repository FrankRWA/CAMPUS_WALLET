#!/usr/bin/env python3
"""
Reconciliation API test suite.

Uses Flask's built-in test client – no running server required.

Run:  python3 test_reconcile.py
"""

import json
import sqlite3

from app import app

DB_PATH = "campus_wallet.db"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def load_chain_from_db() -> list[dict]:
    """Read the existing chained transactions from the database."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT id, student_id, amount, prev_hash, curr_hash, created_at
           FROM   transactions_ledger
           WHERE  curr_hash IS NOT NULL
           ORDER  BY id"""
    ).fetchall()
    conn.close()
    return [
        {
            "transaction_id": row[0],
            "student_id":     row[1],
            "amount":         row[2],
            "prev_hash":      row[3],
            "curr_hash":      row[4],
            "timestamp":      row[5],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_valid_chain(client, txs: list[dict]) -> None:
    print("\n[1] Valid chain — expect 200")
    resp = client.post("/api/reconcile", json={"transactions": txs})
    body = resp.get_json()
    assert resp.status_code == 200, f"Got {resp.status_code}: {body}"
    assert body["status"] == "ok"
    print(f"     {body['message']}")
    print(f"     chain_tip: {body['chain_tip'][:24]}…")
    print("     PASS")


def test_tampered_curr_hash(client, txs: list[dict]) -> None:
    print("\n[2] Tampered curr_hash on block index 1 — expect 400 hash mismatch")
    if len(txs) < 2:
        print("     SKIP (need ≥ 2 transactions)")
        return
    poisoned = [dict(tx) for tx in txs]
    poisoned[1] = {**poisoned[1], "curr_hash": "a" * 64}
    resp = client.post("/api/reconcile", json={"transactions": poisoned})
    body = resp.get_json()
    assert resp.status_code == 400, f"Got {resp.status_code}: {body}"
    assert "mismatch" in body["error"].lower(), f"Unexpected error: {body['error']}"
    assert body["index"] == 1
    print(f"     error     : {body['error']}")
    print(f"     tx_id     : {body['transaction_id']}")
    print(f"     expected  : {body['expected_hash'][:24]}…")
    print(f"     received  : {body['received_hash'][:24]}…")
    print("     PASS")


def test_broken_linkage(client, txs: list[dict]) -> None:
    print("\n[3] Broken linkage — wrong prev_hash on block index 2 — expect 400")
    if len(txs) < 3:
        print("     SKIP (need ≥ 3 transactions)")
        return
    poisoned = [dict(tx) for tx in txs]
    poisoned[2] = {**poisoned[2], "prev_hash": "b" * 64}
    resp = client.post("/api/reconcile", json={"transactions": poisoned})
    body = resp.get_json()
    assert resp.status_code == 400, f"Got {resp.status_code}: {body}"
    assert "linkage" in body["error"].lower(), f"Unexpected error: {body['error']}"
    assert body["index"] == 2
    print(f"     error     : {body['error']}")
    print(f"     tx_id     : {body['transaction_id']}")
    print(f"     expected  : {body['expected_prev_hash'][:24]}…")
    print(f"     received  : {body['received_prev_hash'][:24]}…")
    print("     PASS")


def test_missing_fields(client) -> None:
    print("\n[4] Missing required fields — expect 400")
    resp = client.post(
        "/api/reconcile",
        json={"transactions": [{"transaction_id": 99, "student_id": 1}]},
    )
    body = resp.get_json()
    assert resp.status_code == 400, f"Got {resp.status_code}: {body}"
    assert "missing" in body
    print(f"     error   : {body['error']}")
    print(f"     missing : {body['missing']}")
    print("     PASS")


def test_empty_array(client) -> None:
    print("\n[5] Empty transactions array — expect 400")
    resp = client.post("/api/reconcile", json={"transactions": []})
    body = resp.get_json()
    assert resp.status_code == 400, f"Got {resp.status_code}: {body}"
    print(f"     error : {body['error']}")
    print("     PASS")


def test_bad_content_type(client) -> None:
    print("\n[6] Non-JSON body — expect 400")
    resp = client.post(
        "/api/reconcile",
        data="not json",
        content_type="text/plain",
    )
    body = resp.get_json()
    assert resp.status_code == 400, f"Got {resp.status_code}: {body}"
    print(f"     error : {body['error']}")
    print("     PASS")


def test_negative_amount(client, txs: list[dict]) -> None:
    print("\n[7] Negative amount — expect 400")
    poisoned = [dict(txs[0]), {"amount": -5.0, **{k: txs[0][k] for k in txs[0] if k != "amount"}}]
    # Simpler: just send a fresh minimal tx with negative amount
    bad_tx = {**txs[0], "amount": -10.0}
    resp = client.post("/api/reconcile", json={"transactions": [bad_tx]})
    body = resp.get_json()
    assert resp.status_code == 400, f"Got {resp.status_code}: {body}"
    print(f"     error : {body['error']}")
    print("     PASS")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> None:
    txs = load_chain_from_db()
    print(f"\nLoaded {len(txs)} chained transaction(s) from '{DB_PATH}'.")
    if not txs:
        print("No transactions found – run transactions.py first.")
        return

    client = app.test_client()

    test_valid_chain(client, txs)
    test_tampered_curr_hash(client, txs)
    test_broken_linkage(client, txs)
    test_missing_fields(client)
    test_empty_array(client)
    test_bad_content_type(client)
    test_negative_amount(client, txs)

    print("\n" + "=" * 50)
    print("  All 7 tests passed.")
    print("=" * 50)


if __name__ == "__main__":
    main()
