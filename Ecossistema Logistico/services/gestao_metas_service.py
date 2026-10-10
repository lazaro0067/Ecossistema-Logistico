"""Ressuprimento › Gestão do dia e metas semanais.

• Dias de puxada do mês = todos os dias, menos os marcados como "sem puxada" pela filial.
• Meta semanal (base) = meta do mês dividida pelas semanas, na proporção dos dias de puxada de cada semana.
  O gestor pode "criticar" a semana com um percentual a mais (ou a menos): meta ajustada = base × (1 + %).
• Gestão do dia: quanto falta para a meta (do mês e da semana) dividido pelos dias de puxada que ainda restam.
• Tendência = real ÷ dias de puxada já realizados × dias de puxada do mês.
"""
import calendar
import datetime as dt

import pandas as pd

from core import tempo
from database.connection import execute, query_all
from repositories import ressuprimento_repo
from services.erros import RegraNegocioError

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


# --- Calendário de puxada ---------------------------------------------------------------------
def dias_do_mes(mes_ano: str) -> list[dt.date]:
    a, m = (int(x) for x in mes_ano.split("-"))
    return [dt.date(a, m, d) for d in range(1, calendar.monthrange(a, m)[1] + 1)]


def dias_sem_puxada(operacao_id: int, mes_ano: str) -> set[dt.date]:
    linhas = query_all("SELECT data FROM ressup_sem_puxada WHERE operacao_id = ? AND substr(data, 1, 7) = ?",
                       (operacao_id, mes_ano))
    return {dt.date.fromisoformat(str(r["data"])[:10]) for r in linhas}


def salvar_dias_sem_puxada(operacao_id: int, mes_ano: str, datas) -> None:
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial no menu para marcar os dias sem puxada.")
    validas = {d for d in (datas or []) if isinstance(d, dt.date) and d.strftime("%Y-%m") == mes_ano}
    if len(validas) >= len(dias_do_mes(mes_ano)):
        raise RegraNegocioError("Deixe pelo menos um dia de puxada no mês.")
    execute("DELETE FROM ressup_sem_puxada WHERE operacao_id = ? AND substr(data, 1, 7) = ?", (operacao_id, mes_ano))
    for d in sorted(validas):
        execute("INSERT INTO ressup_sem_puxada (operacao_id, data) VALUES (?, ?)", (operacao_id, d.isoformat()))


def dias_puxada(operacao_id: int, mes_ano: str) -> list[dt.date]:
    fora = dias_sem_puxada(operacao_id, mes_ano)
    return [d for d in dias_do_mes(mes_ano) if d not in fora]


def semanas(mes_ano: str) -> list[tuple[int, dt.date, dt.date]]:
    """(nº, início, fim) — semanas de segunda a domingo, cortadas no mês."""
    saida, atual = [], []
    for d in dias_do_mes(mes_ano):
        if atual and d.weekday() == 0:
            saida.append(atual)
            atual = []
        atual.append(d)
    if atual:
        saida.append(atual)
    return [(i + 1, s[0], s[-1]) for i, s in enumerate(saida)]


# --- Ajuste do gestor por semana --------------------------------------------------------------
def ajustes(operacao_id: int, mes_ano: str) -> dict[str, dict]:
    linhas = query_all("SELECT * FROM ressup_ajuste_semana WHERE operacao_id = ? AND mes_ano = ?",
                       (operacao_id, mes_ano))
    return {str(r["semana_ini"])[:10]: r for r in linhas}


