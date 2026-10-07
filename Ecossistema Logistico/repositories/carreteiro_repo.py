"""Acesso a dados do App Carreteiro: viagens, etapas (com GPS), notas fiscais e fotos."""
import pandas as pd

from config.settings import ETAPAS_VIAGEM
from database.connection import execute, get_conn, query_all, query_df, query_one
from repositories import operacoes_repo

COLUNAS_TS = [e[2] for e in ETAPAS_VIAGEM]
EM_VIAGEM, FINALIZADA, CANCELADA = "Em viagem", "Finalizada", "Cancelada"


# --- Motorista <-> usuário ---------------------------------------------------
def motorista_do_usuario(usuario_id: int) -> dict | None:
    return query_one("SELECT * FROM motoristas WHERE usuario_id = ? ORDER BY id LIMIT 1", (usuario_id,))


def motorista(mid: int) -> dict | None:
    return query_one("SELECT * FROM motoristas WHERE id = ?", (mid,))


def acessos_df(operacao_id: int) -> pd.DataFrame:
    return query_df("""SELECT m.id, m.nome, m.cnh, m.telefone, m.usuario_id, u.login AS acesso,
                              CASE WHEN u.id IS NULL THEN 'Sem acesso' WHEN u.ativo = 1 THEN 'Ativo' ELSE 'Bloqueado' END
                                  AS situacao,
                              u.ultimo_acesso
                       FROM motoristas m LEFT JOIN usuarios u ON u.id = m.usuario_id
                       WHERE m.operacao_id = ? ORDER BY m.nome""", (operacao_id,))


def ativar_usuario(usuario_id: int, ativo: bool) -> None:
    execute("UPDATE usuarios SET ativo = ? WHERE id = ?", (int(ativo), usuario_id))


def vincular_usuario(motorista_id: int, usuario_id: int | None) -> None:
    execute("UPDATE motoristas SET usuario_id = ? WHERE id = ?", (usuario_id, motorista_id))


def motoristas_lista(operacao_id: int) -> list[dict]:
    return query_all("SELECT id, nome FROM motoristas WHERE operacao_id = ? ORDER BY nome", (operacao_id,))


# --- Revenda (ponto e raio para o GPS) ----------------------------------------
def revenda(operacao_id: int) -> dict:
    r = query_one("SELECT id, nome, lat, lon, raio_m FROM operacoes WHERE id = ?", (operacao_id,)) or {}
    return r


def salvar_revenda(operacao_id: int, lat: float | None, lon: float | None, raio_m: float | None) -> None:
    execute("UPDATE operacoes SET lat = ?, lon = ?, raio_m = ? WHERE id = ?", (lat, lon, raio_m, operacao_id))


def link_relato(operacao_id: int) -> str:
    r = query_one("SELECT link_relato FROM operacoes WHERE id = ?", (operacao_id,)) or {}
    return (r.get("link_relato") or "").strip()


def salvar_link_relato(operacao_id: int, link: str | None) -> None:
    execute("UPDATE operacoes SET link_relato = ? WHERE id = ?", (link or None, operacao_id))


# --- Listas de seleção ---------------------------------------------------------
def destinos() -> list[dict]:
    return query_all("SELECT id, nome, cidade, uf FROM fabricas ORDER BY nome")


def placas(operacao_id: int) -> list[dict]:
    return query_all("SELECT id, placa, modelo, status FROM carretas WHERE operacao_id = ? "
                     "AND COALESCE(status, '') <> 'Inativa' ORDER BY placa", (operacao_id,))


# --- Viagens -------------------------------------------------------------------
def viagem(vid: int) -> dict | None:
    return query_one("""SELECT v.*, m.nome AS motorista FROM viagens_carreteiro v
                        JOIN motoristas m ON m.id = v.motorista_id WHERE v.id = ?""", (vid,))


def viagem_ativa_motorista(motorista_id: int) -> dict | None:
    r = query_one("SELECT id FROM viagens_carreteiro WHERE motorista_id = ? AND status = ? ORDER BY id DESC LIMIT 1",
                  (motorista_id, EM_VIAGEM))
    return viagem(r["id"]) if r else None


def viagem_ativa_placa(operacao_id: int, placa: str) -> dict | None:
    return query_one("""SELECT v.id, m.nome AS motorista FROM viagens_carreteiro v JOIN motoristas m ON m.id = v.motorista_id
                        WHERE v.operacao_id = ? AND upper(v.placa) = upper(?) AND v.status = ? LIMIT 1""",
                     (operacao_id, placa, EM_VIAGEM))


