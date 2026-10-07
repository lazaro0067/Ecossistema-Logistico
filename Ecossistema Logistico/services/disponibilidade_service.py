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
        return pd.DataFrame(columns=["placa", "modelo", "perfil", "capacidade_hl", "data", "status", "sugestao",
                                     "observacao", "manual", "pedidos"])
    manual = logistica_repo.disponibilidade_df(operacao_id, ds[0].isoformat(), ds[-1].isoformat())
    manual = {(r["placa"], r["data"]): r for r in manual.to_dict("records")}
    from repositories import pedidos_puxada_repo

    peds = pedidos_puxada_repo.pedidos_df(operacao_id, ds[0].isoformat(), ds[-1].isoformat())
    pedidos: dict = {}
    if not peds.empty:
        from services.pedidos_puxada_service import janela_txt

        for r in peds[~peds["status"].isin(["Cancelado", "Reprogramado"])].to_dict("records"):
            slot = janela_txt(r)
            pedidos.setdefault((str(r["placa"]).upper(), r["data"]), []).append(
                f"{r['numero_pedido']} ({r['tipo']}){' 🕒 ' + slot if slot != '—' else ''}"
                f"{' ✅' if r['status'] == 'Finalizado' else ''}")
    em_manut = carreteiro_repo.paradas_ativas(operacao_id)
    prev = previsao_livre(operacao_id)
    from repositories import manutencao_repo

    manut_prog: dict = {}
    for m in manutencao_repo.lista_df(operacao_id, ds[0].isoformat(), ds[-1].isoformat(),
                                      ["Programada", "Em andamento"]).to_dict("records"):
        manut_prog.setdefault((str(m["placa"]).upper(), m["data"]), m)
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
            if v and v["id"] in em_manut and d == ds[0] and not eh_manual:
                obs = "🔧 parada p/ manutenção · " + obs
            pv = prev.get(placa)
            if pv and not eh_manual and status == "Indisponível Viagem" and d <= pv["livre_em"].date():
                obs = (obs + " · " if obs else "") + pv["texto"]
            elif pv and not eh_manual and d > pv["livre_em"].date() and status == "Disponível":
                obs = (obs + " · " if obs else "") + f"livre desde {pv['livre_em']:%d/%m %H:%M} (previsão)"
            mp = manut_prog.get((placa, d.isoformat()))
            if mp and not eh_manual:
                status = "Indisponível Frota"
                obs = (f"{'⭐ ' if mp.get('prioridade') else ''}🔧 manutenção programada: {mp.get('tipo') or ''}"
                       f"{' · ' + str(mp['descricao']) if isinstance(mp.get('descricao'), str) else ''}")
            ped = pedidos.get((placa, d.isoformat()), [])
            perfil = c.get("perfil") if isinstance(c.get("perfil"), str) and c.get("perfil") else "Sem perfil"
            linhas.append({"placa": c["placa"], "modelo": c.get("modelo"), "perfil": perfil,
                           "capacidade_hl": c.get("capacidade_hl"),
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


def resumo_por_perfil(g: pd.DataFrame, d) -> pd.DataFrame:
    """Disponibilidade do dia aberta por perfil do veículo (9 eixos / LS)."""
    from config.settings import PERFIS_VEICULO

    dia = g[g["data"] == d]
    if dia.empty:
        return pd.DataFrame()
    linhas = []
    for perfil, grupo in dia.groupby("perfil", sort=False):
        disp = grupo[grupo["status"] == "Disponível"]
        linhas.append({
            "perfil": perfil, "paletes": PERFIS_VEICULO.get(perfil),
            "total": len(grupo), "disponivel": len(disp),
            "retornavel": int((disp["sugestao"] == "Retornável").sum()),
            "descartavel": int((disp["sugestao"] == "Descartável").sum()),
            "sem_sugestao": int(disp["sugestao"].map(lambda v: not isinstance(v, str) or not v).sum()),
            "ind_frota": int((grupo["status"] == "Indisponível Frota").sum()),
            "ind_viagem": int((grupo["status"] == "Indisponível Viagem").sum()),
        })
    ordem = {p: i for i, p in enumerate(PERFIS_VEICULO)}
    return pd.DataFrame(linhas).sort_values("perfil", key=lambda s: s.map(lambda p: ordem.get(p, 99)))


def previsao_livre(operacao_id: int) -> dict[str, dict]:
    """Por placa em viagem: quando a carreta fica livre na revenda (chegada/descarga + tempo de doca).

    Base, em ordem: descarga agendada pelo motorista → chegada já registrada → previsão de chegada
    (saída da cervejaria + média dos retornos). Soma o tempo de doca do produto naquele horário."""
    from repositories import manutencao_repo
    from services import carreteiro_service, janelas_service

    saida: dict[str, dict] = {}
    viagens = carreteiro_repo.viagens_df(operacao_id)
    if viagens.empty:
        return saida
    for r in viagens[viagens["status"] == carreteiro_repo.EM_VIAGEM].to_dict("records"):
        v = carreteiro_repo.viagem(int(r["id"]))
        produto = v.get("desc_tipo")
        base, quando = None, None
        if v.get("ts_chegada_revenda"):
            quando, base = tempo.parse_dt(v["ts_chegada_revenda"]), "chegou"
            if v.get("desc_data") and v.get("desc_hora"):
                ag = tempo.parse_dt(f"{v['desc_data']} {v['desc_hora']}")
                if ag and quando and ag > quando:
                    quando, base = ag, "chegou · descarga agendada"
        elif v.get("desc_data") and v.get("desc_hora"):
            quando = tempo.parse_dt(f"{v['desc_data']} {v['desc_hora']}")
            base = "descarga agendada"
        else:
            quando = carreteiro_service.previsao_chegada(v)
            base = "previsão de chegada" if quando else None
        if not quando:
            continue
        minutos = janelas_service.duracao_em(operacao_id, quando, produto)
        livre = quando + dt.timedelta(minutes=minutos)
        manut = manutencao_repo.ativas_da_placa(operacao_id, v["placa"], quando.date().isoformat())
        manut = [m for m in manut if m["data"] <= (quando.date() + dt.timedelta(days=1)).isoformat()]
        saida[str(v["placa"]).upper()] = {
            "livre_em": livre, "base": base, "inicio_descarga": quando, "produto": produto, "viagem_id": v["id"],
            "motorista": v.get("motorista"), "manutencao": manut[0] if manut else None,
            "texto": (f"livre na revenda ~{livre:%d/%m %H:%M} ({base} {quando:%H:%M} + "
                      f"{janelas_service.dur_txt(minutos)} de descarga)")
                     + (" · depois vai p/ 🔧 manutenção" if manut else ""),
        }
    return saida
