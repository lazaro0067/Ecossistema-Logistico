"""Disponibilidade planejada das placas da frota própria — hoje + DISPONIBILIDADE_DIAS dias.

Status de cada placa em cada dia:
  1. Planejamento manual (feito na tela) — sempre vale.
  2. Automático:
     • carreta com status "Manutenção" / "Inativa" no cadastro → Manutenção / Indisponível;
     • viagem em andamento no App Carreteiro → "Em viagem" até o dia da chegada agendada pelo
       motorista (no dia da chegada mostra a hora prevista);
     • senão → Disponível.
"""
import datetime as dt

import pandas as pd

from config.settings import DISPONIBILIDADE_DIAS, STATUS_DISPONIBILIDADE
from core import tempo
from repositories import carreteiro_repo, logistica_repo
from services.erros import RegraNegocioError

CORES = {"Disponível": "#0ca30c", "Programada": "#2a78d6", "Em viagem": "#7b57c8", "Manutenção": "#ec835a",
         "Sem motorista": "#fab219", "Indisponível": "#d03b3b"}


def dias() -> list[dt.date]:
    hoje = tempo.hoje()
    return [hoje + dt.timedelta(days=i) for i in range(DISPONIBILIDADE_DIAS + 1)]


def grade(operacao_id: int) -> pd.DataFrame:
    """Uma linha por placa e dia: placa, modelo, capacidade_hl, data, status, observacao, manual (bool)."""
    ds = dias()
    carretas = logistica_repo.carretas_df(operacao_id)
    if carretas.empty:
        return pd.DataFrame(columns=["placa", "modelo", "capacidade_hl", "data", "status", "observacao", "manual"])
    manual = logistica_repo.disponibilidade_df(operacao_id, ds[0].isoformat(), ds[-1].isoformat())
    manual = {(r["placa"], r["data"]): r for r in manual.to_dict("records")}
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
            if m:
                status, obs, eh_manual = m["status"], m.get("observacao") or "", True
            else:
                eh_manual = False
                cad = str(c.get("status") or "")
                if cad == "Manutenção":
                    status, obs = "Manutenção", "status do cadastro da carreta"
                elif cad == "Inativa":
                    status, obs = "Indisponível", "carreta inativa"
                elif v:
                    chegada = dt.date.fromisoformat(v["desc_data"]) if v.get("desc_data") else None
                    if chegada is None:
                        status, obs = ("Em viagem", f"{v['motorista']} · pedido {v['numero_pedido']}") if d == ds[0] \
                            else ("Disponível", "retorno ainda não agendado pelo motorista")
                    elif d < chegada:
                        status, obs = "Em viagem", f"{v['motorista']} · chega {chegada:%d/%m} {v.get('desc_hora') or ''}"
                    elif d == chegada:
                        status, obs = "Em viagem", f"chega às {v.get('desc_hora') or '--:--'} · {v.get('desc_tipo') or ''}"
                    else:
                        status, obs = "Disponível", ""
                else:
                    status, obs = "Disponível", ""
            linhas.append({"placa": c["placa"], "modelo": c.get("modelo"), "capacidade_hl": c.get("capacidade_hl"),
                           "data": d, "status": status, "observacao": obs, "manual": eh_manual})
    return pd.DataFrame(linhas)


def planejar(operacao_id: int, placa: str, data: dt.date, status: str | None, obs: str, usuario: str) -> None:
    if status is not None and status not in STATUS_DISPONIBILIDADE:
        raise RegraNegocioError("Status inválido.")
    if data not in dias():
        raise RegraNegocioError(f"Planeje só de hoje até {DISPONIBILIDADE_DIAS} dias para frente.")
    logistica_repo.salvar_disponibilidade(operacao_id, placa, data.isoformat(), status, (obs or "").strip() or None,
                                          usuario)
