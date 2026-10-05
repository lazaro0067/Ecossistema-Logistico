"""Conexão com o banco — funciona com SQLite (local) ou PostgreSQL (nuvem).

Qual banco usar:
  • Se existir DATABASE_URL (variável de ambiente ou em st.secrets) começando
    com "postgres", usa PostgreSQL (ex.: Supabase). Obrigatório no Streamlit
    Cloud, onde arquivos locais são apagados a cada reinício.
  • Caso contrário, usa o arquivo SQLite em data/ecossistema.db.

O resto do sistema escreve SQL no estilo SQLite (parâmetros com "?");
a tradução para PostgreSQL é feita aqui, num lugar só.

Uso:  with get_conn() as conn:  conn.execute(sql, params)
"""
import re
import sqlite3
from contextlib import contextmanager

import pandas as pd

from config.settings import DB_PATH

# Tabelas que NÃO têm coluna "id" (o INSERT no Postgres não pode pedir RETURNING id)
_SEM_ID = {"usuario_modulos", "usuario_operacoes", "produtos", "estoque", "linear_vendas", "metas_doi", "fluxo_caixa",
           "_migracoes"}


def database_url() -> str | None:
    from core.segredos import segredo
    return segredo("DATABASE_URL")


def is_postgres() -> bool:
    url = database_url()
    return bool(url and url.startswith(("postgres://", "postgresql://")))


# --- Tradução de SQL SQLite -> PostgreSQL ---------------------------------
def traduzir_sql(sql: str) -> str:
    sql = re.sub(r"group_concat\(", "string_agg(", sql, flags=re.I)
    sql = sql.replace("%", "%%").replace("?", "%s")
    return sql


def traduzir_ddl(ddl: str) -> str:
    ddl = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", ddl)
    ddl = re.sub(r"\bREAL\b", "DOUBLE PRECISION", ddl)
    ddl = re.sub(r"\bBLOB\b", "BYTEA", ddl)
    ddl = ddl.replace("(datetime('now','localtime'))", "(to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))")
    return ddl


# --- Cursor/conexão com a mesma "cara" nos dois bancos --------------------
class Linha(dict):
    """Linha que aceita acesso por nome (r['id']) e por posição (r[0])."""

    def __init__(self, colunas, valores):
        super().__init__(zip(colunas, valores))
        self._valores = list(valores)

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._valores[k]
        return super().__getitem__(k)


class _Cursor:
    def __init__(self, cur, lastrowid=None, linhas=None):
        self._cur = cur
        self.lastrowid = lastrowid if lastrowid is not None else getattr(cur, "lastrowid", None)
        self.rowcount = cur.rowcount
        self._linhas = linhas
        self.colunas = [d[0] for d in cur.description] if cur.description else []

    def _conv(self, r):
        if r is None:
            return None
        v = [bytes(x) if isinstance(x, memoryview) else x for x in r]
        return Linha(self.colunas, v)

    def fetchone(self):
        if self._linhas is not None:
            return self._conv(self._linhas.pop(0)) if self._linhas else None
        return self._conv(self._cur.fetchone())

    def fetchall(self):
        if self._linhas is not None:
            r, self._linhas = self._linhas, []
            return [self._conv(x) for x in r]
        return [self._conv(x) for x in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Conexao:
    def __init__(self, raw, pg: bool):
        self.raw, self.pg = raw, pg

    def execute(self, sql: str, params=()) -> _Cursor:
        cur = self.raw.cursor()
        if not self.pg:
            cur.execute(sql, tuple(params))
            return _Cursor(cur)
        sql_pg = traduzir_sql(sql)
        m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
        if m and m.group(1) not in _SEM_ID and "RETURNING" not in sql.upper():
            cur.execute(sql_pg + " RETURNING id", tuple(params))
            row = cur.fetchone() if cur.description else None
            return _Cursor(cur, lastrowid=row[0] if row else None, linhas=[])
        cur.execute(sql_pg, tuple(params))
        return _Cursor(cur)

    def executemany(self, sql: str, linhas) -> _Cursor:
        cur = self.raw.cursor()
        linhas = [tuple(l) for l in linhas]
        if self.pg:
            cur.executemany(traduzir_sql(sql), linhas)
        else:
            cur.executemany(sql, linhas)
        return _Cursor(cur)

    def executescript(self, script: str) -> None:
        if not self.pg:
            self.raw.executescript(script)
            return
        cur = self.raw.cursor()
        for stmt in traduzir_ddl(script).split(";"):
            if stmt.strip() and not all(l.strip().startswith("--") or not l.strip() for l in stmt.splitlines()):
                cur.execute(stmt)


# --- Pool simples de conexões Postgres (evita reconectar a cada consulta) --
_pool = None


def _pg_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(database_url(), min_size=1, max_size=5, open=True,
                               kwargs={"prepare_threshold": None, "connect_timeout": 15})
        import atexit
        atexit.register(_pool.close)
    return _pool


@contextmanager
def get_conn(db_path=None):
    if is_postgres() and db_path is None:
        with _pg_pool().connection() as raw:
            conn = Conexao(raw, pg=True)
            try:
                yield conn
                raw.commit()
            except Exception:
                raw.rollback()
                raise
        return

    raw = sqlite3.connect(db_path or DB_PATH, timeout=15)
    raw.execute("PRAGMA foreign_keys = ON")
    try:
        raw.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    conn = Conexao(raw, pg=False)
    try:
        yield conn
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def tipo_violacao(e: Exception) -> str | None:
    """'unica' | 'fk' | None — funciona para erros do SQLite e do PostgreSQL."""
    if not any(c.__name__ == "IntegrityError" for c in type(e).__mro__):
        return None
    msg = str(e).lower()
    return "fk" if "foreign" in msg else "unica"


# --- Atalhos usados pelos repositórios -----------------------------------
def query_df(sql: str, params: tuple | list = ()) -> pd.DataFrame:
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        linhas = cur.fetchall()
        return pd.DataFrame([list(r._valores) for r in linhas], columns=cur.colunas)


def query_one(sql: str, params: tuple | list = ()) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def query_all(sql: str, params: tuple | list = ()) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple | list = ()) -> int:
    """Executa um comando e devolve o id inserido (INSERT) ou linhas afetadas."""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount


def execute_many(sql: str, rows: list[tuple]) -> int:
    with get_conn() as conn:
        return conn.executemany(sql, rows).rowcount
