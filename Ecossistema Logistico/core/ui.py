"""Componentes de tela reutilizados (formatação, tabelas, abas, avisos)."""
import pandas as pd
import streamlit as st

from config.settings import MODULOS
from core import tempo

# Streamlit trocou `use_container_width` por `width="stretch"` (v1.46+).
_VERSAO = tuple(int(p) for p in st.__version__.split(".")[:2])
LARGURA = {"width": "stretch"} if _VERSAO >= (1, 46) else {"use_container_width": True}

PLACEHOLDER = "Selecione..."


# --- Formatação (padrão brasileiro) --------------------------------------
def _br(v: float, casas: int) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def moeda(v) -> str:
    return "R$ " + _br(float(v or 0), 2)


def numero(v, casas: int = 0) -> str:
    try:
        return _br(float(v or 0), casas)
    except (TypeError, ValueError):
        return "—"


def pct(v, casas: int = 1) -> str:
    return f"{numero(v, casas)}%"


def compacto(v) -> str:
    """1.234.567 -> 1,2 mi ; 12.345 -> 12,3 mil"""
    v = float(v or 0)
    if abs(v) >= 1e6:
        return f"{numero(v / 1e6, 1)} mi"
    if abs(v) >= 1e4:
        return f"{numero(v / 1e3, 1)} mil"
    return numero(v)


def mes_atual() -> str:
    return tempo.mes_atual()


def hoje() -> str:
    return tempo.hoje().isoformat()


def agora() -> str:
    return tempo.agora_str()


def nome_mes(mes_ano: str) -> str:
    meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    try:
        a, m = mes_ano.split("-")
        return f"{meses[int(m) - 1]}/{a}"
    except (ValueError, IndexError):
        return mes_ano


# --- Tabelas e botões ----------------------------------------------------
def tabela(df: pd.DataFrame, vazio: str = "Nenhum registro encontrado.", **kwargs) -> None:
    if df is None or df.empty:
        st.info(vazio)
        return
    st.dataframe(df, hide_index=True, **LARGURA, **kwargs)


def botao(rotulo: str, key: str | None = None, **kwargs) -> bool:
    return st.button(rotulo, key=key, **LARGURA, **kwargs)


def download_csv(df: pd.DataFrame, nome: str, rotulo: str = "", key: str | None = None) -> None:
    downloads(df, nome, key)


def select_registro(rotulo: str, registros: list[dict], campo: str = "nome",
                    key: str | None = None, permitir_vazio: bool = True, container=st):
    """Selectbox sobre uma lista de dicts; devolve o `id` escolhido (ou None)."""
    opcoes = ([None] if permitir_vazio else []) + [r["id"] for r in registros]
    nomes = {r["id"]: r[campo] for r in registros}
    return container.selectbox(
        rotulo, opcoes, key=key,
        format_func=lambda i: PLACEHOLDER if i is None else nomes.get(i, str(i)),
    )


def seletor_mes(rotulo: str, meses: list[str], key: str, container=st) -> str:
    meses = meses or [mes_atual()]
    return container.selectbox(rotulo, meses, key=key, format_func=nome_mes)


# --- Abas filtradas por permissão ----------------------------------------
def abas_modulo(usuario: dict, modulo: str, renderizadores: dict, *args) -> None:
    """Desenha só as abas que o usuário pode ver. renderizadores = {aba: func}."""
    from core.auth import abas_permitidas

    permitidas = [a for a in abas_permitidas(usuario, modulo) if a in renderizadores]
    if not permitidas:
        st.warning("Você não tem acesso a nenhuma pasta deste módulo.")
        return
    from config.settings import GRUPOS_ABAS

    rotulos = MODULOS[modulo]["abas"]
    grupos = {g: [a for a in abas if a in permitidas] for g, abas in GRUPOS_ABAS.get(modulo, {}).items()}
    sem_grupo = [a for a in permitidas if not any(a in v for v in grupos.values())]
    if sem_grupo:
        grupos["📂 Outros"] = sem_grupo
    grupos = {g: v for g, v in grupos.items() if v}
    if len(grupos) <= 1:
        grupos = {"": permitidas}

    with st.container(key=f"nav_mod_{modulo}"):
        grupo = _escolha(f"nav_{modulo}_grupo", list(grupos), list(grupos)[0]) if len(grupos) > 1 else ""
        abas = grupos[grupo]
        aba = _escolha(f"nav_{modulo}_{grupo}_aba", abas, abas[0], formatar=rotulos.get, pills=True) \
            if len(abas) > 1 else abas[0]
    renderizadores[aba](*args)


