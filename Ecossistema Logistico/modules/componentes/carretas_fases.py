"""🚛 Carretas agora, por fase da viagem (App Carreteiro) — com os itens do pedido de cada carreta.

Mesma métrica do Pátio: os produtos vêm da Puxada Marcada pelo número do pedido da viagem.
Fases: trânsito de ida → apresentado (espera) → carregando → carregado → trânsito de volta → na revenda.
Clica na fase → abre as carretas dela; em cada carreta, os itens do pedido."""
import datetime as dt

import pandas as pd
import streamlit as st

from core import tema, tempo, ui

FASES = [  # chave, título, ícone, etapas do app que caem nela, cor, detalhe
    ("ida", "Trânsito ida", "🛣️", ("inicio",), "info", "indo para a cervejaria"),
    ("espera", "Apresentado · espera", "🙋", ("apresentado",), "atencao", "aguardando chamada"),
    ("carregando", "Carregando", "📣", ("chamado",), "atencao", "chamado para carregar"),
    ("carregado", "Carregado", "📦", ("carregado", "agendado"), "info", "na cervejaria, já carregado"),
    ("volta", "Trânsito volta", "↩️", ("saida",), "info", "vindo para a revenda"),
    ("revenda", "Na revenda", "🏁", ("chegada",), "bom", "chegou — descarga"),
]


def dados(operacao_id: int) -> list[dict]:
    """Viagens em andamento com fase, tempo na fase e os itens do pedido (Puxada Marcada)."""
    from repositories import carreteiro_repo as repo
    from repositories import pedidos_puxada_repo as ped_repo
    from repositories import ressuprimento_repo
    from services import carreteiro_service as svc

    try:
        v = repo.viagens_df(operacao_id, de=(tempo.hoje() - dt.timedelta(days=20)).isoformat())
    except Exception:  # noqa: BLE001 — banco sem viagens ainda
        return []
    if v.empty:
        return []
    v = v[v["status"] == repo.EM_VIAGEM]
    if v.empty:
        return []
    regs = v.to_dict("records")
    nums = [n for r in regs for n in ped_repo.numeros(r.get("numero_pedido"))]
    try:
        itens = ressuprimento_repo.itens_dos_pedidos(operacao_id, nums)
    except Exception:  # noqa: BLE001
        itens = pd.DataFrame()
    if not itens.empty:
        itens = itens.assign(_n=itens["numero_pedido"].map(ressuprimento_repo._num))
    fase_de = {e: f[0] for f in FASES for e in f[3]}
    out = []
    for r in regs:
        et = svc.ultima_etapa(r)
        if not et or et not in fase_de:
            continue
        meus = {ressuprimento_repo._num(n) for n in ped_repo.numeros(r.get("numero_pedido"))} - {""}
        it = itens[itens["_n"].isin(meus)].drop(columns="_n") if not itens.empty and meus else None
        d = tempo.parse_dt(r.get(svc.ETAPAS[et]["coluna"]))
        out.append({**r, "_fase": fase_de[et], "_et": et, "_etapa": svc.ETAPAS[et]["nome"],
                    "_ha": svc.formatar_duracao((tempo.agora() - d).total_seconds() / 3600) if d else "—",
                    "_itens": it})
    return out


def _resumo(it) -> str:
    if it is None or len(it) == 0:
        return "⚠️ sem itens"
    pal = ui.numero(float(it["paletes"].sum()), 1).rstrip("0").rstrip(",")
    return f"{len(it)} item(ns) · {pal} pal · {ui.numero(float(it['cx_marcadas'].sum()))} cx"


def tabela_itens(it: pd.DataFrame) -> None:
    t = it.sort_values("paletes", ascending=False)
    ui.tabela(pd.DataFrame({"Código": [int(c) if c == c and c is not None else None for c in t["cod"]],
                            "Produto": t["descricao"], "Pedido": t["numero_pedido"],
                            "Paletes": t["paletes"].astype(float), "Caixas": t["cx_marcadas"].astype(float),
                            "HL": t["hl_marcado"].astype(float).round(2)}),
              column_config={"Código": st.column_config.NumberColumn(format="%d"),
                             "Paletes": st.column_config.NumberColumn(format="%.1f"),
                             "Caixas": st.column_config.NumberColumn(format="%.0f")}, baixar=False)


def lista_carretas(regs: list[dict], prefixo: str) -> None:
    """Uma linha por carreta (expande para ver os itens do pedido)."""
    if not regs:
        st.info("Nenhuma carreta nesta fase agora.")
        return
    for i, r in enumerate(regs):
        cab = (f"🚛 **{r.get('placa') or '—'}** · {r.get('motorista') or '—'} · Ped. {r.get('numero_pedido') or '—'} · "
               f"{r['_etapa']} há {r['_ha']} · {_resumo(r['_itens'])}")
        with st.expander(cab, expanded=len(regs) == 1):
            if r.get("destino"):
                st.caption(f"🏭 {r['destino']}")
            if r["_itens"] is None or len(r["_itens"]) == 0:
                st.caption("Pedido ainda sem itens na Puxada Marcada — atualize o relatório em 📥 Atualizar relatórios.")
            else:
                tabela_itens(r["_itens"])


@st.dialog("🚛 Carretas", width="large")
def _dialogo(titulo: str, regs: list[dict]) -> None:
    st.markdown(f"### {titulo}")
    lista_carretas(regs, "dlg")
    todos = [r["_itens"].assign(placa=r.get("placa")) for r in regs if r["_itens"] is not None and len(r["_itens"])]
    if len(todos) > 1:
        with st.expander("📋 Somar os itens desta fase"):
            t = pd.concat(todos, ignore_index=True).groupby(["cod", "descricao"], as_index=False)[
                ["paletes", "cx_marcadas"]].sum().sort_values("paletes", ascending=False)
            ui.tabela(t.rename(columns={"cod": "Código", "descricao": "Produto", "paletes": "Paletes",
                                        "cx_marcadas": "Caixas"}), baixar=False)


def cartoes(operacao_id: int, key: str, regs: list[dict] | None = None) -> None:
    """Cards por fase; clicar abre as carretas da fase com os itens."""
    regs = dados(operacao_id) if regs is None else regs
    cards = []
    for chave, tit, ic, _, cor, det in FASES:
        sel = [r for r in regs if r["_fase"] == chave]
        pal = sum(float(r["_itens"]["paletes"].sum()) for r in sel if r["_itens"] is not None and len(r["_itens"]))
        cards.append({"titulo": tit, "valor": len(sel), "icone": ic, "status": cor if sel else "neutro",
                      "detalhe": f"{det}" + (f" · {ui.numero(pal, 0)} pal" if pal else ""),
                      "ao_clicar": (lambda t=tit, s=sel: _dialogo(t, s))})
    tema.kpis(cards, key=f"kp_cf_{key}")


def faixa(operacao_id: int, key: str) -> None:
    """Resumo recolhível no topo das telas: carretas por fase (clica para abrir)."""
    try:
        regs = dados(operacao_id)
    except Exception:  # noqa: BLE001 — nunca derruba a tela
        return
    if not regs:
        return
    cont = {f[0]: sum(r["_fase"] == f[0] for r in regs) for f in FASES}
    txt = " · ".join(f"{f[2]} {cont[f[0]]} {f[1].lower()}" for f in FASES if cont[f[0]])
    with st.expander(f"🚛 Carretas agora ({len(regs)}): {txt}", expanded=False):
        st.caption("Clique numa fase para ver as carretas e, em cada uma, os itens do pedido (Puxada Marcada).")
        cartoes(operacao_id, key, regs)
