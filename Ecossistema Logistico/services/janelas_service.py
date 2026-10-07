"""Slots de descarga da revenda — linha do tempo da doca.

Cada PERÍODO cadastrado diz quanto tempo uma descarga ocupa a doca, conforme o produto:
    20:00 → 02:00  ·  Descartável 1h30  ·  Retornável 2h30
    02:00 → 20:00  ·  Descartável 1h00  ·  Retornável 2h00
(o período pode virar a meia-noite: fim menor que o início).

A doca é UMA linha do tempo: quando um retornável é agendado ele ocupa o horário também para o
descartável (não dá para fazer os dois ao mesmo tempo). "Docas" = quantas descargas simultâneas
cabem (padrão 1). Um horário de início está livre quando a descarga inteira (início + duração do
produto) não encosta em nenhuma outra já agendada. Os horários são oferecidos de 30 em 30 minutos.

Cancelado e No-show liberam o horário. Sem períodos cadastrados, o motorista informa a hora livre.
"""
import datetime as dt
import re

from core import tempo
from repositories import logistica_repo as repo
from services.erros import RegraNegocioError

DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_PADRAO = list(range(7))
PASSO_MIN = 30
# Padrão pedido pela operação (pode ser alterado em 🕒 Slots de descarga)
PERIODOS_PADRAO = [("20:00", "02:00", 90, 150), ("02:00", "20:00", 60, 120)]


# --- Utilidades ----------------------------------------------------------------------------
def _hora(txt, nome: str) -> str:
    if isinstance(txt, dt.time):
        return f"{txt:%H:%M}"
    t = str(txt or "").strip().replace("h", ":").replace(".", ":")
    if re.fullmatch(r"\d{1,2}", t):
        t += ":00"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise RegraNegocioError(f"{nome} inválida. Use HH:MM (ex.: 08:00).")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _min(hhmm: str) -> int:
    h, m = str(hhmm)[:5].split(":")
    return int(h) * 60 + int(m)


def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() in ("", "None", "nan", "NaT")


def dias_lista(dias: str | None) -> list[int]:
    return sorted({int(x) for x in str(dias or "").split(",") if x.strip().isdigit() and int(x) <= 6})


def dias_texto(dias: str | None) -> str:
    d = dias_lista(dias)
    if d == list(range(7)):
        return "Todos os dias"
    if d == list(range(5)):
        return "Seg a Sex"
    if d == list(range(6)):
        return "Seg a Sáb"
    return ", ".join(DIAS[i] for i in d) or "—"


def dur_txt(minutos) -> str:
    m = int(minutos or 0)
    return f"{m // 60}h{m % 60:02d}" if m % 60 else f"{m // 60}h"


def rotulo(j: dict) -> str:
    return f"{j['hora_inicio']}–{j['hora_fim']}"


def _dur(p: dict, produto: str | None) -> int:
    """Minutos que a descarga ocupa a doca. Retornável/Misto usam o tempo do retornável."""
    desc = int(p.get("dur_desc_min") or 60)
    ret = int(p.get("dur_ret_min") or 120)
    return desc if produto == "Descartável" else ret if produto in ("Retornável", "Misto") else desc


def _cobertura(p: dict) -> set[int]:
    """Minutos da semana (0..10079) cobertos pelo período, a partir do dia em que ele começa."""
    ini, fim = _min(p["hora_inicio"]), _min(p["hora_fim"])
    dur = (fim - ini) % 1440 or 1440
    saida = set()
    for d in dias_lista(p["dias"]):
        base = d * 1440 + ini
        saida.update((base + k) % 10080 for k in range(dur))
    return saida


def periodos(operacao_id: int) -> list[dict]:
    return repo.janelas(operacao_id)


def tem_janelas(operacao_id: int) -> bool:
    return bool(periodos(operacao_id))


