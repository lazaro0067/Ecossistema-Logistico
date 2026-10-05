"""Janelas de descarga da revenda (horários em que o pátio recebe carretas) e os slots de cada uma.

  • Cada janela tem início, fim, quantidade de slots (carretas que cabem no intervalo), os dias da
    semana em que vale e, se quiser, o produto (Retornável / Descartável) — vazio = qualquer produto.
  • Uma vaga é consumida por cada descarga do dia na janela (do App Carreteiro ou lançada à mão).
    Cancelado e No-show liberam a vaga.
  • Descarga lançada sem janela conta na janela cujo horário contém a hora agendada.
  • Sem janelas cadastradas na filial, o motorista informa a hora livremente (como antes).
"""
import datetime as dt
import re

from core import tempo
from repositories import logistica_repo as repo
from services.erros import RegraNegocioError

DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_PADRAO = [0, 1, 2, 3, 4, 5]


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


def rotulo(j: dict) -> str:
    return f"{j['hora_inicio']}–{j['hora_fim']}"


def salvar_janela(operacao_id: int, jid: int | None, inicio, fim, slots, dias: list[int], produto: str | None,
                  ativo: bool = True) -> None:
    ini, fim = _hora(inicio, "Hora de início"), _hora(fim, "Hora de fim")
    if fim <= ini:
        raise RegraNegocioError("A hora de fim precisa ser depois da hora de início.")
    try:
        n = int(float(slots or 0))
    except (TypeError, ValueError):
        n = 0
    if n < 1:
        raise RegraNegocioError("Informe pelo menos 1 slot (carreta) na janela.")
    dias = sorted({int(d) for d in (dias or [])})
    if not dias:
        raise RegraNegocioError("Escolha pelo menos um dia da semana.")
    for j in repo.janelas(operacao_id):
        if j["id"] == jid or not (set(dias) & set(dias_lista(j["dias"]))):
            continue
        if (produto or None) != (j.get("produto") or None) and produto and j.get("produto"):
            continue  # janelas de produtos diferentes podem ter o mesmo horário
        if ini < j["hora_fim"] and j["hora_inicio"] < fim:
            raise RegraNegocioError(f"Este horário encosta na janela {rotulo(j)} ({dias_texto(j['dias'])}). "
                                    "Aumente os slots dela ou ajuste os horários.")
    repo.salvar_janela(operacao_id, jid, ini, fim, n, ",".join(map(str, dias)), produto or None, ativo)


def tem_janelas(operacao_id: int) -> bool:
    return bool(repo.janelas(operacao_id))


def _janela_da_hora(janelas: list[dict], hora: str | None) -> dict | None:
    if not hora:
        return None
    return next((j for j in janelas if j["hora_inicio"] <= hora[:5] < j["hora_fim"]), None)


def janelas_do_dia(operacao_id: int, data: dt.date, produto: str | None = None,
                   ignorar_viagem: int | None = None, ignorar_agendamento: int | None = None) -> list[dict]:
    """Janelas válidas no dia com vagas usadas/livres. `produto` filtra as janelas que aceitam o produto."""
    todas = [j for j in repo.janelas(operacao_id) if data.weekday() in dias_lista(j["dias"])]
    uso: dict[int, int] = {j["id"]: 0 for j in todas}
    ids = set(uso)
    for a in repo.agendamentos_ativos_dia(operacao_id, data.isoformat()):
        if (ignorar_viagem and a.get("viagem_id") == ignorar_viagem) or (
                ignorar_agendamento and a["id"] == ignorar_agendamento):
            continue
        jid = a.get("janela_id") if a.get("janela_id") in ids else None
        if jid is None:
            candidatas = [j for j in todas if j["hora_inicio"] <= (a.get("hora") or "")[:5] < j["hora_fim"]]
            prod = [j for j in candidatas if j.get("produto") and j["produto"] == a.get("tipo_carga")]
            j = (prod or candidatas or [None])[0]
            jid = j["id"] if j else None
        if jid is not None:
            uso[jid] += 1
    agora = tempo.agora()
    saida = []
    for j in todas:
        if produto and j.get("produto") and j["produto"] != produto:
            continue
        usados = uso[j["id"]]
        passou = data == agora.date() and j["hora_fim"] <= agora.strftime("%H:%M")
        saida.append({**j, "rotulo": rotulo(j), "usados": usados, "livres": max(int(j["slots"]) - usados, 0),
                      "passou": passou})
    return saida


def validar_reserva(operacao_id: int, data: dt.date, janela_id: int | None, produto: str | None,
                    ignorar_viagem: int | None = None, ignorar_agendamento: int | None = None) -> dict:
    """Confere se ainda há vaga na janela escolhida; devolve a janela."""
    if not janela_id:
        raise RegraNegocioError("Escolha uma janela de descarga.")
    js = janelas_do_dia(operacao_id, data, None, ignorar_viagem, ignorar_agendamento)
    j = next((x for x in js if x["id"] == int(janela_id)), None)
    if not j:
        raise RegraNegocioError("Essa janela não recebe descarga neste dia. Escolha outra.")
    if produto and j.get("produto") and j["produto"] != produto:
        raise RegraNegocioError(f"A janela {j['rotulo']} é só para {j['produto']}.")
    if j["passou"]:
        raise RegraNegocioError(f"A janela {j['rotulo']} de hoje já passou. Escolha outra.")
    if j["livres"] <= 0:
        raise RegraNegocioError(f"A janela {j['rotulo']} acabou de lotar. Escolha outra janela.")
    return j


def janela_de_agendamento(js: list[dict], data: str, hora: str | None, janela_id: int | None) -> str:
    """Rótulo da janela de uma descarga (pela janela gravada ou pela hora). js = repo.janelas(op, False)."""
    j = next((x for x in js if x["id"] == janela_id), None) if janela_id else None
    if not j and data:
        try:
            d = dt.date.fromisoformat(str(data)[:10])
            j = _janela_da_hora([x for x in js if d.weekday() in dias_lista(x["dias"])], hora)
        except ValueError:
            j = None
    return rotulo(j) if j else ""
