"""SQLite storage for the condo data: areas, apartments, reservations and visitors.

The partial unique index on ``reservas`` is what guarantees a single active
reservation per area and date: it is checked by SQLite at the moment of the
insert, so two concurrent writers can never both succeed.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import string
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from aurora import config

CODE_PREFIX = "RSV-"
CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 6
MAX_CODE_ATTEMPTS = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS areas (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    taxa REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS apartamentos (
    numero TEXT PRIMARY KEY,
    morador TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservas (
    codigo TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL,
    area TEXT NOT NULL,
    data TEXT NOT NULL,
    cancelada_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS reservas_area_data_ativa
    ON reservas (area, data) WHERE cancelada_em IS NULL;
CREATE TABLE IF NOT EXISTS visitantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL,
    nome TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS codigos_reserva (
    codigo TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS sessoes (
    session_id TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL,
    criada_em TEXT NOT NULL
);
"""

_initialized: set[Path] = set()
_init_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(path: Path) -> None:
    with _init_lock:
        if path in _initialized:
            return
        is_new = not path.exists()
        conn = _open(path)
        try:
            conn.executescript(SCHEMA)
            if is_new:
                _load_seed(conn)
        finally:
            conn.close()
        _initialized.add(path)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = config.condo_db_path()
    _ensure_schema(path)
    conn = _open(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _transaction(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _read_json(name: str) -> list[dict]:
    return json.loads((config.DADOS_DIR / name).read_text(encoding="utf-8"))


def _load_seed(conn: sqlite3.Connection) -> None:
    with _transaction(conn):
        _replace_condo_data(conn)


def _replace_condo_data(conn: sqlite3.Connection) -> None:
    for table in ("reservas", "visitantes", "areas", "apartamentos"):
        conn.execute(f"DELETE FROM {table}")
    conn.executemany(
        "INSERT INTO areas (id, nome, taxa) VALUES (:id, :nome, :taxa)",
        _read_json("areas.json"),
    )
    conn.executemany(
        "INSERT INTO apartamentos (numero, morador) VALUES (:numero, :morador)",
        _read_json("apartamentos.json"),
    )
    reservas = _read_json("reservas.json")
    conn.executemany(
        "INSERT INTO reservas (codigo, apartamento, area, data)"
        " VALUES (:codigo, :apartamento, :area, :data)",
        reservas,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO codigos_reserva (codigo) VALUES (:codigo)",
        reservas,
    )
    conn.executemany(
        "INSERT INTO visitantes (apartamento, nome, data)"
        " VALUES (:apartamento, :nome, :data)",
        _read_json("visitantes.json"),
    )


def restore() -> None:
    """Brings areas, apartments, reservations and visitors back to ``dados/``.

    Issued reservation codes and sessions are kept, so no code is ever reused.
    """
    with _connect() as conn, _transaction(conn):
        _replace_condo_data(conn)


def list_areas() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, nome, taxa FROM areas ORDER BY nome")
        return [dict(row) for row in rows]


def get_area(area_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, nome, taxa FROM areas WHERE id = ?", (area_id,)
        ).fetchone()
        return dict(row) if row else None


def apartment_exists(numero: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM apartamentos WHERE numero = ?", (numero,)
        ).fetchone()
        return row is not None


def list_reservations(apartamento: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT codigo, area, data FROM reservas"
            " WHERE apartamento = ? AND cancelada_em IS NULL"
            " ORDER BY data, area",
            (apartamento,),
        )
        return [dict(row) for row in rows]


def is_available(area: str, data: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM reservas"
            " WHERE area = ? AND data = ? AND cancelada_em IS NULL",
            (area, data),
        ).fetchone()
        return row is None


def _new_code(conn: sqlite3.Connection) -> str:
    for _ in range(MAX_CODE_ATTEMPTS):
        code = CODE_PREFIX + "".join(
            secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH)
        )
        try:
            conn.execute("INSERT INTO codigos_reserva (codigo) VALUES (?)", (code,))
        except sqlite3.IntegrityError:
            continue
        return code
    raise RuntimeError("could not generate a unique reservation code")


def create_reservation(apartamento: str, area: str, data: str) -> str | None:
    """Creates an active reservation and returns its code.

    Returns ``None`` when the area is already taken on that date; the check is
    the unique index itself, evaluated atomically with the insert.
    """
    with _connect() as conn:
        try:
            with _transaction(conn):
                code = _new_code(conn)
                conn.execute(
                    "INSERT INTO reservas (codigo, apartamento, area, data)"
                    " VALUES (?, ?, ?, ?)",
                    (code, apartamento, area, data),
                )
        except sqlite3.IntegrityError:
            return None
        return code


def cancel_reservation(apartamento: str, area: str, data: str) -> str | None:
    """Cancels the apartment's own active reservation; returns its code or None."""
    with _connect() as conn, _transaction(conn):
        row = conn.execute(
            "SELECT codigo FROM reservas WHERE apartamento = ? AND area = ?"
            " AND data = ? AND cancelada_em IS NULL",
            (apartamento, area, data),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE reservas SET cancelada_em = ? WHERE codigo = ?",
            (_now(), row["codigo"]),
        )
        return row["codigo"]


def list_visitors(apartamento: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento = ?"
            " ORDER BY data, id",
            (apartamento,),
        )
        return [dict(row) for row in rows]


def add_visitor(apartamento: str, nome: str, data: str) -> None:
    with _connect() as conn, _transaction(conn):
        conn.execute(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
            (apartamento, nome, data),
        )


def save_session(session_id: str, apartamento: str) -> None:
    with _connect() as conn, _transaction(conn):
        conn.execute(
            "INSERT INTO sessoes (session_id, apartamento, criada_em) VALUES (?, ?, ?)",
            (session_id, apartamento, _now()),
        )


def session_apartment(session_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT apartamento FROM sessoes WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["apartamento"] if row else None
