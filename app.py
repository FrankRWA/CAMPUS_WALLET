#!/usr/bin/env python3
"""
Campus Wallet – API server.

Endpoints
─────────
POST /api/reconcile                         chain integrity verification
POST /api/parent/login                      parent auth
POST /api/parent/logout
GET  /api/parent/me
POST /api/parent/initiate-recharge
POST /api/momo-webhook
GET  /api/student/<id>/balance              tablet sync

Run:  python3 app.py
"""

import hmac
import logging

from flask import Flask, jsonify, request

from parent_routes import parent_bp
from transactions import GENESIS_HASH, _compute_hash

# ─── App setup ────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.register_blueprint(parent_bp)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── CORS (allows both React dev servers on 5173 / 5174) ─────────────────────

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        res = app.make_response("")
        res.headers["Access-Control-Allow-Origin"]  = "*"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return res


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

# ─── Helpers ──────────────────────────────────────────────────────────────────

_REQUIRED = frozenset({"transaction_id", "student_id", "amount", "timestamp", "prev_hash", "curr_hash"})


def _err(message: str, **extra):
    return jsonify({"error": message, **extra}), 400


def _validate_tx(tx: dict, idx: int):
    missing = _REQUIRED - set(tx.keys())
    if missing:
        return _err("Transaction is missing required fields", index=idx, missing=sorted(missing))
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
            return _err(f"'{field}' must be a 64-character hex string", index=idx, transaction_id=tx_id)
    return None

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/api/reconcile", methods=["POST"])
def reconcile():
    data = request.get_json(silent=True)
    if data is None:
        return _err("Request body must be valid JSON with Content-Type: application/json")

    txs = data.get("transactions")
    if not isinstance(txs, list) or len(txs) == 0:
        return _err("'transactions' must be a non-empty array")

    for idx, tx in enumerate(txs):
        err = _validate_tx(tx, idx)
        if err:
            return err

    expected_prev = txs[0]["prev_hash"]
    for idx, tx in enumerate(txs):
        tx_id      = tx["transaction_id"]
        student_id = tx["student_id"]
        amount     = float(tx["amount"])
        timestamp  = tx["timestamp"]
        prev_hash  = tx["prev_hash"]
        curr_hash  = tx["curr_hash"]

        if not hmac.compare_digest(prev_hash, expected_prev):
            return _err(
                "Chain linkage broken: prev_hash does not match preceding block's curr_hash",
                index=idx, transaction_id=tx_id,
                expected_prev_hash=expected_prev, received_prev_hash=prev_hash,
            )

        recomputed = _compute_hash(prev_hash, student_id, amount, timestamp)
        if not hmac.compare_digest(curr_hash, recomputed):
            return _err(
                "Hash mismatch: curr_hash does not match SHA-256 recomputation",
                index=idx, transaction_id=tx_id,
                expected_hash=recomputed, received_hash=curr_hash,
            )
        expected_prev = curr_hash

    total  = round(sum(float(tx["amount"]) for tx in txs), 2)
    count  = len(txs)
    log.info("Reconciled %d transactions for %.2f RWF", count, total)

    return jsonify({
        "status": "ok",
        "message": f"Reconciled {count} transactions for {total:.2f} RWF",
        "transaction_count": count,
        "total_amount": total,
        "chain_tip": txs[-1]["curr_hash"],
    }), 200

# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
