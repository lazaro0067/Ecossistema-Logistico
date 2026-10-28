"""🧮 Simulador OBZ — orçamento do ano seguinte a partir do histórico do ano atual.

Fluxo: rascunho (financeiro monta) → aprovação do dono do financeiro → crítica dos donos de conta → crítica dos donos
de departamento → revisão do financeiro (aprova/reprova cada crítica) → diretor → corporativo/CEO → publicado no Plan.

Cálculo por conta × departamento × mês:
  base mensal = média do realizado do ano atual (ou real YTD + plan dos meses que faltam ÷ 12)
  pessoal  = base × (1 + dissídio a partir do mês negociado) × (QLP do mês ÷ QLP de hoje) — o QLP acompanha o HL
  fretes   = base × (HL do mês ÷ HL médio do ano atual) × (1 + inflação de fretes)
  insumos  = base × (HL do mês ÷ HL médio) × (1 + inflação de insumos)
  aluguel  = base × (1 + reajuste do aluguel)        ipca / receita = base × (1 + IPCA)        manual = base
  + iniciativas (despesas novas / economias) + impacto mensal do capex aprovado (depreciação, juros, leasing,
    opex − economia) — 🏗️ Gestão de Capex.
"""
import json

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services import obz_service as obz
from services.erros import RegraNegocioError

ETAPAS = {
    "rascunho": "✍️ Montagem (financeiro)",
    "aprov_fin": "🏦 Aprovação do dono do financeiro",
    "critica_conta": "🧾 Crítica dos donos de conta",
    "critica_depto": "🏢 Crítica dos donos de departamento",
    "revisao_fin": "🔍 Revisão do financeiro",
    "diretor": "🎩 Aprovação do diretor",
    "ceo": "🏛️ Aprovação corporativo / CEO",
    "publicado": "✅ Aprovado — publicado no Plan",
}
DRIVERS = {
    "pessoal": "👥 Pessoal (dissídio + equipe pelo HL)",
    "frete": "🚚 Fretes (HL × inflação de fretes)",
    "insumos": "⛽ Insumos / variáveis (HL × inflação de insumos)",
    "aluguel": "🏠 Aluguel (reajuste do aluguel)",
    "ipca": "📈 Fixo corrigido pelo IPCA",
    "receita": "💰 Receita (IPCA)",
    "manual": "✋ Manual (igual ao histórico)",
}
TIPOS_INIC = {"despesa": "➕ Despesa nova", "economia": "➖ Economia / corte"}
PREMISSAS_PADRAO = {"ipca": 4.5, "aluguel": 4.5, "fretes": 6.0, "insumos": 5.0, "dissidio_mes": 5,
                    "dissidio_pct": 5.0, "crescimento_volume": 0.0, "base": "media", "distribuicao": "hl"}
DISTRIBUICAO = {"hl": "🍺 Pelo HL planejado de cada mês (mês que vende mais, custa mais)",
                "linear": "➖ Linear (1/12 por mês)"}
_CHAVES = [
    ("pessoal", ("salario", "ferias", " 13", "13o", "rescis", "inss", "fgts", "plano saude", "odonto", "alimenta",
                 "ticket", "vale ", "seguro de vida", "uniforme", "epi", "exame", "estagi", "aprendiz",
                 "ajuda de custo", "funcionario", "comiss", "gratific", "hora extra", "horas extras", "premio",
                 "plr", "encargo", "folha", "pro labore", "pro-labore", "adicional", "aviso previo", "sindic")),
    ("frete", ("frete", "carreto", "pedagio", "transporte de", "freteiro")),
    ("aluguel", ("aluguel", "alugueis", "locacao", "arrendamento", "leasing")),
    ("insumos", ("combust", "lubrific", "pneu", "peca", "material", "embalag", "palete", "pallet", "lona", "consumo",
                 "energia", " gas", "oleo", "manutencao", "reparo")),
]


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


def driver_padrao(nome: str, natureza: str | None) -> str:
    if natureza == "receita":
        return "receita"
    n = " " + obz._n(nome)
    for drv, chaves in _CHAVES:
        if any(k in n for k in chaves):
            return drv
    return "ipca"


# --- Permissões -------------------------------------------------------------------------------------------------
def _master(u: dict) -> bool:
    from core.auth import e_master

    return e_master(u)


def pode_montar(u: dict) -> bool:
    return _master(u) or u.get("id") in set(obz.usuarios_papel("fin_dono")) | set(obz.usuarios_papel("plan"))


def pode_fin(u: dict) -> bool:
    return _master(u) or u.get("id") in obz.usuarios_papel("fin_dono")


def pode_diretor(u: dict) -> bool:
    return _master(u) or u.get("id") in obz.usuarios_papel("diretor")


def pode_ceo(u: dict) -> bool:
    return _master(u) or u.get("id") in obz.usuarios_papel("ceo")


def _uid_gestor() -> dict:
    g = query_df("SELECT id, usuario_id FROM gestores WHERE usuario_id IS NOT NULL")
    return {int(a): int(b) for a, b in zip(g["id"], g["usuario_id"])}


def donos(linhas: pd.DataFrame) -> pd.DataFrame:
    """Para cada linha: usuários donos da conta (sub-dono / dono da conta) e do departamento."""
    ug = _uid_gestor()
    ar = obz.areas()
    dono_area = {n: ug.get(int(g)) for n, g in zip(ar["nome"], ar["dono_gestor_id"]) if pd.notna(g)}
    rp = query_df("SELECT area, conta, gestor_id FROM obz_resp")
    sub = {(a, c): ug.get(int(g)) for a, c, g in zip(rp["area"], rp["conta"], rp["gestor_id"]) if pd.notna(g)}
    sd = obz.subdonos()
    sub_old = {(c, d): int(u) for c, d, u in zip(sd["conta"], sd["depto"], sd["usuario_id"]) if pd.notna(u)}
    ct = obz.contas()
    dc = {c: int(u) for c, u in zip(ct["codigo"], ct["dono_id"]) if pd.notna(u)}
    out = linhas.copy()
    out["uids_conta"] = [{u for u in (sub.get((a, c)), sub_old.get((c, d)), dc.get(c)) if u}
                         for c, d, a in zip(out["conta"], out["depto"], out["area"])]
    out["uid_area"] = [dono_area.get(a) for a in out["area"]]
    return out


