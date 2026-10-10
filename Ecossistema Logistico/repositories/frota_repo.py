"""Acesso a dados da Frota: placas, locadoras, transportadoras e motoristas (todas as revendas)."""
import pandas as pd

from core import tempo
from database.connection import execute, query_df, query_one

CAMPOS_PLACA = ["placa", "operacao_id", "tipo", "marca_modelo", "ano", "proprietario_id", "aluguel", "locadora_id",
                "area", "motorista_id", "status", "observacao"]


# --- Placas ----------------------------------------------------------------------------------
def placas_df(ids_ops: list[int] | None = None) -> pd.DataFrame:
    sql = """SELECT p.*, o.nome AS revenda, t.nome AS proprietario, l.nome AS locadora, m.nome AS motorista,
                    m.cnh_validade AS motorista_cnh_validade
             FROM frota_placas p
             LEFT JOIN operacoes o ON o.id = p.operacao_id
             LEFT JOIN transportadoras t ON t.id = p.proprietario_id
             LEFT JOIN locadoras l ON l.id = p.locadora_id
             LEFT JOIN motoristas m ON m.id = p.motorista_id"""
    p: list = []
    if ids_ops:
        sql += f" WHERE p.operacao_id IN ({', '.join('?' * len(ids_ops))})"
        p = list(ids_ops)
    return query_df(sql + " ORDER BY o.nome, p.placa", p)


def placa_por_texto(placa: str) -> dict | None:
    return query_one("SELECT * FROM frota_placas WHERE upper(placa) = upper(?)", ((placa or "").strip(),))


def salvar_placa(pid: int | None, dados: dict, usuario: str) -> int:
    valores = [dados.get(c) for c in CAMPOS_PLACA]
    agora = tempo.agora().strftime("%Y-%m-%d %H:%M")
    if pid:
        execute(f"UPDATE frota_placas SET {', '.join(c + ' = ?' for c in CAMPOS_PLACA)}, atualizado_por = ?, "
                f"atualizado_em = ? WHERE id = ?", (*valores, usuario, agora, pid))
        return pid
    return execute(f"INSERT INTO frota_placas ({', '.join(CAMPOS_PLACA)}, atualizado_por, atualizado_em) "
                   f"VALUES ({', '.join('?' * len(CAMPOS_PLACA))}, ?, ?)", (*valores, usuario, agora))


def excluir_placa(pid: int) -> None:
    execute("DELETE FROM frota_placas WHERE id = ?", (pid,))


# --- Locadoras / transportadoras -------------------------------------------------------------
def locadoras_df() -> pd.DataFrame:
    return query_df("""SELECT l.*, (SELECT COUNT(*) FROM frota_placas p WHERE p.locadora_id = l.id) AS placas
                       FROM locadoras l ORDER BY l.nome""")


def salvar_locadora(lid: int | None, nome: str, cnpj: str, contato: str, telefone: str) -> int:
    if lid:
        execute("UPDATE locadoras SET nome = ?, cnpj = ?, contato = ?, telefone = ? WHERE id = ?",
                (nome, cnpj, contato, telefone, lid))
        return lid
    return execute("INSERT INTO locadoras (nome, cnpj, contato, telefone) VALUES (?, ?, ?, ?)",
                   (nome, cnpj, contato, telefone))


def excluir_locadora(lid: int) -> None:
    execute("UPDATE frota_placas SET locadora_id = NULL WHERE locadora_id = ?", (lid,))
    execute("DELETE FROM locadoras WHERE id = ?", (lid,))


def transportadoras_df() -> pd.DataFrame:
    return query_df("""SELECT t.*, (SELECT COUNT(*) FROM frota_placas p WHERE p.proprietario_id = t.id) AS placas
                       FROM transportadoras t ORDER BY t.nome""")


def salvar_transportadora(tid: int | None, nome: str, cnpj: str, contato: str, telefone: str) -> int:
    if tid:
        execute("UPDATE transportadoras SET nome = ?, cnpj = ?, contato = ?, telefone = ? WHERE id = ?",
                (nome, cnpj, contato, telefone, tid))
        return tid
    return execute("INSERT INTO transportadoras (nome, cnpj, contato, telefone) VALUES (?, ?, ?, ?)",
                   (nome, cnpj, contato, telefone))


def transportadora_em_uso(tid: int) -> bool:
    r = query_one("""SELECT (SELECT COUNT(*) FROM frota_placas WHERE proprietario_id = ?) +
                            (SELECT COUNT(*) FROM cotacoes_frete WHERE transportadora_id = ?) +
                            (SELECT COUNT(*) FROM trechos WHERE transportadora_id = ?) AS n""", (tid, tid, tid))
    return bool(r and int(r["n"] or 0))


def excluir_transportadora(tid: int) -> None:
    execute("DELETE FROM transportadoras WHERE id = ?", (tid,))


# --- Motoristas (cadastro da frota) ----------------------------------------------------------
def motoristas_df(ids_ops: list[int]) -> pd.DataFrame:
    if not ids_ops:
        return pd.DataFrame()
    return query_df(f"""SELECT m.id, m.operacao_id, o.nome AS revenda, m.nome, m.cpf, m.cnh, m.categoria_cnh,
                               m.cnh_validade, m.telefone, m.gestor_id, u.nome AS supervisor,
                               (SELECT COUNT(*) FROM frota_placas p WHERE p.motorista_id = m.id) AS placas
                        FROM motoristas m LEFT JOIN operacoes o ON o.id = m.operacao_id
                        LEFT JOIN usuarios u ON u.id = m.gestor_id
                        WHERE m.operacao_id IN ({', '.join('?' * len(ids_ops))}) AND COALESCE(m.terceiro, 0) = 0
                        ORDER BY o.nome, m.nome""",
                    list(ids_ops))


def salvar_categoria_cnh(mid: int, categoria: str | None) -> None:
    execute("UPDATE motoristas SET categoria_cnh = ? WHERE id = ?", (categoria, mid))
