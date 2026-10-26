"""🤖 Robô de relatórios: o que ele baixou/importou (gravado pelo robô que roda no computador da empresa)."""
from __future__ import annotations

import pandas as pd

from core import tempo
from database.connection import execute, query_df
from repositories import operacoes_repo

NOMES = {
    "vendas": "03.02.37 vendas", "compra": "03.02.37 compra", "pcd": "Relatório de mapas (PCD)",
    "saldo_estoque": "02.05.02 saldo de estoque", "contagem_validade": "Contagem com validade (WMS)",
    "estoque": "Grade Cora", "pedidos_marcados": "Puxada marcada",
    "ressuprimento": "Ressuprimento diário", "linear": "Relatório linear", "produtos": "01.11 produtos",
    "politica": "Política de estoque", "so_baixar": "Só baixar (sem importar)",
}


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M:%S")


def inicio(operacao_id: int | None, relatorio: str, maquina: str = "") -> int:
    return execute("INSERT INTO robo_execucoes (operacao_id, relatorio, inicio, status, maquina) VALUES (?, ?, ?, ?, ?)",
                   (operacao_id, relatorio, agora(), "rodando", maquina[:60]))


def fim(exec_id: int, status: str, mensagem: str = "", arquivo: str = "") -> None:
    execute("UPDATE robo_execucoes SET fim = ?, status = ?, mensagem = ?, arquivo = ? WHERE id = ?",
            (agora(), status, str(mensagem)[:500], str(arquivo)[:200], int(exec_id)))
    if status == "erro":
        _avisar_erro(exec_id, mensagem)


def _avisar_erro(exec_id: int, mensagem: str) -> None:
    try:
        from config.settings import PERFIL_MASTER
        from repositories import motoristas_repo

        r = query_df("SELECT relatorio FROM robo_execucoes WHERE id = ?", (int(exec_id),))
        rel = NOMES.get(r["relatorio"].iloc[0], r["relatorio"].iloc[0]) if not r.empty else "relatório"
        for u in query_df("SELECT id FROM usuarios WHERE perfil = ? AND ativo = 1", (PERFIL_MASTER,))["id"]:
            motoristas_repo.criar_notificacao(int(u), "robo", f"robo_erro:{exec_id}:{u}",
                                              f"🤖 Robô não conseguiu: {rel}", str(mensagem)[:300], "bases", agora())
    except Exception:  # noqa: BLE001 — o aviso nunca derruba o robô
        pass


def ultimas(operacao_id: int | None = None, limite: int = 200) -> pd.DataFrame:
    if operacao_id:
        ids = operacoes_repo.ids_efetivos(operacao_id)
        ph = ", ".join("?" * len(ids))
        return query_df(f"SELECT * FROM robo_execucoes WHERE operacao_id IN ({ph}) OR operacao_id IS NULL "
                        f"ORDER BY id DESC LIMIT {int(limite)}", ids)
    return query_df(f"SELECT * FROM robo_execucoes ORDER BY id DESC LIMIT {int(limite)}")


def situacao(operacao_id: int | None = None) -> pd.DataFrame:
    """Última execução de cada relatório."""
    d = ultimas(operacao_id, 1000)
    if d.empty:
        return d
    return d.sort_values("id", ascending=False).drop_duplicates("relatorio").reset_index(drop=True)
