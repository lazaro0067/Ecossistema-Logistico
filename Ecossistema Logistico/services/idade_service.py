"""📅 Armazém › Gestão de Idade (FEFO e vencimentos).

Base: relatório de contagens do WMS com validade (o mesmo da acuracidade): C = Tarefa (área/rua), D = endereço,
E = usuário, H = finalização, I = produto, K = quantidade, L = unidade (PL/LST/CX/UN), M = validade aferida.
Quantidades viram unidade de venda (caixa) pelas conversões da 01.11 (as mesmas do inventário).

- Quebra de FEFO no picking: o estoque (pulmão) tem validade MAIS ANTIGA do que alguma validade que está no picking
  — o picking vai sair antes com produto mais novo. Pede para corrigir (abastecer com a validade mais antiga).
- FEFO estoque × estoque: por rua, onde está a validade mais antiga de cada produto (mistura de validades).
- Contagem × contagem: entre duas contagens, uma validade mais nova diminuiu enquanto uma mais antiga ficou parada
  = saiu o mais novo primeiro (quebra de FEFO na operação).
- Qualidade do armazém = produtos sem quebra ÷ produtos contados.
- Vencimentos (≤30, 31–60, 61–90 dias): quantidade, valor (custo da 02.05.02), linear de venda, dias limite
  (cadastro), previsão de vencer pela linear (FEFO: as validades mais antigas saem primeiro) e última puxada (03.02.37
  compra). O que tem previsão de vencer aparece no Ressuprimento como 🧊 risco de shelf (não comprar).
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services import inventario_service as inv
from services.erros import RegraNegocioError

FAIXAS = {"vencido": "⛔ Vencido", "30": "🔴 Até 30 dias", "60": "🟠 31 a 60 dias", "90": "🟡 61 a 90 dias"}
TIPOS_AREA = {"picking": "🛒 Picking", "estoque": "🧱 Estoque (pulmão)", "ignorar": "🚫 Não considerar"}
DIAS_LIMITE_PADRAO = 15


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


def hoje() -> dt.date:
    return tempo.hoje()


def _data(v) -> str | None:
    d = pd.to_datetime(str(v or "").strip(), format="%d/%m/%Y", errors="coerce")
    if pd.isna(d):
        d = pd.to_datetime(str(v or "").strip()[:10], dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def _br(iso) -> str:
    try:
        return pd.to_datetime(iso).strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        return str(iso or "—")


# --- importação ---------------------------------------------------------------------------------------------------
def ler(conteudo: bytes) -> pd.DataFrame:
    df = inv.ler_contagem(conteudo)
    if "validade" not in df or not df["validade"].astype(str).str.strip().any():
        raise RegraNegocioError("O relatório não tem a validade (coluna M “Validade Aferida”).")
    df["validade"] = df["validade"].map(_data)
    return df


def importar(operacao_id: int, conteudo: bytes, nome: str, usuario: str = "") -> dict:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para subir a contagem.")
    df = ler(conteudo)
    if df.empty:
        raise RegraNegocioError("Nenhuma linha de contagem no arquivo.")
    datas = pd.to_datetime(df["finalizacao"].fillna(df["inicio"]), errors="coerce").dropna()
    data = (datas.max() if len(datas) else pd.Timestamp(hoje())).strftime("%Y-%m-%d")
    conv = inv.conversoes(None, df["produto"].unique().tolist()).set_index("produto").to_dict("index")
    mult, uncx = [], []
    for u, p in zip(df["unidade"], df["produto"]):
        c = conv.get(p, {"un_cx_f": 1.0})
        mult.append(inv._multiplicador(u, c))
        uncx.append(float(c.get("un_cx_f") or 1.0))
    df["qtd_un"] = pd.to_numeric(pd.Series(mult, index=df.index), errors="coerce") * df["qtd"]
    df["un_cx"] = uncx
    _garantir_areas(operacao_id, df["area"].unique().tolist())
    with get_conn() as conn:
        ant = conn.execute("SELECT id FROM idade_contagens WHERE operacao_id = ? AND data = ?",
                           (int(operacao_id), data)).fetchall()
        for a in ant:
            conn.execute("DELETE FROM idade_itens WHERE contagem_id = ?", (int(a[0]),))
            conn.execute("DELETE FROM idade_contagens WHERE id = ?", (int(a[0]),))
    cid = execute("INSERT INTO idade_contagens (operacao_id, data, nome, arquivo, linhas, criado_por, criado_em) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?)", (int(operacao_id), data, f"Contagem {_br(data)}", str(nome)[:200],
                                                   len(df), usuario, agora()))
    with get_conn() as conn:
        conn.executemany("INSERT INTO idade_itens (contagem_id, area, endereco, produto, descricao, qtd, unidade, "
                         "qtd_un, un_cx, validade, usuario) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         [(cid, r.area, r.endereco or "", r.produto, r.descricao, float(r.qtd), r.unidade,
                           None if pd.isna(r.qtd_un) else float(r.qtd_un), float(r.un_cx), r.validade, r.usuario)
                          for r in df.itertuples(index=False)])
    return {"id": cid, "data": data, "linhas": len(df), "produtos": df["produto"].nunique(),
            "sem_validade": int(df["validade"].isna().sum()), "sem_conversao": int(df["qtd_un"].isna().sum()),
            "substituiu": bool(ant)}


def contagens(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT * FROM idade_contagens WHERE {trecho} ORDER BY data DESC, id DESC", p)


def excluir_contagem(cid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM idade_itens WHERE contagem_id = ?", (int(cid),))
        conn.execute("DELETE FROM idade_contagens WHERE id = ?", (int(cid),))


# --- cadastros ----------------------------------------------------------------------------------------------------
def _tipo_auto(area: str) -> str:
    a = inv._norm(area)
    return "picking" if "pick" in a or re.search(r"\bpk\b", a) else "estoque"


def _garantir_areas(operacao_id: int, nomes: list[str]) -> None:
    ja = set(query_df("SELECT area FROM idade_areas WHERE operacao_id = ?", (int(operacao_id),))["area"])
    novas = [a for a in nomes if a and a not in ja]
    if novas:
        with get_conn() as conn:
            conn.executemany("INSERT INTO idade_areas (operacao_id, area, tipo) VALUES (?, ?, ?)",
                             [(int(operacao_id), a, _tipo_auto(a)) for a in novas])


def areas(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT area, MAX(tipo) AS tipo FROM idade_areas WHERE {trecho} GROUP BY area ORDER BY area", p)


def salvar_areas(operacao_id: int, linhas: list[dict]) -> None:
    with get_conn() as conn:
        for r in linhas:
            if r.get("tipo") not in TIPOS_AREA:
                continue
            conn.execute("UPDATE idade_areas SET tipo = ? WHERE operacao_id = ? AND area = ?",
                         (r["tipo"], int(operacao_id), r["area"]))


def limites(operacao_id: int) -> tuple[int, pd.DataFrame]:
    """(dias limite padrão, exceções por produto). Dias limite = quantos dias antes de vencer o produto precisa ter
    saído (não pode mais vender/estar disponível)."""
    ids = operacoes_repo.ids_efetivos(operacao_id)
    ph = ", ".join("?" * len(ids))
    d = query_df(f"SELECT produto, MAX(dias) AS dias FROM idade_limites WHERE operacao_id IN ({ph}) GROUP BY produto",
                 ids)
    pad = d.loc[d["produto"] == "*", "dias"]
    padrao = int(pad.iloc[0]) if len(pad) and pd.notna(pad.iloc[0]) else DIAS_LIMITE_PADRAO
    return padrao, d[d["produto"] != "*"].reset_index(drop=True)


def salvar_limites(operacao_id: int, padrao: int, excecoes: list[dict]) -> int:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para cadastrar os dias limite.")
    if padrao is None or int(padrao) < 0:
        raise RegraNegocioError("Dias limite padrão inválido.")
    linhas = [("*", int(padrao))]
    for r in excecoes:
        p = inv._cod(r.get("produto"))
        d = r.get("dias")
        if p == "0" or d is None or pd.isna(d):
            continue
        linhas.append((p, int(d)))
    with get_conn() as conn:
        conn.execute("DELETE FROM idade_limites WHERE operacao_id = ?", (int(operacao_id),))
        conn.executemany("INSERT INTO idade_limites (operacao_id, produto, dias) VALUES (?, ?, ?)",
                         [(int(operacao_id), p, d) for p, d in linhas])
    return len(linhas) - 1


# --- leitura da contagem --------------------------------------------------------------------------------------------
def itens(cid: int) -> pd.DataFrame:
    c = query_one("SELECT operacao_id FROM idade_contagens WHERE id = ?", (int(cid),))
    df = query_df("SELECT area, endereco, produto, descricao, qtd, unidade, qtd_un, un_cx, validade, usuario "
                  "FROM idade_itens WHERE contagem_id = ?", (int(cid),))
    if df.empty or not c:
        return df.assign(tipo=pd.Series(dtype=str), qtd_cx=pd.Series(dtype=float))
    ar = areas(int(c["operacao_id"]))
    tipos = dict(zip(ar["area"], ar["tipo"]))
    df["tipo"] = df["area"].map(tipos).fillna(df["area"].map(_tipo_auto))
    df = df[df["tipo"] != "ignorar"].copy()
    for k in ("qtd", "qtd_un", "un_cx"):
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df["un_cx"] = df["un_cx"].fillna(1.0).where(df["un_cx"] > 0, 1.0)
    df["qtd_cx"] = df["qtd_un"] / df["un_cx"]
    df["endereco"] = df["endereco"].fillna("")
    df["descricao"] = df["descricao"].fillna("").astype(str).str.strip()
    return df.reset_index(drop=True)


def _lista_val(s: pd.Series) -> str:
    return ", ".join(_br(v) for v in sorted(set(s.dropna())))


# --- 🔁 FEFO no picking --------------------------------------------------------------------------------------------
def fefo_picking(cid: int) -> pd.DataFrame:
    """Produto em que o estoque tem validade mais antiga do que alguma validade do picking."""
    df = itens(cid)
    df = df[df["validade"].notna()]
    pk, es = df[df["tipo"] == "picking"], df[df["tipo"] == "estoque"]
    if pk.empty or es.empty:
        return pd.DataFrame()
    linhas = []
    for prod, p in pk.groupby("produto"):
        e = es[es["produto"] == prod]
        if e.empty:
            continue
        v_es, v_pk_max, v_pk_min = e["validade"].min(), p["validade"].max(), p["validade"].min()
        if v_es >= v_pk_max:
            continue
        mais_velho = e[e["validade"] == v_es]
        mais_novo_pk = p[p["validade"] > v_es]
        linhas.append({
            "produto": prod, "descricao": p["descricao"].iloc[0],
            "picking_end": ", ".join(sorted(set(p["endereco"]))), "picking_area": ", ".join(sorted(set(p["area"]))),
            "picking_validades": _lista_val(p["validade"]), "picking_mais_nova": v_pk_max, "picking_mais_velha": v_pk_min,
            "estoque_validade": v_es, "estoque_end": ", ".join(sorted(set(mais_velho["endereco"]))),
            "estoque_area": ", ".join(sorted(set(mais_velho["area"]))),
            "estoque_cx": float(mais_velho["qtd_cx"].sum(skipna=True)),
            "picking_cx_novo": float(mais_novo_pk["qtd_cx"].sum(skipna=True)),
            "dias_dif": (pd.to_datetime(v_pk_max) - pd.to_datetime(v_es)).days,
        })
    out = pd.DataFrame(linhas)
    if out.empty:
        return out
    out["acao"] = [f"Abastecer o picking ({pe}) com a validade {_br(v)} do endereço {ee} ({ea}) antes da "
                   f"{_br(n)}" for pe, v, ee, ea, n in zip(out["picking_end"], out["estoque_validade"],
                                                            out["estoque_end"], out["estoque_area"],
                                                            out["picking_mais_nova"])]
    return out.sort_values("dias_dif", ascending=False).reset_index(drop=True)


# --- 🧱 FEFO estoque × estoque (por rua) ------------------------------------------------------------------------------
def estoque_por_rua(cid: int) -> pd.DataFrame:
    """Produtos com mais de uma validade no estoque: onde está a mais antiga (sai primeiro) e onde estão as outras."""
    df = itens(cid)
    df = df[(df["tipo"] == "estoque") & df["validade"].notna()]
    linhas = []
    for prod, e in df.groupby("produto"):
        vs = sorted(e["validade"].unique())
        if len(vs) < 2:
            continue
        for v in vs:
            x = e[e["validade"] == v]
            linhas.append({"produto": prod, "descricao": e["descricao"].iloc[0], "validade": v,
                           "ordem": vs.index(v) + 1, "validades": len(vs), "ruas": ", ".join(sorted(set(x["area"]))),
                           "enderecos": ", ".join(sorted(set(x["endereco"]))), "qtd_cx": float(x["qtd_cx"].sum())})
    return pd.DataFrame(linhas)


def resumo_ruas(cid: int) -> pd.DataFrame:
    df = itens(cid)
    df = df[df["validade"].notna()]
    if df.empty:
        return pd.DataFrame()
    mais_velha = df[df["tipo"] == "estoque"].groupby("produto")["validade"].min()
    df["e_mais_velha"] = df["validade"] == df["produto"].map(mais_velha)
    g = df.groupby(["area", "tipo"]).agg(enderecos=("endereco", "nunique"), produtos=("produto", "nunique"),
                                        caixas=("qtd_cx", "sum"), validade_min=("validade", "min"),
                                        validade_max=("validade", "max")).reset_index()
    mix = (df[df["tipo"] == "estoque"].groupby(["area", "produto"])["validade"].nunique() > 1).groupby("area").sum()
    g["produtos_mistos"] = g["area"].map(mix).fillna(0).astype(int)
    return g


# --- 🔄 contagem × contagem ---------------------------------------------------------------------------------------
def fefo_contagens(cid_ant: int, cid: int) -> pd.DataFrame:
    """Saiu validade mais nova enquanto uma mais antiga ficou parada (quantidade igual ou maior)."""
    a, b = itens(cid_ant), itens(cid)
    a, b = a[a["validade"].notna()], b[b["validade"].notna()]
    if a.empty or b.empty:
        return pd.DataFrame()
    qa = a.groupby(["produto", "validade"])["qtd_cx"].sum()
    qb = b.groupby(["produto", "validade"])["qtd_cx"].sum()
    desc = dict(zip(pd.concat([a, b])["produto"], pd.concat([a, b])["descricao"]))
    linhas = []
    for prod in sorted(set(qa.index.get_level_values(0)) & set(qb.index.get_level_values(0))):
        va, vb = qa.loc[prod], qb.loc[prod]
        vals = sorted(set(va.index) | set(vb.index))
        for v_novo in vals:
            antes, depois = float(va.get(v_novo, 0.0)), float(vb.get(v_novo, 0.0))
            saiu = antes - depois
            if saiu <= 0.01:
                continue
            paradas = [v for v in vals if v < v_novo and float(va.get(v, 0.0)) > 0.01
                       and float(vb.get(v, 0.0)) >= float(va.get(v, 0.0)) - 0.01]
            if not paradas:
                continue
            v_velho = min(paradas)
            linhas.append({"produto": prod, "descricao": desc.get(prod, ""), "validade_saiu": v_novo,
                           "saiu_cx": saiu, "validade_parada": v_velho, "parada_cx": float(vb.get(v_velho, 0.0)),
                           "dias_dif": (pd.to_datetime(v_novo) - pd.to_datetime(v_velho)).days})
    return pd.DataFrame(linhas)


def anterior(operacao_id: int, cid: int) -> int | None:
    c = contagens(operacao_id)
    c = c[c["id"].astype(int) != int(cid)]
    atual = query_one("SELECT data FROM idade_contagens WHERE id = ?", (int(cid),))
    if not atual:
        return None
    c = c[c["data"].astype(str) < str(atual["data"])]
    return int(c["id"].iloc[0]) if len(c) else None


def qualidade(operacao_id: int, cid: int) -> dict:
    df = itens(cid)
    prods = set(df.loc[df["validade"].notna(), "produto"])
    pk = fefo_picking(cid)
    ant = anterior(operacao_id, cid)
    cc = fefo_contagens(ant, cid) if ant else pd.DataFrame()
    q_pk = set(pk["produto"]) if not pk.empty else set()
    q_cc = set(cc["produto"]) if not cc.empty else set()
    quebra = q_pk | q_cc
    n = len(prods)
    return {"produtos": n, "quebra_picking": len(q_pk), "quebra_contagem": len(q_cc), "quebras": len(quebra),
            "pct": (n - len(quebra)) / n * 100 if n else None, "anterior": ant}


# --- ⏳ vencimentos -----------------------------------------------------------------------------------------------
def _linear(operacao_id: int, produtos: list[str]) -> dict:
    """Linear de venda (cx/dia): a do Ressuprimento; sem ela, a média dos últimos 30 dias da 03.02.37 vendas."""
    out = {}
    try:
        from services import armazem_service

        pos = armazem_service.posicao_com_indicadores(operacao_id)
        if not pos.empty:
            out = {inv._cod(c): float(v) for c, v in zip(pos["cod"], pos["linear_cx_dia"]) if v and v > 0}
    except Exception:  # noqa: BLE001
        out = {}
    falta = [p for p in produtos if p not in out]
    if falta:
        try:
            from services import faturamento_service as fs

            ops = fs.operacoes_do_setor("hl_venda")
            de = (hoje() - dt.timedelta(days=30)).isoformat()
            trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
            ph = ", ".join("?" * len(ops)) if ops else "''"
            v = query_df(f"SELECT produto, SUM(qtde) AS q FROM notas_prod_dia WHERE {trecho} AND origem = 'venda' "
                         f"AND status = 'A' AND data >= ? AND operacao_cod IN ({ph}) GROUP BY produto",
                         (*p, de, *ops))
            for c, q in zip(v["produto"], v["q"]):
                k = inv._cod(c)
                if k in falta and q and float(q) > 0:
                    out[k] = float(q) / 30.0
        except Exception:  # noqa: BLE001
            pass
    return out


def _custo_cx(operacao_id: int) -> dict:
    """Custo por caixa do último 02.05.02 subido (📥 Relatórios › saldo de estoque)."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    u = query_one(f"SELECT mes, tipo_saldo FROM estoque_saldos WHERE {trecho} ORDER BY mes DESC, "
                  f"CASE WHEN tipo_saldo = 'final' THEN 0 ELSE 1 END LIMIT 1", p)
    if not u:
        return {}
    d = query_df(f"SELECT produto, SUM(valor) AS valor, SUM(qtd_venda) AS q FROM estoque_saldos WHERE {trecho} AND "
                 f"mes = ? AND tipo_saldo = ? GROUP BY produto", (*p, u["mes"], u["tipo_saldo"]))
    out = {}
    for c, v, q in zip(d["produto"], d["valor"], d["q"]):
        if q and float(q) > 0 and v:
            out[inv._cod(c)] = float(v) / float(q)
    return out


