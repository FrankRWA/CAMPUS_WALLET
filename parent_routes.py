#!/usr/bin/env python3
"""
Campus Wallet – parent portal routes (Flask Blueprint).

Endpoints
─────────
POST /api/parent/login
POST /api/parent/logout             (auth)
GET  /api/parent/me                 (auth)
POST /api/parent/initiate-recharge  (auth)
GET  /api/parent/recharges          (auth)
POST /api/momo-webhook
GET  /api/student/<id>/balance
"""

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps

import bcrypt
from flask import Blueprint, jsonify, request

DB_PATH = "campus_wallet.db"

parent_bp = Blueprint("parent", __name__)

# In-memory session store  token → parent_id.
# Replace with Redis or a DB-backed table for production.
_sessions: dict[str, int] = {}

# ─── Schema ───────────────────────────────────────────────────────────────────

_PARENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS parents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    phone         TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parent_student_links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id  INTEGER NOT NULL REFERENCES parents(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    UNIQUE(parent_id, student_id)
);

CREATE TABLE IF NOT EXISTS parent_recharges (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id          INTEGER NOT NULL REFERENCES students(id),
    parent_id           INTEGER REFERENCES parents(id),
    parent_phone        TEXT,
    amount              REAL    NOT NULL,
    momo_transaction_id TEXT    UNIQUE,
    status              TEXT    NOT NULL
        CHECK(status IN ('pending', 'verified', 'failed')),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at         TIMESTAMP
);
"""

# ─── DB helper ────────────────────────────────────────────────────────────────

@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_schema() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_PARENT_SCHEMA)
    conn.close()


_init_schema()

# ─── Auth ─────────────────────────────────────────────────────────────────────

def _bearer(request_obj) -> str:
    auth = request_obj.headers.get("Authorization", "")
    return auth[7:].strip() if auth.startswith("Bearer ") else ""


def _require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = _bearer(request)
        if not token or token not in _sessions:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, parent_id=_sessions[token], **kwargs)
    return wrapper


def _parent_payload(conn, parent_id: int) -> dict | None:
    """Return the full data bundle served on login / me."""
    parent = conn.execute(
        "SELECT id, name, email, phone FROM parents WHERE id = ?", (parent_id,)
    ).fetchone()
    if not parent:
        return None

    student = conn.execute(
        """SELECT s.id, s.name, s.balance
           FROM   parent_student_links l
           JOIN   students s ON s.id = l.student_id
           WHERE  l.parent_id = ?""",
        (parent_id,),
    ).fetchone()

    recharges = conn.execute(
        """SELECT id, amount, status, momo_transaction_id, created_at, verified_at
           FROM   parent_recharges
           WHERE  parent_id = ?
           ORDER  BY id DESC LIMIT 10""",
        (parent_id,),
    ).fetchall()

    return {
        "parent":   dict(parent),
        "student":  dict(student) if student else None,
        "recharges": [dict(r) for r in recharges],
    }

# ─── Routes ───────────────────────────────────────────────────────────────────

@parent_bp.route("/api/parent/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or {}
    email    = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    with _db() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM parents WHERE email = ?", (email,)
        ).fetchone()

    # Constant-time rejection prevents user-enumeration timing attacks.
    dummy_hash = b"$2b$12$AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    stored = row["password_hash"].encode() if row else dummy_hash
    matched = bcrypt.checkpw(password.encode(), stored)

    if not row or not matched:
        return jsonify({"error": "Invalid email or password"}), 401

    token = secrets.token_urlsafe(32)
    _sessions[token] = row["id"]

    with _db() as conn:
        payload = _parent_payload(conn, row["id"])

    return jsonify({"token": token, **payload})


@parent_bp.route("/api/parent/logout", methods=["POST"])
def logout():
    _sessions.pop(_bearer(request), None)
    return jsonify({"success": True})


@parent_bp.route("/api/parent/me", methods=["GET"])
@_require_auth
def me(parent_id):
    with _db() as conn:
        payload = _parent_payload(conn, parent_id)
    if not payload:
        return jsonify({"error": "Parent not found"}), 404
    return jsonify(payload)


@parent_bp.route("/api/parent/initiate-recharge", methods=["POST"])
@_require_auth
def initiate_recharge(parent_id):
    data   = request.get_json(silent=True) or {}
    amount = data.get("amount")
    phone  = str(data.get("parent_phone", "")).strip()

    if amount is None or float(amount) < 100:
        return jsonify({"error": "amount must be at least 100 RWF"}), 400

    amount = round(float(amount), 2)

    with _db() as conn:
        link = conn.execute(
            "SELECT student_id FROM parent_student_links WHERE parent_id = ?", (parent_id,)
        ).fetchone()
        if not link:
            return jsonify({"error": "No linked student found"}), 404

        student_id = link["student_id"]
        student    = conn.execute(
            "SELECT name FROM students WHERE id = ?", (student_id,)
        ).fetchone()

        tx_id = f"RC_{secrets.token_hex(5).upper()}"
        conn.execute(
            """INSERT INTO parent_recharges
               (student_id, parent_id, parent_phone, amount, momo_transaction_id, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (student_id, parent_id, phone or None, amount, tx_id),
        )

    return jsonify({
        "transaction_id":    tx_id,
        "amount":            amount,
        "student_name":      student["name"],
        "momo_payment_link": f"https://momo.rw/pay?txn={tx_id}&amount={int(amount)}&to=CAMPUS_WALLET",
    })


