"""Puxada › Vincular pedido carregado à carreta, fábrica, transportadora, motorista e NFs."""
import datetime as dt

import streamlit as st

from core import tema, tempo, ui
from repositories import cadastros_repo, logistica_repo
from services.erros import RegraNegocioError


def _salvar(operacao_id, vid, pedido, data, placa, fabrica, transp, motorista, nfs, hl):
    if not (pedido or "").strip():
        raise RegraNegocioError("Informe o número do pedido.")
    nfs_limpas = ", ".join(x.strip() for x in (nfs or "").replace("\n", ",").split(",") if x.strip())
    logistica_repo.salvar_vinculo(operacao_id, vid, {
        "numero_pedido": pedido.strip(), "data_puxada": data.isoformat(), "placa": placa, "fabrica": fabrica,
        "transportadora": transp, "motorista": motorista, "notas_fiscais": nfs_limpas, "hl_carregado": hl})


def render(usuario: dict, operacao_id: int) -> None:
    tema.secao("Vincular pedido carregado & NFs",
               "Depois que o pedido carrega, registre a carreta, a fábrica, o motorista e as NFs (uma ou várias).")
    if ui.somente_leitura(operacao_id):
        ui.tabela(logistica_repo.vinculos_df(operacao_id))
        return
    carretas = logistica_repo.carretas_df(operacao_id)["placa"].tolist()
    fabricas = logistica_repo.fabricas_df()["nome"].tolist()
    transps = [t["nome"] for t in cadastros_repo.listar_transportadoras()]
    motoristas = logistica_repo.motoristas_df(operacao_id)["nome"].tolist()
    if not (carretas and fabricas and transps and motoristas):
        st.warning("Complete os cadastros de **carretas, fábricas, transportadoras e motoristas** em ⚙️ Cadastros.")

    vinc = logistica_repo.vinculos_df(operacao_id)
    modo = st.radio("Ação", ["➕ Novo vínculo", "✏️ Editar vínculo"], horizontal=True, key="vinc_modo")
    atual = {}
    if modo.startswith("✏️"):
        if vinc.empty:
            st.info("Nenhum vínculo para editar.")
            return
        rot = {r.id: f"#{r.id} · Pedido {r.numero_pedido} ({r.data_puxada})" for r in vinc.itertuples()}
        vid = st.selectbox("Vínculo", list(rot), format_func=rot.get, key="vinc_sel")
        atual = vinc[vinc["id"] == vid].iloc[0].to_dict()
    else:
        vid = None

    def idx(lista, valor):
        return lista.index(valor) if valor in lista else 0

    with st.form(f"f_vinc_{vid}", clear_on_submit=vid is None):
        a, b, c = st.columns(3)
        pedido = a.text_input("Número do pedido *", value=atual.get("numero_pedido", ""))
        data_atual = dt.date.fromisoformat(atual["data_puxada"]) if atual.get("data_puxada") else tempo.hoje()
        data = b.date_input("Data da puxada", value=data_atual, format="DD/MM/YYYY")
        hl = c.number_input("HL carregado", min_value=0.0, value=float(atual.get("hl_carregado") or 0))
        d, e, f, g = st.columns(4)
        placa = d.selectbox("Carreta", carretas or ["—"], index=idx(carretas, atual.get("placa")))
        fabrica = e.selectbox("Fábrica", fabricas or ["—"], index=idx(fabricas, atual.get("fabrica")))
        transp = f.selectbox("Transportadora", transps or ["—"], index=idx(transps, atual.get("transportadora")))
        motorista = g.selectbox("Motorista", motoristas or ["—"], index=idx(motoristas, atual.get("motorista")))
        nfs = st.text_area("Notas Fiscais do carregamento (vírgula ou uma por linha)",
                           value=(atual.get("notas_fiscais") or "").replace(", ", "\n"))
        if st.form_submit_button("🔗 Salvar vínculo", type="primary"):
            ui.acao(_salvar, operacao_id, vid, pedido, data, placa, fabrica, transp, motorista, nfs, hl,
                    sucesso="Vínculo salvo!")

    st.divider()
    vinc = logistica_repo.vinculos_df(operacao_id)
    if not vinc.empty:
        vinc["qtd_nfs"] = vinc["notas_fiscais"].fillna("").map(lambda t: len([x for x in t.split(",") if x.strip()]))
    ui.tabela(vinc.drop(columns=["id"]) if not vinc.empty else vinc, vazio="Nenhum pedido vinculado ainda.")
    if not vinc.empty:
        ui.downloads(vinc, "pedidos_vinculados", key="dl_vinc")
        with st.popover("🗑️ Excluir vínculo"):
            rid = st.selectbox("ID", vinc["id"].tolist(), key="vinc_del")
            if st.button("Confirmar exclusão", key="vinc_del_btn"):
                logistica_repo.excluir("vinculos_pedidos", int(rid))
                ui.avisar("Vínculo excluído.", "info")
                st.rerun()
