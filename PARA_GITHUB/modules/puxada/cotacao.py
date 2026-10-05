"""Puxada › Solicitar frete. Escolha um trecho cadastrado (já traz transportadora, valor e
aprovador) ou monte um trecho avulso."""
import streamlit as st

from config.settings import MOTIVOS_FRETE
from core import tema, tempo, ui
from repositories import cadastros_repo, fretes_repo, usuarios_repo
from services import fretes_service as svc

AVULSO = "✏️ Outro trecho (preencher manualmente)"


def _kpis(operacao_id: int) -> None:
    df = fretes_repo.listar_df(operacao_id)
    cont = df["status"].value_counts() if not df.empty else {}
    pend = int(cont.get("Pendente Aprovação", 0))
    tema.kpis([
        {"titulo": "Pendentes de aprovação", "valor": pend, "icone": "⏳", "status": "atencao" if pend else "bom"},
        {"titulo": "Aprovados (a finalizar)", "valor": int(cont.get("Aprovado", 0)), "icone": "📋", "status": "info"},
        {"titulo": "Finalizados", "valor": int(cont.get("Finalizado", 0)), "icone": "✅", "status": "info"},
    ])


def render(usuario: dict, operacao_id: int) -> None:
    _kpis(operacao_id)
    if ui.somente_leitura(operacao_id):
        return
    trechos = cadastros_repo.listar_trechos_df(operacao_id)
    transps = cadastros_repo.listar_transportadoras()
    ccs = cadastros_repo.listar_centros_custo()
    aprovs = usuarios_repo.listar_aprovadores()

    opcoes = {AVULSO: None}
    for r in trechos.itertuples():
        opcoes[f"{r.origem} ➔ {r.destino} · {r.transportadora or 'sem transportadora'} · {ui.moeda(r.valor_frete)}"] = r
    escolha = st.selectbox("Trecho", list(opcoes), index=1 if len(opcoes) > 1 else 0, key="cot_trecho")
    t = opcoes[escolha]

    if t is None:
        origens = cadastros_repo.listar_od(operacao_id, "origem")
        destinos = cadastros_repo.listar_od(operacao_id, "destino")
        if not origens or not destinos or not transps:
            st.warning("Cadastre origens, destinos e transportadoras em **⚙️ Cadastros** antes de cotar.")
            return
        c1, c2 = st.columns(2)
        o = ui.select_registro("Origem", origens, container=c1, key="cot_o")
        d = ui.select_registro("Destino", destinos, container=c2, key="cot_d")
        tabela = svc.valor_tabela(operacao_id, o, d)
        tr_padrao, ap_padrao = None, None
    else:
        o, d, tabela = int(t.origem_id), int(t.destino_id), float(t.valor_frete)
        tr_padrao = int(t.transportadora_id) if t.transportadora_id == t.transportadora_id and t.transportadora_id else None
        ap_padrao = int(t.aprovador_id) if t.aprovador_id == t.aprovador_id and t.aprovador_id else None
        st.info(f"📍 **{t.origem} ➔ {t.destino}** · 🚚 {t.transportadora or '—'} · 💰 tabela {ui.moeda(tabela)}"
                f" · ✅ aprovador {t.aprovador or '—'}")

    with st.form(f"f_cotacao_{escolha}", clear_on_submit=True):
        c3, c4, c5 = st.columns(3)
        motivo = c3.selectbox("Motivo", MOTIVOS_FRETE)
        ids_tr = [None] + [x["id"] for x in transps]
        nomes_tr = {x["id"]: x["nome"] for x in transps}
        tr = c4.selectbox("Transportadora", ids_tr, index=ids_tr.index(tr_padrao) if tr_padrao in ids_tr else 0,
                          format_func=lambda i: ui.PLACEHOLDER if i is None else nomes_tr[i])
        data_frete = c5.date_input("Data do frete", value=tempo.hoje(), format="DD/MM/YYYY")
        c6, c7, c8 = st.columns(3)
        valor = c6.number_input("Valor negociado (R$)", min_value=0.0, value=float(tabela or 0), step=50.0)
        cc = ui.select_registro("Centro de custo", ccs, container=c7)
        ids_ap = [None] + [a["id"] for a in aprovs]
        nomes_ap = {a["id"]: f"{a['nome']} (até {ui.moeda(a['alcada'])})" for a in aprovs}
        ap = c8.selectbox("Aprovador", ids_ap, index=ids_ap.index(ap_padrao) if ap_padrao in ids_ap else 0,
                          format_func=lambda i: ui.PLACEHOLDER if i is None else nomes_ap[i])
        obs = st.text_area("Observação")
        st.caption(f"Solicitante: **{usuario['nome']}**")
        if st.form_submit_button("🚀 Enviar para aprovação", type="primary"):
            ui.acao(svc.criar_cotacao, operacao_id=operacao_id, solicitante_id=usuario["id"],
                    origem_id=o, destino_id=d, transportadora_id=tr, centro_custo_id=cc,
                    aprovador_id=ap, data_frete=data_frete, motivo=motivo,
                    valor_negociado=valor, observacao=obs, sucesso="Solicitação enviada para aprovação!")
