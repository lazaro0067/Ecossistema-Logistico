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
             ferias: list[dict], servico: dict | None = None, interj: dict | None = None) -> dict:
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
            ij_ini, ij_fim = _dt((interj or {}).get("inicio")), _dt((interj or {}).get("fim_previsto"))
            desc = f" · 😴 descansando até {ij_fim:%d/%m %H:%M}" if ij_ini and ij_fim and ij_ini <= quando < ij_fim else ""
            return {"status": "Em viagem", "detalhe": f"pedido {ativa['numero_pedido']} · {ativa['placa']}{prev}{desc}",
                    "livre_em": None}
    if servico and dia == tempo.hoje():
        ini = _dt(servico.get("inicio"))
        return {"status": "Em serviço", "detalhe": f"{servico.get('tipo') or 'serviço'} desde "
                                                  f"{ini:%d/%m %H:%M}" if ini else (servico.get("tipo") or ""),
                "livre_em": None}
    ij_ini, ij_fim = _dt((interj or {}).get("inicio")), _dt((interj or {}).get("fim_previsto"))
    if ij_ini and ij_fim and ij_ini <= quando < ij_fim:
        return {"status": "Interjornada",
                "detalhe": f"marcou no app {ij_ini:%d/%m %H:%M} · livre às {ij_fim:%H:%M} de {ij_fim:%d/%m}",
                "livre_em": ij_fim}
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
            repo.servicos_ativos(operacao_id), repo.interjornadas_op(operacao_id))


def agora(operacao_id: int) -> pd.DataFrame:
    """Situação de cada motorista neste momento."""
    mots, ult, ativas, ferias, serv, ij = _base(operacao_id)
    if mots.empty:
        return pd.DataFrame(columns=["id", "nome", "status", "detalhe", "livre_em"])
    now = tempo.agora()
    linhas = []
    for m in mots.to_dict("records"):
        s = situacao(m, now, ult.get(m["id"]), ativas.get(m["id"]), ferias, serv.get(m["id"]), ij.get(m["id"]))
        linhas.append({"id": m["id"], "nome": m["nome"], **s})
    return pd.DataFrame(linhas)


def grade(operacao_id: int) -> pd.DataFrame:
    """Uma linha por motorista e dia (hoje = agora; próximos dias = início do dia, com aviso se libera no dia)."""
    mots, ult, ativas, ferias, serv, ij = _base(operacao_id)
    if mots.empty:
        return pd.DataFrame(columns=["id", "nome", "data", "status", "detalhe", "livre_em"])
    now = tempo.agora()
    linhas = []
    for m in mots.to_dict("records"):
        for d in dias():
            quando = now if d == now.date() else dt.datetime.combine(d, dt.time(0, 0))
            s = situacao(m, quando, ult.get(m["id"]), ativas.get(m["id"]), ferias, serv.get(m["id"]), ij.get(m["id"]))
            # interjornada que acaba no próprio dia: o motorista fica disponível a partir da hora
            if d != now.date() and s["status"] == "Interjornada" and s["livre_em"] and s["livre_em"].date() == d:
                s = {**s, "status": "Disponível", "detalhe": f"a partir das {s['livre_em']:%H:%M} (interjornada)"}
            linhas.append({"id": m["id"], "nome": m["nome"], "data": d, **s})
    return pd.DataFrame(linhas)


def no_momento(operacao_id: int, motorista_id: int, quando: dt.datetime) -> dict:
    """Situação de um motorista num horário (usado no lançamento do pedido)."""
    mots, ult, ativas, ferias, serv, ij = _base(operacao_id)
    m = next((r for r in mots.to_dict("records") if r["id"] == motorista_id), None)
    if not m:
        return {"status": "Disponível", "detalhe": "", "livre_em": None}
    return situacao(m, quando, ult.get(motorista_id), ativas.get(motorista_id), ferias, serv.get(motorista_id),
                    ij.get(motorista_id))


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


# --- Interjornada marcada pelo motorista no app ----------------------------------------------
def iniciar_interjornada(motorista: dict) -> dict:
    """O motorista toca em 😴 Interjornada: começa agora e termina daqui a 11 h. A Puxada recebe o aviso."""
    from repositories import carreteiro_repo

    atual = repo.interjornada_atual(motorista["id"])
    agora_ = tempo.agora()
    if atual and _dt(atual["fim_previsto"]) and agora_ < _dt(atual["fim_previsto"]):
        raise RegraNegocioError(f"Você já está em interjornada até {_dt(atual['fim_previsto']):%d/%m %H:%M}.")
    serv = repo.servico_ativo(motorista["id"])
    if serv:  # descanso começa: o serviço avulso termina
        repo.encerrar_servico(serv["id"])
    viagem = carreteiro_repo.viagem_ativa_motorista(motorista["id"])
    fim = agora_ + dt.timedelta(hours=INTERJORNADA_H)
    repo.iniciar_interjornada(motorista["operacao_id"], motorista["id"], viagem["id"] if viagem else None,
                              agora_.strftime("%Y-%m-%d %H:%M:%S"), fim.strftime("%Y-%m-%d %H:%M:%S"))
    _avisar_puxada(motorista["operacao_id"], f"😴 {motorista['nome']} iniciou a interjornada",
                   f"Início {agora_:%d/%m %H:%M} · fim previsto {fim:%d/%m %H:%M}"
                   + (f" · em viagem (pedido {viagem['numero_pedido']}, placa {viagem['placa']})" if viagem else ""),
                   f"interj:{motorista['id']}:{agora_:%Y%m%d%H%M}")
    return {"inicio": agora_, "fim": fim}


