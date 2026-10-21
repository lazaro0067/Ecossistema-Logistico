"""Tela padrão de cadastro — o mesmo jeito em todos os cadastros:

  ① 🔎 pesquisa + ➕ Novo (recolhido)   ② lista compacta (rola) com o que a pesquisa achou
  ③ ✏️ escolhe um dos encontrados, edita e salva (ou exclui). Achou um só: já abre para editar.

Uso:
    tela(chave="transp", titulo="Transportadoras", icone="🏢", df=df,
         campos=[Campo("nome", "Nome", obrigatorio=True), Campo("cnpj", "CNPJ")],
         salvar=lambda id_, dados: ..., excluir=lambda id_: ...)
"""
import datetime as dt
import html
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd
import streamlit as st

from core import tema, ui
from services.erros import RegraNegocioError


@dataclass
class Campo:
    chave: str
    rotulo: str
    tipo: str = "texto"            # texto | numero | moeda | data | opcoes | multi | senha | inteiro
    obrigatorio: bool = False
    opcoes: Any = None             # lista ou dict {valor: rótulo} (tipo "opcoes")
    ajuda: str | None = None
    na_tabela: bool = True
    no_form: bool = True
    padrao: Any = None
    passo: float = 1.0
    extra: dict = field(default_factory=dict)


def _rotulo_opcao(campo: Campo, v):
    if isinstance(campo.opcoes, dict):
        return campo.opcoes.get(v, "—" if v in (None, "") else v)
    return "—" if v in (None, "") else v


def _formatar(campo: Campo, v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v.strip() == ""):
        return "—"
    if campo.tipo == "moeda":
        return ui.moeda(v)
    if campo.tipo == "numero":
        return ui.numero(v, 1 if float(v) % 1 else 0)
    if campo.tipo == "inteiro":
        return ui.numero(v)
    if campo.tipo == "data":
        d = v if isinstance(v, dt.date) else pd.to_datetime(v, errors="coerce")
        return d.strftime("%d/%m/%Y") if d is not None and not pd.isna(d) else str(v)
    if campo.tipo == "opcoes":
        return str(_rotulo_opcao(campo, v))
    if campo.tipo == "multi":
        return ", ".join(str(_rotulo_opcao(campo, x)) for x in (v if isinstance(v, (list, tuple)) else [v]))
    return str(v)


def tabela_html(df: pd.DataFrame, colunas: list[tuple[str, str]], formatadores: dict | None = None,
                altura_max: int = 460) -> None:
    """Tabela de leitura: cabeçalho em negrito, linhas marcadas, rolagem quando é longa."""
    formatadores = formatadores or {}
    cab = "".join(f"<th>{html.escape(r)}</th>" for _, r in colunas)
    linhas = []
    for reg in df.to_dict("records"):
        tds = []
        for c, _ in colunas:
            v = reg.get(c)
            txt = formatadores[c](v) if c in formatadores else ("—" if v is None or v == "" or
                                                                 (isinstance(v, float) and pd.isna(v)) else v)
            tds.append(f"<td>{html.escape(str(txt))}</td>")
        linhas.append(f"<tr>{''.join(tds)}</tr>")
    st.markdown(f'<div class="eco-tab" style="max-height:{altura_max}px"><table><thead><tr>{cab}</tr></thead>'
                f'<tbody>{"".join(linhas)}</tbody></table></div>', unsafe_allow_html=True)


