"""🚦 Farol de produtividade da frota própria.

Cada atividade da viagem é comparada com a meta (METAS_FAROL) e vira um farol:
🟢 ≥ 90% das ocorrências no tempo · 🟡 ≥ 75% · 🔴 abaixo (FAROL_FAIXAS).

Atividades medidas (todas a partir das etapas do App Carreteiro, dos pedidos da Puxada e do armazém):
  1. Apresentação na cervejaria dentro do agendamento
  2. Espera na cervejaria (apresentou → chamado)
  3. Carregamento (chamado → carregado)
  4. Ida até a fábrica (início → apresentou) vs deslocamento cadastrado + tolerância
  5. Volta até a revenda (saída cervejaria → chegada) vs deslocamento cadastrado + tolerância
  6. Chegada na revenda vs horário de descarga agendado
  7. Descarga (chegada → fim) vs tempo de doca do slot
  8. TMA — carreta parada na revenda até a próxima viagem
  9. Interjornada respeitada (11 h entre o fim de uma viagem e o início da próxima do motorista)
 10. Armazém finalizou o pedido antes do prazo de saída da carreta
 11. Carreta saiu da revenda até o prazo de saída
 12. Parada de manutenção em viagem
"""
import datetime as dt

import pandas as pd

from config.settings import FAROL_FAIXAS, INTERJORNADA_H, METAS_FAROL
from core import tempo
from repositories import carreteiro_repo, logistica_repo
from repositories import pedidos_puxada_repo as ped_repo
from services import carreteiro_service as car
from services import janelas_service as jsvc
from services import pedidos_puxada_service as ped_svc

COLUNAS = ["Data", "Motorista", "Placa", "Pedido", "Real", "Meta", "Excesso", "No tempo"]


def _txt(v) -> str:
    return "" if v is None or (isinstance(v, float) and v != v) or str(v) in ("None", "nan", "NaT", "<NA>") else str(v)


def dur(h) -> str:
    if h is None or (isinstance(h, float) and h != h):
        return "—"
    return car.formatar_duracao(float(h))


def farol(pct: float | None) -> tuple[str, str]:
    """(ícone, status do card)."""
    if pct is None:
        return "⚪", "neutro"
    if pct >= FAROL_FAIXAS[0]:
        return "🟢", "bom"
    if pct >= FAROL_FAIXAS[1]:
        return "🟡", "atencao"
    return "🔴", "critico"


def _item(data, mot, placa, pedido, real_h, meta_h, ok: bool, real_txt: str | None = None,
          meta_txt: str | None = None, minimo: bool = False) -> dict:
    """minimo=True: a meta é um mínimo (ex.: descanso) — o 'excesso' vira o que faltou."""
    exc = None
    if real_h is not None and meta_h is not None and not ok:
        exc = (meta_h - real_h) if minimo else (real_h - meta_h)
    d = pd.Timestamp(data) if data is not None and not (isinstance(data, float) and data != data) else None
    return {"Data": d.strftime("%d/%m/%Y %H:%M") if d is not None and not pd.isna(d) else "—",
            "_ts": d, "Motorista": _txt(mot) or "—", "Placa": _txt(placa) or "—", "Pedido": _txt(pedido) or "—",
            "Real": real_txt if real_txt is not None else dur(real_h),
            "Meta": meta_txt if meta_txt is not None else dur(meta_h),
            "Excesso": (("faltou " if minimo else "") + dur(exc)) if exc is not None and exc > 0 else "", "No tempo": "✅" if ok else "❌", "_ok": ok}


def _atividade(chave: str, nome: str, icone: str, regra: str, itens: list[dict]) -> dict:
    df = pd.DataFrame(itens, columns=[*COLUNAS, "_ts", "_ok"]) if itens else pd.DataFrame(columns=[*COLUNAS, "_ts", "_ok"])
    total = len(df)
    ok = int(df["_ok"].sum()) if total else 0
    pct = ok / total * 100 if total else None
    return {"chave": chave, "nome": nome, "icone": icone, "regra": regra, "total": total, "ok": ok,
            "fora": total - ok, "pct": pct, "itens": df}