def interjornada_do_motorista(motorista_id: int) -> dict | None:
    """{inicio, fim, ativa, concluida_ha_h} da última interjornada (para o app)."""
    r = repo.interjornada_atual(motorista_id)
    if not r:
        return None
    ini, fim = _dt(r["inicio"]), _dt(r["fim_previsto"])
    agora_ = tempo.agora()
    return {"inicio": ini, "fim": fim, "ativa": bool(ini and fim and ini <= agora_ < fim),
            "concluida_ha_h": (agora_ - fim).total_seconds() / 3600 if fim and agora_ >= fim else None}


_ULTIMA_VERIF = {"t": 0.0}


def verificar_interjornadas(forcar: bool = False) -> int:
    """Avisa a Puxada quando a interjornada termina (roda junto com os alertas, no máximo a cada 2 min)."""
    import time

    if not forcar and time.time() - _ULTIMA_VERIF["t"] < 120:
        return 0
    _ULTIMA_VERIF["t"] = time.time()
    n = 0
    for r in repo.interjornadas_a_avisar(tempo.agora().strftime("%Y-%m-%d %H:%M:%S")):
        fim = _dt(r["fim_previsto"])
        _avisar_puxada(r["operacao_id"], f"✅ {r['motorista']} concluiu a interjornada",
                       f"Livre desde {fim:%d/%m %H:%M} — disponível para nova viagem.", f"interjfim:{r['id']}")
        repo.marcar_interjornada_avisada(r["id"])
        n += 1
    return n


def _avisar_puxada(operacao_id: int, titulo: str, texto: str, chave: str) -> None:
    try:
        from config.settings import PERFIL_MOTORISTA
        from core.auth import pode_acessar_aba
        from repositories import usuarios_repo

        agora_ = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
        for u in usuarios_repo.listar(apenas_ativos=True):
            if u["perfil"] == PERFIL_MOTORISTA:
                continue
            sessao = usuarios_repo.carregar_sessao(u["id"])
            if operacao_id not in (sessao.get("operacoes") or [operacao_id]):
                continue
            if pode_acessar_aba(sessao, "puxada", "disp_motoristas") or pode_acessar_aba(sessao, "puxada", "carreteiro"):
                repo.criar_notificacao(u["id"], "interjornada", chave, titulo, texto, "puxada", agora_)
    except Exception:
        pass


# --- Fim da viagem: descanso obrigatório e bloqueio do acesso ao app -------------------------------
def apos_finalizar(v: dict) -> dt.datetime | None:
    """Ao tocar em ✅ Finalizar viagem: começa a interjornada de 11 h (a Puxada é avisada)."""
    fim_viagem = _dt(v.get("ts_fim"))
    if not fim_viagem:
        return None
    livre = fim_viagem + dt.timedelta(hours=INTERJORNADA_H)
    atual = repo.interjornada_atual(v["motorista_id"])
    if not (atual and _dt(atual["fim_previsto"]) and _dt(atual["fim_previsto"]) > fim_viagem):
        repo.iniciar_interjornada(v["operacao_id"], v["motorista_id"], v["id"],
                                  fim_viagem.strftime("%Y-%m-%d %H:%M:%S"), livre.strftime("%Y-%m-%d %H:%M:%S"))
    nome = v.get("motorista") or "Motorista"
    _avisar_puxada(v["operacao_id"], f"🏁 {nome} finalizou a viagem — interjornada",
                   f"Pedido {v.get('numero_pedido') or ''} · {v.get('placa') or ''}. Descanso até "
                   f"{livre:%d/%m %H:%M} (app bloqueado até lá).", f"fimviagem:{v['id']}")
    return livre


def bloqueio_acesso(motorista_id: int) -> dt.datetime | None:
    """Até quando o motorista não pode entrar no app (11 h após Finalizar viagem). None = liberado."""
    r = repo.ultima_finalizacao(motorista_id)
    if not r:
        return None
    fim = _dt(r["ts_fim"])
    if not fim:
        return None
    liberado = _dt(r.get("acesso_liberado_em"))
    if liberado and liberado >= fim:
        return None
    livre = fim + dt.timedelta(hours=INTERJORNADA_H)
    return livre if livre > tempo.agora() else None


def bloqueio_do_usuario(usuario: dict) -> dt.datetime | None:
    from config.settings import PERFIL_MOTORISTA
    from repositories import carreteiro_repo

    if not usuario or usuario.get("perfil") != PERFIL_MOTORISTA:
        return None
    mot = carreteiro_repo.motorista_do_usuario(usuario["id"])
    return bloqueio_acesso(mot["id"]) if mot else None


def liberar_acesso(motorista_id: int, usuario: str = "") -> None:
    """A Puxada libera o app antes das 11 h (ex.: finalizou a viagem por engano)."""
    repo.liberar_acesso(motorista_id, tempo.agora().strftime("%Y-%m-%d %H:%M:%S"))
