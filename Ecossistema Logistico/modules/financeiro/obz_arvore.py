"""🌳 Árvore de donos do OBZ: departamento (dono) → VBZ → conta (sub-dono). Cadastro direto na árvore."""
import html

import pandas as pd
import streamlit as st

from core import tema, ui
from services import gestores_service as gs
from services import obz_service as obz

_CORES_VBZ = {"Pessoal": "#e87ba4", "Gerais": "#2a78d6", "Instalações": "#eda100", "Transporte": "#1baf7a"}


def _dot(areas: pd.DataFrame, mapa: pd.DataFrame, resp: pd.DataFrame, aberta: str | None) -> str:
    e = lambda t: html.escape(str(t or ""), quote=True).replace("\n", " ")  # noqa: E731
    linhas = ['digraph G {', 'rankdir=LR; bgcolor="transparent"; nodesep=0.18; ranksep=0.5;',
              'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#c9d3e3", '
              'fillcolor="#ffffff"]; edge [color="#c9d3e3", arrowsize=0.6];',
              'raiz [label="🎯 OBZ", fillcolor="#0B1F3A", fontcolor="white", fontsize=13];']
    for i, a in areas.iterrows():
        n = mapa[mapa["area"] == a["nome"]]
        dono = a["dono"] if isinstance(a["dono"], str) and a["dono"] else "⚠️ sem dono"
        cor = "#e6f0fb" if a["nome"] == aberta else "#ffffff"
        linhas.append(f'a{i} [label="🏢 {e(a["nome"])}\\n👤 {e(dono)}\\n{n["conta"].nunique()} contas", '
                      f'fillcolor="{cor}", color="{"#2a78d6" if a["nome"] == aberta else "#c9d3e3"}"];')
        linhas.append(f"raiz -> a{i};")
        if a["nome"] != aberta:
            continue
        rs = resp[resp["area"] == a["nome"]].set_index("conta")["subdono"] if not resp.empty else pd.Series(dtype=object)
        for j, (vbz, g) in enumerate(n.groupby("vbz")):
            cor_v = _CORES_VBZ.get(vbz, "#9aa3b2")
            linhas.append(f'v{i}_{j} [label="{e(vbz)}", fillcolor="{cor_v}", fontcolor="white", color="{cor_v}"];')
            linhas.append(f"a{i} -> v{i}_{j};")
            for k, (_, c) in enumerate(g.drop_duplicates("conta").iterrows()):
                sd = rs.get(c["conta"])
                linhas.append(f'c{i}_{j}_{k} [label="{e(c["conta"])} · {e(str(c["nome"])[:30])}\\n'
                              f'{"👤 " + e(sd) if sd else "— sem sub-dono"}", fontsize=10, '
                              f'fillcolor="{"#eefaf3" if sd else "#fff7e6"}"];')
                linhas.append(f"v{i}_{j} -> c{i}_{j}_{k};")
    linhas.append("}")
    return "\n".join(linhas)


