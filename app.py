#!/usr/bin/env python3
"""
Campus Wallet – reconciliation API.

POST /api/reconcile
  Content-Type : application/json
  Body : {
      "transactions": [
          {
              "transaction_id" : <int>,
              "student_id"     : <int>,
              "amount"         : <number>,
              "timestamp"      : <ISO-8601 string>,
              "prev_hash"      : <64-char hex string>,
              "curr_hash"      : <64-char hex string>
          },
          …
      ]
  }

  200 – chain is intact
  400 – malformed request or any hash / linkage mismatch (details in body)

Run:  python3 app.py
"""

import hmac
import logging

from flask import Flask, jsonify, request

from transactions import GENESIS_HASH, _compute_hash

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_REQUIRED_FIELDS = frozenset(
    {"transaction_id", "student_id", "amount", "timestamp", "prev_hash", "curr_hash"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _err(message: str, **extra):
    """Return a 400 JSON response."""
    return jsonify({"error": message, **extra}), 400


def _validate_tx(tx: dict, idx: int):
    """
    Return an _err tuple when the transaction dict is malformed, else None.
    Checks required fields, types, and hash string length.
    """
    missing = _REQUIRED_FIELDS - set(tx.keys())
    if missing:
        return _err(
            "Transaction is missing required fields",
            index=idx,
            missing=sorted(missing),
        )

    tx_id = tx.get("transaction_id")

    if not isinstance(tx["student_id"], int):
        return _err("'student_id' must be an integer", index=idx, transaction_id=tx_id)

    if not isinstance(tx["amount"], (int, float)) or isinstance(tx["amount"], bool):
        return _err("'amount' must be a number", index=idx, transaction_id=tx_id)

    if tx["amount"] <= 0:
        return _err("'amount' must be positive", index=idx, transaction_id=tx_id)

    if not isinstance(tx["timestamp"], str) or not tx["timestamp"].strip():
        return _err("'timestamp' must be a non-empty ISO-8601 string", index=idx, transaction_id=tx_id)

    for field in ("prev_hash", "curr_hash"):
        v = tx.get(field)
        if not isinstance(v, str) or len(v) != 64:
            return _err(
                f"'{field}' must be a 64-character hex string",
                index=idx,
                transaction_id=tx_id,
            )

    return None


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.route("/api/reconcile", methods=["POST"])
def reconcile():
    data = request.get_json(silent=True)
    if data is None:
        return _err("Request body must be valid JSON with Content-Type: application/json")

    txs = data.get("transactions")
    if not isinstance(txs, list) or len(txs) == 0:
        return _err("'transactions' must be a non-empty array")

    # --- Field validation pass ---
    for idx, tx in enumerate(txs):
        err = _validate_tx(tx, idx)
        if err:
            return err

    # --- Cryptographic chain verification pass ---
    # The first block's prev_hash is the accepted anchor; subsequent blocks
    # must chain from it. We do NOT enforce GENESIS_HASH as the anchor so
    # that partial-chain reconciliation (mid-chain batches) is supported.
    expected_prev = txs[0]["prev_hash"]

    for idx, tx in enumerate(txs):
        tx_id     = tx["transaction_id"]
        student_id = tx["student_id"]
        amount    = float(tx["amount"])
        timestamp = tx["timestamp"]
        prev_hash = tx["prev_hash"]
        curr_hash = tx["curr_hash"]

        # 1. Linkage check: each block's prev_hash must equal its predecessor's curr_hash.
        if not hmac.compare_digest(prev_hash, expected_prev):
            return _err(
                "Chain linkage broken: prev_hash does not match preceding block's curr_hash",
                index=idx,
                transaction_id=tx_id,
                expected_prev_hash=expected_prev,
                received_prev_hash=prev_hash,
            )

        # 2. Hash integrity: recompute SHA-256(prev_hash||student_id||amount||timestamp).
        recomputed = _compute_hash(prev_hash, student_id, amount, timestamp)
        if not hmac.compare_digest(curr_hash, recomputed):
            return _err(
                "Hash mismatch: curr_hash does not match SHA-256 recomputation",
                index=idx,
                transaction_id=tx_id,
                expected_hash=recomputed,
                received_hash=curr_hash,
            )

        expected_prev = curr_hash

    # --- All blocks verified ---
    total_amount = round(sum(float(tx["amount"]) for tx in txs), 2)
    count = len(txs)

    log.info("Reconciled %d transactions for %.2f RWF", count, total_amount)

    return jsonify({
        "status": "ok",
        "message": f"Reconciled {count} transactions for {total_amount:.2f} RWF",
        "transaction_count": count,
        "total_amount": total_amount,
        "chain_tip": txs[-1]["curr_hash"],
    }), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
