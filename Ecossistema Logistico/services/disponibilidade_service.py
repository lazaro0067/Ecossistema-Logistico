"""Disponibilidade planejada das placas da frota própria — hoje + DISPONIBILIDADE_DIAS dias.

Status de cada placa em cada dia: Disponível · Indisponível Frota · Indisponível Viagem.
  1. Escolha do gestor da Puxada (clicando no dia) — sempre vale. Placa disponível leva a sugestão
     de pedido (Retornável ou Descartável), que aparece para o Ressuprimento.
  2. Automático:
     • carreta "Manutenção" / "Inativa" no cadastro → Indisponível Frota;
     • viagem em andamento no App Carreteiro → Indisponível Viagem até o dia da chegada agendada;
     • senão → Disponível.
"""
import datetime as dt

import pandas as pd

from config.settings import DISPONIBILIDADE_DIAS, STATUS_DISPONIBILIDADE
from core import tempo
from repositories import carreteiro_repo, logistica_repo
from services.erros import RegraNegocioError

CORES = {"Disponível": "#0ca30c", "Indisponível Frota": "#d03b3b", "Indisponível Viagem": "#7b57c8"}
# planejamentos gravados antes da mudança de status
_ANTIGOS = {"Programada": "Disponível", "Em viagem": "Indisponível Viagem", "Manutenção": "Indisponível Frota",
            "Sem motorista": "Indisponível Frota", "Indisponível": "Indisponível Frota"}


def dias() -> list[dt.date]:
    hoje = tempo.hoje()
    return [hoje + dt.timedelta(days=i) for i in range(DISPONIBILIDADE_DIAS + 1)]


def grade(operacao_id: int) -> pd.DataFrame:
    """Uma linha por placa e dia: placa, modelo, capacidade_hl, data, status, observacao, manual (bool)."""
    ds = dias()
    carretas = logistica_repo.carretas_df(operacao_id)
    if carretas.empty:
        return pd.DataFrame(columns=["placa", "modelo", "capacidade_hl", "data", "status", "sugestao", "observacao",
                                     "manual", "pedidos"])
    manual = logistica_repo.disponibilidade_df(operacao_id, ds[0].isoformat(), ds[-1].isoformat())
    manual = {(r["placa"], r["data"]): r for r in manual.to_dict("records")}
    from repositories import pedidos_puxada_repo

    peds = pedidos_puxada_repo.pedidos_df(operacao_id, ds[0].isoformat(), ds[-1].isoformat())
    pedidos: dict = {}
    if not peds.empty:
        for r in peds[peds["status"] != "Cancelado"].to_dict("records"):
            pedidos.setdefault((str(r["placa"]).upper(), r["data"]), []).append(
                f"{r['numero_pedido']} ({r['tipo']}){' ✅' if r['status'] == 'Finalizado' else ''}")
    viagens = carreteiro_repo.viagens_df(operacao_id)
    ativas = {}
    if not viagens.empty:
        for r in viagens[viagens["status"] == carreteiro_repo.EM_VIAGEM].to_dict("records"):
            ativas[str(r["placa"]).upper()] = carreteiro_repo.viagem(int(r["id"]))
    linhas = []
    for c in carretas.to_dict("records"):
        placa = str(c["placa"]).upper()
        v = ativas.get(placa)
        for d in ds:
            m = manual.get((c["placa"], d.isoformat())) or manual.get((placa, d.isoformat()))
            sugestao = None
            if m:
                obs = m.get("observacao") if isinstance(m.get("observacao"), str) else ""
                status, eh_manual = _ANTIGOS.get(m["status"], m["status"]), True
                sugestao = m.get("sugestao") if status == "Disponível" else None
                if sugestao is not None and not isinstance(sugestao, str):
                    sugestao = None
            else:
                eh_manual = False
                cad = str(c.get("status") or "")
                if cad == "Manutenção":
                    status, obs = "Indisponível Frota", "manutenção (cadastro da carreta)"
                elif cad == "Inativa":
                    status, obs = "Indisponível Frota", "carreta inativa"
                elif v:
                    chegada = dt.date.fromisoformat(v["desc_data"]) if v.get("desc_data") else None
                    if chegada is None:
                        status, obs = ("Indisponível Viagem", f"{v['motorista']} · pedido {v['numero_pedido']}") if d == ds[0] \
                            else ("Disponível", "retorno ainda não agendado pelo motorista")
                    elif d < chegada:
                        status, obs = "Indisponível Viagem", f"{v['motorista']} · chega {chegada:%d/%m} {v.get('desc_hora') or ''}"
                    elif d == chegada:
                        status, obs = "Indisponível Viagem", f"chega às {v.get('desc_hora') or '--:--'} · {v.get('desc_tipo') or ''}"
                    else:
                        status, obs = "Disponível", ""
                else:
                    status, obs = "Disponível", ""
            ped = pedidos.get((placa, d.isoformat()), [])
            linhas.append({"placa": c["placa"], "modelo": c.get("modelo"), "capacidade_hl": c.get("capacidade_hl"),
                           "data": d, "status": status, "sugestao": sugestao, "observacao": obs, "manual": eh_manual,
                           "pedidos": " · ".join(ped)})
    return pd.DataFrame(linhas)


def planejar(operacao_id: int, placa: str, data: dt.date, status: str | None, obs: str, usuario: str,
             sugestao: str | None = None) -> None:
    from config.settings import SUGESTAO_PEDIDO

    if status is not None and status not in STATUS_DISPONIBILIDADE:
        raise RegraNegocioError("Status inválido.")
    if data not in dias():
        raise RegraNegocioError(f"Planeje só de hoje até {DISPONIBILIDADE_DIAS} dias para frente.")
    if status != "Disponível":
        sugestao = None
    elif sugestao not in (None, *SUGESTAO_PEDIDO):
        raise RegraNegocioError("Sugestão de pedido inválida.")
    logistica_repo.salvar_disponibilidade(operacao_id, placa, data.isoformat(), status, (obs or "").strip() or None,
                                          usuario, sugestao)


def salvar_dia(operacao_id: int, data: dt.date, linhas: list[dict], usuario: str) -> int:
    """Grava o dia inteiro: [{placa, status, sugestao, observacao}]. Devolve quantas placas mudaram."""
    atual = {r["placa"]: r for r in grade(operacao_id).to_dict("records") if r["data"] == data}
    n = 0
    for l in linhas:
        a = atual.get(l["placa"])
        sug = l.get("sugestao") if l["status"] == "Disponível" else None
        obs = (l.get("observacao") or "").strip()
        if a and a["manual"] and a["status"] == l["status"] and (a.get("sugestao") or None) == (sug or None) \
                and (a.get("observacao") or "") == obs:
            continue
        if a and not a["manual"] and a["status"] == l["status"] and not sug and obs == (a.get("observacao") or ""):
            continue  # nada mudou em relação ao automático
        planejar(operacao_id, l["placa"], data, l["status"], obs, usuario, sug)
        n += 1
    return n
