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


def fabricas_df(operacao_id: int | None = None) -> pd.DataFrame:
    """Fábricas; com `operacao_id` traz também o tempo de deslocamento daquela revenda até a fábrica."""
    if operacao_id is None:
        return query_df("SELECT id, nome, cidade, uf FROM fabricas ORDER BY nome")
    return query_df("""SELECT f.id, f.nome, f.cidade, f.uf, COALESCE(d.horas, 0) AS deslocamento_h
                       FROM fabricas f LEFT JOIN fabrica_deslocamento d ON d.fabrica_id = f.id AND d.operacao_id = ?
                       ORDER BY f.nome""", (operacao_id,))


def deslocamento_h(operacao_id: int, fabrica_id: int | None) -> float:
    if not fabrica_id:
        return 0.0
    r = query_all("SELECT horas FROM fabrica_deslocamento WHERE operacao_id = ? AND fabrica_id = ?",
                  (operacao_id, int(fabrica_id)))
    return float(r[0]["horas"] or 0) if r else 0.0


def salvar_deslocamento(operacao_id: int, fabrica_id: int, horas: float) -> None:
    execute("DELETE FROM fabrica_deslocamento WHERE operacao_id = ? AND fabrica_id = ?", (operacao_id, fabrica_id))
    execute("INSERT INTO fabrica_deslocamento (operacao_id, fabrica_id, horas) VALUES (?, ?, ?)",
            (operacao_id, fabrica_id, float(horas or 0)))


def salvar_fabrica(fid: int | None, nome: str, cidade: str, uf: str) -> int | None:
    if fid:
        execute("UPDATE fabricas SET nome=?, cidade=?, uf=? WHERE id=?", (nome, cidade, uf, fid))
        return fid
    return execute("INSERT INTO fabricas (nome, cidade, uf) VALUES (?, ?, ?)", (nome, cidade, uf))


def motoristas_df(operacao_id: int) -> pd.DataFrame:
    return query_df("SELECT id, nome, cnh, telefone FROM motoristas WHERE operacao_id = ? ORDER BY nome",
                    (operacao_id,))


def salvar_motorista(operacao_id: int, mid: int | None, nome: str, cnh: str, tel: str, **extras) -> int | None:
    """extras (opcionais): cpf, cnh_validade, gestor_id, salario_fixo."""
    campos = {"nome": nome, "cnh": cnh, "telefone": tel,
              **{k: v for k, v in extras.items() if k in ("cpf", "cnh_validade", "gestor_id", "salario_fixo")}}
    if mid:
        execute(f"UPDATE motoristas SET {', '.join(k + ' = ?' for k in campos)} WHERE id = ?", (*campos.values(), mid))
        return mid
    cols = ["operacao_id", *campos]
    return execute(f"INSERT INTO motoristas ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   (operacao_id, *campos.values()))


def excluir(tabela: str, rid: int) -> None:
    if tabela not in {"carretas", "fabricas", "motoristas", "agendamentos_descarga", "vinculos_pedidos",
                      "janelas_descarga"}:
        raise ValueError(tabela)
    execute(f"DELETE FROM {tabela} WHERE id = ?", (rid,))


# --- Agendamentos de descarga (pátio) --------------------------------------
def agendamentos_df(operacao_id: int, de: str | None = None, ate: str | None = None) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    f_sql = f_sql.replace("operacao_id", "a.operacao_id", 1)
    sql, p = (f"""SELECT a.id, a.data, a.hora, a.placa, a.slot, a.tipo_carga, a.status, a.observacao, a.criado_por,
                         a.viagem_id, a.janela_id, m.nome AS motorista, v.numero_pedido AS pedido_app
                  FROM agendamentos_descarga a
                  LEFT JOIN viagens_carreteiro v ON v.id = a.viagem_id
                  LEFT JOIN motoristas m ON m.id = v.motorista_id
                  WHERE {f_sql}""", list(ids))
    if de:
        sql += " AND a.data >= ?"
        p.append(de)
    if ate:
        sql += " AND a.data <= ?"
        p.append(ate)
    return query_df(sql + " ORDER BY a.data, a.hora, a.slot", p)


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


def agendamentos_ativos_dia(operacao_id: int, data: str) -> list[dict]:
    """Agendamentos que ocupam vaga no dia (cancelado e no-show liberam a vaga)."""
    return query_all("""SELECT id, hora, janela_id, viagem_id, tipo_carga FROM agendamentos_descarga
                        WHERE operacao_id = ? AND data = ? AND status NOT IN ('Cancelado', 'No-show')""",
                     (operacao_id, data))


# --- Janelas de descarga ------------------------------------------------------
def janelas(operacao_id: int, apenas_ativas: bool = True) -> list[dict]:
    sql = "SELECT * FROM janelas_descarga WHERE operacao_id = ?" + (" AND ativo = 1" if apenas_ativas else "")
    return query_all(sql + " ORDER BY hora_inicio, hora_fim", (operacao_id,))


def janelas_df(operacao_id: int) -> pd.DataFrame:
    return query_df("SELECT * FROM janelas_descarga WHERE operacao_id = ? ORDER BY hora_inicio, hora_fim",
                    (operacao_id,))


def salvar_janela(operacao_id: int, jid: int | None, inicio: str, fim: str, slots: int, dias: str,
                  produto: str | None, ativo: bool = True) -> None:
    if jid:
        execute("""UPDATE janelas_descarga SET hora_inicio = ?, hora_fim = ?, slots = ?, dias = ?, produto = ?,
                   ativo = ? WHERE id = ?""", (inicio, fim, slots, dias, produto, 1 if ativo else 0, jid))
    else:
        execute("""INSERT INTO janelas_descarga (operacao_id, hora_inicio, hora_fim, slots, dias, produto, ativo)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""", (operacao_id, inicio, fim, slots, dias, produto, 1 if ativo else 0))


# --- Vínculos de pedidos / viagens -------------------------------------------
def vinculos_df(operacao_id: int, mes_ano: str | None = None) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, p = (f"""SELECT id, numero_pedido, data_puxada, placa, fabrica, transportadora, motorista, notas_fiscais,
                  hl_carregado, dt_atualizacao, viagem_id FROM vinculos_pedidos WHERE {f_sql}""", list(ids))
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


# --- Disponibilidade planejada das placas -------------------------------------------
def disponibilidade_df(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    f_sql, ids = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"""SELECT operacao_id, placa, data, status, sugestao, observacao, atualizado_por, dt_atualizacao
                        FROM disponibilidade_placas WHERE {f_sql} AND data >= ? AND data <= ?""", (*ids, de, ate))


def salvar_disponibilidade(operacao_id: int, placa: str, data: str, status: str | None, obs: str | None,
                           usuario: str, sugestao: str | None = None) -> None:
    """status None = volta para o automático (apaga o planejamento manual)."""
    execute("DELETE FROM disponibilidade_placas WHERE operacao_id = ? AND placa = ? AND data = ?",
            (operacao_id, placa, data))
    if status:
        execute("""INSERT INTO disponibilidade_placas (operacao_id, placa, data, status, sugestao, observacao,
                   atualizado_por, dt_atualizacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (operacao_id, placa, data, status, sugestao, obs, usuario, tempo.agora_str()))
