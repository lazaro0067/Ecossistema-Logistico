"""Pátio / Descarga: o que cada carreta faz DEPOIS de descarregar.

Para cada descarga agendada o armazém vê:
  • 📦 o próximo pedido que a Puxada já lançou para a mesma placa (o que vai carregar);
  • 🔧 a manutenção programada para a placa (no dia da descarga ou no seguinte);
  • ⭐ se o pedido ou a manutenção foi marcado como prioridade.
"""
import datetime as dt

import pandas as pd

from repositories import manutencao_repo
from repositories import pedidos_puxada_repo as ped_repo
from services import pedidos_puxada_service as ped_svc


def _txt(v) -> str:
    return "" if v is None or (isinstance(v, float) and v != v) or str(v) in ("None", "nan", "NaT", "<NA>") else str(v)


def _inicio(r: dict) -> dt.datetime | None:
    try:
        return dt.datetime.combine(dt.date.fromisoformat(_txt(r.get("data"))[:10]),
                                   dt.datetime.strptime(_txt(r.get("hora"))[:5], "%H:%M").time())
    except ValueError:
        return None


def enriquecer(operacao_id: int, regs: list[dict]) -> list[dict]:
    """Acrescenta _depois (pedido), _manut (manutenção) e _prio (bool) em cada agendamento."""
    if not regs:
        return regs
    datas = sorted(_txt(r.get("data"))[:10] for r in regs if _txt(r.get("data")))
    de = datas[0] if datas else None
    try:
        peds = ped_repo.pedidos_df(operacao_id, de, None, apenas_abertos=True)
    except Exception:
        peds = pd.DataFrame()
    pedidos = peds.to_dict("records") if not peds.empty else []
    manuts: dict = {}
    for r in regs:
        op = int(r.get("operacao_id") or operacao_id)
        placa = _txt(r.get("placa")).upper()
        data = _txt(r.get("data"))[:10]
        ini = _inicio(r)
        atual = set(ped_repo.numeros(r.get("pedido_app")))
        cand = []
        for p in pedidos:
            if _txt(p.get("placa")).upper() != placa or int(p.get("operacao_id") or op) != op:
                continue
            if ped_svc._v(p.get("viagem_id")) or atual & set(ped_repo.numeros(p.get("numero_pedido"))):
                continue
            if _txt(p.get("data"))[:10] < data:
                continue
            ag = ped_svc.agendamento_dt(p)
            if ag and ini and ag < ini:
                continue
            cand.append(p)
        cand.sort(key=lambda p: (ped_svc.agendamento_dt(p) or dt.datetime.max, p["id"]))
        r["_depois"] = cand[0] if cand else None
        chave = (op, placa, data)
        if chave not in manuts:
            fim = (dt.date.fromisoformat(data) + dt.timedelta(days=1)).isoformat() if data else ""
            ms = [m for m in manutencao_repo.ativas_da_placa(op, placa, data) if m["data"] <= fim] if data else []
            manuts[chave] = ms[0] if ms else None
        r["_manut"] = manuts[chave]
        r["_prio"] = bool((r["_depois"] and ped_svc.e_prioritario(r["_depois"]))
                          or (r["_manut"] and ped_svc._v(r["_manut"].get("prioridade"))))
    return regs


def depois_txt(p: dict | None) -> str:
    if not p:
        return ""
    pz = ped_svc.prazo_saida(p)
    ag = ped_svc.agendamento_dt(p)
    partes = [f"Ped. {p['numero_pedido']}", p.get("tipo") or "", ped_svc.composicao(p)]
    if _txt(p.get("fabrica")):
        partes.append(f"🏭 {p['fabrica']}")
    if ag:
        partes.append(f"fábrica {ag:%d/%m} {ped_svc.janela_txt(p)}")
    if pz:
        partes.append(f"🚦 sair até {pz:%d/%m %H:%M}")
    return " · ".join(x for x in partes if x)


def manut_txt(m: dict | None) -> str:
    if not m:
        return ""
    d = dt.date.fromisoformat(str(m["data"])[:10])
    partes = [f"{d:%d/%m}{' ' + _txt(m.get('hora')) if _txt(m.get('hora')) else ''}", _txt(m.get("tipo")),
              _txt(m.get("descricao")), f"🏪 {m['oficina']}" if _txt(m.get("oficina")) else ""]
    return " · ".join(x for x in partes if x)


def tabela_depois(regs: list[dict]) -> pd.DataFrame:
    linhas = []
    for r in regs:
        if not (r.get("_depois") or r.get("_manut")):
            continue
        linhas.append({"Prioridade": "⭐" if r.get("_prio") else "", "Descarga": _txt(r.get("hora")) or "—",
                       "Placa": _txt(r.get("placa")), "Status": _txt(r.get("status")),
                       "Depois carrega": depois_txt(r.get("_depois")) or "—",
                       "Depois vai para manutenção": manut_txt(r.get("_manut")) or "—"})
    return pd.DataFrame(linhas)