def _mapa(ps: list[dict]) -> dict[int, dict]:
    mapa: dict[int, dict] = {}
    for p in ps:
        for m in _cobertura(p):
            mapa.setdefault(m, p)
    return mapa


def periodo_em(ps: list[dict], quando: dt.datetime, mapa: dict | None = None) -> dict | None:
    """Período que cobre o instante (considera período que vira a meia-noite)."""
    alvo = quando.weekday() * 1440 + quando.hour * 60 + quando.minute
    if mapa is not None:
        return mapa.get(alvo)
    for p in ps:
        if alvo in _cobertura(p):
            return p
    return None


# --- Cadastro -------------------------------------------------------------------------------
def salvar_janela(operacao_id: int, jid: int | None, inicio, fim, docas, dias: list[int], dur_desc, dur_ret,
                  ativo: bool = True) -> None:
    ini, fi = _hora(inicio, "Hora de início"), _hora(fim, "Hora de fim")
    if ini == fi:
        raise RegraNegocioError("Início e fim do período não podem ser iguais.")
    try:
        n, dd, dr = int(float(docas or 1)), int(float(dur_desc or 0)), int(float(dur_ret or 0))
    except (TypeError, ValueError):
        raise RegraNegocioError("Valores inválidos.")
    if n < 1:
        raise RegraNegocioError("Informe pelo menos 1 doca.")
    if dd < 15 or dr < 15:
        raise RegraNegocioError("Informe o tempo de descarga do descartável e do retornável (em minutos).")
    dias = sorted({int(d) for d in (dias or [])})
    if not dias:
        raise RegraNegocioError("Escolha pelo menos um dia da semana.")
    novo = {"hora_inicio": ini, "hora_fim": fi, "dias": ",".join(map(str, dias))}
    if ativo:
        cob = _cobertura(novo)
        for p in periodos(operacao_id):
            if p["id"] != jid and cob & _cobertura(p):
                raise RegraNegocioError(f"Este período encosta no período {rotulo(p)} ({dias_texto(p['dias'])}).")
    repo.salvar_janela(operacao_id, jid, ini, fi, n, novo["dias"], None, ativo, dd, dr)


def criar_padrao(operacao_id: int) -> None:
    """Sobe os períodos padrão (pausa os antigos)."""
    for p in repo.janelas(operacao_id, apenas_ativas=False):
        if p.get("ativo"):
            repo.salvar_janela(operacao_id, p["id"], p["hora_inicio"], p["hora_fim"], p["slots"], p["dias"],
                               None, False, p.get("dur_desc_min"), p.get("dur_ret_min"))
    for ini, fim, dd, dr in PERIODOS_PADRAO:
        repo.salvar_janela(operacao_id, None, ini, fim, 1, ",".join(map(str, DIAS_PADRAO)), None, True, dd, dr)


# --- Ocupação da doca -----------------------------------------------------------------------
def _ocupacoes(operacao_id: int, data: dt.date, ps: list[dict], ignorar_viagem=None,
               ignorar_agendamento=None, mapa: dict | None = None) -> list[tuple[dt.datetime, dt.datetime, dict]]:
    """Descargas agendadas de ontem a amanhã (as da noite anterior podem invadir a madrugada)."""
    mapa = mapa if mapa is not None else _mapa(ps)
    saida = []
    for d in (data - dt.timedelta(days=1), data, data + dt.timedelta(days=1)):
        for a in repo.agendamentos_ativos_dia(operacao_id, d.isoformat()):
            if (ignorar_viagem and a.get("viagem_id") == ignorar_viagem) or (
                    ignorar_agendamento and a["id"] == ignorar_agendamento) or _vazio(a.get("hora")):
                continue
            try:
                ini = dt.datetime.combine(d, dt.datetime.strptime(str(a["hora"])[:5], "%H:%M").time())
            except ValueError:
                continue
            p = periodo_em(ps, ini, mapa) or {}
            saida.append((ini, ini + dt.timedelta(minutes=_dur(p, a.get("tipo_carga"))), a))
    return saida


