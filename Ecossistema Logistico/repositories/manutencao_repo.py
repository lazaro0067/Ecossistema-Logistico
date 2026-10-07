"""Acesso a dados: manutenções programadas das placas (frota própria)."""
import pandas as pd

from core import tempo
from database.connection import execute, query_all, query_df, query_one

CAMPOS = ["placa", "data", "hora", "tipo", "descricao", "oficina", "previsao_fim", "prioridade"]


def lista_df(operacao_id: int, de: str | None = None, ate: str | None = None,
             status: list[str] | None = None) -> pd.DataFrame:
    sql, p = "SELECT * FROM manutencoes WHERE operacao_id = ?", [operacao_id]
    if de:
        sql += " AND data >= ?"
        p.append(de)
    if ate:
        sql += " AND data <= ?"
        p.append(ate)
    if status:
        sql += f" AND status IN ({', '.join('?' * len(status))})"
        p += status
    return query_df(sql + " ORDER BY data, COALESCE(hora, ''), placa", p)


def buscar(mid: int) -> dict | None:
    return query_one("SELECT * FROM manutencoes WHERE id = ?", (mid,))


def salvar(operacao_id: int, mid: int | None, dados: dict, usuario: str) -> int:
    valores = [dados.get(c) for c in CAMPOS]
    if mid:
        execute(f"UPDATE manutencoes SET {', '.join(c + ' = ?' for c in CAMPOS)} WHERE id = ?", (*valores, mid))
        return mid
    return execute(f"""INSERT INTO manutencoes (operacao_id, {', '.join(CAMPOS)}, status, criado_por, criado_em)
                       VALUES (?, {', '.join('?' * len(CAMPOS))}, 'Programada', ?, ?)""",
                   (operacao_id, *valores, usuario, tempo.agora_str()))


def mudar_status(mid: int, status: str) -> None:
    agora = tempo.agora_str()
    extra = {"Em andamento": ", iniciado_em = ?", "Concluída": ", concluido_em = ?"}.get(status, "")
    execute(f"UPDATE manutencoes SET status = ?{extra} WHERE id = ?",
            (status, agora, mid) if extra else (status, mid))


def ativas_da_placa(operacao_id: int, placa: str, a_partir: str) -> list[dict]:
    return query_all("""SELECT * FROM manutencoes WHERE operacao_id = ? AND upper(placa) = upper(?) AND data >= ?
                        AND status IN ('Programada', 'Em andamento') ORDER BY data, COALESCE(hora, '')""",
                     (operacao_id, placa, a_partir))
