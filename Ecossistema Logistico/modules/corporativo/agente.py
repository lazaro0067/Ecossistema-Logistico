"""🏛️ Gestão Corporativa › 📊 Gestão › 🤖 Agente de Resultados — pergunte e ele busca os números no sistema."""
import streamlit as st

from core import tema, ui
from core.auth import operacoes_permitidas
from services import agente_service as ag

SUGESTOES = [
    "Faça um resumo do resultado deste mês e compare com o mês anterior.",
    "Quais os 10 produtos que mais faturaram este mês e o R$/HL de cada?",
    "Como está a produtividade da entrega e a frota sugerida por modal?",
    "Quais departamentos mais gastaram no DRE deste mês?",
    "Tem produto com risco de vencer no armazém? Quanto em R$?",
    "Mostre a evolução do faturamento e do resultado nos últimos 6 meses.",
]


def link_celular() -> str:
    from modules.puxada.app_motorista import link_do_app

    return link_do_app().replace("?app=motorista", "?app=agente")


def _no_celular() -> None:
    with st.expander("📱 Usar no celular — salvar o agente na tela inicial"):
        link = link_celular()
        st.code(link, language=None)
        st.markdown(
            "1. Abra este link **no celular** e entre com seu e-mail e senha (deixe marcado *Manter conectado*).\n"
            "2. **Android (Chrome):** menu **⋮** › **Adicionar à tela inicial** (ou *Instalar app*).\n"
            "3. **iPhone (Safari):** botão **Compartilhar** (quadrado com seta) › **Adicionar à Tela de Início**.\n\n"
            "Pronto: aparece o ícone 🤖 *Agente de Resultados* no celular, abrindo direto no agente. "
            "Se clicar em *Sair*, no próximo acesso ele pede a senha de novo.")
        st.link_button("Abrir o link", link)


def render(usuario: dict, operacao_id: int, modo_app: bool = False) -> None:
    if not modo_app:
        st.markdown("##### 📊 Gestão › **🤖 Agente de Resultados**")
        _no_celular()
    if not ag.configurado():
        tema.secao("🤖 Agente de Resultados", "Faça perguntas em português e ele busca os números no próprio sistema.")
        st.info("Para ligar o agente, o administrador coloca a chave da API do Claude nos Secrets do sistema:\n\n"
                "`ANTHROPIC_API_KEY = \"sk-ant-...\"`\n\n(crie em console.anthropic.com › API Keys). O uso é cobrado "
                "pela Anthropic por pergunta. Enquanto isso, use o 🏆 Painel de Resultados.")
        return
    ops = operacoes_permitidas(usuario)
    if not ops:
        st.info("Nenhuma revenda disponível.")
        return
    ids = [o["id"] for o in ops]
    nomes = {o["id"]: o["nome"] for o in ops}
    if st.session_state.get("ag_op") not in ids:
        st.session_state["ag_op"] = operacao_id if operacao_id in ids else ids[0]
    c1, c2 = st.columns([1.6, 1]) if not modo_app else (st.container(), st.container())
    op = c1.selectbox("🏢 Qual operação vamos analisar?", ids, key="ag_op", format_func=nomes.get)
    chave = f"ag_hist_{op}"
    hist = st.session_state.setdefault(chave, {"msgs": [], "tela": []})
    c2.write("")
    if hist["tela"] and c2.button("🧹 Nova conversa", key="ag_limpar"):
        st.session_state[chave] = {"msgs": [], "tela": []}
        st.rerun()

    if not hist["tela"]:
        st.caption(f"Pergunte sobre **{nomes[op]}**: vendas, DRE, compras, entrega, frota, estoque… "
                   "Ele lê os números do sistema (não inventa). Sugestões:")
        cols = st.columns(2)
        for i, s_ in enumerate(SUGESTOES):
            if cols[i % 2].button(s_, key=f"ag_sug_{i}", **ui.LARGURA):
                st.session_state["ag_pendente"] = s_
                st.rerun()
    for item in hist["tela"]:
        with st.chat_message(item["papel"], avatar="🧑" if item["papel"] == "user" else "🤖"):
            st.markdown(item["texto"])
            if item.get("consultas"):
                with st.expander(f"🔎 {len(item['consultas'])} consulta(s) ao sistema"):
                    for c in item["consultas"]:
                        st.caption(f"• {c['ferramenta']} {c['entrada'] or ''}")

    pergunta = st.chat_input(f"Pergunte sobre {nomes[op]}…") or st.session_state.pop("ag_pendente", None)
    if not pergunta:
        return
    hist["tela"].append({"papel": "user", "texto": pergunta})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(pergunta)
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Buscando os números no sistema…"):
            try:
                resposta, msgs, consultas = ag.perguntar(hist["msgs"], pergunta, op)
            except Exception as e:  # noqa: BLE001 — chave errada, sem crédito, sem internet…
                resposta, msgs, consultas = (f"⚠️ Não consegui falar com o agente agora ({type(e).__name__}: {e}).",
                                             hist["msgs"], [])
        st.markdown(resposta)
    hist["msgs"] = _cortar(msgs)
    hist["tela"].append({"papel": "assistant", "texto": resposta, "consultas": consultas})
    st.rerun()


def _cortar(msgs: list[dict], maximo: int = 40) -> list[dict]:
    """Guarda as últimas trocas sem separar pergunta de consulta (começa sempre numa pergunta do usuário)."""
    if len(msgs) <= maximo:
        return msgs
    for i in range(len(msgs) - maximo, len(msgs)):
        if msgs[i]["role"] == "user" and isinstance(msgs[i]["content"], str):
            return msgs[i:]
    return []

