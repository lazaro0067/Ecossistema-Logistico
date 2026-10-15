"""Financeiro › 📝 Justificar Dispersão.

Contas (conta × depto) do mês com dispersão ≥ limite (padrão 5%, para mais ou para menos) contra o plan. Cada dono
(dono do departamento, sub-dono ou dono da conta) vê e justifica só as suas; o Master e o dono do financeiro veem
tudo, definem o prazo e acompanham quem já fez. Justificou → financeiro aprova/reprova → as aprovadas entram na
reunião como insumo (🗓️ Reunião & Ações)."""
import datetime as dt

import pandas as pd

from core import tempo
from database.connection import execute, query_df, query_one
from repositories import operacoes_repo
from services import obz_service as obz
from services.erros import RegraNegocioError

STATUS = {"pendente": "⏳ Pendente", "aguardando": "🕒 Aguardando aprovação", "aprovada": "✔️ Aprovada",
          "reprovada": "❌ Reprovada — refazer"}


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


def _master(u: dict) -> bool:
    from core.auth import e_master

    return e_master(u)


def ve_tudo(u: dict) -> bool:
    return _master(u) or u.get("id") in set(obz.usuarios_papel("fin_dono")) | set(obz.usuarios_papel("aprovador"))


def pode_configurar(u: dict) -> bool:
    return _master(u) or u.get("id") in obz.usuarios_papel("fin_dono")


def pode_aprovar(u: dict) -> bool:
    return ve_tudo(u)


# --- Prazo / limite do mês ---------------------------------------------------------------------------------------
def config(operacao_id: int, mes: str) -> dict:
    ids = operacoes_repo.ids_efetivos(operacao_id)
    r = query_one(f"SELECT * FROM obz_just_mes WHERE operacao_id IN ({', '.join('?' * len(ids))}) AND mes = ? "
                  "ORDER BY prazo LIMIT 1", (*ids, mes))
    return {"prazo": r["prazo"] if r else None, "limite": float(r["limite_pct"]) if r and r["limite_pct"] is not None
            else 5.0, "definido_por": r["definido_por"] if r else None}


def salvar_config(operacao_id: int, mes: str, prazo: dt.date, limite: float, usuario: dict) -> None:
    if not pode_configurar(usuario):
        raise RegraNegocioError("Só o Master e o dono do financeiro definem o prazo das justificativas.")
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para definir o prazo.")
    execute("""INSERT INTO obz_just_mes (operacao_id, mes, prazo, limite_pct, definido_por, definido_em)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(operacao_id, mes) DO UPDATE SET prazo = excluded.prazo, limite_pct = excluded.limite_pct,
                 definido_por = excluded.definido_por, definido_em = excluded.definido_em""",
            (operacao_id, mes, prazo.isoformat(), float(limite), usuario.get("nome"), agora()))
    _avisar_donos(operacao_id, mes, prazo)


# --- Lista de dispersões -----------------------------------------------------------------------------------------
def lista(operacao_id: int, mes: str) -> pd.DataFrame:
    """Linhas com dispersão ≥ limite: plan, fechamento, disp, área, donos, status e texto da justificativa."""
    from services import obz_sim_service as sim

    lim = config(operacao_id, mes)["limite"]
    b = obz.base(operacao_id, mes)
    if b.empty:
        return b
    pct = b["disp_pct"]
    sem_plan = (b["plan"] == 0) & (b["fechamento"].abs() >= 1)
    b = b[(pct.abs() >= lim) | sem_plan].copy()
    if b.empty:
        return b
    b["disp_pct"] = b["disp_pct"].where(~sem_plan.loc[b.index], 100.0)
    b = obz.enriquecer(b)
    b = sim.donos(b)
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    js = query_df(f"SELECT * FROM obz_just WHERE {trecho} AND mes = ?", (*p, mes))
    jm = js.set_index(["conta", "depto"]) if not js.empty else None

    def pega(c, d, col):
        if jm is None or (c, d) not in jm.index:
            return None
        v = jm.loc[(c, d), col]
        return v.iloc[0] if isinstance(v, pd.Series) else v

    for col in ("id", "texto", "acao", "status", "por", "em", "aprovador", "aprovado_em", "comentario"):
        b[f"j_{col}"] = [pega(c, d, col) for c, d in zip(b["conta"], b["depto"])]
    b["j_status"] = b["j_status"].fillna("pendente")
    b["tipo"] = ["acima" if (x > 0) == (n != "receita") else "abaixo" for x, n in zip(b["disp"], b["natureza"])]
    return b.sort_values("disp", key=lambda s: -s.abs()).reset_index(drop=True)