def salvar_ajuste(operacao_id: int, mes_ano: str, semana_ini: dt.date, pct, observacao: str, usuario: str) -> None:
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial no menu para ajustar as metas semanais.")
    try:
        pct = float(pct or 0)
    except (TypeError, ValueError):
        raise RegraNegocioError("Percentual inválido.")
    if not -50 <= pct <= 100:
        raise RegraNegocioError("Use um percentual entre −50% e +100%.")
    execute("DELETE FROM ressup_ajuste_semana WHERE operacao_id = ? AND mes_ano = ? AND semana_ini = ?",
            (operacao_id, mes_ano, semana_ini.isoformat()))
    if pct or (observacao or "").strip():
        execute("""INSERT INTO ressup_ajuste_semana (operacao_id, mes_ano, semana_ini, ajuste_pct, observacao,
                   atualizado_por, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (operacao_id, mes_ano, semana_ini.isoformat(), pct, (observacao or "").strip() or None, usuario,
                 tempo.agora().strftime("%Y-%m-%d %H:%M")))


# --- Cálculos -----------------------------------------------------------------------------------
def _real_por_dia(operacao_id: int, mes_ano: str) -> pd.DataFrame:
    """data (date), cesta, dia (HL do dia, somando filiais)."""
    from services import ressuprimento_service

    d = ressuprimento_service.diario_normalizado(operacao_id, mes_ano)
    if d.empty:
        return pd.DataFrame(columns=["data", "cesta", "dia"])
    d = d[["data", "cesta", "dia"]].copy()
    d["data"] = d["data"].map(lambda x: dt.date.fromisoformat(str(x)[:10]))
    return d


def referencia(operacao_id: int, mes_ano: str, real: pd.DataFrame | None = None) -> dt.date | None:
    """Último dia já realizado: a última data com lançamento (no mês corrente, no máximo ontem/hoje)."""
    real = _real_por_dia(operacao_id, mes_ano) if real is None else real
    hoje = tempo.hoje()
    dias = dias_do_mes(mes_ano)
    if mes_ano < hoje.strftime("%Y-%m"):
        return dias[-1]
    if mes_ano > hoje.strftime("%Y-%m"):
        return None
    if real.empty:
        return None
    return min(max(real["data"]), hoje)


def fator_tendencia(operacao_id: int, mes_ano: str, ultima: dt.date | None) -> float:
    """Dias de puxada do mês ÷ dias de puxada até a última data com dado."""
    dp = dias_puxada(operacao_id, mes_ano)
    if not ultima or not dp:
        return 1.0
    feitos = sum(1 for d in dp if d <= ultima)
    return len(dp) / feitos if feitos else 1.0


def plano(operacao_id: int, mes_ano: str, cestas: list[str] | None = None) -> dict:
    """Tudo o que a tela precisa: resumo por cesta (mês/dia) e as semanas (base, ajuste, real, por dia)."""
    from services import ressuprimento_service as rs

    metas = ressuprimento_repo.metas_df(operacao_id, mes_ano)
    meta = (metas.set_index("cesta")["meta_volume_hl"].astype(float) if not metas.empty
            else pd.Series(dtype=float))
    real = _real_por_dia(operacao_id, mes_ano)
    todas = sorted(set(meta.index) | set(real["cesta"]))
    if cestas:
        todas = [c for c in todas if c in cestas]
    ref = referencia(operacao_id, mes_ano, real)
    dp = dias_puxada(operacao_id, mes_ano)
    sem_pux = dias_sem_puxada(operacao_id, mes_ano)
    hoje = tempo.hoje()
    restantes = [d for d in dp if ref is None or d > ref]
    feitos = [d for d in dp if ref is not None and d <= ref]
    fator = len(dp) / len(feitos) if feitos else 1.0
    corrente = mes_ano == hoje.strftime("%Y-%m")

    linhas = []
    for c in todas:
        m = float(meta.get(c, 0.0))
        r = float(real.loc[real["cesta"] == c, "dia"].sum()) if not real.empty else 0.0
        falta = max(m - r, 0.0)
        tend = r * fator if corrente else r
        linhas.append({"cesta": c, "indicador": rs.nome_cesta(c), "meta": m, "real": r, "falta": falta,
                       "dias_restantes": len(restantes),
                       "por_dia": falta / len(restantes) if restantes else (falta if falta else 0.0),
                       "media_realizada": r / len(feitos) if feitos else 0.0,
                       "tendencia": tend, "ating_tend": tend / m * 100 if m else None})
    resumo = pd.DataFrame(linhas)

    aj = ajustes(operacao_id, mes_ano)
    sem_linhas = []
    for n, ini, fim in semanas(mes_ano):
        dias_sem = [d for d in dp if ini <= d <= fim]
        a = aj.get(ini.isoformat(), {})
        pct = float(a.get("ajuste_pct") or 0)
        rest_sem = [d for d in dias_sem if d in restantes]
        for c in todas:
            m = float(meta.get(c, 0.0))
            base = m * len(dias_sem) / len(dp) if dp else 0.0
            ajust = base * (1 + pct / 100)
            rs_ = (float(real[(real["cesta"] == c) & (real["data"] >= ini) & (real["data"] <= fim)]["dia"].sum())
                   if not real.empty else 0.0)
            falta = max(ajust - rs_, 0.0)
            sem_linhas.append({
                "semana": n, "ini": ini, "fim": fim, "cesta": c, "indicador": rs.nome_cesta(c),
                "dias_puxada": len(dias_sem), "meta_base": base, "ajuste_pct": pct, "meta_ajustada": ajust,
                "real": rs_, "falta": falta, "dias_restantes": len(rest_sem),
                "por_dia": falta / len(rest_sem) if rest_sem else 0.0,
                "ating": rs_ / ajust * 100 if ajust else None,
                "atual": ini <= hoje <= fim, "observacao": a.get("observacao") or "",
                "ajustado_por": a.get("atualizado_por") or ""})
    return {"resumo": resumo, "semanas": pd.DataFrame(sem_linhas), "ref": ref, "dias_puxada": dp,
            "sem_puxada": sorted(sem_pux), "restantes": restantes, "feitos": feitos, "fator": fator,
            "corrente": corrente}