def render(usuario: dict, pode: bool) -> None:
    areas = obz.areas()
    if areas.empty:
        st.info("Suba a Base OBZ (📥 Realizado & Base) para montar os departamentos.")
        return
    gest = gs.nomes()
    if not gest:
        st.warning("Nenhum gestor cadastrado. Cadastre em **👥 Gente & SSMA › 👔 Gestores** e volte aqui para "
                   "vincular como dono do departamento e sub-dono das contas.")
    mapa = obz.query_df("""SELECT m.conta, m.depto, m.area, m.vbz, c.nome FROM obz_mapa m
                           LEFT JOIN obz_contas c ON c.codigo = m.conta""")
    resp = obz.resp_df()
    c1, c2 = st.columns([1, 2])
    aberta = c1.selectbox("Abrir departamento na árvore", ["— todos fechados —"] + areas["nome"].tolist(),
                          key="obz_arv_area")
    aberta = None if aberta.startswith("—") else aberta
    sem_dono = areas["dono"].isna().sum()
    sem_sub = mapa["conta"].nunique() - (resp["conta"].nunique() if not resp.empty else 0)
    c2.markdown(f"🏢 **{len(areas)}** departamentos · ⚠️ **{sem_dono}** sem dono · 🧾 **{mapa['conta'].nunique()}** "
                f"contas · **{max(sem_sub, 0)}** sem sub-dono")
    try:
        st.graphviz_chart(_dot(areas, mapa, resp, aberta), **ui.LARGURA)
    except Exception:
        st.caption("(não foi possível desenhar a árvore neste navegador)")
    if not aberta:
        st.caption("Escolha um departamento acima para abrir os VBZ e as contas e cadastrar os donos.")
        return
    tema.secao(f"✏️ Donos de {aberta}")
    ids = [None] + list(gest)
    fmt = lambda i: "— sem dono —" if i is None else gest.get(i, str(i))  # noqa: E731
    atual = areas.set_index("nome").at[aberta, "dono_gestor_id"]
    atual = int(atual) if pd.notna(atual) else None
    c1, c2 = st.columns([2, 1])
    dono = c1.selectbox("👤 Dono do departamento (gestor)", ids, index=ids.index(atual) if atual in ids else 0,
                        format_func=fmt, key=f"obz_arv_dono_{aberta}", disabled=not pode)
    c2.write("")
    if pode and c2.button("Salvar dono", key=f"obz_arv_dono_s_{aberta}", type="primary"):
        ui.acao(obz.salvar_area, aberta, dono, sucesso="Dono do departamento salvo.")
    n = mapa[mapa["area"] == aberta].drop_duplicates("conta")
    rs = resp[resp["area"] == aberta].set_index("conta")["gestor_id"] if not resp.empty else pd.Series(dtype=float)
    ed = pd.DataFrame({"conta": n["conta"], "VBZ": n["vbz"], "Conta": n["conta"] + " · " + n["nome"].fillna(""),
                       "Sub-dono": [gest.get(int(rs.get(c))) if pd.notna(rs.get(c)) else None for c in n["conta"]]})
    ed = ed.sort_values(["VBZ", "conta"]).reset_index(drop=True)
    novo = st.data_editor(ed, hide_index=True, key=f"obz_arv_ed_{aberta}", **ui.LARGURA,
                          disabled=["conta", "VBZ", "Conta"] if pode else True, column_order=["VBZ", "Conta", "Sub-dono"],
                          column_config={"Sub-dono": st.column_config.SelectboxColumn(
                              "👤 Sub-dono da conta ✏️", options=list(gest.values()))})
    if pode and st.button("💾 Salvar sub-donos", key=f"obz_arv_sd_s_{aberta}"):
        por_nome = {v: k for k, v in gest.items()}
        for (_, o), (_, r) in zip(ed.iterrows(), novo.iterrows()):
            if (o["Sub-dono"] or None) != (r["Sub-dono"] or None):
                obz.salvar_resp(aberta, o["conta"], por_nome.get(r["Sub-dono"]))
        ui.avisar("Sub-donos salvos.")
        st.rerun()


def render_areas(usuario: dict, pode: bool) -> None:
    st.caption("Departamentos do OBZ (as abas da Base). Renomeie, mude a ordem, defina o dono ou exclua.")
    areas = obz.areas()
    gest = gs.nomes()
    ed = pd.DataFrame({"nome": areas["nome"], "novo_nome": areas["nome"], "ordem": areas["ordem"].fillna(0).astype(int),
                       "dono": [gest.get(int(i)) if pd.notna(i) else None for i in areas["dono_gestor_id"]],
                       "excluir": False})
    novo = st.data_editor(ed, hide_index=True, num_rows="dynamic", key="obz_areas_ed", **ui.LARGURA,
                          disabled=not pode, column_order=["novo_nome", "ordem", "dono", "excluir"],
                          column_config={"novo_nome": st.column_config.TextColumn("Departamento ✏️"),
                                         "ordem": st.column_config.NumberColumn("Ordem", step=1),
                                         "dono": st.column_config.SelectboxColumn("Dono", options=list(gest.values())),
                                         "excluir": st.column_config.CheckboxColumn("🗑️")})
    if pode and st.button("💾 Salvar departamentos", key="obz_areas_s", type="primary"):
        por_nome = {v: k for k, v in gest.items()}
        for _, r in novo.iterrows():
            nome = r["nome"] if isinstance(r["nome"], str) and r["nome"] else None
            novo_nome = str(r["novo_nome"] or "").strip()
            if r["excluir"] and nome:
                obz.excluir_area(nome)
            elif nome:
                obz.salvar_area(nome, por_nome.get(r["dono"]), int(r["ordem"] or 0), novo_nome)
            elif novo_nome:
                obz.salvar_area(novo_nome, por_nome.get(r["dono"]), int(r["ordem"] or 0))
        ui.avisar("Departamentos salvos.")
        st.rerun()