@parent_bp.route("/api/momo-webhook", methods=["POST"])
def momo_webhook():
    """
    Called by MoMo after payment completes or fails.
    Production: verify MTN/Airtel HMAC signature before trusting the payload.
    Demo:       call directly to simulate a payment outcome.
    """
    data   = request.get_json(silent=True) or {}
    tx_id  = str(data.get("transaction_id", "")).strip()
    status = str(data.get("status", "")).strip().lower()

    if not tx_id:
        return jsonify({"error": "transaction_id is required"}), 400
    if status not in ("completed", "failed"):
        return jsonify({"error": "status must be 'completed' or 'failed'"}), 400

    new_balance = None
    db_status   = "verified" if status == "completed" else "failed"
    now         = datetime.now(timezone.utc).isoformat()

    with _db() as conn:
        recharge = conn.execute(
            """SELECT id, student_id, amount, status
               FROM   parent_recharges
               WHERE  momo_transaction_id = ?""",
            (tx_id,),
        ).fetchone()

        if not recharge:
            return jsonify({"error": "Transaction not found"}), 404
        if recharge["status"] != "pending":
            return jsonify({"error": f"Transaction already {recharge['status']}"}), 409

        conn.execute(
            "UPDATE parent_recharges SET status = ?, verified_at = ? WHERE momo_transaction_id = ?",
            (db_status, now, tx_id),
        )

        if status == "completed":
            conn.execute(
                "UPDATE students SET balance = balance + ? WHERE id = ?",
                (recharge["amount"], recharge["student_id"]),
            )
            row         = conn.execute(
                "SELECT balance FROM students WHERE id = ?", (recharge["student_id"],)
            ).fetchone()
            new_balance = row["balance"]

    resp = {"success": True, "transaction_id": tx_id, "status": db_status}
    if new_balance is not None:
        resp["new_balance"] = new_balance
    return jsonify(resp)


@parent_bp.route("/api/student/<int:student_id>/balance", methods=["GET"])
def student_balance(student_id: int):
    """Cashier-tablet sync endpoint — returns current cloud balance."""
    with _db() as conn:
        row = conn.execute(
            "SELECT id, name, balance, created_at FROM students WHERE id = ?", (student_id,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Student not found"}), 404
    return jsonify({
        "student_id":   row["id"],
        "name":         row["name"],
        "balance":      row["balance"],
        "last_updated": row["created_at"],
    })