def horarios(operacao_id: int, data: dt.date, produto: str | None, ignorar_viagem: int | None = None,
             ignorar_agendamento: int | None = None) -> list[dict]:
    """Todos os inícios possíveis do dia (de 30 em 30 min) para o produto, com livre/ocupado."""
    ps = periodos(operacao_id)
    if not ps:
        return []
    mapa = _mapa(ps)
    ocup = _ocupacoes(operacao_id, data, ps, ignorar_viagem, ignorar_agendamento, mapa)
    agora = tempo.agora()
    saida = []
    for k in range(0, 1440, PASSO_MIN):
        ini = dt.datetime.combine(data, dt.time(k // 60, k % 60))
        p = periodo_em(ps, ini, mapa)
        if not p:
            continue
        fim = ini + dt.timedelta(minutes=_dur(p, produto))
        choques = [o for o in ocup if o[0] < fim and ini < o[1]]
        livre = len(choques) < int(p.get("slots") or 1)
        saida.append({"hora": ini.strftime("%H:%M"), "inicio": ini, "fim": fim, "periodo": p, "livre": livre,
                      "passou": ini < agora, "choques": choques,
                      "rotulo": f"{ini:%H:%M} → {fim:%H:%M}{' (+1 dia)' if fim.date() > data else ''}"})
    return saida


def horarios_livres(operacao_id: int, data: dt.date, produto: str | None, **ign) -> list[dict]:
    return [h for h in horarios(operacao_id, data, produto, **ign) if h["livre"] and not h["passou"]]


def validar_reserva(operacao_id: int, data: dt.date, hora, produto: str | None, ignorar_viagem: int | None = None,
                    ignorar_agendamento: int | None = None) -> dict:
    """Confere se o horário ainda está livre para o produto; devolve o horário (com o período)."""
    if _vazio(hora):
        raise RegraNegocioError("Escolha o horário da descarga.")
    h = _hora(hora, "Horário")
    hs = {x["hora"]: x for x in horarios(operacao_id, data, produto, ignorar_viagem, ignorar_agendamento)}
    x = hs.get(h)
    if not x:
        raise RegraNegocioError(f"A revenda não recebe descarga às {h} de {data:%d/%m}. Escolha outro horário.")
    if x["passou"]:
        raise RegraNegocioError(f"O horário {h} de hoje já passou. Escolha outro.")
    if not x["livre"]:
        raise RegraNegocioError(f"O horário {x['rotulo']} acabou de ser ocupado. Escolha outro horário.")
    return x


def resumo_dia(operacao_id: int, data: dt.date) -> dict:
    """Quantos inícios livres ainda existem para cada produto e quantas descargas ocupam a doca."""
    desc = horarios_livres(operacao_id, data, "Descartável")
    ret = horarios_livres(operacao_id, data, "Retornável")
    ocup = [o for o in _ocupacoes(operacao_id, data, periodos(operacao_id)) if o[0].date() == data]
    return {"livres_desc": len(desc), "livres_ret": len(ret), "ocupados": len(ocup),
            "prox_desc": desc[0]["hora"] if desc else None, "prox_ret": ret[0]["hora"] if ret else None}


def janela_de_agendamento(js: list[dict], data, hora, janela_id=None, produto: str | None = None) -> str:
    """'20:00–21:30' de uma descarga (início + duração do produto no período)."""
    if _vazio(data) or _vazio(hora):
        return ""
    try:
        ini = dt.datetime.combine(dt.date.fromisoformat(str(data)[:10]),
                                  dt.datetime.strptime(str(hora)[:5], "%H:%M").time())
    except ValueError:
        return ""
    p = periodo_em([x for x in js if x.get("ativo", 1)], ini) or periodo_em(js, ini)
    if not p:
        return ""
    return f"{ini:%H:%M}–{ini + dt.timedelta(minutes=_dur(p, produto)):%H:%M}"
