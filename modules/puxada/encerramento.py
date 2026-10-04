"""Puxada › Encerramento do frete (anexo de NF e CT-e)."""
import streamlit as st

from config.settings import StatusFrete
from core import ui
from repositories import fretes_repo
from services import fretes_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    aprovados = fretes_repo.listar_df(operacao_id, [StatusFrete.APROVADO])
    st.subheader("Encerrar frete aprovado")
    if aprovados.empty:
        st.info("Nenhum frete aprovado aguardando encerramento.")
    else:
        rotulos = {r.id: f"#{r.id} · {r.origem} ➔ {r.destino} · {ui.moeda(r.valor_negociado)}"
                   for r in aprovados.itertuples()}
        with st.form("f_encerrar", clear_on_submit=True):
            cid = st.selectbox("Frete", list(rotulos), format_func=rotulos.get)
            numero = st.text_input("Número do CT-e")
            c1, c2 = st.columns(2)
            nf = c1.file_uploader("Nota Fiscal", type=["pdf", "xml", "jpg", "png"])
            cte = c2.file_uploader("CT-e", type=["pdf", "xml", "jpg", "png"])
            if st.form_submit_button("Finalizar frete", type="primary"):
                ui.acao(svc.finalizar, int(cid), numero,
                        (nf.name, nf.getvalue()) if nf else None,
                        (cte.name, cte.getvalue()) if cte else None,
                        sucesso="Frete finalizado!")

    st.divider()
    st.subheader("Fretes finalizados")
    fin = fretes_repo.listar_df(operacao_id, [StatusFrete.FINALIZADO])
    ui.tabela(fin[["id", "data_frete", "origem", "destino", "transportadora", "valor_negociado",
                   "numero_cte", "finalizado_em"]] if not fin.empty else fin)
    if not fin.empty:
        cid = st.selectbox("Baixar anexos do frete", fin["id"].tolist(), key="enc_dl")
        anexos = svc.anexos(int(cid))
        if not anexos:
            st.caption("Este frete não tem arquivos guardados.")
        cols = st.columns(max(len(anexos), 1))
        for col, a in zip(cols, anexos):
            col.download_button(f"⬇️ {a['tipo']} · {a['nome']}", a["conteudo"], file_name=a["nome"],
                                key=f"dl_anexo_{a['id']}")