def minhas(df: pd.DataFrame, usuario: dict) -> pd.DataFrame:
    if df.empty:
        return df
    uid = usuario.get("id")
    return df[[uid in (u or set()) or uid == a for u, a in zip(df["uids_conta"], df["uid_area"])]]


def pode_justificar(linha: dict, usuario: dict) -> bool:
    uid = usuario.get("id")
    return _master(usuario) or uid in (linha.get("uids_conta") or set()) or uid == linha.get("uid_area") or \
        uid in obz.usuarios_papel("fin_dono")


def justificar(operacao_id: int, mes: str, linha: dict, texto: str, acao: str, usuario: dict) -> None:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha a revenda para justificar.")
    if not pode_justificar(linha, usuario):
        raise RegraNegocioError("Esta conta não é sua — quem justifica é o dono do departamento / da conta.")
    texto = (texto or "").strip()
    if len(texto) < 10:
        raise RegraNegocioError("Escreva a justificativa (o que aconteceu e por quê).")
    execute("""INSERT INTO obz_just (operacao_id, mes, conta, depto, plan, fechamento, disp, disp_pct, texto, acao,
                                     status, por, por_id, em, aprovador, aprovado_em, comentario)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aguardando', ?, ?, ?, NULL, NULL, NULL)
               ON CONFLICT(operacao_id, mes, conta, depto) DO UPDATE SET plan = excluded.plan,
                 fechamento = excluded.fechamento, disp = excluded.disp, disp_pct = excluded.disp_pct,
                 texto = excluded.texto, acao = excluded.acao, status = 'aguardando', por = excluded.por,
                 por_id = excluded.por_id, em = excluded.em, aprovador = NULL, aprovado_em = NULL, comentario = NULL""",
            (operacao_id, mes, str(linha["conta"]), str(linha["depto"]), float(linha["plan"]),
             float(linha["fechamento"]), float(linha["disp"]), float(linha["disp_pct"] or 0), texto,
             (acao or "").strip() or None, usuario.get("nome"), usuario.get("id"), agora()))
    _notificar(set(obz.usuarios_papel("fin_dono")) | set(obz.usuarios_papel("aprovador")),
               f"📝 Justificativa para aprovar ({obz.nome_mes(mes)})",
               f"{usuario.get('nome')} justificou a conta {linha['conta']} · {linha.get('nome_conta') or ''} "
               f"({obz._brl(float(linha['disp']))}). Financeiro › 📝 Justificar Dispersão › Aprovar.",
               f"just:{operacao_id}:{mes}:{linha['conta']}:{linha['depto']}:{agora()}")


def aprovar(jid: int, usuario: dict, ok: bool, comentario: str = "") -> None:
    if not pode_aprovar(usuario):
        raise RegraNegocioError("Só o financeiro aprova as justificativas.")
    if not ok and not (comentario or "").strip():
        raise RegraNegocioError("Para reprovar, escreva o motivo — o dono vai refazer.")
    r = query_one("SELECT * FROM obz_just WHERE id = ?", (int(jid),))
    if not r:
        raise RegraNegocioError("Justificativa não encontrada.")
    execute("UPDATE obz_just SET status = ?, aprovador = ?, aprovado_em = ?, comentario = ? WHERE id = ?",
            ("aprovada" if ok else "reprovada", usuario.get("nome"), agora(), (comentario or "").strip() or None,
             int(jid)))
    if not ok and r.get("por_id"):
        _notificar({int(r["por_id"])}, f"❌ Justificativa reprovada ({obz.nome_mes(r['mes'])})",
                   f"Conta {r['conta']}: {comentario}. Refaça em Financeiro › 📝 Justificar Dispersão.",
                   f"justrep:{jid}:{agora()}")


def aprovadas(operacao_id: int, mes: str) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("j.operacao_id", operacao_id)
    return query_df(f"""SELECT j.*, c.nome AS nome_conta FROM obz_just j LEFT JOIN obz_contas c ON c.codigo = j.conta
                        WHERE {trecho} AND j.mes = ? AND j.status = 'aprovada' ORDER BY ABS(j.disp) DESC""",
                    (*p, mes))


