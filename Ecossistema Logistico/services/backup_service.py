"""💾 Cópia de segurança do banco inteiro (usuários, permissões, cadastros, bases…).

• exportar()  → bytes de um .zip com um JSON por tabela + manifesto.
• importar()  → restaura um .zip gerado por exportar(): para cada tabela do arquivo apaga o que
                existe e regrava as linhas (na ordem das chaves estrangeiras). Tudo numa transação:
                se algo falhar, nada muda.
• banco_temporario() → True quando o sistema roda na nuvem (Streamlit Cloud) com SQLite — o arquivo
                é apagado a cada reinício do servidor, então acessos e cadastros se perdem.
"""
import base64
import datetime as dt
import io
import json
import os
import re
import zipfile

from core import tempo
from database import schema
from database.connection import get_conn, is_postgres
from services.erros import RegraNegocioError

_IGNORAR = {"_migracoes"}


def _ordem() -> list[str]:
    """Tabelas na ordem em que são criadas (pais antes dos filhos)."""
    return re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", schema.TABELAS)


def _tabelas_do_banco(conn) -> list[str]:
    if conn.pg:
        rows = conn.execute("SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'").fetchall()
    else:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                            "AND name NOT LIKE 'sqlite_%'").fetchall()
    existentes = {r[0] for r in rows} - _IGNORAR
    ordem = [t for t in _ordem() if t in existentes]
    return ordem + sorted(existentes - set(ordem))


def _colunas(conn, tabela: str) -> list[str]:
    if conn.pg:
        rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
                            "AND table_name = ? ORDER BY ordinal_position", (tabela,)).fetchall()
        return [r[0] for r in rows]
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()]


def _pk(conn, tabela: str) -> list[str]:
    if conn.pg:
        rows = conn.execute("""SELECT k.column_name FROM information_schema.table_constraints c
                               JOIN information_schema.key_column_usage k
                                 ON k.constraint_name = c.constraint_name AND k.table_schema = c.table_schema
                               WHERE c.table_schema = current_schema() AND c.table_name = ?
                                 AND c.constraint_type = 'PRIMARY KEY' ORDER BY k.ordinal_position""",
                            (tabela,)).fetchall()
        return [r[0] for r in rows]
    rows = sorted((r[5], r[1]) for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall() if r[5])
    return [c for _, c in rows]


def _para_json(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"__b64__": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat(sep=" ") if isinstance(v, dt.datetime) else v.isoformat()
    if hasattr(v, "is_finite"):  # Decimal
        return float(v)
    return v


def _de_json(v):
    if isinstance(v, dict) and "__b64__" in v:
        return base64.b64decode(v["__b64__"])
    return v


def banco_temporario() -> bool:
    if is_postgres():
        return False
    return os.path.isdir("/mount/src") or "/mount/src" in os.getcwd() or bool(os.environ.get("STREAMLIT_SHARING_MODE"))


def resumo() -> list[dict]:
    """Quantidade de linhas por tabela (para a tela)."""
    with get_conn() as conn:
        return [{"Tabela": t, "Linhas": conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]}
                for t in _tabelas_do_banco(conn)]


# Bases que vêm dos relatórios (sobem de novo pelos arquivos) e são enormes: ficam fora do backup automático.
# Usuários, acessos, cadastros, metas, OBZ, simulador, lançamentos — tudo o que é digitado — continua no backup.
BASES_RELATORIO = {"notas_cli_prod_mes", "notas_produto_mes", "notas_cliente_mes", "notas_dia", "entregas_notas",
                   "entregas_mapas", "obz_real_lanc", "estoque_saldos", "notas_prod_dia", "notas_mapa_prod"}
_LOTE = 5_000
_MAX_LINHAS_TABELA = 400_000  # tabela maior que isso não entra (protege a memória do servidor)