def _widget(campo: Campo, valor, chave: str, container):
    rot = campo.rotulo + (" *" if campo.obrigatorio else "")
    if campo.tipo in ("numero", "moeda", "inteiro"):
        v = float(valor) if valor not in (None, "") and not (isinstance(valor, float) and pd.isna(valor)) else \
            float(campo.padrao or 0)
        return container.number_input(rot, min_value=0.0, value=v, step=float(campo.passo), key=chave,
                                      help=campo.ajuda, format="%.2f" if campo.tipo == "moeda" else None)
    if campo.tipo == "data":
        d = pd.to_datetime(valor, errors="coerce") if valor not in (None, "") else None
        return container.date_input(rot, value=d.date() if d is not None and not pd.isna(d) else None, key=chave,
                                    format="DD/MM/YYYY", help=campo.ajuda,
                                    min_value=dt.date(2000, 1, 1), max_value=dt.date(2060, 12, 31))
    if campo.tipo == "opcoes":
        opcoes = list(campo.opcoes) if isinstance(campo.opcoes, dict) else list(campo.opcoes or [])
        if not campo.obrigatorio and None not in opcoes:
            opcoes = [None] + opcoes
        atual = valor if valor in opcoes else (campo.padrao if campo.padrao in opcoes else opcoes[0] if opcoes else None)
        return container.selectbox(rot, opcoes, index=opcoes.index(atual) if atual in opcoes else 0, key=chave,
                                   format_func=lambda x: ui.PLACEHOLDER if x is None else str(_rotulo_opcao(campo, x)),
                                   help=campo.ajuda)
    if campo.tipo == "multi":
        opcoes = list(campo.opcoes) if isinstance(campo.opcoes, dict) else list(campo.opcoes or [])
        atual = valor if isinstance(valor, (list, tuple)) else (campo.padrao or [])
        return container.multiselect(rot, opcoes, default=[x for x in atual if x in opcoes], key=chave,
                                     format_func=lambda x: str(_rotulo_opcao(campo, x)), help=campo.ajuda)
    if campo.tipo == "senha":
        return container.text_input(rot, type="password", key=chave, help=campo.ajuda)
    v = "" if valor is None or (isinstance(valor, float) and pd.isna(valor)) else str(valor)
    return container.text_input(rot, value=v, key=chave, help=campo.ajuda)


def _form(campos: list[Campo], valores: dict, chave: str, por_linha: int = 3) -> dict:
    visiveis = [c for c in campos if c.no_form]
    dados = {}
    for ini in range(0, len(visiveis), por_linha):
        grupo = visiveis[ini:ini + por_linha]
        cols = st.columns(por_linha)
        for col, c in zip(cols, grupo):
            dados[c.chave] = _widget(c, valores.get(c.chave), f"{chave}_{c.chave}", col)
    return dados


def _salvar_seguro(salvar, rid, dados) -> None:
    """Executa o salvar convertendo erros de banco (duplicado/em uso) em mensagem amigável."""
    try:
        salvar(rid, dados)
    except RegraNegocioError:
        raise
    except Exception as e:
        from database.connection import tipo_violacao

        tipo = tipo_violacao(e)
        if tipo == "unica":
            raise RegraNegocioError("Já existe um cadastro igual a este.")
        if tipo == "fk":
            raise RegraNegocioError("Este registro está em uso por outros lançamentos.")
        raise


def _checar(campos: list[Campo], dados: dict) -> None:
    for c in campos:
        if c.obrigatorio and c.no_form and (dados.get(c.chave) in (None, "") or dados.get(c.chave) == []):
            raise RegraNegocioError(f"Preencha: {c.rotulo}.")


