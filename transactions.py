#!/usr/bin/env python3
"""
Campus Wallet – cryptographic transaction chain with bcrypt PIN verification.

Public API
----------
process_transaction(conn, student_id, pin, amount, description, transaction_type)
    -> TransactionResult

verify_chain(conn) -> bool
print_chain(conn)

Run as a script to execute 5 demo transactions:
    python3 transactions.py
"""

import hashlib
import hmac
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import bcrypt

DB_PATH = "campus_wallet.db"

# Anchors the chain – 64 hex zeros, representing 256 bits of "nothing before this".
GENESIS_HASH = "0" * 64


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TransactionError(Exception):
    """Base for all transaction failures."""


class AuthError(TransactionError):
    """PIN verification failed or student not found."""


class InsufficientFundsError(TransactionError):
    """Debit amount exceeds available balance."""


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class TransactionResult:
    transaction_id: int
    prev_hash: str
    curr_hash: str
    student_id: int
    amount: float
    transaction_type: str
    balance_after: float
    timestamp: str


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

def _migrate_ledger(conn: sqlite3.Connection) -> None:
    """Add prev_hash / curr_hash columns to transactions_ledger if absent."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(transactions_ledger)")}
    for col in ("prev_hash", "curr_hash"):
        if col not in existing:
            conn.execute(f"ALTER TABLE transactions_ledger ADD COLUMN {col} TEXT")
    conn.commit()


# ---------------------------------------------------------------------------
# Cryptographic chain helpers
# ---------------------------------------------------------------------------

def _compute_hash(prev_hash: str, student_id: int, amount: float, timestamp: str) -> str:
    """SHA-256( prev_hash || student_id || amount || timestamp )"""
    payload = f"{prev_hash}{student_id}{amount:.10f}{timestamp}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _chain_tip(conn: sqlite3.Connection) -> str:
    """Most recent curr_hash, or GENESIS_HASH when the chain is empty."""
    row = conn.execute(
        "SELECT curr_hash FROM transactions_ledger "
        "WHERE curr_hash IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else GENESIS_HASH


# ---------------------------------------------------------------------------
# PIN verification
# ---------------------------------------------------------------------------

def _verify_pin(conn: sqlite3.Connection, student_id: int, pin: str) -> None:
    """
    Raise AuthError when the PIN is wrong.

    bcrypt.checkpw already performs its internal comparison with
    hmac.compare_digest; we apply a second constant-time gate on the boolean
    result to eliminate any residual branch-timing leakage at this call site.
    """
    row = conn.execute(
        "SELECT pin_hash FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    if row is None:
        raise AuthError(f"Student {student_id} not found.")

    matched = bcrypt.checkpw(pin.encode(), row[0].encode())
    # Map the boolean to equal-length byte strings before comparing,
    # so the comparison takes constant time regardless of the result.
    if not hmac.compare_digest(b"\x01" if matched else b"\x00", b"\x01"):
        raise AuthError("Invalid PIN.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_transaction(
    conn: sqlite3.Connection,
    student_id: int,
    pin: str,
    amount: float,
    description: str = "",
    transaction_type: str = "debit",
) -> TransactionResult:
    """
    Full transaction pipeline:
      1. Validate inputs.
      2. Verify PIN with constant-time bcrypt check.
      3. Inside one atomic DB transaction:
         a. Read the current chain tip.
         b. Compute SHA-256 hash linking this record to the chain.
         c. Read and adjust student balance.
         d. INSERT into transactions_ledger with both hash fields.
    Returns TransactionResult with transaction_id and curr_hash for audit.

    Raises
    ------
    AuthError              – wrong PIN or unknown student_id
    InsufficientFundsError – debit would make balance negative
    TransactionError       – invalid amount or transaction_type
    """
    if transaction_type not in ("credit", "debit"):
        raise TransactionError(f"Unknown transaction_type: {transaction_type!r}")
    if amount <= 0:
        raise TransactionError("Amount must be positive.")

    _migrate_ledger(conn)

    # PIN check is a read-only pre-flight; no balance is touched yet.
    _verify_pin(conn, student_id, pin)

    # Fix the timestamp before entering the write transaction so the hash
    # we compute outside matches the value stored in the ledger row.
    timestamp = datetime.now(timezone.utc).isoformat()

    with conn:  # BEGIN … COMMIT; rolls back automatically on any exception
        # Read chain tip inside the transaction to prevent a race where another
        # writer inserts between our tip-read and our INSERT.
        prev_hash = _chain_tip(conn)
        curr_hash = _compute_hash(prev_hash, student_id, amount, timestamp)

        row = conn.execute(
            "SELECT balance FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        balance = row[0]

        if transaction_type == "debit":
            if balance < amount:
                raise InsufficientFundsError(
                    f"Insufficient funds: balance={balance:.2f}, requested={amount:.2f}"
                )
            new_balance = round(balance - amount, 2)
        else:
            new_balance = round(balance + amount, 2)

        conn.execute(
            "UPDATE students SET balance = ? WHERE id = ?", (new_balance, student_id)
        )
        cur = conn.execute(
            """
            INSERT INTO transactions_ledger
                (student_id, amount, transaction_type, description,
                 prev_hash, curr_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, amount, transaction_type, description,
             prev_hash, curr_hash, timestamp),
        )
        tx_id = cur.lastrowid

    return TransactionResult(
        transaction_id=tx_id,
        prev_hash=prev_hash,
        curr_hash=curr_hash,
        student_id=student_id,
        amount=amount,
        transaction_type=transaction_type,
        balance_after=new_balance,
        timestamp=timestamp,
    )


