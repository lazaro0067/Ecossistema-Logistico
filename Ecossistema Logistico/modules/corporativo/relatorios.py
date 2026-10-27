"""Gestão Corporativa › 📥 Relatórios — um lugar só para os relatórios da gestão corporativa.

1. Relatório de mapas (PCD) ............ Produtividade Entrega
2. 03.02.37 vendas ...................... Produtividade Entrega (HL por mapa) + 💵 Faturamento
3. 03.02.37 compra ...................... 🛒 Compras de Mercadoria (Financeiro)
4. Relatório de operações ............... nomes das operações (para os filtros e o ⚙️ Cadastro por setor)
5. 02.05.02 (saldo inicial e final) ..... 🏬 Estoque, lucro bruto real e 📑 DRE
6. Financeiro contabilidade ............. 📑 DRE fechado (despesas por departamento)
"""
import datetime as dt

import streamlit as st

from core import arquivos, tema, ui
from repositories import operacoes_repo
from services import estoque_valor_service as ev
from services import faturamento_service as fs
from services import produtividade_entrega_service as pe
from services.erros import RegraNegocioError


LIMITE_TXT = ("📦 Até 1 GB por arquivo — " + arquivos.FORMATOS_TXT + ". Subir de novo um mês substitui o mês inteiro. "
              "Arquivo grande (ano inteiro)? Compacte em .zip — fica ~20× menor e o sistema lê mês a mês.")


def _quando(v) -> str:
    return dt.datetime.fromisoformat(v).strftime("%d/%m/%Y %H:%M") if v else "nunca"


def _d(iso) -> str:
    return dt.date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def _ign(r: dict) -> str:
    ig = r.get("ignorados") or []
    if not ig:
        return ""
    return (" Mantidos sem mexer (já carregados; o arquivo só tinha poucas notas soltas deles): "
            + ", ".join(f"{ui.nome_mes(m)} ({n} linha(s))" for m, n in ig) + ".")


def _card(titulo: str, ultima: str, texto: str, chave: str, tipos: list[str], acao, usuario: dict,
          varios: bool = False) -> None:
    with st.container(border=True):
        st.markdown(f"**{titulo}**  \nÚltima carga: {ultima}")
        st.caption(texto)
        versao = st.session_state.get(f"rel_up_v_{chave}", 0)  # muda após gravar: limpa o arquivo da memória
        arqs = st.file_uploader(titulo, type=tipos, key=f"rel_up_{chave}_{versao}", label_visibility="collapsed",
                                accept_multiple_files=varios)
        arqs = [a for a in ((arqs or []) if varios else [arqs]) if a is not None]
        st.caption(LIMITE_TXT + (" Pode escolher vários arquivos de uma vez (ex.: um por mês)." if varios else ""))
        for a in arqs:
            st.caption(f"📄 {a.name} · {ui.numero(a.size / 1024 ** 2, 1)} MB")
        if arqs and st.button("Gravar" if len(arqs) == 1 else f"Gravar os {len(arqs)} arquivos",
                              key=f"rel_gravar_{chave}", type="primary"):
            barra = st.progress(0.0, text="Preparando a leitura…")
            msgs, erros = [], []
            for k, arq in enumerate(arqs):
                pre = f"{arq.name} ({k + 1} de {len(arqs)}) · " if len(arqs) > 1 else ""
                try:
                    msgs.append(acao(arquivos.preparar(arq), lambda f, t, pre=pre: barra.progress(f, text=pre + t)))
                except RegraNegocioError as e:
                    erros.append(f"{arq.name}: {e}")
                except MemoryError:
                    erros.append(f"{arq.name}: faltou memória no servidor para ler o arquivo. Compacte em .zip e "
                                 "suba de novo (fica bem menor).")
                except Exception as e:  # noqa: BLE001 — mostra em português em vez de travar a tela
                    erros.append(f"{arq.name}: erro inesperado ({e}). Confira se é o relatório certo, em CSV ou .zip.")
            barra.empty()
            import gc

            gc.collect()  # devolve a memória do arquivo processado
            for m in msgs:
                ui.avisar(m)
            if erros:
                st.error("❌ Não foi possível gravar:\n\n- " + "\n- ".join(erros))
            if msgs and not erros:
                st.session_state[f"rel_up_v_{chave}"] = versao + 1
                st.rerun()


