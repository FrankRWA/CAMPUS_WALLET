#!/usr/bin/env python3
"""
Campus Wallet – database setup, student seeding, and QR code generation.

Run:  python3 setup_db_and_qr.py
"""

import json
import os
import random
import sqlite3
import string

import bcrypt
import qrcode

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = "campus_wallet.db"
QR_DIR = "./qr_codes"
TOKEN_MAP_PATH = "token_student_map.json"
DEFAULT_PIN = b"1234"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    code        TEXT    UNIQUE NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    account_number TEXT    UNIQUE NOT NULL,
    pin_hash       TEXT    NOT NULL,
    balance        REAL    NOT NULL DEFAULT 0.0,
    school_id      INTEGER REFERENCES schools(id),
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions_ledger (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL REFERENCES students(id),
    amount           REAL    NOT NULL,
    transaction_type TEXT    NOT NULL CHECK(transaction_type IN ('credit', 'debit')),
    description      TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
SCHOOLS = [
    ("University of Rwanda",              "UR"),
    ("Kigali Independent University",     "ULK"),
    ("Carnegie Mellon University Africa", "CMU"),
    ("Rwanda Polytechnic",                "RP"),
]

STUDENT_NAMES = [
    "Alice Johnson",    "Bob Smith",       "Carol White",    "David Brown",
    "Eva Martinez",     "Frank Wilson",    "Grace Lee",      "Henry Taylor",
    "Iris Anderson",    "Jack Thomas",     "Karen Jackson",  "Liam Harris",
    "Mia Garcia",       "Noah Martinez",   "Olivia Davis",   "Peter Robinson",
    "Quinn Thompson",   "Rachel Lewis",    "Samuel Walker",  "Tina Hall",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _account_number(index: int) -> str:
    return f"CW{index:04d}{random.randint(1000, 9999)}"


def _unique_suffix(used: set, length: int = 6) -> str:
    while True:
        s = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
        if s not in used:
            used.add(s)
            return s


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def setup_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    print("[db]  Schema created (schools, students, transactions_ledger).")


def seed_schools(conn: sqlite3.Connection) -> list[int]:
    cur = conn.cursor()
    ids = []
    for name, code in SCHOOLS:
        cur.execute("INSERT OR IGNORE INTO schools (name, code) VALUES (?, ?)", (name, code))
        cur.execute("SELECT id FROM schools WHERE code = ?", (code,))
        ids.append(cur.fetchone()[0])
    conn.commit()
    print(f"[db]  Seeded {len(SCHOOLS)} schools.")
    return ids


def seed_students(conn: sqlite3.Connection, school_ids: list[int]) -> list[int]:
    cur = conn.cursor()
    student_ids = []
    for i, name in enumerate(STUDENT_NAMES, start=1):
        pin_hash = bcrypt.hashpw(DEFAULT_PIN, bcrypt.gensalt()).decode()
        acct = _account_number(i)
        balance = round(random.uniform(0, 500), 2)
        school_id = random.choice(school_ids)
        cur.execute(
            """
            INSERT INTO students (name, account_number, pin_hash, balance, school_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, acct, pin_hash, balance, school_id),
        )
        student_ids.append(cur.lastrowid)
    conn.commit()
    print(f"[db]  Seeded {len(STUDENT_NAMES)} students (PIN='1234' for all).")
    return student_ids


# ---------------------------------------------------------------------------
# QR codes
# ---------------------------------------------------------------------------
def generate_qr_codes(student_ids: list[int]) -> dict[str, int]:
    os.makedirs(QR_DIR, exist_ok=True)
    used_suffixes: set[str] = set()
    token_map: dict[str, int] = {}

    for i, student_id in enumerate(student_ids, start=1):
        suffix = _unique_suffix(used_suffixes)
        token = f"TOKEN_{i:03d}_{suffix}"
        token_map[token] = student_id

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(token)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        filename = f"student_{student_id:03d}_{token}.png"
        img.save(os.path.join(QR_DIR, filename))

    print(f"[qr]  Generated {len(student_ids)} QR codes → '{QR_DIR}/'")
    return token_map


# ---------------------------------------------------------------------------
# Token map
# ---------------------------------------------------------------------------
def save_token_map(token_map: dict[str, int]) -> None:
    with open(TOKEN_MAP_PATH, "w") as fh:
        json.dump(token_map, fh, indent=2)
    print(f"[map] Token→student_id mapping saved → '{TOKEN_MAP_PATH}'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        setup_schema(conn)
        school_ids = seed_schools(conn)
        student_ids = seed_students(conn, school_ids)
        token_map = generate_qr_codes(student_ids)
        save_token_map(token_map)
    finally:
        conn.close()

    print("\nSetup complete.")
    print(f"  Database  : {DB_PATH}")
    print(f"  QR codes  : {QR_DIR}/  ({len(token_map)} files)")
    print(f"  Token map : {TOKEN_MAP_PATH}")


if __name__ == "__main__":
    main()