def _sem_acento(t: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()


def filtrar(df: pd.DataFrame, termo: str, campos: list[Campo] | None = None,
            colunas: list[str] | None = None) -> pd.DataFrame:
    """Pesquisa em todas as colunas (como aparecem na tela), sem acento e sem maiúscula. Várias palavras = todas."""
    termo = _sem_acento(termo or "").strip()
    if df.empty or not termo:
        return df
    fmts = {c.chave: c for c in (campos or [])}
    cols = [c for c in (colunas or list(df.columns)) if c in df.columns]
    texto = pd.Series([""] * len(df), index=df.index)
    for c in cols:
        vals = df[c].map(lambda v, c=c: _formatar(fmts[c], v) if c in fmts else ("" if v is None else str(v)))
        texto = texto + " " + vals.map(_sem_acento)
    ok = pd.Series(True, index=df.index)
    for palavra in termo.split():
        ok &= texto.str.contains(palavra, regex=False)
    return df[ok]


MAX_COLUNAS_LISTA = 6


def tela(*, chave: str, titulo: str, df: pd.DataFrame, campos: list[Campo],
         salvar: Callable[[int | None, dict], Any], excluir: Callable[[int], Any] | None = None,
         icone: str = "", descricao: str = "", rotulo_registro: Callable[[dict], str] | None = None,
         colunas_extras: list[tuple[str, str]] | None = None, permitir_novo: bool = True,
         por_linha: int = 3, aviso_vazio: str = "Nenhum registro cadastrado ainda.") -> None:
    """Cadastro compacto: pesquisa + lista pequena (rola) → escolhe o resultado para editar · ➕ Novo recolhido."""
    regs_todos = df.to_dict("records") if not df.empty else []
    tema.secao(f"{icone} {titulo}".strip(), descricao)

    # ① barra: pesquisa · contagem · novo
    c1, c2 = st.columns([3, 1.2])
    termo = c1.text_input("🔎 Pesquisar", key=f"{chave}_busca", label_visibility="collapsed",
                          placeholder=f"🔎 Pesquisar em {titulo.lower()} (qualquer informação)…")
    colunas = [(c.chave, c.rotulo) for c in campos if c.na_tabela]
    for col_extra in (colunas_extras or []):
        colunas.append(col_extra)
    achados = filtrar(df, termo, campos, [c for c, _ in colunas]) if regs_todos else df
    c2.markdown(f'<span class="eco-pill">{len(regs_todos)} cadastrado(s)'
                + (f" · {len(achados)} encontrado(s)" if (termo or "").strip() else "") + "</span>",
                unsafe_allow_html=True)

    if permitir_novo:
        with st.expander(f"➕ Novo — {titulo.lower()}", expanded=not regs_todos):
            v = st.session_state.get(f"{chave}__novo_v", 0)
            with st.form(f"{chave}_novo_{v}"):
                dados = _form(campos, {c.chave: c.padrao for c in campos}, f"{chave}_n{v}", por_linha)
                if st.form_submit_button("💾 Salvar", type="primary"):
                    try:
                        _checar(campos, dados)
                        _salvar_seguro(salvar, None, dados)
                    except RegraNegocioError as e:
                        st.error(str(e))
                    else:
                        st.session_state[f"{chave}__novo_v"] = v + 1
                        ui.avisar(f"{titulo}: registro incluído.")
                        st.rerun()

    if not regs_todos:
        st.info(aviso_vazio)
        return
    if achados.empty:
        st.info("Nada encontrado com essa pesquisa.")
        return

    # ② lista compacta (rola; as demais informações aparecem ao editar)
    fmts = {c.chave: (lambda v, c=c: _formatar(c, v)) for c in campos}
    tabela_html(achados, colunas[:MAX_COLUNAS_LISTA], fmts, altura_max=230)

    # ③ editar ou excluir — escolhe entre os encontrados
    regs = achados.to_dict("records")
    rotulo = rotulo_registro or (lambda r: str(r.get(campos[0].chave) or f"#{r.get('id')}"))
    ids = [r["id"] for r in regs]
    nomes = {r["id"]: rotulo(r) for r in regs}
    k_sel = f"{chave}_alt_sel"
    if st.session_state.get(k_sel) not in [None, *ids]:
        st.session_state.pop(k_sel, None)  # a pesquisa mudou e o escolhido saiu da lista
    if (len(ids) == 1 and (termo or "").strip() and st.session_state.get(k_sel) is None
            and st.session_state.get(f"{chave}_fechou") != termo):
        st.session_state[k_sel] = ids[0]  # pesquisa achou um só: já abre para editar
    rid = st.selectbox("✏️ Editar ou excluir", [None] + ids, key=k_sel,
                       format_func=lambda i: (f"✏️ Escolha para editar ou excluir ({len(ids)} na lista)…"
                                              if i is None else nomes[i]))
    if rid is None:
        return
    atual = next(r for r in regs if r["id"] == rid)
    with st.container(border=True, key=f"cad_alt_{chave}"):
        st.markdown(f'<div class="eco-alt-titulo">✏️ {html.escape(nomes[rid])}</div>', unsafe_allow_html=True)
        with st.form(f"{chave}_alt_{rid}"):
            dados = _form(campos, atual, f"{chave}_a{rid}", por_linha)
            b1, b2 = st.columns([1, 1])
            gravar = b1.form_submit_button("💾 Salvar alterações", type="primary")
            fechar = b2.form_submit_button("✖️ Fechar")
        if fechar:
            st.session_state.pop(k_sel, None)
            st.session_state[f"{chave}_fechou"] = termo
            st.rerun()
        if gravar:
            try:
                _checar(campos, dados)
                _salvar_seguro(salvar, int(rid), dados)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                ui.avisar("Alteração salva.")
                st.rerun()
        if excluir:
            with st.popover("🗑️ Excluir este registro"):
                st.caption(f"Excluir **{nomes[rid]}**? Não dá para desfazer.")
                if st.button("Confirmar exclusão", key=f"{chave}_del_{rid}", type="primary"):
                    try:
                        excluir(int(rid))
                    except RegraNegocioError as e:
                        st.error(str(e))
                    except Exception as e:
                        from database.connection import tipo_violacao

                        st.error("Este registro está em uso e não pode ser excluído."
                                 if tipo_violacao(e) == "fk" else f"Não foi possível excluir: {e}")
                    else:
                        st.session_state.pop(k_sel, None)
                        ui.avisar("Registro excluído.", "info")
                        st.rerun()
