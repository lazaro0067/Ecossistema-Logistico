"""Puxada › Finalizar frete: CT-e e Notas Fiscais obrigatórios; arquivos (PDF/XML) opcionais."""
import streamlit as st

from config.settings import StatusFrete
from core import tema, ui
from repositories import fretes_repo
from services import fretes_service as svc


def render(usuario: dict, operacao_id: int) -> None:
    aprovados = fretes_repo.listar_df(operacao_id, [StatusFrete.APROVADO])
    tema.secao("Finalizar frete aprovado", "Informe o CT-e e as NFs transportadas. Os arquivos ficam guardados.")
    if aprovados.empty:
        st.info("Nenhum frete aprovado aguardando finalização.")
    elif not ui.somente_leitura(operacao_id):
        rotulos = {r.id: f"#{r.id} · {r.origem} ➔ {r.destino} · {r.transportadora or '—'} · {ui.moeda(r.valor_negociado)}"
                   for r in aprovados.itertuples()}
        with st.form("f_encerrar", clear_on_submit=True):
            cid = st.selectbox("Frete", list(rotulos), format_func=rotulos.get)
            numero = st.text_input("Número / chave do CT-e *")
            nfs = st.text_area("Notas Fiscais transportadas * (separe por vírgula ou uma por linha)",
                               placeholder="NF 12345, NF 12346")
            c1, c2 = st.columns(2)
            arq_nf = c1.file_uploader("Arquivos das NFs (opcional)", type=["pdf", "xml", "jpg", "png"],
                                      accept_multiple_files=True)
            arq_cte = c2.file_uploader("Arquivo do CT-e (opcional)", type=["pdf", "xml", "jpg", "png"])
            if st.form_submit_button("🏁 Finalizar frete", type="primary"):
                arquivos = [("NF", a.name, a.getvalue()) for a in (arq_nf or [])]
                if arq_cte:
                    arquivos.append(("CT-e", arq_cte.name, arq_cte.getvalue()))
                ui.acao(svc.finalizar, int(cid), numero, nfs, arquivos, sucesso="Frete finalizado!")

    st.divider()
    tema.secao("Fretes finalizados")
    fin = fretes_repo.listar_df(operacao_id, [StatusFrete.FINALIZADO])
    cols = ["id", "data_frete", "origem", "destino", "transportadora", "valor_negociado", "numero_cte",
            "notas_fiscais", "finalizado_em"]
    ui.tabela(fin[cols] if not fin.empty else fin, column_config={
        "valor_negociado": st.column_config.NumberColumn("Valor", format="R$ %.2f")})
    if not fin.empty:
        ui.downloads(fin[cols], "fretes_finalizados", key="dl_fin")
        cid = st.selectbox("Baixar anexos do frete", fin["id"].tolist(), key="enc_dl")
        anexos = svc.anexos(int(cid))
        if not anexos:
            st.caption("Este frete não tem arquivos guardados.")
        cols_dl = st.columns(max(min(len(anexos), 4), 1))
        for i, a in enumerate(anexos):
            cols_dl[i % len(cols_dl)].download_button(f"⬇️ {a['tipo']} · {a['nome']}", a["conteudo"],
                                                      file_name=a["nome"], key=f"dl_anexo_{a['id']}")