def verify_chain(conn: sqlite3.Connection) -> bool:
    """
    Walk every chained record in insertion order and recompute each hash.
    Returns True when the chain is intact; prints the first broken link and
    returns False if any record has been tampered with.
    """
    _migrate_ledger(conn)
    rows = conn.execute(
        """SELECT id, student_id, amount, prev_hash, curr_hash, created_at
           FROM   transactions_ledger
           WHERE  curr_hash IS NOT NULL
           ORDER  BY id"""
    ).fetchall()

    expected_prev = GENESIS_HASH
    for tx_id, student_id, amount, prev_hash, curr_hash, created_at in rows:
        if not hmac.compare_digest(prev_hash, expected_prev):
            print(f"  [CHAIN BROKEN] tx {tx_id}: prev_hash mismatch")
            return False
        expected = _compute_hash(prev_hash, student_id, amount, created_at)
        if not hmac.compare_digest(curr_hash, expected):
            print(f"  [CHAIN BROKEN] tx {tx_id}: curr_hash mismatch (record tampered?)")
            return False
        expected_prev = curr_hash

    return True


def print_chain(conn: sqlite3.Connection) -> None:
    """Pretty-print every chained transaction and verify integrity."""
    _migrate_ledger(conn)
    rows = conn.execute(
        """
        SELECT tl.id, tl.student_id, s.name, tl.amount, tl.transaction_type,
               tl.description, tl.prev_hash, tl.curr_hash, tl.created_at
        FROM   transactions_ledger tl
        JOIN   students s ON s.id = tl.student_id
        WHERE  tl.curr_hash IS NOT NULL
        ORDER  BY tl.id
        """
    ).fetchall()

    W = 74
    print("=" * W)
    print("  CAMPUS WALLET  —  TRANSACTION CHAIN")
    print("=" * W)
    print(f"  {'GENESIS':10}  {GENESIS_HASH[:40]}…")
    print("-" * W)

    for tx_id, student_id, name, amount, tx_type, desc, prev_hash, curr_hash, ts in rows:
        sign = "−" if tx_type == "debit" else "+"
        print(f"  Block #{tx_id:<5} {name} (student_id={student_id})")
        print(f"  Type    :  {tx_type}   {sign} RWF {amount:>10,.2f}")
        print(f"  Desc    :  {desc or '—'}")
        print(f"  Time    :  {ts}")
        print(f"  Prev    :  {prev_hash[:40]}…")
        print(f"  Hash    :  {curr_hash[:40]}…")
        print("-" * W)

    integrity_ok = verify_chain(conn)
    status = "VALID  ✓" if integrity_ok else "BROKEN ✗"
    print(f"  Chain integrity : {status}   ({len(rows)} block(s))")
    print("=" * W)


# ---------------------------------------------------------------------------
# Demo / smoke-test  (python3 transactions.py)
# ---------------------------------------------------------------------------

def _run_demo(conn: sqlite3.Connection) -> None:
    _migrate_ledger(conn)

    students = conn.execute(
        "SELECT id, name, balance FROM students ORDER BY id LIMIT 5"
    ).fetchall()
    if not students:
        print("No students found – run setup_db_and_qr.py first.")
        return

    # (student_id, description, amount, transaction_type)
    samples = [
        (students[0][0], "Canteen lunch",         50.00, "debit"),
        (students[1][0], "Library fine",          15.50, "debit"),
        (students[2][0], "Sports equipment rent", 30.00, "debit"),
        (students[3][0], "Bursary top-up",       100.00, "credit"),
        (students[4][0], "Campus bus fare",        20.00, "debit"),
    ]

    print("\n  Processing 5 sample transactions…\n")
    for student_id, desc, amount, tx_type in samples:
        try:
            r = process_transaction(
                conn,
                student_id=student_id,
                pin="1234",
                amount=amount,
                description=desc,
                transaction_type=tx_type,
            )
            sign = "−" if tx_type == "debit" else "+"
            print(
                f"  [OK]  tx_id={r.transaction_id:<3}"
                f"  student={r.student_id:<3}"
                f"  {sign}RWF {amount:>7,.2f}"
                f"  balance_after={r.balance_after:>8,.2f}"
                f"  hash={r.curr_hash[:16]}…"
            )
        except TransactionError as exc:
            print(f"  [ERR] student={student_id}: {exc}")

    print()
    print_chain(conn)


if __name__ == "__main__":
    _conn = sqlite3.connect(DB_PATH)
    _conn.execute("PRAGMA foreign_keys = ON")
    try:
        _run_demo(_conn)
    finally:
        _conn.close()
