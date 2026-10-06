"""Puxada › Solicitar frete spot. Fábrica de origem + transportadora + tipo de carga trazem o frete
cadastrado no trecho (pode ser alterado — o aprovador vê a diferença e justifica)."""
import streamlit as st

from config.settings import MOTIVOS_FRETE, SUGESTAO_PEDIDO
from core import tema, tempo, ui
from repositories import cadastros_repo, fretes_repo, usuarios_repo
from services import fretes_service as svc

COLUNAS = ["id", "status", "data_frete", "origem", "destino", "transportadora", "tipo_carga", "motivo",
           "valor_negociado", "valor_tabela", "justificativa_aprovacao", "solicitante", "aprovador", "numero_cte"]
FORMATO = {"valor_negociado": st.column_config.NumberColumn("Negociado", format="R$ %.2f"),
           "valor_tabela": st.column_config.NumberColumn("Cadastrado", format="R$ %.2f"),
           "tipo_carga": "Carga", "justificativa_aprovacao": "Justificativa (valor ≠ cadastrado)"}


def _kpis(operacao_id: int) -> None:
    df = fretes_repo.listar_df(operacao_id)

    def por(status):
        return df[df["status"] == status][COLUNAS] if not df.empty else df

    pend = len(por("Pendente Aprovação"))
    tema.kpis([
        {"titulo": "Pendentes de aprovação", "valor": pend, "icone": "⏳", "status": "atencao" if pend else "bom",
         "dados": por("Pendente Aprovação"), "colunas": FORMATO},
        {"titulo": "Aprovados (a finalizar)", "valor": len(por("Aprovado")), "icone": "📋", "status": "info",
         "dados": por("Aprovado"), "colunas": FORMATO},
        {"titulo": "Finalizados", "valor": len(por("Finalizado")), "icone": "✅", "status": "info",
         "dados": por("Finalizado"), "colunas": FORMATO},
    ], key="kp_cot")


def render(usuario: dict, operacao_id: int) -> None:
    _kpis(operacao_id)
    if ui.somente_leitura(operacao_id):
        return
    from services import cadastros_service

    try:
        cadastros_service.garantir_od_padrao(operacao_id)  # fábricas = origens, revenda = destino
    except Exception:
        pass
    transps = cadastros_repo.listar_transportadoras()
    ccs = cadastros_repo.listar_centros_custo()
    aprovs = usuarios_repo.listar_aprovadores()
    origens = cadastros_repo.listar_od(operacao_id, "origem")
    destinos = cadastros_repo.listar_od(operacao_id, "destino")
    if not origens or not destinos or not transps:
        st.warning("Cadastre as **fábricas** (viram origens) em **⚙️ Cadastros › 🏭 Fábricas** e as **transportadoras** "
                   "antes de solicitar. A revenda já entra como destino.")
        return

    tema.secao("📝 Nova solicitação", "Escolha a fábrica de origem, a transportadora e o tipo de carga — o frete "
               "cadastrado vem sozinho e pode ser alterado.")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.3, 1.3, 1.3, 1.1])
        o = ui.select_registro("🏭 Fábrica de origem *", origens, container=c1, key="cot_o")
        d = ui.select_registro("📍 Destino *", destinos, container=c2, key="cot_d", permitir_vazio=len(destinos) > 1)
        ids_tr = [None] + [x["id"] for x in transps]
        nomes_tr = {x["id"]: x["nome"] for x in transps}
        tr = c3.selectbox("🚚 Transportadora *", ids_tr, key="cot_tr",
                          format_func=lambda i: ui.PLACEHOLDER if i is None else nomes_tr[i])
        tipo = c4.radio("Carga *", SUGESTAO_PEDIDO, horizontal=False, index=None, key="cot_tipo",
                        format_func=lambda t: f"{'♻️' if t == 'Retornável' else '🥫'} {t}")
        trecho = svc.trecho_cadastrado(operacao_id, o, d, tr, tipo) if (o and d) else None
        tabela = float(trecho["valor_frete"]) if trecho and trecho.get("valor_frete") else None
        if o and d and tr and tipo:
            if tabela:
                st.success(f"💰 Frete cadastrado: **{ui.moeda(tabela)}**"
                           + (f" · pedágio {ui.moeda(trecho.get('pedagio'))}" if trecho.get("pedagio") else ""))
            else:
                st.warning("Sem frete cadastrado para esta fábrica + transportadora + tipo. Informe o valor negociado "
                           "(cadastre o trecho em ⚙️ Cadastros › 🚚 Trechos spot).")
        c5, c6, c7 = st.columns(3)
        motivo = c5.selectbox("Motivo", MOTIVOS_FRETE, key="cot_motivo")
        data_frete = c6.date_input("Data do frete", value=tempo.hoje(), format="DD/MM/YYYY", key="cot_data")
        valor = c7.number_input("Valor negociado (R$) *", min_value=0.0, value=float(tabela or 0), step=50.0,
                                key=f"cot_valor_{o}_{d}_{tr}_{tipo}")
        if tabela and valor:
            txt = svc.texto_divergencia(valor, tabela)
            (st.info if "igual" in txt else st.warning)(f"⚖️ Valor {txt}. O aprovador será avisado"
                                                         + (" e precisa justificar." if "igual" not in txt else "."))
        c8, c9 = st.columns(2)
        cc = ui.select_registro("Centro de custo", ccs, container=c8, key="cot_cc")
        ap_padrao = int(trecho["aprovador_id"]) if trecho and trecho.get("aprovador_id") else None
        ids_ap = [None] + [a["id"] for a in aprovs]
        nomes_ap = {a["id"]: f"{a['nome']} (até {ui.moeda(a['alcada'])})" for a in aprovs}
        ap = c9.selectbox("Aprovador *", ids_ap, index=ids_ap.index(ap_padrao) if ap_padrao in ids_ap else 0,
                          key=f"cot_ap_{ap_padrao}", format_func=lambda i: ui.PLACEHOLDER if i is None else nomes_ap[i])
        obs = st.text_area("Observação", key="cot_obs")
        st.caption(f"Solicitante: **{usuario['nome']}**")
        if st.button("🚀 Enviar para aprovação", type="primary", key="cot_enviar"):
            from services.erros import RegraNegocioError

            try:
                svc.criar_cotacao(operacao_id=operacao_id, solicitante_id=usuario["id"], origem_id=o, destino_id=d,
                                  transportadora_id=tr, centro_custo_id=cc, aprovador_id=ap, data_frete=data_frete,
                                  motivo=motivo, valor_negociado=valor, observacao=obs, tipo_carga=tipo)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                for k in [k for k in st.session_state if str(k).startswith("cot_")]:
                    st.session_state.pop(k, None)
                ui.avisar("Solicitação enviada para aprovação!")
                st.rerun()
