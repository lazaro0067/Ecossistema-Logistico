"""Cartão de atualização de base: envia o arquivo e o sistema grava sozinho.

Mostra se a base está em dia (verde), precisa atualizar (amarelo) ou está
desatualizada/nunca importada (vermelho). Se as colunas forem reconhecidas,
a gravação é automática; senão, abre o "de/para" para confirmar.
"""
import datetime as dt

import streamlit as st

from core import tema, tempo, ui
from services import bases_service
from services import importacao_service as imp
from services.erros import RegraNegocioError

TIPOS_ARQUIVO = ["xlsx", "xls", "csv", "docx"]


def _gravar(layout_key, df, mapa, operacao_id, usuario, arquivo, data_padrao=None, remover_digito=False,
            mes_ano=None) -> bool:
    try:
        dados = imp.preparar(layout_key, df, mapa, data_padrao=data_padrao, remover_digito=remover_digito)
        n = imp.gravar(layout_key, dados, operacao_id, mes_ano=mes_ano, usuario=usuario["login"], arquivo=arquivo)
    except RegraNegocioError as e:
        st.error(str(e))
        return False
    ui.avisar(f"{imp.LAYOUTS[layout_key]['rotulo'].split(' —')[0]}: {ui.numero(n)} linhas gravadas.")
    return True


def card_base(layout_key: str, operacao_id: int, usuario: dict, titulo: str, frequencia: str) -> None:
    sit = bases_service.situacao(layout_key, operacao_id)
    detalhe = (f"{bases_service.idade_txt(sit['idade_dias'])} · {ui.numero(sit['linhas'])} linhas"
               if sit["linhas"] else "Envie o primeiro arquivo")
    st.markdown(
        f'<div class="eco-base"><h4>{tema._e(titulo)}</h4><div class="freq">{tema._e(frequencia)}</div>'
        f'{tema.selo(sit["status"], sit["rotulo"])}<div class="freq" style="margin-top:.3rem">{tema._e(detalhe)}</div></div>',
        unsafe_allow_html=True,
    )

    layout = imp.LAYOUTS[layout_key]
    data_padrao, remover_digito, mes_ano = None, False, None
    from repositories import operacoes_repo
    if layout["por_operacao"] and layout["modo"] != "multi_operacao" and operacoes_repo.e_consolidada(operacao_id):
        st.caption("🔒 Visão consolidada — escolha uma filial no menu para enviar esta base.")
        return
    if layout.get("data_padrao"):
        hoje = tempo.hoje()
        opcoes = {f"D{i} · {(hoje + dt.timedelta(days=i)):%d/%m}": (hoje + dt.timedelta(days=i)).isoformat()
                  for i in range(3)}
        escolha = st.radio("Dia da puxada (se o arquivo não tiver data)", list(opcoes), horizontal=True,
                           key=f"dia_{layout_key}_{operacao_id}")
        data_padrao = opcoes[escolha]
    if layout.get("digito_verificador"):
        remover_digito = st.checkbox("Código com dígito verificador", value=True,
                                     key=f"dv_{layout_key}_{operacao_id}",
                                     help="Remove o último dígito do código para casar com a base 01.11.")
    if layout.get("pede_mes"):
        mes_ano = st.text_input("Mês de referência (AAAA-MM)", value=ui.mes_atual(), key=f"mes_{layout_key}")

    arq = st.file_uploader(f"Enviar {titulo}", type=TIPOS_ARQUIVO, key=f"up_{layout_key}_{operacao_id}",
                           label_visibility="collapsed")
    if not arq:
        return
    marca = f"proc_{layout_key}_{operacao_id}"
    fid = (arq.name, arq.size, data_padrao, remover_digito, mes_ano)
    if st.session_state.get(marca) == fid:
        st.success(f"✅ {arq.name} importado.")
        return

    try:
        df = imp.ler_arquivo(arq.name, arq.getvalue(), layout_key)
    except Exception as e:
        st.error(f"Não consegui ler o arquivo: {e}")
        return

    mapa = imp.sugerir_mapeamento(layout_key, list(df.columns))
    if not imp.faltando(layout_key, mapa):
        with st.spinner("Gravando..."):
            if _gravar(layout_key, df, mapa, operacao_id, usuario, arq.name, data_padrao, remover_digito, mes_ano):
                st.session_state[marca] = fid
                st.rerun()
        return

    st.warning("Não reconheci todas as colunas. Confirme o de/para:")
    opcoes_col = [None] + list(df.columns)
    for campo, c in layout["campos"].items():
        mapa[campo] = st.selectbox(
            c.rotulo + (" *" if c.obrigatorio else ""), opcoes_col,
            index=opcoes_col.index(mapa[campo]) if mapa.get(campo) in opcoes_col else 0,
            format_func=lambda c: "— não importar —" if c is None else c,
            key=f"map_{layout_key}_{campo}",
        )
    with st.expander("Prévia do arquivo"):
        ui.tabela(df.head(8))
    if st.button("📥 Gravar", type="primary", key=f"grv_{layout_key}"):
        if _gravar(layout_key, df, mapa, operacao_id, usuario, arq.name, data_padrao, remover_digito, mes_ano):
            st.session_state[marca] = fid
            st.rerun()