def progresso(df: pd.DataFrame) -> pd.DataFrame:
    """Por responsável: total, justificadas, aprovadas, pendentes."""
    if df.empty:
        return pd.DataFrame()
    g = df.assign(feito=df["j_status"].isin(["aguardando", "aprovada"]), ok=df["j_status"] == "aprovada",
                  pend=df["j_status"].isin(["pendente", "reprovada"]))
    out = g.groupby("responsavel", as_index=False).agg(contas=("conta", "size"), justificadas=("feito", "sum"),
                                                       aprovadas=("ok", "sum"), pendentes=("pend", "sum"))
    out["pct"] = out["justificadas"] / out["contas"] * 100
    return out.sort_values(["pendentes", "contas"], ascending=False).reset_index(drop=True)


def _notificar(uids: set, titulo: str, texto: str, chave: str) -> None:
    try:
        from repositories import motoristas_repo

        for u in {x for x in uids if x}:
            motoristas_repo.criar_notificacao(int(u), "obz", f"{chave}:{u}", titulo, texto, "financeiro",
                                              agora() + ":00")
    except Exception:  # noqa: BLE001
        pass


def _avisar_donos(operacao_id: int, mes: str, prazo: dt.date) -> None:
    df = lista(operacao_id, mes)
    if df.empty:
        return
    pend = df[df["j_status"].isin(["pendente", "reprovada"])]
    por_uid: dict = {}
    for r in pend.itertuples(index=False):
        for u in (set(r.uids_conta or set()) | ({r.uid_area} if r.uid_area else set())):
            por_uid[u] = por_uid.get(u, 0) + 1
    for u, n in por_uid.items():
        _notificar({u}, f"📝 {n} dispersão(ões) para justificar até {prazo:%d/%m}",
                   f"{obz.nome_mes(mes)}: abra Financeiro › 📝 Justificar Dispersão e clique no ✏️ de cada conta.",
                   f"justprazo:{operacao_id}:{mes}:{prazo.isoformat()}")


# --- Janela da tendência ------------------------------------------------------------------------------------------
DIA_LIMITE_TEND = 15


def prazo_tend(mes: str) -> dt.date:
    """A tendência do mês M é lançada até o dia 15 do mês anterior."""
    a, m = map(int, mes.split("-"))
    a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return dt.date(a, m, DIA_LIMITE_TEND)


def reabertura(operacao_id: int, mes: str) -> dict | None:
    ids = operacoes_repo.ids_efetivos(operacao_id)
    r = query_one(f"SELECT * FROM obz_tend_abertura WHERE operacao_id IN ({', '.join('?' * len(ids))}) AND mes = ? "
                  "ORDER BY ate DESC LIMIT 1", (*ids, mes))
    return dict(r) if r else None


def tend_aberta(operacao_id: int, mes: str) -> tuple[bool, str]:
    hoje = tempo.hoje()
    pz = prazo_tend(mes)
    if hoje <= pz:
        return True, f"🟢 Aberta até {pz:%d/%m/%Y} ({(pz - hoje).days} dia(s))"
    r = reabertura(operacao_id, mes)
    if r and dt.date.fromisoformat(str(r["ate"])[:10]) >= hoje:
        return True, (f"🟡 Reaberta por {r['aberto_por']} até {dt.date.fromisoformat(str(r['ate'])[:10]):%d/%m/%Y} — "
                      f"{r['justificativa']}")
    return False, f"🔒 Fechada desde {pz:%d/%m/%Y} (prazo: dia {DIA_LIMITE_TEND} do mês anterior)"


def reabrir_tend(operacao_id: int, mes: str, ate: dt.date, justificativa: str, usuario: dict) -> None:
    if not pode_configurar(usuario):
        raise RegraNegocioError("Depois do prazo, só o dono do financeiro reabre a tendência.")
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha a revenda para reabrir.")
    if not (justificativa or "").strip():
        raise RegraNegocioError("Escreva a justificativa da reabertura.")
    if ate < tempo.hoje():
        raise RegraNegocioError("A data final precisa ser hoje ou depois.")
    execute("INSERT INTO obz_tend_abertura (operacao_id, mes, ate, justificativa, aberto_por, em) "
            "VALUES (?, ?, ?, ?, ?, ?)", (operacao_id, mes, ate.isoformat(), justificativa.strip(),
                                          usuario.get("nome"), agora()))