def pedido_em_viagem(operacao_id: int, numero: str) -> bool:
    return query_one("SELECT 1 AS x FROM viagens_carreteiro WHERE operacao_id = ? AND trim(numero_pedido) = ? "
                     "AND status <> ?", (operacao_id, numero.strip(), CANCELADA)) is not None


def criar_viagem(dados: dict) -> int:
    cols = list(dados)
    return execute(f"INSERT INTO viagens_carreteiro ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   tuple(dados.values()))


def atualizar(vid: int, **campos) -> int:
    return execute(f"UPDATE viagens_carreteiro SET {', '.join(k + ' = ?' for k in campos)} WHERE id = ?",
                   (*campos.values(), vid))


def marcar_etapa(vid: int, coluna: str, ts: str, extra: dict | None = None) -> bool:
    """Grava a hora da etapa só se ainda estiver vazia (evita clique duplo)."""
    if coluna not in COLUNAS_TS:
        raise ValueError(coluna)
    extra = extra or {}
    sets = [f"{coluna} = ?"] + [f"{k} = ?" for k in extra]
    n = execute(f"UPDATE viagens_carreteiro SET {', '.join(sets)} WHERE id = ? AND {coluna} IS NULL",
                (ts, *extra.values(), vid))
    return n > 0


def registrar_evento(vid: int, etapa: str, ts: str, geo: dict | None) -> None:
    geo = geo or {}
    execute("""INSERT INTO viagem_eventos (viagem_id, etapa, ts, lat, lon, precisao_m, distancia_m, dentro_raio)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (vid, etapa, ts, geo.get("lat"), geo.get("lon"), geo.get("precisao"), geo.get("distancia_m"),
             geo.get("dentro_raio")))


def apagar_evento(vid: int, etapa: str) -> None:
    execute("DELETE FROM viagem_eventos WHERE viagem_id = ? AND etapa = ?", (vid, etapa))


def eventos_df(vid: int) -> pd.DataFrame:
    return query_df("SELECT etapa, ts, lat, lon, precisao_m, distancia_m, dentro_raio FROM viagem_eventos "
                    "WHERE viagem_id = ? ORDER BY ts, id", (vid,))


def ultimas_posicoes(ids: list[int]) -> dict[int, dict]:
    """Por viagem: o último ponto de GPS registrado (etapa, hora, lat/lon, precisão)."""
    if not ids:
        return {}
    marcas = ", ".join("?" * len(ids))
    linhas = query_all(f"""SELECT viagem_id, etapa, ts, lat, lon, precisao_m FROM viagem_eventos
                           WHERE viagem_id IN ({marcas}) AND lat IS NOT NULL AND lon IS NOT NULL
                           ORDER BY ts, id""", list(ids))
    return {r["viagem_id"]: r for r in linhas}  # o último sobrescreve


def geo_viagens(ids: list[int]) -> pd.DataFrame:
    """Eventos de GPS (chegada/início) de várias viagens, para o TMA confirmado por raio."""
    if not ids:
        return pd.DataFrame(columns=["viagem_id", "etapa", "dentro_raio", "distancia_m"])
    marcas = ", ".join("?" * len(ids))
    return query_df(f"SELECT viagem_id, etapa, dentro_raio, distancia_m FROM viagem_eventos "
                    f"WHERE viagem_id IN ({marcas}) AND etapa IN ('inicio', 'chegada')", ids)


def viagens_df(operacao_id: int, de: str | None = None, ate: str | None = None,
               motorista_id: int | None = None, incluir_canceladas: bool = False) -> pd.DataFrame:
    """Viagens com nome do motorista e contagem de NFs/fotos (sem carregar as imagens)."""
    f_sql, p = operacoes_repo.filtro("v.operacao_id", operacao_id)
    p = list(p)
    sql = f"""SELECT v.id, v.operacao_id, v.motorista_id, m.nome AS motorista, v.numero_pedido, v.agendamento,
                     v.destino_id, v.destino, v.placa, v.status, {', '.join('v.' + c for c in COLUNAS_TS)},
                     v.apresentou_no_prazo, v.atraso_min, v.observacao, v.desc_data, v.desc_hora, v.desc_tipo, v.desc_janela_id,
                     (SELECT COUNT(*) FROM viagem_notas n WHERE n.viagem_id = v.id) AS qtd_nfs,
                     (SELECT COUNT(*) FROM viagem_fotos f WHERE f.viagem_id = v.id) AS qtd_fotos
              FROM viagens_carreteiro v JOIN motoristas m ON m.id = v.motorista_id
              WHERE {f_sql}"""
    if not incluir_canceladas:
        sql += " AND v.status <> ?"
        p.append(CANCELADA)
    if de:
        sql += " AND substr(v.ts_inicio, 1, 10) >= ?"
        p.append(de)
    if ate:
        sql += " AND substr(v.ts_inicio, 1, 10) <= ?"
        p.append(ate)
    if motorista_id:
        sql += " AND v.motorista_id = ?"
        p.append(motorista_id)
    return query_df(sql + " ORDER BY v.ts_inicio DESC, v.id DESC", p)


def proximas_saidas(operacao_id: int, placas_: list[str], depois_de: str) -> pd.DataFrame:
    """Inícios de viagem por placa a partir de uma data — usados para fechar o TMA da última viagem do período."""
    if not placas_:
        return pd.DataFrame(columns=["id", "placa", "ts_inicio"])
    f_sql, p = operacoes_repo.filtro("operacao_id", operacao_id)
    marcas = ", ".join("?" * len(placas_))
    return query_df(f"""SELECT id, placa, ts_inicio FROM viagens_carreteiro
                        WHERE {f_sql} AND status <> ? AND placa IN ({marcas}) AND ts_inicio >= ?
                        ORDER BY ts_inicio""", [*p, CANCELADA, *placas_, depois_de])


# --- Notas fiscais e fotos -------------------------------------------------------
def notas(vid: int) -> list[dict]:
    return query_all("""SELECT n.id, n.numero_nf, n.criado_em,
                               (SELECT COUNT(*) FROM viagem_fotos f WHERE f.nota_id = n.id) AS fotos
                        FROM viagem_notas n WHERE n.viagem_id = ? ORDER BY n.id""", (vid,))


def adicionar_nota(vid: int, numero: str, ts: str, fotos: list[tuple[str, str, bytes]]) -> int:
    with get_conn() as conn:
        nid = conn.execute("INSERT INTO viagem_notas (viagem_id, numero_nf, criado_em) VALUES (?, ?, ?)",
                           (vid, numero, ts)).lastrowid
        for nome, tipo, conteudo in fotos:
            conn.execute("INSERT INTO viagem_fotos (viagem_id, nota_id, nome, tipo, conteudo, criado_em) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (vid, nid, nome, tipo, conteudo, ts))
        return nid


def adicionar_fotos(vid: int, nota_id: int, ts: str, fotos: list[tuple[str, str, bytes]]) -> None:
    with get_conn() as conn:
        for nome, tipo, conteudo in fotos:
            conn.execute("INSERT INTO viagem_fotos (viagem_id, nota_id, nome, tipo, conteudo, criado_em) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (vid, nota_id, nome, tipo, conteudo, ts))


def nota_existe(vid: int, numero: str) -> bool:
    return query_one("SELECT 1 AS x FROM viagem_notas WHERE viagem_id = ? AND numero_nf = ?", (vid, numero)) is not None


def remover_nota(vid: int, nota_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM viagem_fotos WHERE nota_id = ? AND viagem_id = ?", (nota_id, vid))
        conn.execute("DELETE FROM viagem_notas WHERE id = ? AND viagem_id = ?", (nota_id, vid))


def fotos(vid: int, nota_id: int | None = None) -> list[dict]:
    sql, p = "SELECT id, nota_id, nome, tipo, conteudo FROM viagem_fotos WHERE viagem_id = ?", [vid]
    if nota_id:
        sql += " AND nota_id = ?"
        p.append(nota_id)
    return query_all(sql + " ORDER BY id", p)


def nfs_texto(vid: int) -> str:
    return ", ".join(n["numero_nf"] for n in notas(vid))


# --- Integração: Pedidos Marcados, Vincular Pedido & NFs, Descarga (pátio) ----------
def pedido_marcado(operacao_id: int, numero: str) -> dict | None:
    """Resumo do pedido nos Pedidos Marcados (aceita o número com ou sem zeros à esquerda)."""
    numero = (numero or "").strip()
    if not numero:
        return None
    f_sql, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_one(f"""SELECT COUNT(*) AS itens, COALESCE(SUM(cx_marcadas), 0) AS cx, COALESCE(SUM(hl_marcado), 0) AS hl,
                             MAX(data_puxada) AS data_puxada
                      FROM pedidos_marcados WHERE {f_sql}
                      AND (trim(numero_pedido) = ? OR ltrim(trim(numero_pedido), '0') = ltrim(?, '0'))""",
                  [*p, numero, numero])
    return r if r and int(r["itens"] or 0) > 0 else None


def vinculo_da_viagem(vid: int) -> dict | None:
    return query_one("SELECT * FROM vinculos_pedidos WHERE viagem_id = ? ORDER BY id LIMIT 1", (vid,))


def vinculo_manual_do_pedido(operacao_id: int, numero: str) -> dict | None:
    """Vínculo lançado à mão para o mesmo pedido (sem viagem) — é aproveitado em vez de duplicar."""
    return query_one("""SELECT * FROM vinculos_pedidos WHERE operacao_id = ? AND trim(numero_pedido) = ?
                        AND viagem_id IS NULL ORDER BY id DESC LIMIT 1""", (operacao_id, (numero or "").strip()))


def apagar_vinculo_da_viagem(vid: int) -> None:
    execute("DELETE FROM vinculos_pedidos WHERE viagem_id = ?", (vid,))


def agendamento_da_viagem(vid: int) -> dict | None:
    return query_one("SELECT * FROM agendamentos_descarga WHERE viagem_id = ? ORDER BY id LIMIT 1", (vid,))


def agendamento_livre_da_placa(operacao_id: int, placa: str, de: str, ate: str) -> dict | None:
    """Descarga agendada à mão para a mesma placa (ainda sem viagem) — a viagem assume esse agendamento."""
    return query_one("""SELECT * FROM agendamentos_descarga WHERE operacao_id = ? AND upper(placa) = upper(?)
                        AND viagem_id IS NULL AND status = 'Agendado' AND data >= ? AND data <= ?
                        ORDER BY data, hora LIMIT 1""", (operacao_id, placa, de, ate))


def apagar_agendamento(aid: int) -> None:
    execute("DELETE FROM agendamentos_descarga WHERE id = ?", (aid,))


def retornos_destino(operacao_id: int, destino_id: int | None, limite: int = 30) -> list[dict]:
    """Últimos retornos (saída da cervejaria → chegada na revenda) para prever a chegada."""
    sql = """SELECT ts_saida_cervejaria, ts_chegada_revenda FROM viagens_carreteiro
             WHERE operacao_id = ? AND ts_saida_cervejaria IS NOT NULL AND ts_chegada_revenda IS NOT NULL
             AND status <> 'Cancelada'"""
    p = [operacao_id]
    if destino_id:
        sql += " AND destino_id = ?"
        p.append(destino_id)
    return query_all(sql + " ORDER BY ts_chegada_revenda DESC LIMIT ?", [*p, limite])


# --- Paradas na viagem (manutenção) -----------------------------------------------------------
def parada_ativa(vid: int) -> dict | None:
    return query_one("SELECT * FROM paradas_viagem WHERE viagem_id = ? AND fim IS NULL ORDER BY id DESC LIMIT 1",
                     (vid,))


def iniciar_parada(vid: int, motorista_id: int, tipo: str, obs: str | None, ts: str, lat=None, lon=None) -> int:
    return execute("""INSERT INTO paradas_viagem (viagem_id, motorista_id, tipo, observacao, inicio, lat, lon)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""", (vid, motorista_id, tipo, obs, ts, lat, lon))


def encerrar_parada(pid: int, ts: str) -> None:
    execute("UPDATE paradas_viagem SET fim = ? WHERE id = ?", (ts, pid))


def paradas_df(viagem_ids: list[int] | None = None, operacao_id: int | None = None) -> pd.DataFrame:
    sql = """SELECT p.id, p.viagem_id, v.numero_pedido, v.placa, m.nome AS motorista, p.tipo, p.observacao,
                    p.inicio, p.fim
             FROM paradas_viagem p JOIN viagens_carreteiro v ON v.id = p.viagem_id
             LEFT JOIN motoristas m ON m.id = v.motorista_id WHERE 1 = 1"""
    params: list = []
    if viagem_ids is not None:
        if not viagem_ids:
            return pd.DataFrame(columns=["id", "viagem_id", "numero_pedido", "placa", "motorista", "tipo",
                                         "observacao", "inicio", "fim"])
        sql += f" AND p.viagem_id IN ({', '.join('?' * len(viagem_ids))})"
        params += list(viagem_ids)
    if operacao_id is not None:
        sql += " AND v.operacao_id = ?"
        params.append(operacao_id)
    return query_df(sql + " ORDER BY p.inicio DESC", params)


def paradas_ativas(operacao_id: int) -> dict[int, dict]:
    """Por viagem: a parada de manutenção em andamento."""
    return {r["viagem_id"]: r for r in query_all(
        """SELECT p.* FROM paradas_viagem p JOIN viagens_carreteiro v ON v.id = p.viagem_id
           WHERE v.operacao_id = ? AND p.fim IS NULL""", (operacao_id,))}
