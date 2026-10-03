"""Conexão com o SQLite.

Use sempre `with get_conn() as conn:` — a conexão faz commit ao sair
do bloco sem erro, rollback se houver exceção, e fecha no final.
"""
import sqlite3
from contextlib import contextmanager

import pandas as pd

from config.settings import DB_PATH


def _connect(db_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_conn(db_path=None):
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- Atalhos usados pelos repositórios -----------------------------------
def query_df(sql: str, params: tuple | list = ()) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def query_one(sql: str, params: tuple | list = ()) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def query_all(sql: str, params: tuple | list = ()) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple | list = ()) -> int:
    """Executa um comando e devolve o id da linha inserida (ou linhas afetadas)."""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount


def execute_many(sql: str, rows: list[tuple]) -> int:
    with get_conn() as conn:
        cur = conn.executemany(sql, rows)
        return cur.rowcount