def exportar(completo: bool = False) -> bytes:
    """Gera o .zip tabela por tabela, em lotes — sem montar o banco inteiro na memória (isso derrubava o
    servidor da nuvem). completo=False deixa de fora as bases de relatório (BASES_RELATORIO)."""
    buf = io.BytesIO()
    manifesto = {"gerado_em": tempo.agora().strftime("%Y-%m-%d %H:%M:%S"),
                 "banco": "postgres" if is_postgres() else "sqlite", "tabelas": {}, "fora": {}}
    with get_conn() as conn, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for t in _tabelas_do_banco(conn):
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if (not completo and t in BASES_RELATORIO) or n > _MAX_LINHAS_TABELA:
                manifesto["fora"][t] = int(n)
                continue
            cols = _colunas(conn, t)
            cur = conn.raw.cursor(name=f"bk_{t}") if conn.pg else conn.raw.cursor()
            cur.execute(f"SELECT {', '.join(cols)} FROM {t}")
            total = 0
            with z.open(f"{t}.json", "w") as fh:
                fh.write(("{\"colunas\": " + json.dumps(cols, ensure_ascii=False) + ", \"linhas\": [").encode("utf-8"))
                primeiro = True
                while True:
                    lote = cur.fetchmany(_LOTE)
                    if not lote:
                        break
                    partes = [json.dumps([_para_json(v) for v in r], ensure_ascii=False) for r in lote]
                    fh.write(((", " if not primeiro else "") + ", ".join(partes)).encode("utf-8"))
                    primeiro = False
                    total += len(lote)
                fh.write(b"]}")
            cur.close()
            manifesto["tabelas"][t] = total
        z.writestr("manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=1))
    return buf.getvalue()


def ler_manifesto(arquivo: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo)) as z:
            return json.loads(z.read("manifesto.json"))
    except Exception as e:
        raise RegraNegocioError("Arquivo inválido — use o .zip gerado em 💾 Backup.") from e


def importar(arquivo: bytes, tabelas: list[str] | None = None) -> dict[str, int]:
    """Restaura o backup. `tabelas` limita quais tabelas do arquivo são restauradas (None = todas)."""
    man = ler_manifesto(arquivo)
    feito: dict[str, int] = {}
    with zipfile.ZipFile(io.BytesIO(arquivo)) as z, get_conn() as conn:
        no_banco = _tabelas_do_banco(conn)
        alvo = [t for t in no_banco if t in man["tabelas"] and (tabelas is None or t in tabelas)]
        if not alvo:
            raise RegraNegocioError("Nenhuma tabela do arquivo existe neste banco.")
        dados = {}
        for t in alvo:
            d = json.loads(z.read(f"{t}.json"))
            atuais = set(_colunas(conn, t))
            idx = [i for i, c in enumerate(d["colunas"]) if c in atuais]
            cols = [d["colunas"][i] for i in idx]
            pk = [c for c in _pk(conn, t) if c in cols]
            dados[t] = (cols, [tuple(_de_json(l[i]) for i in idx) for l in d["linhas"]], pk)
        # 1) tira o que não está no backup — filhos antes dos pais
        for t in reversed(alvo):
            cols, linhas, pk = dados[t]
            if not pk:
                conn.execute(f"DELETE FROM {t}")
                continue
            pos = [cols.index(c) for c in pk]
            manter = {tuple(l[p] for p in pos) for l in linhas}
            existentes = conn.execute(f"SELECT {', '.join(pk)} FROM {t}").fetchall()
            sobra = [tuple(r._valores) for r in existentes if tuple(r._valores) not in manter]
            if sobra:
                conn.executemany(f"DELETE FROM {t} WHERE {' AND '.join(c + ' = ?' for c in pk)}", sobra)
        # 2) grava/atualiza — pais antes dos filhos
        for t in alvo:
            cols, linhas, pk = dados[t]
            if linhas:
                sql = f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
                resto = [c for c in cols if c not in pk]
                if pk:
                    sql += f" ON CONFLICT ({', '.join(pk)}) DO " + (
                        "UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in resto) if resto else "NOTHING")
                for i in range(0, len(linhas), 2000):
                    conn.executemany(sql, linhas[i:i + 2000])
            if conn.pg and "id" in cols:
                conn.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                             f"COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)")
            feito[t] = len(linhas)
    return feito