def _ultima_puxada(operacao_id: int) -> dict:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    d = query_df(f"SELECT produto, MAX(data) AS d FROM notas_prod_dia WHERE {trecho} AND origem = 'compra' "
                 f"GROUP BY produto", p)
    out = {}
    for c, x in zip(d["produto"], d["d"]):
        k = inv._cod(c)
        if x and (k not in out or str(x) > out[k]):
            out[k] = str(x)[:10]
    return out


def vencimentos(operacao_id: int, cid: int, ate_dias: int = 90) -> pd.DataFrame:
    """Uma linha por produto × validade (todas as áreas somadas) que vence em até `ate_dias` (e os vencidos)."""
    df = itens(cid)
    df = df[df["validade"].notna()]
    cols = ["produto", "descricao", "validade", "qtd_cx", "dias", "faixa", "custo_cx", "valor", "linear",
            "dias_limite", "dias_disp", "sai_cx", "vencer_cx", "vencer_valor", "ultima_puxada", "situacao", "enderecos"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    g = df.groupby(["produto", "validade"]).agg(descricao=("descricao", "first"), qtd_cx=("qtd_cx", "sum"),
                                                enderecos=("endereco", lambda s: ", ".join(sorted(set(s))))) \
        .reset_index().sort_values(["produto", "validade"])
    h = pd.Timestamp(hoje())
    g["dias"] = (pd.to_datetime(g["validade"]) - h).dt.days
    lin = _linear(operacao_id, g["produto"].unique().tolist())
    custo = _custo_cx(operacao_id)
    ult = _ultima_puxada(operacao_id)
    padrao, exc = limites(operacao_id)
    lim = dict(zip(exc["produto"].astype(str), exc["dias"])) if not exc.empty else {}
    g["linear"] = g["produto"].map(lin)
    g["custo_cx"] = g["produto"].map(custo)
    g["valor"] = g["qtd_cx"] * g["custo_cx"]
    g["dias_limite"] = g["produto"].map(lambda p_: int(lim.get(p_, padrao)))
    g["dias_disp"] = (g["dias"] - g["dias_limite"]).clip(lower=0)
    # FEFO: as validades mais antigas consomem a venda primeiro
    sai, vencer = [], []
    for prod, x in g.groupby("produto", sort=False):
        ln = float(lin.get(prod) or 0.0)
        usado = 0.0
        for r in x.itertuples():
            q = float(r.qtd_cx) if pd.notna(r.qtd_cx) else 0.0
            if ln <= 0 and r.dias >= 0:  # sem linear: não dá para prever
                sai.append((r.Index, float("nan")))
                vencer.append((r.Index, float("nan")))
                continue
            cap = max(ln * float(r.dias_disp) - usado, 0.0)
            s_ = min(q, cap)
            usado += s_
            sai.append((r.Index, s_))
            vencer.append((r.Index, q - s_))
    g["sai_cx"] = pd.Series(dict(sai))
    g["vencer_cx"] = pd.to_numeric(pd.Series(dict(vencer)), errors="coerce").clip(lower=0)
    g.loc[g["vencer_cx"] < 0.5, "vencer_cx"] = 0.0
    g["vencer_valor"] = g["vencer_cx"] * g["custo_cx"]
    g["ultima_puxada"] = g["produto"].map(ult)
    g["faixa"] = pd.cut(g["dias"], [-10 ** 6, -1, 30, 60, 90, 10 ** 6], labels=["vencido", "30", "60", "90", "mais"]) \
        .astype(str)
    g["situacao"] = ["⛔ Vencido" if d < 0 else "❔ Sem linear" if not lin.get(p_) else
                     f"🔴 Vai vencer {v:,.0f} cx".replace(",", ".") if v > 0 else "🟢 Sai a tempo"
                     for d, p_, v in zip(g["dias"], g["produto"], g["vencer_cx"])]
    g = g[g["dias"] <= ate_dias]
    return g[cols].reset_index(drop=True)


def ultima_contagem(operacao_id: int) -> int | None:
    c = contagens(operacao_id)
    return int(c["id"].iloc[0]) if len(c) else None


def risco_shelf(operacao_id: int) -> pd.DataFrame:
    """Para o Ressuprimento: produtos da última contagem com previsão de vencer (não comprar)."""
    cid = ultima_contagem(operacao_id)
    if not cid:
        return pd.DataFrame()
    v = vencimentos(operacao_id, cid, ate_dias=10 ** 5)
    v = v[(v["vencer_cx"] > 0) | (v["dias"] < 0)]
    if v.empty:
        return v
    return (v.groupby("produto", as_index=False)
            .agg(descricao=("descricao", "first"), validade=("validade", "min"), dias=("dias", "min"),
                 vencer_cx=("vencer_cx", "sum"), vencer_valor=("vencer_valor", lambda s_: s_.sum(min_count=1)),
                 linear=("linear", "first"),
                 ultima_puxada=("ultima_puxada", "first"))
            .sort_values("dias").reset_index(drop=True))


def pedir_correcao(operacao_id: int, cid: int, usuario: dict) -> int:
    """Avisa os responsáveis do armazém (🎯 Acuracidade › Cadastros) das quebras de FEFO no picking."""
    q = fefo_picking(cid)
    if q.empty:
        raise RegraNegocioError("Nenhuma quebra de FEFO no picking para corrigir.")
    from repositories import motoristas_repo

    uids = inv.responsaveis(operacao_id)
    if not uids:
        raise RegraNegocioError("Cadastre os responsáveis em 🎯 Acuracidade › ⚙️ Cadastros › Responsáveis.")
    lista = "; ".join(f"{r.produto} {str(r.descricao)[:25]}: {r.acao}" for r in q.head(15).itertuples())
    for uid in uids:
        motoristas_repo.criar_notificacao(
            uid, "idade", f"fefo_pk:{operacao_id}:{cid}:{agora()}:{uid}",
            f"🔁 Corrigir FEFO no picking — {len(q)} produto(s)",
            f"{usuario.get('nome', '')} pediu a correção: {lista}" + (" …" if len(q) > 15 else ""), "armazem", agora())
    return len(uids)

