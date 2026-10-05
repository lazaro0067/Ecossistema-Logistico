"""Acesso a dados: carretas, fábricas, motoristas, agendamentos de descarga e vínculos de pedidos."""
import pandas as pd

from core import tempo
from database.connection import execute, query_all, query_df
from repositories import operacoes_repo


# --- Cadastros simples (operação) ------------------------------------------
def carretas_df(operacao_id: int) -> pd.DataFrame:
    return query_df("SELECT id, placa, modelo, capacidade_hl, status FROM carretas WHERE operacao_id = ? ORDER BY placa",
                    (operacao_id,))


def salvar_carreta(operacao_id: int, cid: int | None, placa: str, modelo: str, cap: float, status: str) -> None:
    if cid:
        execute("UPDATE carretas SET placa=?, modelo=?, capacidade_hl=?, status=? WHERE id=?",
                (placa, modelo, cap, status, cid))
    else:
        execute("INSERT INTO carretas (operacao_id, placa, modelo, capacidade_hl, status) VALUES (?, ?, ?, ?, ?)",
                (operacao_id, placa, modelo, cap, status))


def fabricas_df() -> pd.DataFrame:
    return query_df("SELECT id, nome, cidade, uf FROM fabricas ORDER BY nome")


def salvar_fabrica(fid: int | None, nome: str, cidade: str, uf: str) -> None:
    if fid:
        execute("UPDATE fabricas SET nome=?, cidade=?, uf=? WHERE id=?", (nome, cidade, uf, fid))
    else:
        execute("INSERT INTO fabricas (nome, cidade, uf) VALUES (?, ?, ?)", (nome, cidade, uf))


def motoristas_df(operacao_id: int) -> pd.DataFrame:
    return query_df("SELECT id, nome, cnh, telefone FROM motoristas WHERE operacao_id = ? ORDER BY nome",
                    (operacao_id,))


def salvar_motorista(operacao_id: int, mid: int | None, nome: str, cnh: str, tel: str) -> None:
    if mid:
        execute("UPDATE motoristas SET nome=?, cnh=?, telefone=? WHERE id=?", (nome, cnh, tel, mid))
    else:
        execute("INSERT INTO motoristas (operacao_id, nome, cnh, telefone) VALUES (?, ?, ?, ?)",
                (operacao_id, nome, cnh, tel))


def excluir(tabela: str, rid: int) -> None:
    if tabela not in {"carretas", "fabricas", "motoristas", "agendamentos_descarga", "vinculos_pedidos"}:
        raise ValueError(tabela)
    execute(f"DELETE FROM {tabela} WHERE id = ?", (rid,))


# --- Agendamentos de descarga (pátio) --------------------------------------
def agendamentos_df(operacao_id: int, de: str | None = None, ate: str | None = None) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, p = f"SELECT id, data, hora, placa, slot, tipo_carga, status, observacao, criado_por FROM agendamentos_descarga WHERE {f_sql}", list(ids)
    if de:
        sql += " AND data >= ?"
        p.append(de)
    if ate:
        sql += " AND data <= ?"
        p.append(ate)
    return query_df(sql + " ORDER BY data, hora, slot", p)


def inserir_agendamento(operacao_id: int, data: str, hora: str, placa: str, slot: str, tipo: str,
                        obs: str, usuario: str) -> int:
    return execute("""INSERT INTO agendamentos_descarga (operacao_id, data, hora, placa, slot, tipo_carga, status,
                      observacao, criado_por, dt_atualizacao) VALUES (?, ?, ?, ?, ?, ?, 'Agendado', ?, ?, ?)""",
                   (operacao_id, data, hora, placa, slot, tipo, obs, usuario, tempo.agora_str()))


def slot_ocupado(operacao_id: int, data: str, hora: str, slot: str) -> bool:
    return bool(query_all("""SELECT 1 FROM agendamentos_descarga WHERE operacao_id = ? AND data = ? AND hora = ?
                             AND slot = ? AND status NOT IN ('Cancelado', 'Descarregado')""",
                          (operacao_id, data, hora, slot)))


def atualizar_agendamento(aid: int, **campos) -> None:
    campos["dt_atualizacao"] = tempo.agora_str()
    execute(f"UPDATE agendamentos_descarga SET {', '.join(k + ' = ?' for k in campos)} WHERE id = ?",
            (*campos.values(), aid))


# --- Vínculos de pedidos / viagens -------------------------------------------
def vinculos_df(operacao_id: int, mes_ano: str | None = None) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, p = (f"""SELECT id, numero_pedido, data_puxada, placa, fabrica, transportadora, motorista, notas_fiscais,
                  hl_carregado, dt_atualizacao FROM vinculos_pedidos WHERE {f_sql}""", list(ids))
    if mes_ano:
        sql += " AND substr(data_puxada, 1, 7) = ?"
        p.append(mes_ano)
    return query_df(sql + " ORDER BY data_puxada DESC, id DESC", p)


def salvar_vinculo(operacao_id: int, vid: int | None, dados: dict) -> None:
    dados = {**dados, "dt_atualizacao": tempo.agora_str()}
    if vid:
        execute(f"UPDATE vinculos_pedidos SET {', '.join(k + ' = ?' for k in dados)} WHERE id = ?",
                (*dados.values(), vid))
    else:
        cols = ["operacao_id", *dados]
        execute(f"INSERT INTO vinculos_pedidos ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                (operacao_id, *dados.values()))


def meses_vinculos(operacao_id: int) -> list[str]:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    df = query_df(f"SELECT DISTINCT substr(data_puxada, 1, 7) AS m FROM vinculos_pedidos WHERE {f_sql} ORDER BY m DESC",
                  ids)
    return [m for m in df["m"].tolist() if m]
