"""Pedidos D0 (hoje) e D+1 (amanhã) da Puxada.

Fluxo:
  1. Puxada › 🗓️ Disponibilidade: o gestor marca cada placa do dia (Disponível / Indisponível Frota /
     Indisponível Viagem) e, se disponível, a sugestão de pedido (Retornável ou Descartável).
  2. Puxada › 📋 Pedidos D0 / D+1: escolhe a placa, informa o número do pedido e o tipo.
     Retornável → paletes de 600 ml Âmbar, 600 ml Verde, 1 Litro e 300 ml. Descartável → paletes no total.
  3. O pedido aparece para o Ressuprimento e para o Armazém (Gestão de Pedidos).
     Quando o armazém termina, clica em ✅ Finalizado — o status muda em todas as telas.
"""
import datetime as dt
import re

import pandas as pd

from config.settings import EMBALAGENS_RETORNAVEL, SUGESTAO_PEDIDO
from core import tempo
from repositories import pedidos_puxada_repo as repo
from services.erros import RegraNegocioError

STATUS_ICONE = {"Aberto": "🟡", "Finalizado": "✅", "Cancelado": "⛔"}


def dias_pedido() -> list[dt.date]:
    """D0 = hoje, D+1 = amanhã."""
    hoje = tempo.hoje()
    return [hoje, hoje + dt.timedelta(days=1)]


def rotulo_dia(d: dt.date) -> str:
    hoje = tempo.hoje()
    nome = "D0 · hoje" if d == hoje else "D+1 · amanhã" if d == hoje + dt.timedelta(days=1) else "Anterior"
    return f"{nome} {d:%d/%m}"


def _num(v) -> float:
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        raise RegraNegocioError("Quantidade de paletes inválida.")
    if f < 0:
        raise RegraNegocioError("A quantidade de paletes não pode ser negativa.")
    return f


def salvar_pedido(operacao_id: int, pid: int | None, data: dt.date, placa: str, numero: str, tipo: str,
                  qtds: dict | None, paletes, observacao: str, usuario: str, fabrica_id: int | None = None) -> int:
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial no menu para lançar pedidos.")
    atual = repo.pedido(pid) if pid else None
    if atual and atual["status"] != "Aberto":
        raise RegraNegocioError(f"Este pedido está {atual['status'].lower()} — não pode mais ser alterado.")
    if not atual and data not in dias_pedido():
        raise RegraNegocioError("Lance pedidos só para hoje (D0) ou amanhã (D+1).")
    placa = (placa or "").strip().upper()
    if not placa:
        raise RegraNegocioError("Escolha a placa.")
    numero = re.sub(r"\s+", "", str(numero or ""))
    if not numero:
        raise RegraNegocioError("Informe o número do pedido.")
    if repo.numero_existe(operacao_id, numero, pid):
        raise RegraNegocioError(f"O pedido {numero} já foi lançado.")
    from repositories import logistica_repo

    fabricas = set(logistica_repo.fabricas_df()["id"].astype(int))
    if not fabricas:
        raise RegraNegocioError("Cadastre as fábricas em Puxada › ⚙️ Cadastros › 🏭 Fábricas.")
    if not fabrica_id or int(fabrica_id) not in fabricas:
        raise RegraNegocioError("Escolha a fábrica do pedido.")
    if tipo not in SUGESTAO_PEDIDO:
        raise RegraNegocioError("Escolha Retornável ou Descartável.")
    dados = {"data": data.isoformat(), "placa": placa, "numero_pedido": numero, "fabrica_id": int(fabrica_id), "tipo": tipo,
             "observacao": (observacao or "").strip() or None, **{k: 0.0 for k in EMBALAGENS_RETORNAVEL}, "paletes": 0.0}
    if tipo == "Retornável":
        for k in EMBALAGENS_RETORNAVEL:
            dados[k] = _num((qtds or {}).get(k))
        dados["paletes"] = sum(dados[k] for k in EMBALAGENS_RETORNAVEL)
        if dados["paletes"] <= 0:
            raise RegraNegocioError("Informe a quantidade de paletes de pelo menos uma embalagem retornável.")
    else:
        dados["paletes"] = _num(paletes)
        if dados["paletes"] <= 0:
            raise RegraNegocioError("Informe a quantidade de paletes do pedido descartável.")
    return repo.salvar(operacao_id, pid, dados, usuario)


