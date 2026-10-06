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


DIAS_A_FRENTE = 2  # D0, D+1 e D+2


def dias_pedido() -> list[dt.date]:
    """D0 = hoje, D+1 = amanhã, D+2 = depois de amanhã."""
    hoje = tempo.hoje()
    return [hoje + dt.timedelta(days=i) for i in range(DIAS_A_FRENTE + 1)]


def rotulo_dia(d: dt.date) -> str:
    n = (d - tempo.hoje()).days
    nome = {0: "D0 · hoje", 1: "D+1 · amanhã", 2: "D+2"}.get(n, "Anterior" if n < 0 else f"D+{n}")
    return f"{nome} {d:%d/%m}"


# --- Prazo de saída da carreta (prioridade do armazém) ---------------------------------
def agendamento_dt(r: dict) -> dt.datetime | None:
    hora = r.get("hora_agendamento")
    if not isinstance(hora, str) or not hora:
        return None
    try:
        return dt.datetime.combine(dt.date.fromisoformat(str(r["data"])[:10]), dt.datetime.strptime(hora, "%H:%M").time())
    except ValueError:
        return None


def prazo_saida(r: dict) -> dt.datetime | None:
    """Hora máxima para a carreta sair da revenda = agendamento na fábrica − deslocamento até a fábrica."""
    ag = agendamento_dt(r)
    if not ag:
        return None
    try:
        h = float(r.get("deslocamento_h") or 0)
    except (TypeError, ValueError):
        h = 0.0
    return ag - dt.timedelta(hours=h if h == h else 0)


def prioridade(r: dict) -> tuple[int, str, str]:
    """(ordem, rótulo, cor) — quanto menor a ordem, mais urgente para o armazém."""
    if r.get("status") == "Finalizado":
        return 9, "✅ Finalizado", "#146c43"
    if r.get("status") == "Cancelado":
        return 10, "⛔ Cancelado", "#77766f"
    pz = prazo_saida(r)
    if not pz:
        return 6, "⚪ Sem agendamento", "#77766f"
    falta_h = (pz - tempo.agora()).total_seconds() / 3600
    if falta_h < 0:
        return 0, f"⛔ Atrasado {_dur(-falta_h)}", "#a32025"
    if falta_h <= 2:
        return 1, f"🔴 Sai em {_dur(falta_h)}", "#d03b3b"
    if falta_h <= 6:
        return 2, f"🟠 Sai em {_dur(falta_h)}", "#c2571a"
    if falta_h <= 24:
        return 3, f"🟡 Sai em {_dur(falta_h)}", "#b7791f"
    return 4, f"🟢 Sai em {_dur(falta_h)}", "#146c43"


def _dur(h: float) -> str:
    m = int(round(h * 60))
    if m < 60:
        return f"{m} min"
    if m < 48 * 60:
        return f"{m // 60}h{m % 60:02d}"
    return f"{m // 1440} dias"


def _num(v) -> float:
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        raise RegraNegocioError("Quantidade de paletes inválida.")
    if f < 0:
        raise RegraNegocioError("A quantidade de paletes não pode ser negativa.")
    return f


def salvar_pedido(operacao_id: int, pid: int | None, data: dt.date, placa: str, numero: str, tipo: str,
                  qtds: dict | None, paletes, observacao: str, usuario: str, fabrica_id: int | None = None,
                  motorista_id: int | None = None, hora_agendamento=None) -> int:
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial no menu para lançar pedidos.")
    atual = repo.pedido(pid) if pid else None
    if atual and atual["status"] != "Aberto":
        raise RegraNegocioError(f"Este pedido está {atual['status'].lower()} — não pode mais ser alterado.")
    if not atual and data not in dias_pedido():
        raise RegraNegocioError("Lance pedidos para hoje (D0), amanhã (D+1) ou depois de amanhã (D+2).")
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
    motoristas = set(logistica_repo.motoristas_df(operacao_id)["id"].astype(int))
    if not motorista_id or int(motorista_id) not in motoristas:
        raise RegraNegocioError("Escolha o motorista do pedido.")
    if not hora_agendamento:
        raise RegraNegocioError("Informe a hora do agendamento na fábrica.")
    hora = hora_agendamento.strftime("%H:%M") if isinstance(hora_agendamento, dt.time) else str(hora_agendamento)[:5]
    if not re.fullmatch(r"\d{2}:\d{2}", hora):
        raise RegraNegocioError("Hora do agendamento inválida (use HH:MM).")
    if tipo not in SUGESTAO_PEDIDO:
        raise RegraNegocioError("Escolha Retornável ou Descartável.")
    dados = {"data": data.isoformat(), "placa": placa, "numero_pedido": numero, "fabrica_id": int(fabrica_id),
             "motorista_id": int(motorista_id), "hora_agendamento": hora, "tipo": tipo,
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
        ag, pz = agendamento_dt(r), prazo_saida(r)
        mot = r.get("motorista")
        d.update({"Prioridade": prioridade(r)[1],
                  "Placa": r["placa"], "Pedido": r["numero_pedido"], "Fábrica": fab if isinstance(fab, str) else "—",
                  "Motorista": mot if isinstance(mot, str) else "—",
                  "Agendamento fábrica": f"{ag:%d/%m %H:%M}" if ag else "—",
                  "Sair da revenda até": f"{pz:%d/%m %H:%M}" if pz else "—",
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
