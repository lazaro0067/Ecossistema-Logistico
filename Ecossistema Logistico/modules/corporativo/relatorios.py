"""Gestão Corporativa › 📥 Relatórios — um lugar só para os relatórios da gestão corporativa.

1. Relatório de mapas (PCD) ............ Produtividade Entrega
2. 03.02.37 vendas ...................... Produtividade Entrega (HL por mapa) + 💵 Faturamento
3. 03.02.37 compra ...................... 🛒 Compras de Mercadoria (Financeiro)
4. Relatório de operações ............... nomes das operações (para os filtros e o ⚙️ Cadastro por setor)
"""
import datetime as dt

import streamlit as st

from core import tema, ui
from repositories import operacoes_repo
from services import faturamento_service as fs
from services import produtividade_entrega_service as pe
from services.erros import RegraNegocioError


def _quando(v) -> str:
    return dt.datetime.fromisoformat(v).strftime("%d/%m/%Y %H:%M") if v else "nunca"


def _d(iso) -> str:
    return dt.date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def _card(titulo: str, ultima: str, texto: str, chave: str, tipos: list[str], acao, usuario: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{titulo}**  \nÚltima carga: {ultima}")
        st.caption(texto)
        arq = st.file_uploader(titulo, type=tipos, key=f"rel_up_{chave}", label_visibility="collapsed")
        if arq is not None and st.button("Gravar", key=f"rel_gravar_{chave}", type="primary"):
            try:
                with st.spinner("Lendo o arquivo e gravando..."):
                    msg = acao(arq)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(msg)
                st.rerun()


def render(usuario: dict, operacao_id: int) -> None:
    tema.secao("📥 Relatórios da Gestão Corporativa",
               "Os dados vão se acumulando: subir de novo um período substitui só as datas que vierem no arquivo. "
               "Arquivo grande? Compacte em .zip antes de subir — o sistema aceita o .zip direto.")
    if operacoes_repo.e_consolidada(operacao_id):
        st.info("Escolha uma revenda no menu (não a visão consolidada) para subir os relatórios.")
        return
    nome_rev = (operacoes_repo.buscar(operacao_id) or {}).get("nome", "")
    st.caption(f"🏢 Os relatórios serão gravados em **{nome_rev}** (o PCD reconhece a revenda pela coluna “Nome UNB”).")
    ult = fs.ultimas(operacao_id)
    quem = usuario.get("nome", "")

    def pcd(arq):
        r = pe.importar_pcd(arq.getvalue(), arq.name, operacao_id, quem)
        return f"{r['linhas']} mapas gravados ({_d(r['de'])} a {_d(r['ate'])})."

    def vendas(arq):
        r = pe.importar_notas(arq.getvalue(), arq.name, operacao_id, quem)
        msg = (f"03.02.37 vendas: {ui.numero(r['itens'])} itens · {r['mapas']} mapas · {ui.numero(r['hl'])} HL · "
               f"{ui.moeda(r['valor'])} ({_d(r['de'])} a {_d(r['ate'])}).")
        return msg + (f" {r['sem_fator']} produto(s) sem fator HL na 01.11." if r["sem_fator"] else "")

    def compra(arq):
        r = fs.importar_compra(arq.getvalue(), arq.name, operacao_id, quem)
        msg = (f"03.02.37 compra: {ui.numero(r['itens'])} itens · {ui.numero(r['hl'])} HL · {ui.moeda(r['valor'])} "
               f"({_d(r['de'])} a {_d(r['ate'])}).")
        return msg + (f" {r['sem_fator']} produto(s) sem fator HL na 01.11." if r["sem_fator"] else "")

    def operacoes(arq):
        return f"{fs.importar_operacoes(arq.getvalue(), arq.name)} operações atualizadas."

    c1, c2 = st.columns(2)
    with c1:
        _card("1. Relatório de mapas (PCD)", _quando(ult["entregas_pcd"]),
              "Uma linha por mapa: placa, veículo, entregas, caixas, % ocupação, peso, KM previsto. "
              "→ 🚚 Produtividade Entrega.", "pcd", ["csv", "zip"], pcd, usuario)
        _card("3. 03.02.37 compra", _quando(ult["notas_compra"]),
              "Notas de entrada (o que foi investido em mercadoria). Coluna Z = total; HL = coluna T × fator HL "
              "da 01.11. → 💰 Financeiro › 🛒 Compras de Mercadoria.", "compra", ["csv", "zip"], compra, usuario)
    with c2:
        _card("2. 03.02.37 vendas", _quando(ult["entregas_notas"]),
              "Notas de saída. Coluna Z = total faturado; C = operação (1 venda, 2 bonificação…); "
              "HL = coluna T × fator HL da 01.11; AA = mapa. → 💵 Faturamento e 🚚 Produtividade Entrega.",
              "vendas", ["csv", "zip"], vendas, usuario)
        _card("4. Relatório de operações", f"{ult['operacoes']} operações cadastradas",
              "Código; Tipo Movimento; Nome da Operação — dá nome às operações nos filtros e no ⚙️ Cadastro.",
              "operacoes", ["csv", "zip"], operacoes, usuario)
