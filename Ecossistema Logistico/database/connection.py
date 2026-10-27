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
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager

import pandas as pd

try:  # pandas 3: texto volta a ser "object" com None (como no pandas 2) — vazio do banco não vira NaN (que é "verdadeiro")
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001 — pandas antigo não tem a opção
    pass

from config.settings import DB_PATH

# Tabelas que NÃO têm coluna "id" (o INSERT no Postgres não pode pedir RETURNING id)
_SEM_ID = {"inv_conversao", "inv_config", "remun_fabrica_map", "remun_config", "obz_just_mes", "vendas_calendario", "grade_controle", "grade_config", "dre_manual", "dre_editado", "obz_sim_volume", "obz_sim_equipe", "obz_sim_valor", "obz_areas", "obz_mapa", "obz_resp", "obz_departamentos", "obz_contas", "obz_subdonos", "obz_papeis", "obz_plan", "depositos_nomes", "operacoes_fiscais", "setor_operacoes", "usuario_modulos", "usuario_operacoes", "produtos", "estoque", "linear_vendas", "metas_doi", "fluxo_caixa",
           "_migracoes", "fabrica_deslocamento", "linear_config", "linear_ajustes", "usuario_distribui"}


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

    def tuplas(self) -> list:
        """Linhas cruas (rápido para montar DataFrame — sem criar um objeto por linha)."""
        r = self._linhas if self._linhas is not None else self._cur.fetchall()
        self._linhas = [] if self._linhas is not None else None
        if r and any(isinstance(x, memoryview) for x in r[0]):
            return [tuple(bytes(x) if isinstance(x, memoryview) else x for x in t) for t in r]
        return r


# --- Cache de leitura ------------------------------------------------------------------------------------------
# Cada tela repete as mesmas consultas (revenda, operações, cadastros...) e, no PostgreSQL da nuvem, cada consulta é
# uma ida e volta pela rede. As leituras (query_df / query_one / query_all) ficam guardadas na memória e TODO o cache
# é descartado na hora em que qualquer gravação acontece — o que aparece na tela nunca fica desatualizado.
_CACHE: "OrderedDict[tuple, tuple[float, object]]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 60           # segundos — gravações deste app limpam na hora; o TTL cobre o app do motorista (outro processo)
_CACHE_MAX_ITENS = 300
_CACHE_MAX_LINHAS = 40_000           # resultado maior que isso não é guardado
_CACHE_MAX_BYTES = 80 * 1024 ** 2    # teto de memória do cache inteiro (o servidor da nuvem tem pouca memória)
_CACHE_MAX_ITEM = 12 * 1024 ** 2     # um resultado sozinho não passa disso
_cache_bytes = [0]
_LEITURA = re.compile(r"^\s*(SELECT|WITH|PRAGMA|EXPLAIN)\b", re.I)


def limpar_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
        _cache_bytes[0] = 0


def _tamanho(valor) -> int:
    try:
        if isinstance(valor, pd.DataFrame):
            return int(valor.memory_usage(index=False, deep=False).sum()) + len(valor) * len(valor.columns) * 40
        if isinstance(valor, list):
            return len(valor) * (len(valor[0]) if valor else 1) * 90
        return 2_000
    except Exception:  # noqa: BLE001
        return 1_000_000


def _cache_get(chave):
    with _CACHE_LOCK:
        item = _CACHE.get(chave)
        if item is None:
            return None
        quando, valor, tam = item
        if time.monotonic() - quando > _CACHE_TTL:
            _CACHE.pop(chave, None)
            _cache_bytes[0] -= tam
            return None
        _CACHE.move_to_end(chave)
        return valor


def _cache_put(chave, valor) -> None:
    tam = _tamanho(valor)
    if tam > _CACHE_MAX_ITEM:
        return
    with _CACHE_LOCK:
        antigo = _CACHE.pop(chave, None)
        if antigo:
            _cache_bytes[0] -= antigo[2]
        _CACHE[chave] = (time.monotonic(), valor, tam)
        _cache_bytes[0] += tam
        while _CACHE and (len(_CACHE) > _CACHE_MAX_ITENS or _cache_bytes[0] > _CACHE_MAX_BYTES):
            _, (_, _, t) = _CACHE.popitem(last=False)
            _cache_bytes[0] -= t


class Conexao:
    def __init__(self, raw, pg: bool):
        self.raw, self.pg = raw, pg
        self.escreveu = False

    def execute(self, sql: str, params=()) -> _Cursor:
        if not _LEITURA.match(sql):
            self.escreveu = True
            limpar_cache()
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
        self.escreveu = True
        limpar_cache()
        cur = self.raw.cursor()
        linhas = [tuple(l) for l in linhas]
        if self.pg:
            cur.executemany(traduzir_sql(sql), linhas)
        else:
            cur.executemany(sql, linhas)
        return _Cursor(cur)

    def executescript(self, script: str) -> None:
        self.escreveu = True
        limpar_cache()
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
            finally:
                if conn.escreveu:
                    limpar_cache()
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
        if conn.escreveu:
            limpar_cache()


def tipo_violacao(e: Exception) -> str | None:
    """'unica' | 'fk' | None — funciona para erros do SQLite e do PostgreSQL."""
    if not any(c.__name__ == "IntegrityError" for c in type(e).__mro__):
        return None
    msg = str(e).lower()
    return "fk" if "foreign" in msg else "unica"


# --- Atalhos usados pelos repositórios -----------------------------------
def _chave(tipo: str, sql: str, params) -> tuple | None:
    try:
        return (tipo, _destino_cache(), sql, tuple(params))
    except TypeError:  # parâmetro não "hasheável": não usa cache
        return None


def _destino_cache() -> str:
    return "pg" if is_postgres() else str(DB_PATH)


def query_df(sql: str, params: tuple | list = ()) -> pd.DataFrame:
    chave = _chave("df", sql, params) if _LEITURA.match(sql) else None
    if chave is not None:
        hit = _cache_get(chave)
        if hit is not None:
            return hit.copy()
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        df = pd.DataFrame.from_records(cur.tuplas(), columns=cur.colunas)
    if chave is not None and len(df) <= _CACHE_MAX_LINHAS:
        _cache_put(chave, df.copy())
    return df


def query_one(sql: str, params: tuple | list = ()) -> dict | None:
    chave = _chave("one", sql, params) if _LEITURA.match(sql) else None
    if chave is not None:
        hit = _cache_get(chave)
        if hit is not None:
            return dict(hit[0]) if hit[0] is not None else None
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        r = dict(row) if row else None
    if chave is not None:
        _cache_put(chave, (r,))
    return dict(r) if r else None


def query_all(sql: str, params: tuple | list = ()) -> list[dict]:
    chave = _chave("all", sql, params) if _LEITURA.match(sql) else None
    if chave is not None:
        hit = _cache_get(chave)
        if hit is not None:
            return [dict(x) for x in hit]
    with get_conn() as conn:
        rs = [dict(r) for r in conn.execute(sql, params).fetchall()]
    if chave is not None and len(rs) <= _CACHE_MAX_LINHAS:
        _cache_put(chave, rs)
    return [dict(x) for x in rs]


def execute(sql: str, params: tuple | list = ()) -> int:
    """Executa um comando e devolve o id inserido (INSERT) ou linhas afetadas."""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount


def execute_many(sql: str, rows: list[tuple]) -> int:
    with get_conn() as conn:
        return conn.executemany(sql, rows).rowcount
