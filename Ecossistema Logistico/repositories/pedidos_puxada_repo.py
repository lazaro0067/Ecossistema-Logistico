"""Acesso a dados: pedidos D0 / D+1 montados pela Puxada para cada placa."""
import pandas as pd

from core import tempo
from database.connection import execute, query_all, query_df, query_one
from repositories import operacoes_repo

CAMPOS = ["data", "placa", "numero_pedido", "fabrica_id", "motorista_id", "hora_agendamento", "hora_agendamento_fim",
          "tipo", "p_corona600", "p_outros", "outros_desc", "p600_ambar", "p600_verde", "p1l", "p300", "paletes", "observacao", "prioridade"]


def pedidos_df(operacao_id: int, de: str | None = None, ate: str | None = None,
               apenas_abertos: bool = False) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("p.operacao_id", operacao_id)
    sql, p = (f"""SELECT p.*, o.nome AS filial, f.nome AS fabrica, m.nome AS motorista,
                         COALESCE(d.horas, 0) AS deslocamento_h, v.status AS viagem_status
                  FROM pedidos_puxada p
                  JOIN operacoes o ON o.id = p.operacao_id LEFT JOIN fabricas f ON f.id = p.fabrica_id
                  LEFT JOIN motoristas m ON m.id = p.motorista_id
                  LEFT JOIN fabrica_deslocamento d ON d.operacao_id = p.operacao_id AND d.fabrica_id = p.fabrica_id
                  LEFT JOIN viagens_carreteiro v ON v.id = p.viagem_id
                  WHERE {f_sql}""", list(ids))
    if de:
        sql += " AND p.data >= ?"
        p.append(de)
    if ate:
        sql += " AND p.data <= ?"
        p.append(ate)
    if apenas_abertos:
        sql += " AND p.status = 'Aberto'"
    return query_df(sql + " ORDER BY p.data, p.placa, p.id", p)


def pedido(pid: int) -> dict | None:
    return query_one("""SELECT p.*, f.nome AS fabrica, m.nome AS motorista FROM pedidos_puxada p
                        LEFT JOIN fabricas f ON f.id = p.fabrica_id LEFT JOIN motoristas m ON m.id = p.motorista_id
                        WHERE p.id = ?""", (pid,))


def numeros(texto) -> list[str]:
    """'4501, 4502 / 4503' → ['4501', '4502', '4503'] (um agendamento pode levar mais de um pedido)."""
    import re

    return [n for n in re.split(r"[\s,;/+]+", str(texto or "")) if n]


def _ativos_com_numero(operacao_id: int, numero: str) -> list[dict]:
    linhas = query_all("""SELECT p.*, f.nome AS fabrica, m.nome AS motorista FROM pedidos_puxada p
                          LEFT JOIN fabricas f ON f.id = p.fabrica_id LEFT JOIN motoristas m ON m.id = p.motorista_id
                          WHERE p.operacao_id = ? AND p.numero_pedido LIKE ?
                          AND p.status NOT IN ('Cancelado', 'Reprogramado') ORDER BY p.id DESC""",
                       (operacao_id, f"%{numero}%"))
    return [r for r in linhas if numero in numeros(r["numero_pedido"])]


def pedido_por_numero(operacao_id: int, numero: str) -> dict | None:
    """Agendamento ativo que contém esse número de pedido — usado pelo App Carreteiro."""
    r = _ativos_com_numero(operacao_id, numero)
    return r[0] if r else None


def ligar_viagem(pid: int, viagem_id: int | None) -> None:
    execute("UPDATE pedidos_puxada SET viagem_id = ? WHERE id = ?", (viagem_id, pid))


def numero_existe(operacao_id: int, numero: str, ignorar_id: int | None) -> str | None:
    """Devolve o primeiro número que já está em outro agendamento ativo (ou None)."""
    for n in numeros(numero):
        if any(r["id"] != (ignorar_id or 0) for r in _ativos_com_numero(operacao_id, n)):
            return n
    return None


def marcar_reprogramado(pid: int, novo_id: int, motivo: str, usuario: str) -> None:
    agora = tempo.agora_str()
    execute("""UPDATE pedidos_puxada SET status = 'Reprogramado', substituido_por = ?, reprogramado_motivo = ?,
               editado_por = ?, editado_em = ?, atualizado_em = ? WHERE id = ?""",
            (novo_id, motivo, usuario, agora, agora, pid))
    execute("UPDATE pedidos_puxada SET substitui_id = ? WHERE id = ?", (pid, novo_id))


def salvar(operacao_id: int, pid: int | None, dados: dict, usuario: str, resumo: str | None = None,
           reabrir: bool = False) -> int:
    agora = tempo.agora_str()
    valores = [dados.get(c) for c in CAMPOS]
    if pid:
        extra = ", status = 'Aberto', finalizado_por = NULL, finalizado_em = NULL" if reabrir else ""
        execute(f"""UPDATE pedidos_puxada SET {', '.join(c + ' = ?' for c in CAMPOS)}, atualizado_em = ?,
                    editado_por = ?, editado_em = ?, editado_resumo = ?{extra} WHERE id = ?""",
                (*valores, agora, usuario, agora, resumo, pid))
        return pid
    return execute(f"""INSERT INTO pedidos_puxada (operacao_id, {', '.join(CAMPOS)}, status, criado_por, criado_em,
                       atualizado_em) VALUES (?, {', '.join('?' * len(CAMPOS))}, 'Aberto', ?, ?, ?)""",
                   (operacao_id, *valores, usuario, agora, agora))


def mudar_status(pid: int, status: str, usuario: str | None) -> None:
    agora = tempo.agora_str()
    if status == "Finalizado":
        execute("""UPDATE pedidos_puxada SET status = ?, finalizado_por = ?, finalizado_em = ?, atualizado_em = ?
                   WHERE id = ?""", (status, usuario, agora, agora, pid))
    else:
        execute("""UPDATE pedidos_puxada SET status = ?, finalizado_por = NULL, finalizado_em = NULL, atualizado_em = ?
                   WHERE id = ?""", (status, agora, pid))
