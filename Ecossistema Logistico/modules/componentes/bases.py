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
    extra = ""
    campo = imp.LAYOUTS[layout_key].get("data_padrao")
    if campo and campo in dados:
        hoje = tempo.hoje()
        partes = []
        for d, g in dados.groupby(campo):
            try:
                dd = dt.date.fromisoformat(str(d)[:10])
            except ValueError:
                continue
            k = (dd - hoje).days
            partes.append(f"{'D' + str(k) if k >= 0 else 'anterior'} {dd:%d/%m}: {len(g)} item(ns)")
        extra = " · " + " · ".join(partes) if partes else ""
    ui.avisar(f"{imp.LAYOUTS[layout_key]['rotulo'].split(' —')[0]}: {ui.numero(n)} linhas gravadas{extra}.")
    return True


def card_base(layout_key: str, operacao_id: int, usuario: dict, titulo: str, frequencia: str,
              prefixo: str = "") -> None:
    """`prefixo` separa as chaves quando o mesmo cartão aparece em mais de um lugar da tela."""
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
        st.caption("📅 Envie um relatório só: o sistema lê a data de cada linha e separa D0, D1 e D2.")
    if layout.get("digito_verificador"):
        remover_digito = st.checkbox("Código com dígito verificador", value=True,
                                     key=f"{prefixo}dv_{layout_key}_{operacao_id}",
                                     help="Remove o último dígito do código para casar com a base 01.11.")
    if layout.get("pede_mes"):
        mes_ano = st.text_input("Mês de referência (AAAA-MM)", value=ui.mes_atual(), key=f"{prefixo}mes_{layout_key}")

    arq = st.file_uploader(f"Enviar {titulo}", type=TIPOS_ARQUIVO, key=f"{prefixo}up_{layout_key}_{operacao_id}",
                           label_visibility="collapsed")
    if not arq:
        return
    marca = f"{prefixo}proc_{layout_key}_{operacao_id}"
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
    campo_data = layout.get("data_padrao")
    if campo_data and not mapa.get(campo_data):
        # arquivo sem coluna de data: o usuário escolhe o dia da puxada
        hoje = tempo.hoje()
        opcoes = {f"D{i} · {(hoje + dt.timedelta(days=i)):%d/%m}": (hoje + dt.timedelta(days=i)).isoformat()
                  for i in range(3)}
        st.warning("Não achei a coluna de data no arquivo. Escolha o dia da puxada:")
        escolha = st.radio("Dia da puxada", list(opcoes), horizontal=True, key=f"{prefixo}dia_{layout_key}_{operacao_id}")
        data_padrao = opcoes[escolha]
        if st.button("📥 Gravar", type="primary", key=f"{prefixo}grv_dia_{layout_key}"):
            if _gravar(layout_key, df, mapa, operacao_id, usuario, arq.name, data_padrao, remover_digito, mes_ano):
                st.session_state[marca] = fid
                st.rerun()
        return
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
            key=f"{prefixo}map_{layout_key}_{campo}",
        )
    with st.expander("Prévia do arquivo"):
        ui.tabela(df.head(8))
    if st.button("📥 Gravar", type="primary", key=f"{prefixo}grv_{layout_key}"):
        if _gravar(layout_key, df, mapa, operacao_id, usuario, arq.name, data_padrao, remover_digito, mes_ano):
            st.session_state[marca] = fid
            st.rerun()


# --- Barra "Atualizar" no topo de Puxada, Armazém e Ressuprimento ------------------------------
BASES_TITULOS = {
    "produtos": ("Relatório 01.11", "Cadastro · quando mudar"),
    "linear": ("Relatório Linear", "A cada 3 meses"),
    "estoque": ("Relatório 02.03.04", "Diário"),
    "pedidos_marcados": ("Puxada Marcada", "D0, D1, D2 · diário"),
    "ressuprimento": ("Ressuprimento diário", "Diário · todas as filiais"),
    "politica": ("Política de estoque", "Semanal"),
    "metas_doi": ("Metas de DOI por SKU", "Quando revisar"),
}
BASES_POR_MODULO = {
    "puxada": ["pedidos_marcados", "estoque", "ressuprimento"],
    "armazem": ["estoque", "pedidos_marcados", "produtos", "linear"],
    "ressuprimento": ["estoque", "pedidos_marcados", "ressuprimento", "linear", "produtos", "politica", "metas_doi"],
}
_ICONE = {"bom": "🟢", "atencao": "🟡", "serio": "🟠", "critico": "🔴", "neutro": "⚪"}


def barra_atualizar(modulo: str, operacao_id: int, usuario: dict) -> None:
    """🔄 recarrega a tela com os dados mais novos · 📥 envia as bases sem sair da aba."""
    bases = BASES_POR_MODULO.get(modulo, [])
    sits = {b: bases_service.situacao(b, operacao_id) for b in bases}
    atrasadas = [b for b, s in sits.items() if s["status"] in ("critico", "serio", "atencao")]
    with st.container(key=f"barra_atu_{modulo}"):
        c1, c2, c3 = st.columns([4.2, 1.1, 1.4])
        chips = " ".join(
            f'<span class="eco-bchip" title="{tema._e(s["rotulo"])}">{_ICONE.get(s["status"], "⚪")} '
            f'{tema._e(BASES_TITULOS[b][0])} · {tema._e(bases_service.idade_txt(s["idade_dias"]) if s["linhas"] else "sem dados")}</span>'
            for b, s in sits.items())
        c1.markdown(f'<div class="eco-bchips">{chips}</div>', unsafe_allow_html=True)
        if c2.button("🔄 Atualizar tela", key=f"atu_tela_{modulo}", help="Recarrega com os dados mais recentes",
                     **ui.LARGURA):
            try:
                st.cache_data.clear()
            except Exception:
                pass
            ui.avisar(f"Atualizado às {tempo.agora():%H:%M}.", "info")
            st.rerun()
        rot = f"📥 Atualizar relatórios{f' ({len(atrasadas)})' if atrasadas else ''}"
        if c3.button(rot, key=f"atu_bases_{modulo}", type="primary" if atrasadas else "secondary",
                     help="Abre a central única de relatórios", **ui.LARGURA):
            from modules.bases.page import ir

            ir()