def _escolha(chave: str, opcoes: list, padrao, formatar=None, pills: bool = False):
    """Seletor de grupo/tela que lembra a última escolha (clicar de novo na mesma não "desmarca")."""
    lembrada = f"{chave}__ultima"
    atual = st.session_state.get(lembrada, padrao)
    if atual not in opcoes:
        atual = padrao
    if st.session_state.get(chave) not in opcoes:
        st.session_state[chave] = atual
    widget = getattr(st, "pills" if pills else "segmented_control", None)
    if widget is None:  # Streamlit antigo
        valor = st.radio("Tela" if pills else "Grupo", opcoes, key=chave, horizontal=True, format_func=formatar or str,
                         label_visibility="collapsed")
    else:
        valor = widget("Tela" if pills else "Grupo", opcoes, key=chave, format_func=formatar or str, selection_mode="single",
                       label_visibility="collapsed")
    valor = valor if valor in opcoes else atual
    st.session_state[lembrada] = valor
    return valor


# --- Mensagens que sobrevivem ao st.rerun() ------------------------------
def avisar(msg: str, tipo: str = "success") -> None:
    st.session_state.setdefault("_avisos", []).append((tipo, msg))


def mostrar_avisos() -> None:
    for tipo, msg in st.session_state.pop("_avisos", []):
        icone = {"success": "✅", "info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(tipo, "")
        st.toast(msg, icon=icone or None)


def salvo_automatico(msg: str = "Salvo automaticamente") -> None:
    st.toast(msg, icon="💾")


def acao(func, *args, sucesso: str = "Salvo com sucesso!", **kwargs) -> bool:
    """Executa uma ação de serviço; mostra erro de negócio sem quebrar a tela."""
    from services.erros import RegraNegocioError

    try:
        func(*args, **kwargs)
    except RegraNegocioError as e:
        st.error(str(e))
        return False
    avisar(sucesso)
    st.rerun()
    return True


# --- Cabeçalho padrão das páginas ----------------------------------------
_DESCRICOES = {
    "puxada": "Fretes, pátio, viagens, pedidos vinculados e cadastros da puxada",
    "ressuprimento": "Bases Ambev, estoque, sugestão de marcação, cestas, política e metas",
    "armazem": "Saúde do estoque, Book DPO do armazém, pátio e capacidade",
    "distribuicao": "Book DPO de entrega, rotas, OTIF e devoluções",
    "frota": "Manutenção e custos da frota",
    "gente": "SSMA, absenteísmo e turnover",
    "vendas": "Estoque do dia para o comercial, metas e curva ABC",
    "financeiro": "Contas a pagar, vencimentos, fluxo de caixa e OBZ",
    "compras": "Pedidos de compra e acompanhamento",
    "relatorios": "Todas as bases do sistema para download e histórico de atualizações",
}


def cabecalho(titulo: str, subtitulo: str = "", icone: str = "") -> None:
    from core import session, tema

    pills = []
    if session.operacao_nome():
        pills.append(f"🏢 {session.operacao_nome()}")
    pills.append(f"📅 {tempo.hoje():%d/%m/%Y}")
    tema.cabecalho(titulo, subtitulo, icone, pills)


def cabecalho_modulo(modulo: str) -> None:
    m = MODULOS[modulo]
    cabecalho(m["rotulo"], _DESCRICOES.get(modulo, ""), m["icone"])


def downloads(df: pd.DataFrame, nome: str, key: str | None = None) -> None:
    """Botões de download em Excel e CSV (como no sistema original)."""
    import io

    if df is None or df.empty:
        return
    k = key or nome
    stamp = tempo.agora().strftime("%Y%m%d_%H%M")
    c1, c2, _ = st.columns([1, 1, 3])
    buf = io.BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Dados")
        c1.download_button("⬇️ Excel", buf.getvalue(), file_name=f"{nome}_{stamp}.xlsx", key=f"dlx_{k}",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        pass
    c2.download_button("⬇️ CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=f"{nome}_{stamp}.csv", mime="text/csv", key=f"dlc_{k}")


def somente_leitura(operacao_id: int | None) -> bool:
    """True quando a operação é uma visão consolidada (não aceita lançamentos)."""
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        st.info("🔒 Visão consolidada (somente leitura). Para lançar ou editar, escolha uma filial no menu.")
        return True
    return False
