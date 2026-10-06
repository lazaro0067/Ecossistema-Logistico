"""Disponibilidade dos motoristas da frota própria.

Status em um momento:
  1. 🏖️ Férias ......... período cadastrado em Puxada › 👤 Disponibilidade de Motoristas › Férias
  2. 🛣️ Em viagem ...... viagem em andamento no App Carreteiro (até a chegada agendada, nos próximos dias)
  3. 🔧 Em serviço ..... o motorista marcou "+ Em serviço" no app (manobra, oficina, abastecimento...)
  4. 😴 Interjornada ... 11 h de descanso contadas do último "Finalizar viagem" do App Carreteiro
  4. 🟢 Disponível
"""
import datetime as dt

import pandas as pd

from config.settings import DISPONIBILIDADE_DIAS, INTERJORNADA_H
from core import tempo
from repositories import logistica_repo
from repositories import motoristas_repo as repo
from services.erros import RegraNegocioError

CORES = {"Disponível": "#0ca30c", "Interjornada": "#b7791f", "Em viagem": "#7b57c8", "Férias": "#2a78d6",
         "Em serviço": "#c2571a"}
ICONES = {"Disponível": "🟢", "Interjornada": "😴", "Em viagem": "🛣️", "Férias": "🏖️", "Em serviço": "🔧"}


def dias() -> list[dt.date]:
    hoje = tempo.hoje()
    return [hoje + dt.timedelta(days=i) for i in range(DISPONIBILIDADE_DIAS + 1)]


def _dt(v) -> dt.datetime | None:
    return tempo.parse_dt(v) if isinstance(v, str) and v else None