# --- Simulações ---------------------------------------------------------------------------------------------------
def listar(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT * FROM obz_sim WHERE {trecho} ORDER BY ano DESC, id DESC", p)


def buscar(sim_id: int) -> dict | None:
    s = query_one("SELECT * FROM obz_sim WHERE id = ?", (int(sim_id),))
    if not s:
        return None
    s = dict(s)
    s["premissas"] = {**PREMISSAS_PADRAO, **json.loads(s.get("premissas") or "{}")}
    s["ano_base"] = str(int(s["ano"]) - 1)
    return s


def _log(sim_id: int, etapa: str, acao: str, usuario: dict, comentario: str = "") -> None:
    execute("INSERT INTO obz_sim_log (sim_id, etapa, acao, usuario, em, comentario) VALUES (?, ?, ?, ?, ?, ?)",
            (sim_id, etapa, acao, usuario.get("nome") or usuario.get("login"), agora(), comentario or None))


def historico(sim_id: int) -> pd.DataFrame:
    return query_df("SELECT * FROM obz_sim_log WHERE sim_id = ? ORDER BY id DESC", (int(sim_id),))


def criar(operacao_id: int, ano: str, nome: str, usuario: dict, premissas: dict | None = None) -> int:
    """Cria o simulador a partir do histórico do ano atual (ano − 1): linhas conta × depto, volume e equipes."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para criar o simulador.")
    if not pode_montar(usuario):
        raise RegraNegocioError("Só o dono do financeiro (ou quem o Master liberou para o Plan) cria o simulador.")
    ano = str(ano)
    base_ano = str(int(ano) - 1)
    rl = obz.real_df(operacao_id, f"{base_ano}-01", f"{base_ano}-12")
    if rl.empty:
        raise RegraNegocioError(f"Não há realizado de {base_ano} (16.03.01 / Base OBZ) — o simulador começa pelo "
                                "histórico do ano atual.")
    sim_id = execute("""INSERT INTO obz_sim (operacao_id, ano, nome, status, premissas, criado_por, criado_em,
                                             atualizado_em) VALUES (?, ?, ?, 'rascunho', ?, ?, ?, ?)""",
                     (operacao_id, ano, (nome or f"Orçamento {ano}").strip(),
                      json.dumps({**PREMISSAS_PADRAO, **(premissas or {})}), usuario.get("nome"), agora(), agora()))
    ct = obz.contas()
    ok = set(ct.loc[ct["no_obz"].fillna(1).astype(int) == 1, "codigo"])
    nome_c, nat = dict(zip(ct["codigo"], ct["nome"])), dict(zip(ct["codigo"], ct["natureza"]))
    pares = rl[rl["conta"].isin(ok)][["conta", "depto"]].drop_duplicates()
    mp = obz._mapas()
    with get_conn() as conn:
        conn.executemany("""INSERT INTO obz_sim_linha (sim_id, conta, depto, area, driver) VALUES (?, ?, ?, ?, ?)""",
                         [(sim_id, c, d, obz.area_de(c, d, mp), driver_padrao(nome_c.get(c, ""), nat.get(c)))
                          for c, d in pares.itertuples(index=False)])
        hl = obz.hl_mensal(operacao_id, base_ano)
        cresc = float((premissas or {}).get("crescimento_volume", 0) or 0)
        for m in range(1, 13):
            hb = hl.get(f"{base_ano}-{m:02d}")  # mês sem venda carregada fica vazio — preenche manual
            conn.execute("INSERT INTO obz_sim_volume (sim_id, mes, hl_base, hl_plan, fonte) VALUES (?, ?, ?, ?, ?)",
                         (sim_id, f"{ano}-{m:02d}", round(float(hb), 2) if hb else None,
                          round(float(hb) * (1 + cresc / 100), 2) if hb else None, "vendas" if hb else None))
        for a in sorted({obz.area_de(c, d, mp) for c, d in pares.itertuples(index=False)}):
            conn.execute("INSERT INTO obz_sim_equipe (sim_id, area, acompanha) VALUES (?, ?, 1)", (sim_id, a))
    _log(sim_id, "rascunho", "Simulador criado a partir do histórico de " + base_ano, usuario)
    calcular(sim_id)
    return sim_id


def excluir(sim_id: int, usuario: dict) -> None:
    s = buscar(sim_id)
    if not s:
        return
    if s["status"] == "publicado" and not _master(usuario):
        raise RegraNegocioError("Simulador já publicado no Plan — só o Master exclui.")
    if not pode_montar(usuario):
        raise RegraNegocioError("Sem permissão para excluir o simulador.")
    with get_conn() as conn:
        for t in ("obz_sim_linha", "obz_sim_valor", "obz_sim_volume", "obz_sim_equipe", "obz_sim_inic", "obz_sim_log",
                  "obz_sim_reuniao"):
            conn.execute(f"DELETE FROM {t} WHERE sim_id = ?", (int(sim_id),))
        conn.execute("DELETE FROM obz_sim WHERE id = ?", (int(sim_id),))


def _editavel(s: dict, usuario: dict) -> None:
    if s["status"] != "rascunho":
        raise RegraNegocioError("Premissas, volume, equipe e iniciativas só mudam na etapa de montagem (rascunho).")
    if not pode_montar(usuario):
        raise RegraNegocioError("Só o dono do financeiro (ou quem o Master liberou para o Plan) monta o simulador.")


def salvar_premissas(sim_id: int, premissas: dict, usuario: dict) -> None:
    s = buscar(sim_id)
    _editavel(s, usuario)
    execute("UPDATE obz_sim SET premissas = ?, atualizado_em = ? WHERE id = ?",
            (json.dumps({**s["premissas"], **premissas}), agora(), int(sim_id)))
    calcular(sim_id)


def volume(sim_id: int) -> pd.DataFrame:
    df = query_df("SELECT mes, hl_base, hl_plan, fonte FROM obz_sim_volume WHERE sim_id = ? ORDER BY mes",
                  (int(sim_id),))
    for c in ("hl_base", "hl_plan"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def salvar_volume(sim_id: int, df: pd.DataFrame, usuario: dict) -> None:
    """Grava HL base (meses sem venda carregada são preenchidos à mão) e HL planejado."""
    _editavel(buscar(sim_id), usuario)
    atual = volume(sim_id).set_index("mes")
    with get_conn() as conn:
        for m, hb, hp in zip(df["mes"], df["hl_base"], df["hl_plan"]):
            hb = float(hb) if pd.notna(hb) else None
            ant = atual.at[m, "hl_base"] if m in atual.index else None
            fonte = atual.at[m, "fonte"] if m in atual.index else None
            if hb is not None and (pd.isna(ant) or abs(hb - float(ant)) >= 0.005):
                fonte = "manual"
            conn.execute("UPDATE obz_sim_volume SET hl_base = ?, hl_plan = ?, fonte = ? WHERE sim_id = ? AND mes = ?",
                         (hb, float(hp) if pd.notna(hp) else None, fonte if hb is not None else None, int(sim_id), m))
    calcular(sim_id)


def equipe(sim_id: int) -> pd.DataFrame:
    df = query_df("SELECT area, equipe_atual, qlp_plan FROM obz_sim_equipe WHERE sim_id = ? ORDER BY area",
                  (int(sim_id),))
    for c in ("equipe_atual", "qlp_plan"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def salvar_equipe(sim_id: int, df: pd.DataFrame, usuario: dict) -> None:
    """QLP de hoje (obrigatório para enxergar o custo por pessoa) e QLP planejado (opcional — sem ele o QLP
    acompanha o volume de HL)."""
    _editavel(buscar(sim_id), usuario)
    with get_conn() as conn:
        for r in df.itertuples(index=False):
            conn.execute("UPDATE obz_sim_equipe SET equipe_atual = ?, qlp_plan = ? WHERE sim_id = ? AND area = ?",
                         (float(r.equipe_atual) if pd.notna(r.equipe_atual) else None,
                          float(r.qlp_plan) if pd.notna(r.qlp_plan) else None, int(sim_id), r.area))
    calcular(sim_id)


def _razao_volume(sim_id: int) -> tuple[dict, float]:
    """{mês 1–12: HL planejado ÷ HL médio do ano atual} e o HL médio."""
    vol = volume(sim_id)
    hb = vol["hl_base"].dropna()
    hl_med = float(hb.mean()) if len(hb) else 0.0
    plan = {int(m[5:]): (float(h) if pd.notna(h) else (float(b) if pd.notna(b) else hl_med))
            for m, b, h in zip(vol["mes"], vol["hl_base"], vol["hl_plan"])}
    return {m: (plan.get(m, hl_med) / hl_med) if hl_med else 1.0 for m in range(1, 13)}, hl_med


def pesos_hl(sim_id: int) -> dict:
    """{mês 1–12: participação do mês no HL planejado do ano} — soma 1. Sem HL, 1/12 cada."""
    vol = volume(sim_id)
    hp = {int(m[5:]): (float(h) if pd.notna(h) else float(b) if pd.notna(b) else 0.0)
          for m, b, h in zip(vol["mes"], vol["hl_base"], vol["hl_plan"])}
    tot = sum(max(v, 0.0) for v in hp.values())
    return {m: (max(hp.get(m, 0.0), 0.0) / tot) if tot else 1 / 12 for m in range(1, 13)}


def qlp_mensal(sim_id: int) -> pd.DataFrame:
    """QLP projetado por departamento e mês: o planejado (se informado) ou o de hoje × crescimento do HL."""
    razao, _ = _razao_volume(sim_id)
    eq = equipe(sim_id)
    linhas = []
    for r in eq.itertuples(index=False):
        if pd.isna(r.equipe_atual) or not r.equipe_atual:
            continue
        linhas.append({"area": r.area, "hoje": float(r.equipe_atual),
                       **{m: float(r.qlp_plan) if pd.notna(r.qlp_plan) else float(r.equipe_atual) * razao[m]
                          for m in range(1, 13)}})
    return pd.DataFrame(linhas)


def gente(sim_id: int) -> pd.DataFrame:
    """Por departamento: QLP de hoje, custo de pessoal (histórico), custo por pessoa, QLP projetado e custo projetado."""
    li = linhas(sim_id)
    eq = equipe(sim_id)
    if li.empty:
        return eq
    pes = li[li["driver"] == "pessoal"].assign(b=lambda x: x["base_ano"] * x["sinal"],
                                                c=lambda x: x["final_ano"] * x["sinal"])
    g = pes.groupby("area")[["b", "c"]].sum()
    qm = qlp_mensal(sim_id)
    qm = qm.set_index("area") if not qm.empty else pd.DataFrame()
    eq["custo_base"] = eq["area"].map(g["b"]).fillna(0.0)
    eq["custo_plan"] = eq["area"].map(g["c"]).fillna(0.0)
    eq["custo_pessoa_mes"] = [cb / 12 / q if pd.notna(q) and q else None for cb, q in zip(eq["custo_base"],
                                                                                          eq["equipe_atual"])]
    eq["qlp_medio"] = [float(qm.loc[a, list(range(1, 13))].mean()) if a in qm.index else None for a in eq["area"]]
    return eq


def iniciativas(sim_id: int) -> pd.DataFrame:
    return query_df("SELECT * FROM obz_sim_inic WHERE sim_id = ? ORDER BY id", (int(sim_id),))


def salvar_iniciativas(sim_id: int, df: pd.DataFrame, usuario: dict) -> None:
    _editavel(buscar(sim_id), usuario)
    linhas = []
    for r in df.to_dict("records"):
        desc = str(r.get("descricao") or "").strip()
        if not desc or desc == "nan":
            continue
        tipo = r.get("tipo") if r.get("tipo") in TIPOS_INIC else "despesa"
        mes_ini = int(r.get("mes_ini") or 1) if pd.notna(r.get("mes_ini")) else 1
        linhas.append((int(sim_id), tipo, desc, r.get("area") or None,
                       obz._cod(r.get("conta")) if r.get("conta") and str(r.get("conta")) != "nan" else None,
                       min(max(mes_ini, 1), 12), float(r.get("valor") or 0), 1 if r.get("recorrente") else 0))
    with get_conn() as conn:
        conn.execute("DELETE FROM obz_sim_inic WHERE sim_id = ?", (int(sim_id),))
        conn.executemany("""INSERT INTO obz_sim_inic (sim_id, tipo, descricao, area, conta, mes_ini, valor, recorrente)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", linhas)
    calcular(sim_id)


def salvar_drivers(sim_id: int, mudancas: dict, usuario: dict) -> None:
    """mudancas: {linha_id: driver}"""
    _editavel(buscar(sim_id), usuario)
    with get_conn() as conn:
        for lid, drv in mudancas.items():
            if drv in DRIVERS:
                conn.execute("UPDATE obz_sim_linha SET driver = ? WHERE id = ? AND sim_id = ?",
                             (drv, int(lid), int(sim_id)))
    calcular(sim_id)


# --- Cálculo ------------------------------------------------------------------------------------------------------
def _base_mensal(s: dict) -> tuple[dict, int]:
    """{(conta, depto): base mensal} e quantos meses de histórico entraram."""
    op, base_ano = s["operacao_id"], s["ano_base"]
    rl = obz.real_df(op, f"{base_ano}-01", f"{base_ano}-12")
    meses_ = sorted(rl["mes"].unique()) if not rl.empty else []
    n = len(meses_) or 1
    soma = rl.groupby(["conta", "depto"])["valor"].sum().to_dict() if not rl.empty else {}
    if s["premissas"].get("base") == "ytd_plan" and meses_:
        pl = obz.plan_df(op, f"{base_ano}-01", f"{base_ano}-12")
        pl = pl[~pl["mes"].isin(meses_)] if not pl.empty else pl
        resto = pl.groupby(["conta", "depto"])["valor"].sum().to_dict() if not pl.empty else {}
        chaves = set(soma) | set(resto)
        return {k: (soma.get(k, 0.0) + resto.get(k, 0.0)) / 12 for k in chaves}, len(meses_)
    return {k: v / n for k, v in soma.items()}, len(meses_)


def calcular(sim_id: int) -> None:
    """Recalcula valores mensais (obz_sim_valor), base e calculado por linha. Mantém as críticas."""
    s = buscar(sim_id)
    pm = s["premissas"]
    base, _ = _base_mensal(s)
    razao, _ = _razao_volume(sim_id)
    eq = equipe(sim_id).set_index("area")

    def fator_equipe(area: str, m: int) -> float:
        """Todos os departamentos: QLP planejado ÷ QLP de hoje; sem QLP planejado, acompanha o HL."""
        if area in eq.index:
            hoje, plan = eq.at[area, "equipe_atual"], eq.at[area, "qlp_plan"]
            if pd.notna(hoje) and hoje and pd.notna(plan):
                return float(plan) / float(hoje)
        return razao[m]

    pct = {k: float(pm.get(k) or 0) / 100 for k in ("ipca", "aluguel", "fretes", "insumos", "dissidio_pct")}
    mes_dis = int(pm.get("dissidio_mes") or 1)
    pelo_hl = (pm.get("distribuicao") or "hl") == "hl"
    peso = pesos_hl(sim_id) if pelo_hl else {m: 1 / 12 for m in range(1, 13)}
    linhas = query_df("SELECT id, conta, depto, area, driver FROM obz_sim_linha WHERE sim_id = ?", (int(sim_id),))
    ano = s["ano"]
    valores, upd = [], []
    for r in linhas.itertuples(index=False):
        b = float(base.get((r.conta, r.depto), 0.0))
        tot = 0.0
        for m in range(1, 13):
            if r.driver == "pessoal":
                v = b * (1 + (pct["dissidio_pct"] if m >= mes_dis else 0.0)) * fator_equipe(r.area, m)
            elif r.driver == "frete":
                v = b * razao[m] * (1 + pct["fretes"])
            elif r.driver == "insumos":
                v = b * razao[m] * (1 + pct["insumos"])
            elif r.driver == "aluguel":  # o total do ano se reparte pelos meses conforme o HL planejado
                v = b * 12 * peso[m] * (1 + pct["aluguel"])
            elif r.driver in ("ipca", "receita"):
                v = b * 12 * peso[m] * (1 + pct["ipca"])
            else:
                v = b * 12 * peso[m]
            valores.append((int(sim_id), r.conta, r.depto, f"{ano}-{m:02d}", round(v, 2)))
            tot += v
        upd.append((round(b * 12, 2), round(tot, 2), int(r.id)))
    # iniciativas (despesa + / economia −) entram na conta × 1º depto do departamento
    ini = iniciativas(sim_id)
    deptos = obz.departamentos()
    dep_area = {}
    for c, a in zip(deptos["codigo"], deptos["area"]):
        if a and a not in dep_area:
            dep_area[a] = c
    extra: dict = {}
    for r in ini.itertuples(index=False):
        if r.tipo not in TIPOS_INIC or not r.conta:
            continue
        dep = dep_area.get(r.area, "0")
        sinal = -1.0 if r.tipo == "economia" else 1.0
        for m in range(int(r.mes_ini or 1), 13 if r.recorrente else int(r.mes_ini or 1) + 1):
            k = (r.conta, dep, f"{ano}-{m:02d}")
            extra[k] = extra.get(k, 0.0) + sinal * abs(float(r.valor or 0))
    # capex aprovado: depreciação / juros / leasing / opex − economia na conta do projeto
    from services import capex_service

    for area, conta, mes, v, _ in capex_service.impactos_orcamento(s["operacao_id"], ano):
        k = (obz._cod(conta), dep_area.get(area, "0"), mes)
        extra[k] = extra.get(k, 0.0) + v
    novos_pares = {(c, d) for c, d, _ in extra} - set(zip(linhas["conta"], linhas["depto"]))
    with get_conn() as conn:
        for c, d in novos_pares:
            conn.execute("INSERT INTO obz_sim_linha (sim_id, conta, depto, area, driver, base_ano) "
                         "VALUES (?, ?, ?, ?, 'manual', 0)", (int(sim_id), c, d, obz.area_de(c, d)))
        conn.execute("DELETE FROM obz_sim_valor WHERE sim_id = ?", (int(sim_id),))
        vals = {(a, b_, c_, d_): e for a, b_, c_, d_, e in valores}
        for (c, d, m), v in extra.items():
            vals[(int(sim_id), c, d, m)] = vals.get((int(sim_id), c, d, m), 0.0) + v
        conn.executemany("INSERT INTO obz_sim_valor (sim_id, conta, depto, mes, valor) VALUES (?, ?, ?, ?, ?)",
                         [(*k, round(v, 2)) for k, v in vals.items()])
        conn.executemany("UPDATE obz_sim_linha SET base_ano = ?, calc_ano = ? WHERE id = ?", upd)
        # calculado anual = soma dos meses (inclui iniciativas)
        conn.execute("""UPDATE obz_sim_linha SET calc_ano = (SELECT COALESCE(SUM(v.valor), 0) FROM obz_sim_valor v
                         WHERE v.sim_id = obz_sim_linha.sim_id AND v.conta = obz_sim_linha.conta
                         AND v.depto = obz_sim_linha.depto) WHERE sim_id = ?""", (int(sim_id),))
        conn.execute("UPDATE obz_sim SET atualizado_em = ? WHERE id = ?", (agora(), int(sim_id)))
    _recalcular_final(sim_id)


def _proposta(r) -> float | None:
    for c in ("prop_depto", "prop_conta"):
        v = r[c] if isinstance(r, dict) else getattr(r, c)
        if v is not None and pd.notna(v):
            return float(v)
    return None


def _recalcular_final(sim_id: int) -> None:
    """final = proposta aprovada pelo financeiro; senão o calculado."""
    li = query_df("SELECT id, calc_ano, prop_conta, prop_depto, decisao FROM obz_sim_linha WHERE sim_id = ?",
                  (int(sim_id),))
    upd = []
    for r in li.to_dict("records"):
        p = _proposta(r)
        final = p if (p is not None and r["decisao"] == "aprovada") else r["calc_ano"]
        upd.append((final, int(r["id"])))
    with get_conn() as conn:
        conn.executemany("UPDATE obz_sim_linha SET final_ano = ? WHERE id = ?", upd)


def linhas(sim_id: int) -> pd.DataFrame:
    """Linhas com nome da conta, natureza, proposta e variações."""
    li = query_df("SELECT * FROM obz_sim_linha WHERE sim_id = ? ORDER BY area, conta, depto", (int(sim_id),))
    if li.empty:
        return li
    ct = obz.contas().set_index("codigo")
    li["nome_conta"] = li["conta"].map(ct["nome"])
    li["natureza"] = li["conta"].map(ct["natureza"]).fillna("despesa")
    nd = obz.nomes_deptos()
    li["nome_depto"] = li["depto"].map(lambda d: nd.get(d) or f"Depto {d}")
    for c in ("base_ano", "calc_ano", "final_ano", "prop_conta", "prop_depto"):
        li[c] = pd.to_numeric(li[c], errors="coerce")
    li["proposta"] = [_proposta(r) for r in li.itertuples(index=False)]
    li["var_pct"] = (li["final_ano"] / li["base_ano"].where(li["base_ano"] != 0) - 1) * 100
    # sinal líquido (receita reduz a despesa)
    li["sinal"] = li["natureza"].map(lambda n: -1.0 if n == "receita" else 1.0)
    return li


def valores_mensais(sim_id: int, final: bool = True) -> pd.DataFrame:
    """conta × depto × mês — com final=True aplica a proporção final/calculado de cada linha."""
    v = query_df("SELECT conta, depto, mes, valor FROM obz_sim_valor WHERE sim_id = ?", (int(sim_id),))
    if v.empty or not final:
        return v
    li = query_df("SELECT conta, depto, calc_ano, final_ano FROM obz_sim_linha WHERE sim_id = ?", (int(sim_id),))
    li = li.set_index(["conta", "depto"])
    s = buscar(sim_id)
    peso = pesos_hl(sim_id) if ((s or {}).get("premissas") or {}).get("distribuicao", "hl") == "hl" \
        else {m: 1 / 12 for m in range(1, 13)}
    fat, plano = {}, {}
    for (c, d), r in li.iterrows():
        ca, fa = float(r["calc_ano"] or 0), float(r["final_ano"] or 0)
        if abs(fa - ca) < 0.005:
            continue
        if ca:
            fat[(c, d)] = fa / ca
        else:
            plano[(c, d)] = fa
    v["valor"] = [plano[(c, d)] * peso[int(m[5:])] if (c, d) in plano else x * fat.get((c, d), 1.0)
                  for c, d, m, x in zip(v["conta"], v["depto"], v["mes"], v["valor"])]
    return v


def resumo_areas(sim_id: int) -> pd.DataFrame:
    li = linhas(sim_id)
    if li.empty:
        return pd.DataFrame(columns=["area", "base", "calculado", "final"])
    li = li.assign(b=li["base_ano"] * li["sinal"], c=li["calc_ano"] * li["sinal"], f=li["final_ano"] * li["sinal"])
    g = li.groupby("area", as_index=False)[["b", "c", "f"]].sum().rename(
        columns={"b": "base", "c": "calculado", "f": "final"})
    g["var_pct"] = (g["final"] / g["base"].where(g["base"] != 0) - 1) * 100
    return g.sort_values("final", ascending=False).reset_index(drop=True)


def hl_totais(sim_id: int) -> tuple[float, float]:
    v = volume(sim_id)
    return float(pd.to_numeric(v["hl_base"], errors="coerce").sum()), float(pd.to_numeric(v["hl_plan"],
                                                                                           errors="coerce").sum())


def capex(sim_id: int) -> float:
    """Investimento aprovado na 🏗️ Gestão de Capex para o ano do simulador."""
    from services import capex_service

    s = buscar(sim_id)
    return capex_service.total_aprovado(s["operacao_id"], s["ano"])


def capex_impacto(sim_id: int) -> float:
    from services import capex_service

    s = buscar(sim_id)
    return float(sum(v for *_, v, _ in capex_service.impactos_orcamento(s["operacao_id"], s["ano"])))


def mensal_area(sim_id: int) -> pd.DataFrame:
    """Valor final (líquido: receita reduz) por departamento × mês, com o histórico mensal médio."""
    v = valores_mensais(sim_id, final=True)
    li = linhas(sim_id)
    if v.empty or li.empty:
        return pd.DataFrame()
    v = v.merge(li[["conta", "depto", "area", "nome_conta", "sinal"]], on=["conta", "depto"], how="left")
    v["liq"] = v["valor"] * v["sinal"].fillna(1.0)
    return v


# --- Críticas -----------------------------------------------------------------------------------------------------
def salvar_critica(sim_id: int, nivel: str, dados: list[dict], usuario: dict) -> int:
    """nivel 'conta' ou 'depto'. dados: [{id, proposta (None = concorda), justificativa}]"""
    s = buscar(sim_id)
    etapa = {"conta": "critica_conta", "depto": "critica_depto"}[nivel]
    if s["status"] != etapa:
        raise RegraNegocioError(f"A crítica de {'conta' if nivel == 'conta' else 'departamento'} não está aberta.")
    li = donos(linhas(sim_id)).set_index("id")
    quem, quando = usuario.get("nome") or usuario.get("login"), agora()
    n = 0
    with get_conn() as conn:
        for d in dados:
            lid = int(d["id"])
            if lid not in li.index:
                continue
            dono_ok = _master(usuario) or pode_fin(usuario) or (
                usuario["id"] in (li.at[lid, "uids_conta"] or set()) if nivel == "conta"
                else usuario["id"] == li.at[lid, "uid_area"])
            if not dono_ok:
                continue
            prop = d.get("proposta")
            prop = None if prop is None or (isinstance(prop, float) and pd.isna(prop)) else float(prop)
            just = (d.get("justificativa") or "").strip()
            if prop is not None and abs(prop - float(li.at[lid, "calc_ano"] or 0)) >= 0.005 and not just:
                raise RegraNegocioError(f"Conta {li.at[lid, 'conta']}: escreva a justificativa da proposta.")
            conn.execute(f"""UPDATE obz_sim_linha SET prop_{nivel} = ?, just_{nivel} = ?, por_{nivel} = ?,
                             em_{nivel} = ?, decisao = NULL WHERE id = ?""",
                         (prop, just or None, quem, quando, lid))
            n += 1
    _recalcular_final(sim_id)
    return n


def decidir(sim_id: int, decisoes: list[dict], usuario: dict) -> int:
    """Financeiro: [{id, decisao: aprovada|reprovada, justificativa}] — reprovar exige justificativa."""
    s = buscar(sim_id)
    if s["status"] != "revisao_fin":
        raise RegraNegocioError("A revisão do financeiro não está aberta.")
    if not pode_fin(usuario):
        raise RegraNegocioError("Só o dono do financeiro revisa as críticas.")
    quem, quando = usuario.get("nome") or usuario.get("login"), agora()
    n = 0
    with get_conn() as conn:
        for d in decisoes:
            dec = d.get("decisao")
            if dec not in ("aprovada", "reprovada"):
                continue
            just = (d.get("justificativa") or "").strip()
            if dec == "reprovada" and not just:
                raise RegraNegocioError("Para reprovar uma crítica, escreva a justificativa.")
            conn.execute("UPDATE obz_sim_linha SET decisao = ?, just_fin = ?, por_fin = ?, em_fin = ? WHERE id = ?",
                         (dec, just or None, quem, quando, int(d["id"])))
            n += 1
    _recalcular_final(sim_id)
    return n


# --- Fluxo --------------------------------------------------------------------------------------------------------
_TRANSICOES = {
    "enviar_fin": ("rascunho", "aprov_fin", pode_montar, False),
    "aprovar_fin": ("aprov_fin", "critica_conta", pode_fin, False),
    "devolver_fin": ("aprov_fin", "rascunho", pode_fin, True),
    "encerrar_conta": ("critica_conta", "critica_depto", pode_fin, False),
    "encerrar_depto": ("critica_depto", "revisao_fin", pode_fin, False),
    "reabrir_montagem": ("revisao_fin", "rascunho", pode_fin, True),
    "enviar_diretor": ("revisao_fin", "diretor", pode_fin, False),
    "aprovar_diretor": ("diretor", "ceo", pode_diretor, False),
    "reprovar_diretor": ("diretor", "revisao_fin", pode_diretor, True),
    "aprovar_ceo": ("ceo", "publicado", pode_ceo, False),
    "criticar_ceo": ("ceo", "revisao_fin", pode_ceo, True),
}
ROTULO_ACAO = {
    "enviar_fin": "📤 Enviar ao dono do financeiro", "aprovar_fin": "✔️ Aprovar e abrir a crítica das contas",
    "devolver_fin": "↩️ Devolver para ajustes", "encerrar_conta": "➡️ Encerrar crítica de contas → departamentos",
    "encerrar_depto": "➡️ Encerrar crítica de departamentos → revisão",
    "reabrir_montagem": "↩️ Voltar para a montagem (recalcular)", "enviar_diretor": "📤 Enviar ao diretor",
    "aprovar_diretor": "✔️ Aprovar → corporativo / CEO", "reprovar_diretor": "↩️ Reprovar → financeiro revisar",
    "aprovar_ceo": "🏁 Aprovar e publicar no Plan", "criticar_ceo": "↩️ Criticar → financeiro revisar",
}


def acoes_disponiveis(sim: dict, usuario: dict) -> list[str]:
    return [a for a, (de, _, pode, _) in _TRANSICOES.items() if sim["status"] == de and pode(usuario)]


def pendencias_revisao(sim_id: int) -> int:
    li = linhas(sim_id)
    if li.empty:
        return 0
    tem = li["proposta"].notna() & ((li["proposta"] - li["calc_ano"]).abs() >= 0.005)
    return int((tem & li["decisao"].isna()).sum())


def avancar(sim_id: int, acao: str, usuario: dict, comentario: str = "") -> str:
    s = buscar(sim_id)
    if acao not in _TRANSICOES:
        raise RegraNegocioError("Ação desconhecida.")
    de, para, pode, exige = _TRANSICOES[acao]
    if s["status"] != de:
        raise RegraNegocioError(f"O simulador está em “{ETAPAS[s['status']]}”.")
    if not pode(usuario):
        raise RegraNegocioError("Você não tem o papel desta etapa (o Master libera em ⚙️ Cadastros OBZ › Papéis).")
    if exige and not (comentario or "").strip():
        raise RegraNegocioError("Escreva a justificativa / crítica para devolver.")
    if acao == "enviar_diretor" and pendencias_revisao(sim_id):
        raise RegraNegocioError(f"Ainda há {pendencias_revisao(sim_id)} crítica(s) sem decisão (aprovar/reprovar).")
    execute("UPDATE obz_sim SET status = ?, atualizado_em = ? WHERE id = ?", (para, agora(), int(sim_id)))
    if para == "rascunho":
        calcular(sim_id)
    _log(sim_id, para, ROTULO_ACAO[acao], usuario, comentario)
    if para == "publicado":
        publicar(sim_id, usuario)
    _avisar(sim_id, para, usuario, comentario)
    return para


def publicar(sim_id: int, usuario: dict) -> int:
    """Grava o orçamento aprovado como Plan do ano (substitui o plan dos 12 meses da revenda)."""
    s = buscar(sim_id)
    v = valores_mensais(sim_id, final=True)
    op, ano = s["operacao_id"], s["ano"]
    with get_conn() as conn:
        for m in range(1, 13):
            conn.execute("DELETE FROM obz_plan WHERE operacao_id = ? AND mes = ?", (op, f"{ano}-{m:02d}"))
        conn.executemany("INSERT INTO obz_plan (operacao_id, mes, conta, depto, valor) VALUES (?, ?, ?, ?, ?)",
                         [(op, r.mes, r.conta, r.depto, round(float(r.valor), 2))
                          for r in v.itertuples(index=False) if abs(float(r.valor)) >= 0.005])
        conn.execute("UPDATE obz_sim SET publicado_em = ? WHERE id = ?", (agora(), int(sim_id)))
    _log(sim_id, "publicado", f"Plan {ano} publicado ({len(v)} valores mensais)", usuario)
    return len(v)


def _notificar(uids: set, titulo: str, texto: str, chave: str) -> None:
    try:
        from repositories import motoristas_repo

        for uid in {u for u in uids if u}:
            motoristas_repo.criar_notificacao(int(uid), "obz", f"{chave}:{uid}", titulo, texto, "financeiro",
                                              agora() + ":00")
    except Exception:  # noqa: BLE001 — aviso nunca trava o fluxo
        pass


def _avisar(sim_id: int, etapa: str, usuario: dict, comentario: str) -> None:
    s = buscar(sim_id)
    nome = s["nome"]
    chave = f"obzsim:{sim_id}:{etapa}:{agora()}"
    quem = usuario.get("nome") or ""
    obs = f" Comentário: {comentario}" if comentario else ""
    if etapa == "aprov_fin":
        _notificar(set(obz.usuarios_papel("fin_dono")), f"🧮 {nome}: aguardando sua aprovação",
                   f"{quem} enviou o simulador para aprovação.{obs}", chave)
    elif etapa == "critica_conta":
        d = donos(linhas(sim_id))
        uids = set().union(*d["uids_conta"]) if len(d) else set()
        _notificar(uids, f"🧾 {nome}: critique as suas contas",
                   "O orçamento do próximo ano abriu para crítica. Confira o valor calculado das suas contas e "
                   "proponha ajustes com justificativa (Financeiro › 🧮 Simulador OBZ › 💬 Críticas).", chave)
    elif etapa == "critica_depto":
        d = donos(linhas(sim_id))
        _notificar(set(d["uid_area"].dropna().astype(int)), f"🏢 {nome}: critique o seu departamento",
                   "As contas já foram criticadas pelos donos. Revise o departamento e proponha ajustes.", chave)
    elif etapa == "revisao_fin":
        _notificar(set(obz.usuarios_papel("fin_dono")), f"🔍 {nome}: revisar as críticas",
                   f"O simulador voltou para a revisão do financeiro.{obs}", chave)
    elif etapa == "diretor":
        _notificar(set(obz.usuarios_papel("diretor")), f"🎩 {nome}: aguardando aprovação da diretoria",
                   f"O financeiro ({quem}) enviou o orçamento para aprovação.", chave)
    elif etapa == "ceo":
        _notificar(set(obz.usuarios_papel("ceo")), f"🏛️ {nome}: aguardando aprovação corporativa",
                   f"A diretoria ({quem}) aprovou. Falta a aprovação final.", chave)
    elif etapa == "publicado":
        d = donos(linhas(sim_id))
        uids = set(obz.usuarios_papel("fin_dono")) | set(d["uid_area"].dropna().astype(int))
        uids |= set().union(*d["uids_conta"]) if len(d) else set()
        _notificar(uids, f"✅ {nome} aprovado — virou o Plan de {s['ano']}",
                   "O orçamento foi aprovado pelo corporativo e já está no Plan do OBZ por conta e departamento.",
                   chave)
    elif etapa == "rascunho":
        _notificar(set(obz.usuarios_papel("fin_dono")) | set(obz.usuarios_papel("plan")),
                   f"↩️ {nome}: voltou para ajustes", f"{quem} devolveu o simulador.{obs}", chave)


# --- Reuniões -----------------------------------------------------------------------------------------------------
REUNIOES = {
    "rascunho": "🚀 Kick-off do orçamento (premissas e volume)",
    "aprov_fin": "🏦 Validação com o dono do financeiro",
    "critica_conta": "🧾 Rodada de crítica com os donos de conta",
    "critica_depto": "🏢 Fechamento por departamento",
    "revisao_fin": "🔍 Revisão financeira das críticas",
    "diretor": "🎩 Apresentação à diretoria",
    "ceo": "🏛️ Aprovação corporativa / CEO",
    "publicado": "✅ Desdobramento para a operação",
}


def pauta_sugerida(sim_id: int, etapa: str) -> str:
    s = buscar(sim_id)
    pm = s["premissas"]
    ra = resumo_areas(sim_id)
    hb, hp = hl_totais(sim_id)
    base, fin = float(ra["base"].sum()), float(ra["final"].sum())
    li = linhas(sim_id)

    def m(v):
        return obz._brl(v, 0)

    def pct(v):
        return f"{v:+.1f}%".replace(".", ",")

    linhas_p = [f"Orçamento {s['ano']} · base = histórico de {s['ano_base']}",
                f"Total: {m(base)} → {m(fin)} ({pct((fin / base - 1) * 100 if base else 0)}) · "
                + f"HL {hb:,.0f} → {hp:,.0f}".replace(",", ".")]
    if hb and hp:
        linhas_p.append(f"R$/HL: {obz._brl(base / hb)} → {obz._brl(fin / hp)}")
    if etapa == "rascunho":
        linhas_p += ["1. Premissas macro: IPCA {ipca}%, aluguel {aluguel}%, fretes {fretes}%, insumos {insumos}%"
                     .format(**pm),
                     f"2. Dissídio: {pm['dissidio_pct']}% a partir do mês {pm['dissidio_mes']}",
                     "3. Volume de HL mês a mês e QLP por departamento (acompanha o HL)",
                     "4. Iniciativas, novos gastos e capex aprovado (🏗️ Gestão de Capex)",
                     "5. Cronograma das etapas e responsáveis"]
    elif etapa in ("critica_conta", "critica_depto", "revisao_fin"):
        top = li.assign(dif=(li["final_ano"] - li["base_ano"]) * li["sinal"]).nlargest(5, "dif")
        linhas_p.append("Maiores aumentos vs histórico:")
        linhas_p += [f"  • {r.conta} {str(r.nome_conta or '')[:30]} ({r.area}): +{m(r.dif)}" for r in top.itertuples()]
        if etapa == "revisao_fin":
            linhas_p.append(f"Críticas sem decisão: {pendencias_revisao(sim_id)}")
        linhas_p += ["Pontos de atenção e justificativas", "Ações e responsáveis"]
    elif etapa in ("diretor", "ceo", "aprov_fin"):
        linhas_p.append("Por departamento:")
        linhas_p += [f"  • {r.area}: {m(r.base)} → {m(r.final)} ({pct(r.var_pct)})" if pd.notna(r.var_pct)
                     else f"  • {r.area}: {m(r.final)}" for r in ra.itertuples()]
        linhas_p += [f"Capex aprovado: {m(capex(sim_id))} · impacto no resultado: {m(capex_impacto(sim_id))}",
                     "Riscos, premissas e decisões"]
    else:
        linhas_p += ["1. Plan publicado por conta e departamento (mês a mês)",
                     "2. Metas de R$/HL por departamento", "3. Rotina mensal: tendência, dispersão e justificativas",
                     "4. Calendário de reuniões de acompanhamento"]
    return "\n".join(linhas_p)


def reunioes(sim_id: int) -> pd.DataFrame:
    return query_df("SELECT * FROM obz_sim_reuniao WHERE sim_id = ? ORDER BY data DESC, id DESC", (int(sim_id),))


def salvar_reuniao(sim_id: int, dados: dict, usuario: dict, reuniao_id: int | None = None) -> None:
    if not (dados.get("pauta") or "").strip():
        raise RegraNegocioError("Escreva a pauta da reunião.")
    campos = (dados.get("etapa"), dados.get("data"), dados.get("participantes"), dados.get("pauta"),
              dados.get("ata"), dados.get("decisoes"))
    if reuniao_id:
        execute("""UPDATE obz_sim_reuniao SET etapa = ?, data = ?, participantes = ?, pauta = ?, ata = ?, decisoes = ?
                   WHERE id = ?""", (*campos, int(reuniao_id)))
    else:
        execute("""INSERT INTO obz_sim_reuniao (sim_id, etapa, data, participantes, pauta, ata, decisoes, criado_por,
                                                criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (int(sim_id), *campos, usuario.get("nome"), agora()))


def excluir_reuniao(reuniao_id: int) -> None:
    execute("DELETE FROM obz_sim_reuniao WHERE id = ?", (int(reuniao_id),))
