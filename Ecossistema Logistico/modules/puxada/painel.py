"""Puxada › Painel geral de fretes."""
import streamlit as st

from config.settings import StatusFrete
from core import graficos, tema, ui
from repositories import fretes_repo
from services import fretes_service as svc

_COR_STATUS = {StatusFrete.PENDENTE: "atencao", StatusFrete.APROVADO: "info", StatusFrete.FINALIZADO: "bom",
               StatusFrete.REJEITADO: "critico", StatusFrete.CANCELADO: "neutro"}


def render(usuario: dict, operacao_id: int) -> None:
    c1, c2 = st.columns([3, 1])
    status = c1.multiselect("Status", StatusFrete.TODOS, default=StatusFrete.TODOS, key="pn_status")
    mes = c2.text_input("Mês do frete (AAAA-MM)", value="", placeholder="todos", key="pn_mes")
    df = fretes_repo.listar_df(operacao_id, status or None, mes or None)

    if df.empty:
        st.info("Nenhuma cotação com esses filtros.")
        return
    df["diferenca"] = (df["valor_negociado"] - df["valor_tabela"]).where(df["valor_tabela"].notna())
    df["diferenca_pct"] = (df["diferenca"] / df["valor_tabela"] * 100).where(df["valor_tabela"] > 0)
    colunas = ["id", "status", "data_frete", "origem", "destino", "transportadora", "tipo_carga", "motivo",
               "valor_negociado", "valor_tabela", "diferenca", "diferenca_pct", "justificativa_aprovacao",
               "centro_custo", "solicitante", "aprovador", "numero_cte", "motivo_rejeicao"]
    fmt = {"valor_negociado": st.column_config.NumberColumn("Negociado", format="R$ %.2f"),
           "valor_tabela": st.column_config.NumberColumn("Cadastrado", format="R$ %.2f"),
           "diferenca": st.column_config.NumberColumn("Diferença", format="R$ %.2f"),
           "diferenca_pct": st.column_config.NumberColumn("Dif. %", format="%.1f%%"),
           "tipo_carga": "Carga", "justificativa_aprovacao": "Justificativa (valor ≠ cadastrado)"}
    pend_df = df[df["status"] == StatusFrete.PENDENTE][colunas]
    pend = len(pend_df)
    acima = df[df["valor_tabela"].notna() & (df["valor_negociado"] > df["valor_tabela"])]
    abaixo = df[df["valor_tabela"].notna() & (df["valor_negociado"] < df["valor_tabela"])]
    tema.kpis([
        {"titulo": "Cotações", "valor": len(df), "icone": "📋", "status": "info", "dados": df[colunas], "colunas": fmt},
        {"titulo": "Valor total", "valor": ui.moeda(df["valor_negociado"].sum()), "icone": "💸", "status": "info",
         "dados": df[colunas].sort_values("valor_negociado", ascending=False), "colunas": fmt},
        {"titulo": "Aguardando aprovação", "valor": pend, "icone": "⏳", "status": "atencao" if pend else "bom",
         "selo": "fila vazia" if not pend else "pendentes", "dados": pend_df, "colunas": fmt},
        {"titulo": "Acima da tabela", "valor": len(acima), "icone": "🔺",
         "detalhe": f"+{ui.moeda((acima['valor_negociado'] - acima['valor_tabela']).sum())}" if len(acima) else "",
         "status": "serio" if len(acima) else "bom", "selo": "negociar melhor" if len(acima) else "dentro da tabela",
         "dados": acima[colunas], "colunas": fmt},
        {"titulo": "Abaixo do cadastrado", "valor": len(abaixo), "icone": "🔻",
         "detalhe": f"−{ui.moeda((abaixo['valor_tabela'] - abaixo['valor_negociado']).sum())}" if len(abaixo) else "",
         "status": "bom", "dados": abaixo[colunas], "colunas": fmt},
    ], key="kp_painel")

    g1, g2 = st.columns(2)
    with g1:
        por_tr = df.groupby(df["transportadora"].fillna("—"))["valor_negociado"].sum().sort_values(ascending=False).head(8)
        base = df.assign(transportadora=df["transportadora"].fillna("—"))[colunas]
        graficos.mostrar(graficos.barras_h(por_tr.index, por_tr.values, titulo="Valor por transportadora (R$)"),
                         key="g_pn_tr", detalhe=(base, "transportadora"), colunas=fmt, titulo="Transportadora")
    with g2:
        cont = df["status"].value_counts()
        graficos.mostrar(graficos.barras_h(cont.index, cont.values,
                                           cores=[tema.STATUS[_COR_STATUS.get(s, "neutro")][0] for s in cont.index],
                                           titulo="Cotações por status"), key="g_pn_st",
                         detalhe=(df[colunas], "status"), colunas=fmt, titulo="Status")
    st.caption("🔎 Clique num card ou numa barra para ver os registros.")
    ui.tabela(df[colunas], column_config=fmt)
    ui.downloads(df[colunas], "relatorio_fretes_spot", key="dl_fretes")

    cancelaveis = df[df["status"].isin([StatusFrete.PENDENTE, StatusFrete.APROVADO])]
    if not cancelaveis.empty:
        with st.popover("🚫 Cancelar cotação"):
            cid = st.selectbox("Cotação", cancelaveis["id"].tolist(), key="pn_cancel")
            if st.button("Confirmar cancelamento", key="pn_cancel_btn"):
                ui.acao(svc.cancelar, int(cid), usuario, sucesso="Cotação cancelada.")