def seletor_revenda(usuario: dict, operacao_id: int | None, key: str) -> int | None:
    """Revenda que vai receber os arquivos — escolhida aqui, sem trocar a revenda do menu."""
    from core.auth import operacoes_permitidas

    ops = [o for o in operacoes_permitidas(usuario) if not operacoes_repo.e_consolidada(o["id"])]
    if not ops:
        st.info("Nenhuma revenda disponível para subir relatórios.")
        return None
    ids = [o["id"] for o in ops]
    nomes = {o["id"]: o["nome"] for o in ops}
    if st.session_state.get(key) not in ids:
        st.session_state[key] = operacao_id if operacao_id in ids else ids[0]
    c1, _ = st.columns([1.3, 2])
    return c1.selectbox("🏢 Revenda que recebe os arquivos", ids, key=key, format_func=nomes.get,
                        help="Escolha aqui para quem é o relatório — não precisa trocar a revenda no menu.")


def render(usuario: dict, operacao_id: int) -> None:
    """Gestão Corporativa › 📥 Relatórios — só as bases que fecham o DRE (as demais ficam em 📥 Atualizar relatórios)."""
    tema.secao("📥 Bases do DRE",
               "Vendas e compras (03.02.37), saldo de estoque (02.05.02) e o financeiro da contabilidade. Subir de novo "
               "um mês substitui o mês inteiro. O PCD e as bases da operação ficam em 📥 Atualizar relatórios.")
    op = seletor_revenda(usuario, operacao_id, "rel_corp_op")
    if op:
        cartoes(usuario, op, "dre")


def cartoes(usuario: dict, operacao_id: int, grupo: str = "todos", so: set | None = None) -> None:
    """grupo "dre" = 03.02.37 vendas e compra, operações, 02.05.02 e contabilidade · "todos" = + PCD.
    so = só estes cartões: {"vendas", "compra", "operacoes", "pcd", "estoque", "contab"} (central por frequência)."""
    nome_rev = (operacoes_repo.buscar(operacao_id) or {}).get("nome", "")
    st.caption(f"🏢 Os arquivos serão gravados em **{nome_rev}** (o PCD reconhece a revenda pela coluna “Nome UNB”).")
    ult = fs.ultimas(operacao_id)
    quem = usuario.get("nome", "")
    sufixo = "" if grupo == "dre" else "_c"

    def pcd(arq, _prog=None):
        r = pe.importar_pcd(arq.getvalue(), arq.name, operacao_id, quem)
        return f"{r['linhas']} mapas gravados ({_d(r['de'])} a {_d(r['ate'])})."

    def vendas(arq, prog=None):
        r = pe.importar_notas(arq, arq.name, operacao_id, quem, prog)
        msg = (f"03.02.37 vendas gravada em {nome_rev}: {ui.numero(r['itens'])} itens · {r['meses']} mês(es) · "
               f"{r['mapas']} mapas · {ui.numero(r['hl'])} HL · {ui.moeda(r['valor'])} ({_d(r['de'])} a {_d(r['ate'])}).")
        return msg + (f" {r['sem_fator']} produto(s) sem fator HL na 01.11." if r["sem_fator"] else "") + _ign(r)

    def compra(arq, prog=None):
        r = fs.importar_compra(arq, arq.name, operacao_id, quem, prog)
        msg = (f"03.02.37 compra gravada em {nome_rev}: {ui.numero(r['itens'])} itens · {r['meses']} mês(es) · "
               f"{ui.numero(r['hl'])} HL · {ui.moeda(r['valor'])} ({_d(r['de'])} a {_d(r['ate'])}).")
        return msg + (f" {r['sem_fator']} produto(s) sem fator HL na 01.11." if r["sem_fator"] else "") + _ign(r)

    def operacoes(arq, _prog=None):
        return f"{fs.importar_operacoes(arq.getvalue(), arq.name)} operações atualizadas."

    quer = (lambda n: so is None or n in so)  # noqa: E731
    lista = []
    if quer("vendas"):
        lista.append(lambda: _card(
            "03.02.37 vendas", _quando(ult["entregas_notas"]),
            "Notas de saída. Coluna Z = total faturado; C = operação (1 venda, 2 bonificação…); HL = coluna T × fator "
            "HL da 01.11; AA = mapa. → 💵 Faturamento, 📑 DRE e 🚚 Produtividade Entrega.",
            "vendas" + sufixo, arquivos.FORMATOS, vendas, usuario, varios=True))
    if quer("compra"):
        lista.append(lambda: _card(
            "03.02.37 compra", _quando(ult["notas_compra"]),
            "Notas de entrada (o que foi investido em mercadoria). Coluna Z = total; HL = coluna T × fator HL da "
            "01.11. → 🛒 Compras, 📑 DRE e Remuneração Ambev.", "compra" + sufixo, arquivos.FORMATOS, compra,
            usuario, varios=True))
    if quer("pcd") and grupo != "dre":
        lista.append(lambda: _card(
            "Relatório de mapas (PCD)", _quando(ult["entregas_pcd"]),
            "Uma linha por mapa: placa, veículo, entregas, caixas, % ocupação, peso, KM previsto. "
            "→ 🚚 Produtividade Entrega e Frota por modal.", "pcd" + sufixo, arquivos.FORMATOS, pcd, usuario))
    if quer("operacoes"):
        lista.append(lambda: _card(
            "Relatório de operações", f"{ult['operacoes']} operações cadastradas",
            "Código; Tipo Movimento; Nome da Operação — dá nome às operações nos filtros e no ⚙️ Cadastro.",
            "operacoes" + sufixo, arquivos.FORMATOS, operacoes, usuario))
    for ini in range(0, len(lista), 2):
        for col, f in zip(st.columns(2), lista[ini:ini + 2]):
            with col:
                f()
    if quer("estoque"):
        _card_estoque(usuario, operacao_id, sufixo)
    if quer("contab"):
        _card_contab(usuario, operacao_id, sufixo)


