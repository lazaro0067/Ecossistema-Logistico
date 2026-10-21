"""🏆 Resultados da operação num mês — a mesma conta das telas do sistema, reunida para o Painel de Resultados e
para o 🤖 Agente. Cada bloco é independente: se uma base não estiver carregada, só aquele bloco fica vazio."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from core import tempo


def mes_anterior(mes: str) -> str:
    a, m = map(int, mes.split("-"))
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


def meses_disponiveis(op: int) -> list[str]:
    from services import faturamento_service as fs
    from services import produtividade_entrega_service as pe

    ms = set(fs.meses(op, "venda")) | set(fs.meses(op, "compra")) | set(pe.meses_disponiveis(op))
    atual = tempo.hoje().strftime("%Y-%m")
    return sorted(ms | {atual}, reverse=True)


def _seguro(f, *a, **k):
    try:
        return f(*a, **k)
    except Exception as e:  # noqa: BLE001 — um bloco sem base não derruba o painel
        return {"erro": f"{type(e).__name__}: {e}"}


# --- blocos --------------------------------------------------------------------------------------------------------
def vendas(op: int, mes: str) -> dict:
    from services import faturamento_service as fs

    de, ate = fs.periodo_mes(mes)
    dv = fs.dia_df(op, "venda", de, ate, fs.STATUS_PADRAO["venda"])
    if dv.empty:
        return {"vazio": True}
    v = fs.combinar(dv, fs.operacoes_do_setor("fat_venda"), fs.operacoes_do_setor("hl_venda"))
    b = fs.totais(fs.separar(dv, {"b": fs.operacoes_do_setor("fat_bonif")})["b"])
    dia = fs.serie_combinada(dv, fs.operacoes_do_setor("fat_venda"), fs.operacoes_do_setor("hl_venda"), "data")
    return {"faturamento": v["valor"], "hl": v["hl"], "rs_hl": v["rs_hl"], "notas": v["notas"],
            "dias": v["dias"], "desconto": v["desconto"], "bonificacao": b["valor"], "por_dia": dia}


def top(op: int, mes: str, tipo: str = "produtos", n: int = 15) -> pd.DataFrame:
    from services import faturamento_service as fs

    ov, oh = fs.operacoes_do_setor("fat_venda"), fs.operacoes_do_setor("hl_venda")
    st_ = fs.STATUS_PADRAO["venda"]
    d = (fs.produto_combinado(op, "venda", mes, mes, st_, ov, oh) if tipo == "produtos"
         else fs.cliente_combinado(op, "venda", mes, mes, st_, ov, oh))
    return d.head(n)


def compras(op: int, mes: str) -> dict:
    from services import faturamento_service as fs

    de, ate = fs.periodo_mes(mes)
    dc = fs.dia_df(op, "compra", de, ate, fs.STATUS_PADRAO["compra"])
    if dc.empty:
        return {"vazio": True}
    c = fs.combinar(dc, fs.operacoes_do_setor("compra"), fs.operacoes_do_setor("hl_compra"))
    return {"compras": c["valor"], "hl": c["hl"], "rs_hl": c["rs_hl"], "notas": c["notas"]}


def dre(op: int, mes: str) -> dict:
    from services import estoque_valor_service as ev

    r = ev.dre_mes(op, mes)
    bruta = r["receita_bruta"] or 0.0
    return {"receita_bruta": bruta, "receita_liquida": r["receita"], "cmv": r["cmv"], "lucro_bruto": r["lucro_bruto"],
            "margem_bruta": (r["lucro_bruto"] / bruta * 100) if r["lucro_bruto"] is not None and bruta else None,
            "despesas": r["despesas"], "resultado": r["resultado"],
            "margem_operacional": (r["resultado"] / bruta * 100) if r["resultado"] is not None and bruta else None,
            "fechado": bool(r.get("fechado")), "estoque_ok": bool(r["ok"]),
            "departamentos": r["obz"][["pacote", "realizado", "orcado"]].rename(
                columns={"pacote": "departamento"}) if r["despesas"] is not None else pd.DataFrame(),
            "_bruto": r}


def entrega(op: int, mes: str) -> dict:
    from services import faturamento_service as fs
    from services import produtividade_entrega_service as pe

    de, ate = fs.periodo_mes(mes)
    b = pe.base(op, de, ate)
    if b.empty:
        return {"vazio": True}
    r = pe.resumo(b)
    out = {k: r.get(k) for k in ("viagens", "placas", "dias", "entregas", "hl", "ocup_efetiva", "km_total",
                                 "hl_viagem", "entregas_viagem", "eficiencia")}
    out["por_veiculo"] = pe.por_veiculo(b)
    try:
        base_mod = b[b["veiculo"].isin(pe.ordem_modais(b))]
        m = pe.modais(base_mod) if not base_mod.empty else {}
        if m:
            out["modal_certo_pct"] = m["certo"] / m["total"] * 100
            out["cabe_menor"] = m["menor"]
            out["precisa_maior"] = m["maior"]
            out["frota_sugerida"] = m["previsao"][["modal", "placas_atuais", "atual_max", "sugerido"]]
    except Exception:  # noqa: BLE001
        pass
    return out


def shelf(op: int) -> dict:
    from services import idade_service as ids

    r = ids.risco_shelf(op)
    if r.empty:
        return {"vazio": True, "produtos": 0, "valor": 0.0}
    return {"produtos": len(r), "valor": float(r["vencer_valor"].fillna(0).sum()),
            "caixas": float(r["vencer_cx"].fillna(0).sum()), "lista": r}


def acuracidade(op: int) -> dict:
    from services import inventario_service as inv

    invs = inv.inventarios(op)
    if invs.empty:
        return {"vazio": True}
    i = invs.iloc[0]
    r = inv.resultado(int(i["id"]))
    fech = r[~r["situacao"].isin(["⏳ pendente", "❔ sem conversão"])]
    ok = int((fech["situacao"] == "✅ ok").sum())
    return {"inventario": f"{i['nome']} ({i['mes']})", "acuracidade": ok / len(fech) * 100 if len(fech) else None,
            "produtos": len(r), "sobra_cx": float(r.loc[r["dif_cx"] > 0, "dif_cx"].sum()),
            "falta_cx": float(r.loc[r["dif_cx"] < 0, "dif_cx"].sum()), "lista": r}


def resumo_mes(op: int, mes: str) -> dict:
    """Todos os blocos do mês e do mês anterior (para a comparação)."""
    ant = mes_anterior(mes)
    return {"mes": mes, "anterior": ant,
            "vendas": _seguro(vendas, op, mes), "vendas_ant": _seguro(vendas, op, ant),
            "compras": _seguro(compras, op, mes), "compras_ant": _seguro(compras, op, ant),
            "dre": _seguro(dre, op, mes), "dre_ant": _seguro(dre, op, ant),
            "entrega": _seguro(entrega, op, mes), "entrega_ant": _seguro(entrega, op, ant),
            "shelf": _seguro(shelf, op), "acuracidade": _seguro(acuracidade, op)}


def evolucao(op: int, n: int = 12, ate: str | None = None) -> pd.DataFrame:
    """Faturamento, HL, compras e resultado operacional dos últimos n meses."""
    from services import estoque_valor_service as ev
    from services import faturamento_service as fs

    ate = ate or tempo.hoje().strftime("%Y-%m")
    ms = [ate]
    for _ in range(n - 1):
        ms.append(mes_anterior(ms[-1]))
    ms = sorted(ms)
    de, fim = fs.periodo_mes(ms[0])[0], fs.periodo_mes(ms[-1])[1]
    dv = fs.dia_df(op, "venda", de, fim, fs.STATUS_PADRAO["venda"])
    sv = fs.serie_combinada(dv, fs.operacoes_do_setor("fat_venda"), fs.operacoes_do_setor("hl_venda"), "mes")
    dc = fs.dia_df(op, "compra", de, fim, fs.STATUS_PADRAO["compra"])
    sc = fs.serie_combinada(dc, fs.operacoes_do_setor("compra"), fs.operacoes_do_setor("hl_compra"), "mes")
    out = pd.DataFrame({"mes": ms})
    out = out.merge(sv[["mes", "valor", "hl"]].rename(columns={"valor": "faturamento"}), on="mes", how="left")
    out = out.merge(sc[["mes", "valor"]].rename(columns={"valor": "compras"}), on="mes", how="left")
    res = []
    for m in ms:
        try:
            r = ev.dre_mes(op, m)
            res.append(r["resultado"])
        except Exception:  # noqa: BLE001
            res.append(None)
    out["resultado"] = res
    return out


def hoje() -> dt.date:
    return tempo.hoje()
