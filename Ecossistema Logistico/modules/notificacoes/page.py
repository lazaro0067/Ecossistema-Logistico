"""🔔 Notificações do usuário (ex.: CNH de motorista vencendo — aviso semanal ao gestor)."""
import streamlit as st

from core import session, tema, tempo, ui
from repositories import motoristas_repo as repo

ICONES = {"cnh": "🪪"}


def render(usuario: dict, operacao_id: int | None) -> None:
    ui.cabecalho("Notificações", "Avisos do sistema para você", "🔔")
    agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    lista = repo.notificacoes(usuario["id"])
    pendentes = [n for n in lista if not n["lida_em"]]
    c1, c2 = st.columns([3, 1])
    c1.caption(f"{len(pendentes)} não lida(s) · os avisos de CNH se repetem toda semana até a validade ser atualizada.")
    if pendentes and c2.button("✓ Marcar todas como lidas", key="not_todas", **ui.LARGURA):
        repo.marcar_lida(usuario["id"], None, agora)
        st.rerun()
    if not lista:
        st.info("Nenhuma notificação por enquanto. 🎉")
        return
    for n in lista:
        lida = bool(n["lida_em"])
        quando = tempo.parse_dt(n["criado_em"])
        with st.container(border=True):
            a, b = st.columns([5, 1.3])
            a.markdown(f"{'' if lida else '🔵 '}**{ICONES.get(n['tipo'], '🔔')} {tema._e(n['titulo'])}**  \n"
                       f"{tema._e(n['texto'] or '')}  \n"
                       f"<span style='color:#898781;font-size:.8rem'>{quando:%d/%m/%Y %H:%M}</span>"
                       if quando else n["titulo"], unsafe_allow_html=True)
            if n.get("pagina") and b.button("Abrir ›", key=f"not_abrir_{n['id']}", **ui.LARGURA):
                repo.marcar_lida(usuario["id"], n["id"], agora)
                session.ir_para(n["pagina"])
                st.rerun()
            if not lida and b.button("✓ Lida", key=f"not_lida_{n['id']}", **ui.LARGURA):
                repo.marcar_lida(usuario["id"], n["id"], agora)
                st.rerun()