def _viagens(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    df = car.indicadores(operacao_id, de, ate)
    if df.empty:
        return df
    for c in ("desc_data", "desc_hora", "desc_tipo"):
        if c not in df:
            df[c] = None
    return df


def atividades(operacao_id: int, de: dt.date, ate: dt.date) -> list[dict]:
    m = METAS_FAROL
    v = _viagens(operacao_id, de.isoformat(), ate.isoformat())
    regs = v.to_dict("records") if not v.empty else []
    desloc_cache: dict = {}

    def desloc(r) -> float:
        chave = (int(r.get("operacao_id") or operacao_id), r.get("destino_id"))
        if chave not in desloc_cache:
            try:
                fid = int(r["destino_id"]) if _txt(r.get("destino_id")) else None
            except (TypeError, ValueError):
                fid = None
            desloc_cache[chave] = logistica_repo.deslocamento_h(chave[0], fid) if fid else 0.0
        return desloc_cache[chave]

    def ok_num(x) -> bool:
        return x is not None and not (isinstance(x, float) and x != x) and not pd.isna(x)

    saida = []
    # 1. Apresentação no prazo
    it = []
    for r in regs:
        if ok_num(r.get("apresentou_no_prazo")):
            atraso = float(r.get("atraso_min") or 0)
            it.append(_item(r["ts_apresentado"], r["motorista"], r["placa"], r["numero_pedido"],
                            max(atraso, 0) / 60, 0, bool(int(r["apresentou_no_prazo"])),
                            real_txt="no horário" if atraso <= 0 else f"{dur(atraso / 60)} de atraso",
                            meta_txt="até o agendamento"))
    saida.append(_atividade("apresentacao", "Apresentação no agendamento", "🏭",
                            "Chegar na cervejaria até o horário agendado (com a tolerância do app).", it))

    # 2 e 3. Espera e carregamento
    for chave, col, nome, icone, meta in (("espera", "espera_h", "Espera na cervejaria", "⏳", m["espera_h"]),
                                          ("carregamento", "carregamento_h", "Carregamento", "📦", m["carregamento_h"])):
        it = [_item(r["ts_apresentado"] if chave == "espera" else r["ts_chamado"], r["motorista"], r["placa"],
                    r["numero_pedido"], r[col], meta, r[col] <= meta) for r in regs if ok_num(r.get(col))]
        saida.append(_atividade(chave, nome, icone, f"Até {dur(meta)}.", it))

    # 4 e 5. Ida e volta vs deslocamento cadastrado
    tol = 1 + m["tolerancia_trecho"]
    for chave, col, nome, icone, ts in (("ida", "ida_h", "Ida até a fábrica", "🛣️", "ts_inicio"),
                                        ("volta", "volta_h", "Volta até a revenda", "🔙", "ts_saida_cervejaria")):
        it = []
        for r in regs:
            base = desloc(r)
            if ok_num(r.get(col)) and base > 0:
                meta = base * tol
                it.append(_item(r[ts], r["motorista"], r["placa"], r["numero_pedido"], r[col], meta, r[col] <= meta))
        saida.append(_atividade(chave, nome, icone, f"Deslocamento cadastrado da fábrica + "
                                f"{m['tolerancia_trecho'] * 100:.0f}% de tolerância.", it))

    # 6. Chegada vs descarga agendada  ·  7. Descarga vs tempo de doca
    it6, it7 = [], []
    tol_ch = m["tolerancia_chegada_min"] / 60
    for r in regs:
        chegada = r.get("ts_chegada_revenda")
        if not ok_num(chegada):
            continue
        ag = None
        if _txt(r.get("desc_data")) and _txt(r.get("desc_hora")):
            try:
                ag = dt.datetime.combine(dt.date.fromisoformat(_txt(r["desc_data"])[:10]),
                                         dt.datetime.strptime(_txt(r["desc_hora"])[:5], "%H:%M").time())
                atraso = (pd.Timestamp(chegada).to_pydatetime() - ag).total_seconds() / 3600
                it6.append(_item(chegada, r["motorista"], r["placa"], r["numero_pedido"], max(atraso, 0), tol_ch,
                                 atraso <= tol_ch, real_txt="no horário" if atraso <= 0 else f"{dur(atraso)} depois",
                                 meta_txt=f"até {dur(tol_ch)} depois de {ag:%H:%M}"))
            except ValueError:
                pass
        if ok_num(r.get("ts_fim")):
            # a descarga começa no horário agendado (ou na chegada, se chegou depois)
            ch = pd.Timestamp(chegada).to_pydatetime()
            ini = max(ch, ag) if ag else ch
            real = (pd.Timestamp(r["ts_fim"]).to_pydatetime() - ini).total_seconds() / 3600
            meta = jsvc.duracao_em(int(r.get("operacao_id") or operacao_id), ag or ch,
                                   _txt(r.get("desc_tipo")) or None) / 60
            it7.append(_item(ini, r["motorista"], r["placa"], r["numero_pedido"], max(real, 0), meta, real <= meta))
    saida.append(_atividade("chegada", "Chegada no horário da descarga", "🕒",
                            f"Chegar na revenda até {m['tolerancia_chegada_min']} min depois do horário agendado.", it6))
    saida.append(_atividade("descarga", "Descarga na doca", "🅿️",
                            "Do horário agendado (ou da chegada, se chegou depois) ao fim da viagem dentro do tempo de "
                            "doca do slot (descartável/retornável).", it7))

    # 8. TMA
    it = [_item(r["ts_chegada_revenda"], r["motorista"], r["placa"], r["numero_pedido"], r["tma_h"], m["tma_h"],
                r["tma_h"] <= m["tma_h"]) for r in regs if ok_num(r.get("tma_h"))]
    saida.append(_atividade("tma", "TMA na revenda", "🔁",
                            f"Carreta parada na revenda até a próxima viagem em até {dur(m['tma_h'])}.", it))

    # 9. Interjornada
    it = []
    if regs:
        por_mot = v.dropna(subset=["ts_inicio"]).sort_values("ts_inicio").groupby("motorista_id")
        for _, g in por_mot:
            linhas = g.to_dict("records")
            for ant, prox in zip(linhas, linhas[1:]):
                if not ok_num(ant.get("ts_fim")):
                    continue
                folga = (prox["ts_inicio"] - ant["ts_fim"]).total_seconds() / 3600
                it.append(_item(prox["ts_inicio"], prox["motorista"], prox["placa"], prox["numero_pedido"],
                                folga, INTERJORNADA_H, folga >= INTERJORNADA_H, real_txt=f"{dur(folga)} de descanso",
                                meta_txt=f"mín. {INTERJORNADA_H} h", minimo=True))
    saida.append(_atividade("interjornada", "Interjornada respeitada", "😴",
                            f"Pelo menos {INTERJORNADA_H} h entre o fim de uma viagem e o início da próxima.", it))

    # 10 e 11. Pedidos: armazém e saída da revenda
    peds = ped_repo.pedidos_df(operacao_id, de.isoformat(), ate.isoformat())
    agora = tempo.agora()
    it10, it11 = [], []
    viagens_ini = {int(r["id"]): r for r in regs}
    if not peds.empty:
        for p in peds.to_dict("records"):
            if p["status"] in ("Cancelado", "Reprogramado"):
                continue
            pz = ped_svc.prazo_saida(p)
            if not pz:
                continue
            fin = tempo.parse_dt(p["finalizado_em"]) if _txt(p.get("finalizado_em")) else None
            mot = p.get("motorista")
            if fin:
                atraso = (fin - pz).total_seconds() / 3600
                it10.append(_item(fin, mot, p["placa"], p["numero_pedido"], max(atraso, 0), 0, atraso <= 0,
                                  real_txt=f"finalizado {fin:%d/%m %H:%M}", meta_txt=f"até {pz:%d/%m %H:%M}"))
            elif pz < agora:
                it10.append(_item(pz, mot, p["placa"], p["numero_pedido"], (agora - pz).total_seconds() / 3600, 0,
                                  False, real_txt="não finalizado", meta_txt=f"até {pz:%d/%m %H:%M}"))
            vid = p.get("viagem_id")
            vg = viagens_ini.get(int(vid)) if _txt(vid) else None
            if vg is not None and ok_num(vg.get("ts_inicio")):
                saiu = pd.Timestamp(vg["ts_inicio"]).to_pydatetime()
                atraso = (saiu - pz).total_seconds() / 3600
                it11.append(_item(saiu, mot, p["placa"], p["numero_pedido"], max(atraso, 0), 0, atraso <= 0,
                                  real_txt=f"saiu {saiu:%d/%m %H:%M}", meta_txt=f"até {pz:%d/%m %H:%M}"))
    saida.append(_atividade("armazem", "Armazém finalizou no prazo", "🏬",
                            "Pedido finalizado pelo armazém antes do prazo de saída da carreta "
                            "(agendamento na fábrica − deslocamento).", it10))
    saida.append(_atividade("saida", "Saída da revenda no prazo", "🚦",
                            "Viagem iniciada no app até o prazo de saída do pedido.", it11))

    # 12. Paradas de manutenção
    it = []
    if regs:
        par = carreteiro_repo.paradas_df([int(r["id"]) for r in regs])
        for p in par.to_dict("records"):
            if not _txt(p.get("fim")):
                continue
            h = (tempo.parse_dt(p["fim"]) - tempo.parse_dt(p["inicio"])).total_seconds() / 3600
            it.append(_item(p["inicio"], p["motorista"], p["placa"], p["numero_pedido"], h,
                            m["parada_manutencao_h"], h <= m["parada_manutencao_h"]))
    saida.append(_atividade("parada", "Parada de manutenção", "🔧",
                            f"Parada em viagem resolvida em até {dur(m['parada_manutencao_h'])}.", it))
    return saida


def geral(ativs: list[dict]) -> dict:
    total = sum(a["total"] for a in ativs)
    ok = sum(a["ok"] for a in ativs)
    return {"total": total, "ok": ok, "fora": total - ok, "pct": ok / total * 100 if total else None}


def fora_do_tempo(ativs: list[dict]) -> pd.DataFrame:
    partes = []
    for a in ativs:
        f = a["itens"]
        f = f[~f["_ok"].astype(bool)] if not f.empty else f
        if not f.empty:
            partes.append(f.assign(Atividade=f"{a['icone']} {a['nome']}"))
    if not partes:
        return pd.DataFrame(columns=["Atividade", *COLUNAS])
    df = pd.concat(partes, ignore_index=True).sort_values("_ts", ascending=False, na_position="last")
    return df[["Atividade", "Data", "Motorista", "Placa", "Pedido", "Real", "Meta", "Excesso"]].reset_index(drop=True)


def por_motorista(ativs: list[dict]) -> pd.DataFrame:
    """% no tempo de cada motorista em cada atividade (e no geral)."""
    linhas: dict = {}
    for a in ativs:
        f = a["itens"]
        if f.empty:
            continue
        for mot, g in f.groupby("Motorista"):
            d = linhas.setdefault(mot, {"Motorista": mot, "_ok": 0, "_tot": 0})
            ok, tot = int(g["_ok"].sum()), len(g)
            d[f"{a['icone']} {a['nome']}"] = f"{farol(ok / tot * 100)[0]} {ok / tot * 100:.0f}% ({ok}/{tot})"
            d["_ok"] += ok
            d["_tot"] += tot
    if not linhas:
        return pd.DataFrame()
    df = pd.DataFrame(list(linhas.values()))
    df["_pct"] = df["_ok"] / df["_tot"] * 100
    df.insert(1, "Geral", [f"{farol(p)[0]} {p:.0f}%" for p in df["_pct"]])
    df.insert(2, "Fora do tempo", df["_tot"] - df["_ok"])
    return df.sort_values("_pct").drop(columns=["_ok", "_tot", "_pct"]).fillna("—").reset_index(drop=True)
