"""Gestão Corporativa › 📥 Relatórios — um lugar só para os relatórios da gestão corporativa.

1. Relatório de mapas (PCD) ............ Produtividade Entrega
2. 03.02.37 vendas ...................... Produtividade Entrega (HL por mapa) + 💵 Faturamento
3. 03.02.37 compra ...................... 🛒 Compras de Mercadoria (Financeiro)
4. Relatório de operações ............... nomes das operações (para os filtros e o ⚙️ Cadastro por setor)
5. 02.05.02 (saldo inicial e final) ..... 🏬 Estoque, lucro bruto real e 📑 DRE
"""
import datetime as dt

import streamlit as st

from core import tema, ui
from repositories import operacoes_repo
from services import estoque_valor_service as ev
from services import faturamento_service as fs
from services import produtividade_entrega_service as pe
from services.erros import RegraNegocioError


LIMITE_TXT = ("📦 Limite de 1 GB por arquivo (CSV ou .zip). Ano inteiro? Compacte o CSV em .zip — 1,6 GB vira cerca "
              "de 60 MB, sobe rápido e é lido mês a mês.")


def _quando(v) -> str:
    return dt.datetime.fromisoformat(v).strftime("%d/%m/%Y %H:%M") if v else "nunca"


def _d(iso) -> str:
    return dt.date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def _card(titulo: str, ultima: str, texto: str, chave: str, tipos: list[str], acao, usuario: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{titulo}**  \nÚltima carga: {ultima}")
        st.caption(texto)
        arq = st.file_uploader(titulo, type=tipos, key=f"rel_up_{chave}", label_visibility="collapsed")
        st.caption(LIMITE_TXT)
        if arq is not None:
            mb = arq.size / 1024 ** 2
            grande = mb > 150 and not arq.name.lower().endswith(".zip")
            st.caption(f"📄 {arq.name} · {ui.numero(mb, 1)} MB"
                       + (" — dica: em .zip ele sobe bem mais rápido." if grande else ""))
        if arq is not None and st.button("Gravar", key=f"rel_gravar_{chave}", type="primary"):
            barra = st.progress(0.0, text="Preparando a leitura…")
            try:
                msg = acao(arq, lambda f, t: barra.progress(f, text=t))
            except RegraNegocioError as e:
                barra.empty()
                st.error(f"❌ Não foi possível gravar: {e}")
            except MemoryError:
                barra.empty()
                st.error("❌ O arquivo é grande demais para ler sem compactar. Compacte em .zip e suba de novo.")
            except Exception as e:  # noqa: BLE001 — mostra em português em vez de travar a tela
                barra.empty()
                st.error(f"❌ Erro inesperado ao ler o arquivo: {e}. Confira se é o relatório certo, em CSV ou .zip.")
            else:
                barra.empty()
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

    def pcd(arq, _prog=None):
        r = pe.importar_pcd(arq.getvalue(), arq.name, operacao_id, quem)
        return f"{r['linhas']} mapas gravados ({_d(r['de'])} a {_d(r['ate'])})."

    def vendas(arq, prog=None):
        r = pe.importar_notas(arq, arq.name, operacao_id, quem, prog)
        msg = (f"03.02.37 vendas gravada: {ui.numero(r['itens'])} itens · {r['meses']} mês(es) · {r['mapas']} mapas · "
               f"{ui.numero(r['hl'])} HL · {ui.moeda(r['valor'])} ({_d(r['de'])} a {_d(r['ate'])}).")
        return msg + (f" {r['sem_fator']} produto(s) sem fator HL na 01.11." if r["sem_fator"] else "")

    def compra(arq, prog=None):
        r = fs.importar_compra(arq, arq.name, operacao_id, quem, prog)
        msg = (f"03.02.37 compra gravada: {ui.numero(r['itens'])} itens · {r['meses']} mês(es) · {ui.numero(r['hl'])} HL · "
               f"{ui.moeda(r['valor'])} ({_d(r['de'])} a {_d(r['ate'])}).")
        return msg + (f" {r['sem_fator']} produto(s) sem fator HL na 01.11." if r["sem_fator"] else "")

    def operacoes(arq, _prog=None):
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
    _card_estoque(usuario, operacao_id)


def _card_estoque(usuario: dict, operacao_id: int) -> None:
    ult = ev.ultimo_saldo(operacao_id)
    with st.container(border=True):
        st.markdown(f"**5. 02.05.02 — saldo de estoque (inicial e final do mês)**  \nÚltimo saldo inicial: "
                    f"{_quando(ult['inicial'])} · último saldo final: {_quando(ult['final'])}")
        st.caption("Coluna AD = valor do estoque (custo médio) · AB = quantidade em unidades ÷ fator (X) = unidade de "
                   "venda → HL pela 01.11 · B = depósito. → 🏬 Estoque, 📊 Lucro bruto real e 📑 DRE.")
        c1, c2, c3 = st.columns([1, 1, 2])
        meses = [ev.mes_atual()]
        for _ in range(12):
            meses.append(ev.mes_anterior(meses[-1]))
        mes = c1.selectbox("Mês", meses, format_func=ui.nome_mes, key="rel_ev_mes")
        tipo = c2.radio("Saldo", list(ev.TIPOS_SALDO), format_func=ev.TIPOS_SALDO.get, key="rel_ev_tipo",
                        horizontal=True)
        arq = c3.file_uploader("02.05.02", type=["csv", "zip"], key="rel_up_estoque", label_visibility="collapsed")
        if arq is not None and st.button("Gravar saldo", key="rel_gravar_estoque", type="primary"):
            try:
                with st.spinner("Lendo o estoque..."):
                    r = ev.importar(arq.getvalue(), arq.name, operacao_id, mes, tipo, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(f"{ev.TIPOS_SALDO[tipo]} de {ui.nome_mes(mes)}: {r['itens']} itens · {r['depositos']} "
                          f"depósitos · {ui.moeda(r['valor'])} · {ui.numero(r['hl'])} HL."
                          + (f" {r['sem_fator']} item(ns) sem fator HL na 01.11." if r["sem_fator"] else ""))
                st.rerun()