def finalizar(pid: int, usuario: str) -> None:
    p = repo.pedido(pid)
    if not p:
        raise RegraNegocioError("Pedido não encontrado.")
    if p["status"] == "Cancelado":
        raise RegraNegocioError("Pedido cancelado não pode ser finalizado.")
    repo.mudar_status(pid, "Finalizado", usuario)


def reabrir(pid: int) -> None:
    repo.mudar_status(pid, "Aberto", None)


def cancelar(pid: int, usuario: str) -> None:
    p = repo.pedido(pid)
    if p and p["status"] == "Finalizado":
        raise RegraNegocioError("O armazém já finalizou este pedido — peça para reabrir antes de cancelar.")
    repo.mudar_status(pid, "Cancelado", usuario)


def composicao(r: dict) -> str:
    """'Retornável: 600 ml Âmbar 4 · 1 Litro 2' ou 'Descartável: 10 paletes'."""
    if r.get("tipo") == "Retornável":
        partes = [f"{rot} {_fmt(r.get(k))}" for k, rot in EMBALAGENS_RETORNAVEL.items() if float(r.get(k) or 0)]
        return " · ".join(partes) or "—"
    return f"{_fmt(r.get('paletes'))} palete(s)"


def _fmt(v) -> str:
    f = float(v or 0)
    return f"{f:.0f}" if f == int(f) else f"{f:.1f}".replace(".", ",")


def tabela(df: pd.DataFrame, com_filial: bool = False) -> pd.DataFrame:
    """Pedidos no formato de leitura (telas, detalhes e download)."""
    if df is None or df.empty:
        return pd.DataFrame()
    linhas = []
    for r in df.to_dict("records"):
        d = {"Dia": rotulo_dia(dt.date.fromisoformat(str(r["data"])[:10]))}
        if com_filial:
            d["Filial"] = r.get("filial")
        fab = r.get("fabrica")
        d.update({"Placa": r["placa"], "Pedido": r["numero_pedido"], "Fábrica": fab if isinstance(fab, str) else "—",
                  "Tipo": r["tipo"],
                  **{rot: float(r.get(k) or 0) if r["tipo"] == "Retornável" else None
                     for k, rot in EMBALAGENS_RETORNAVEL.items()},
                  "Paletes (total)": float(r.get("paletes") or 0),
                  "Status": f"{STATUS_ICONE.get(r['status'], '')} {r['status']}",
                  "Lançado por": r.get("criado_por") or "",
                  "Finalizado": (f"{r['finalizado_por']} · {tempo.parse_dt(r['finalizado_em']):%d/%m %H:%M}"
                                 if isinstance(r.get("finalizado_em"), str) and r.get("finalizado_em") else "")})
        linhas.append(d)
    return pd.DataFrame(linhas)


def resumo(df: pd.DataFrame) -> dict:
    """Totais de paletes por embalagem (pedidos não cancelados)."""
    if df is None or df.empty:
        return {"pedidos": 0, "finalizados": 0, "abertos": 0, "ret": 0.0, "desc": 0.0,
                **{k: 0.0 for k in EMBALAGENS_RETORNAVEL}}
    v = df[df["status"] != "Cancelado"]
    ret = v[v["tipo"] == "Retornável"]
    return {"pedidos": len(v), "finalizados": int((v["status"] == "Finalizado").sum()),
            "abertos": int((v["status"] == "Aberto").sum()),
            "ret": float(ret["paletes"].fillna(0).sum()),
            "desc": float(v[v["tipo"] == "Descartável"]["paletes"].fillna(0).sum()),
            **{k: float(ret[k].fillna(0).sum()) for k in EMBALAGENS_RETORNAVEL}}
