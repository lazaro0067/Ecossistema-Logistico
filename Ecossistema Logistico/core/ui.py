"""Componentes visuais reutilizados em todas as telas."""
import datetime as dt

import pandas as pd
import streamlit as st

# Streamlit trocou `use_container_width` por `width="stretch"` (v1.46+).
_VERSAO = tuple(int(p) for p in st.__version__.split(".")[:2])
_LARGURA = {"width": "stretch"} if _VERSAO >= (1, 46) else {"use_container_width": True}

PLACEHOLDER = "Selecione..."


# --- Formatação -----------------------------------------------------------
def moeda(v) -> str:
    v = float(v or 0)
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def numero(v, casas: int = 0) -> str:
    v = float(v or 0)
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v, casas: int = 1) -> str:
    return f"{numero(v, casas)}%"


def mes_atual() -> str:
    return dt.date.today().strftime("%Y-%m")


def hoje() -> str:
    return dt.date.today().isoformat()


def agora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


# --- Layout ---------------------------------------------------------------
def cabecalho(titulo: str, subtitulo: str | None = None) -> None:
    st.title(titulo)
    if subtitulo:
        st.caption(subtitulo)


def tabela(df: pd.DataFrame, vazio: str = "Nenhum registro encontrado.", **kwargs) -> None:
    if df is None or df.empty:
        st.info(vazio)
        return
    st.dataframe(df, hide_index=True, **_LARGURA, **kwargs)


def botao(rotulo: str, key: str | None = None, **kwargs) -> bool:
    return st.button(rotulo, key=key, **_LARGURA, **kwargs)


def download_csv(df: pd.DataFrame, nome: str, rotulo: str = "⬇️ Exportar CSV") -> None:
    if df is not None and not df.empty:
        st.download_button(
            rotulo,
            df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name=f"{nome}.csv",
            mime="text/csv",
        )


def select_registro(rotulo: str, registros: list[dict], campo: str = "nome",
                    key: str | None = None, permitir_vazio: bool = True,
                    container=st):
    """Selectbox sobre uma lista de dicts; devolve o `id` escolhido (ou None)."""
    opcoes = ([None] if permitir_vazio else []) + [r["id"] for r in registros]
    nomes = {r["id"]: r[campo] for r in registros}
    return container.selectbox(
        rotulo, opcoes, key=key,
        format_func=lambda i: PLACEHOLDER if i is None else nomes.get(i, str(i)),
    )


# --- Mensagens que sobrevivem ao st.rerun() ------------------------------
def avisar(msg: str, tipo: str = "success") -> None:
    st.session_state.setdefault("_avisos", []).append((tipo, msg))


def mostrar_avisos() -> None:
    for tipo, msg in st.session_state.pop("_avisos", []):
        getattr(st, tipo)(msg)


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