def _card_contab(usuario: dict, operacao_id: int, sufixo: str = "") -> None:
    from modules.corporativo import contabilidade
    from services import contabilidade_service as cs

    with st.container(border=True):
        ult = cs.meses(operacao_id)
        st.markdown("**Financeiro contabilidade (financeiro fechado)**  \nMeses fechados: "
                    + (", ".join(ui.nome_mes(m) for m in ult[:6]) if ult else "nenhum"))
        st.caption("Despesas fechadas pela contabilidade, por departamento. Só com ele o 📑 DRE do mês fica 🔒 "
                   "fechado. Outras contas: 📑 DRE › 🧾 Financeiro contabilidade › ✍️ Outras contas.")
        meses = [ev.mes_atual()]
        for _ in range(12):
            meses.append(ev.mes_anterior(meses[-1]))
        c1, c2 = st.columns([1, 3])
        mes = c1.selectbox("Mês", meses, format_func=ui.nome_mes, key="rel_ctb_mes" + sufixo, index=1)
        with c2:
            contabilidade.card_upload(usuario, operacao_id, mes, chave="rel_ctb" + sufixo)


def _card_estoque(usuario: dict, operacao_id: int, sufixo: str = "") -> None:
    ult = ev.ultimo_saldo(operacao_id)
    with st.container(border=True):
        st.markdown(f"**02.05.02 — saldo de estoque (inicial e final do mês)**  \nÚltimo saldo inicial: "
                    f"{_quando(ult['inicial'])} · último saldo final: {_quando(ult['final'])}")
        st.caption("Coluna AD = valor do estoque (custo médio) · AB = quantidade em unidades ÷ fator (X) = unidade de "
                   "venda → HL pela 01.11 · B = depósito. → 🏬 Estoque, 📊 Lucro bruto real e 📑 DRE.")
        c1, c2, c3 = st.columns([1, 1, 2])
        meses = [ev.mes_atual()]
        for _ in range(12):
            meses.append(ev.mes_anterior(meses[-1]))
        mes = c1.selectbox("Mês", meses, format_func=ui.nome_mes, key="rel_ev_mes" + sufixo)
        tipo = c2.radio("Saldo", list(ev.TIPOS_SALDO), format_func=ev.TIPOS_SALDO.get, key="rel_ev_tipo" + sufixo,
                        horizontal=True)
        arq = c3.file_uploader("02.05.02", type=arquivos.FORMATOS, key="rel_up_estoque" + sufixo, label_visibility="collapsed")
        if arq is not None and st.button("Gravar saldo", key="rel_gravar_estoque" + sufixo, type="primary"):
            try:
                with st.spinner("Lendo o estoque..."):
                    a2 = arquivos.preparar(arq)
                    r = ev.importar(a2.getvalue(), a2.name, operacao_id, mes, tipo, usuario.get("nome", ""))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar(f"{ev.TIPOS_SALDO[tipo]} de {ui.nome_mes(mes)}: {r['itens']} itens · {r['depositos']} "
                          f"depósitos · {ui.moeda(r['valor'])} · {ui.numero(r['hl'])} HL."
                          + (f" {r['sem_fator']} item(ns) sem fator HL na 01.11." if r["sem_fator"] else ""))
                st.rerun()