def _data(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def liberado_em(ultima: dict | None) -> dt.datetime | None:
    """Fim da última viagem + 11 h de interjornada."""
    fim = _dt((ultima or {}).get("ts_fim"))
    return fim + dt.timedelta(hours=INTERJORNADA_H) if fim else None


def situacao(m: dict, quando: dt.datetime, ultima: dict | None, ativa: dict | None,
             ferias: list[dict], servico: dict | None = None) -> dict:
    """{status, detalhe, livre_em} do motorista no momento `quando`."""
    dia = quando.date()
    for f in ferias:
        ini, fim = _data(f["inicio"]), _data(f["fim"])
        if f["motorista_id"] == m["id"] and ini and fim and ini <= dia <= fim:
            return {"status": "Férias", "detalhe": f"férias de {ini:%d/%m} a {fim:%d/%m}",
                    "livre_em": dt.datetime.combine(fim + dt.timedelta(days=1), dt.time(0, 0))}
    if ativa:
        chegada = _data(ativa.get("desc_data"))
        if chegada is None or dia <= chegada or dia == tempo.hoje():
            prev = f" · chega {chegada:%d/%m} {ativa.get('desc_hora') or ''}".rstrip() if chegada else ""
            return {"status": "Em viagem", "detalhe": f"pedido {ativa['numero_pedido']} · {ativa['placa']}{prev}",
                    "livre_em": None}
    if servico and dia == tempo.hoje():
        ini = _dt(servico.get("inicio"))
        return {"status": "Em serviço", "detalhe": f"{servico.get('tipo') or 'serviço'} desde "
                                                  f"{ini:%d/%m %H:%M}" if ini else (servico.get("tipo") or ""),
                "livre_em": None}
    livre = liberado_em(ultima)
    if livre and quando < livre:
        fim = _dt(ultima["ts_fim"])
        return {"status": "Interjornada",
                "detalhe": f"finalizou {fim:%d/%m %H:%M} · livre às {livre:%H:%M} de {livre:%d/%m}",
                "livre_em": livre}
    det = f"última viagem finalizada {_dt(ultima['ts_fim']):%d/%m %H:%M}" if ultima and _dt(ultima.get("ts_fim")) else ""
    return {"status": "Disponível", "detalhe": det, "livre_em": None}


def _base(operacao_id: int):
    mots = logistica_repo.motoristas_df(operacao_id)
    ds = dias()
    return (mots, repo.ultimas_viagens(operacao_id), repo.viagens_ativas(operacao_id),
            repo.ferias_periodo(operacao_id, ds[0].isoformat(), (ds[-1] + dt.timedelta(days=60)).isoformat()),
            repo.servicos_ativos(operacao_id))


def agora(operacao_id: int) -> pd.DataFrame:
    """Situação de cada motorista neste momento."""
    mots, ult, ativas, ferias, serv = _base(operacao_id)
    if mots.empty:
        return pd.DataFrame(columns=["id", "nome", "status", "detalhe", "livre_em"])
    now = tempo.agora()
    linhas = []
    for m in mots.to_dict("records"):
        s = situacao(m, now, ult.get(m["id"]), ativas.get(m["id"]), ferias, serv.get(m["id"]))
        linhas.append({"id": m["id"], "nome": m["nome"], **s})
    return pd.DataFrame(linhas)


def grade(operacao_id: int) -> pd.DataFrame:
    """Uma linha por motorista e dia (hoje = agora; próximos dias = início do dia, com aviso se libera no dia)."""
    mots, ult, ativas, ferias, serv = _base(operacao_id)
    if mots.empty:
        return pd.DataFrame(columns=["id", "nome", "data", "status", "detalhe", "livre_em"])
    now = tempo.agora()
    linhas = []
    for m in mots.to_dict("records"):
        for d in dias():
            quando = now if d == now.date() else dt.datetime.combine(d, dt.time(0, 0))
            s = situacao(m, quando, ult.get(m["id"]), ativas.get(m["id"]), ferias, serv.get(m["id"]))
            # interjornada que acaba no próprio dia: o motorista fica disponível a partir da hora
            if d != now.date() and s["status"] == "Interjornada" and s["livre_em"] and s["livre_em"].date() == d:
                s = {**s, "status": "Disponível", "detalhe": f"a partir das {s['livre_em']:%H:%M} (interjornada)"}
            linhas.append({"id": m["id"], "nome": m["nome"], "data": d, **s})
    return pd.DataFrame(linhas)


def no_momento(operacao_id: int, motorista_id: int, quando: dt.datetime) -> dict:
    """Situação de um motorista num horário (usado no lançamento do pedido)."""
    mots, ult, ativas, ferias, serv = _base(operacao_id)
    m = next((r for r in mots.to_dict("records") if r["id"] == motorista_id), None)
    if not m:
        return {"status": "Disponível", "detalhe": "", "livre_em": None}
    return situacao(m, quando, ult.get(motorista_id), ativas.get(motorista_id), ferias, serv.get(motorista_id))


# --- Férias ---------------------------------------------------------------------------
def salvar_ferias(operacao_id: int, fid: int | None, motorista_id: int | None, inicio, fim, obs: str,
                  usuario: str) -> None:
    if not motorista_id:
        raise RegraNegocioError("Escolha o motorista.")
    ini, fi = _data(inicio), _data(fim)
    if not ini or not fi:
        raise RegraNegocioError("Informe o início e o fim das férias.")
    if fi < ini:
        raise RegraNegocioError("O fim das férias não pode ser antes do início.")
    if (fi - ini).days > 60:
        raise RegraNegocioError("Período de férias maior que 60 dias — confira as datas.")
    for f in repo.ferias_periodo(operacao_id, ini.isoformat(), fi.isoformat()):
        if f["motorista_id"] == int(motorista_id) and f["id"] != fid:
            raise RegraNegocioError(f"Já existem férias cadastradas de {_data(f['inicio']):%d/%m/%Y} a "
                                    f"{_data(f['fim']):%d/%m/%Y} para este motorista.")
    repo.salvar_ferias(operacao_id, fid, int(motorista_id), ini.isoformat(), fi.isoformat(),
                       (obs or "").strip() or None, usuario)


def situacao_ferias(inicio, fim) -> str:
    hoje = tempo.hoje()
    ini, fi = _data(inicio), _data(fim)
    if not ini or not fi:
        return "—"
    if fi < hoje:
        return "✔️ Encerrada"
    if ini <= hoje:
        return f"🏖️ Em férias (volta {fi + dt.timedelta(days=1):%d/%m})"
    return f"🗓️ Programada (em {(ini - hoje).days} dia(s))"


# --- Em serviço (App Carreteiro) -----------------------------------------------------------------
def iniciar_servico(motorista: dict, tipo: str, obs: str = "") -> int:
    from config.settings import TIPOS_SERVICO_MOTORISTA
    from repositories import carreteiro_repo

    if tipo not in TIPOS_SERVICO_MOTORISTA:
        raise RegraNegocioError("Escolha o tipo de serviço.")
    if tipo == "Outro" and len((obs or "").strip()) < 3:
        raise RegraNegocioError("Descreva o serviço.")
    if repo.servico_ativo(motorista["id"]):
        raise RegraNegocioError("Você já está em serviço — encerre antes de começar outro.")
    if carreteiro_repo.viagem_ativa_motorista(motorista["id"]):
        raise RegraNegocioError("Você tem uma viagem em andamento.")
    return repo.iniciar_servico(motorista["operacao_id"], motorista["id"], tipo, (obs or "").strip() or None)


def encerrar_servico(motorista: dict) -> None:
    s = repo.servico_ativo(motorista["id"])
    if not s:
        raise RegraNegocioError("Nenhum serviço em andamento.")
    repo.encerrar_servico(s["id"])
