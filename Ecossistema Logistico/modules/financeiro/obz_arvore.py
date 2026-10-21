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
              'raiz [label="🎯 OBZ' + (f'\\n👤 {e(_TT[0])}' if _TT[0] else '') + '", fillcolor="#0B1F3A", '
              'fontcolor="white", fontsize=13];']
    for i, a in areas.iterrows():
        n = mapa[mapa["area"] == a["nome"]]
        dono = a["dono"] if isinstance(a["dono"], str) and a["dono"] else (f"↳ {_TT[0]} (OBZ)" if _TT[0] else
                                                                           "⚠️ sem dono")
        cor = "#e6f0fb" if a["nome"] == aberta else "#ffffff"
        linhas.append(f'a{i} [label="🏢 {e(a["nome"])}\\n{"" if dono.startswith(("↳", "⚠")) else "👤 "}{e(dono)}\\n{n["conta"].nunique()} contas", '
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
                              f'{"👤 " + e(sd) if sd else e(dono if dono.startswith(("↳", "⚠")) else "↳ " + dono)}", fontsize=10, '
                              f'fillcolor="{"#eefaf3" if sd else "#fff7e6"}"];')
                linhas.append(f"v{i}_{j} -> c{i}_{j}_{k};")
    linhas.append("}")
    return "\n".join(linhas)


_TT = [None]


def render(usuario: dict, pode: bool) -> None:
    _TT[0] = gs.nomes().get(obz.dono_tt())
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


# --- 👤 Donos em cascata: OBZ total → departamento → conta --------------------------------------------------------
def render_cascata(usuario: dict, pode: bool) -> None:
    """Cadastro em cascata: escolhe o dono do OBZ total, depois o departamento (e o dono dele), depois as contas
    daquele departamento. Quem fica vazio herda o dono de cima — e isso aparece na tela (↳ herdado)."""
    from modules.componentes.cadastro import filtrar

    areas = obz.areas()
    if areas.empty:
        st.info("Suba a Base OBZ (📥 Realizado & Base) para montar os departamentos.")
        return
    gest = gs.nomes()
    if not gest:
        st.warning("Nenhum gestor cadastrado. Cadastre em **👥 Gente & SSMA › 👔 Gestores** e volte aqui.")
        return
    ids = [None] + list(gest)
    nome = lambda i: gest.get(int(i), str(i)) if i is not None and i == i else None  # noqa: E731
    cas = obz.donos_cascata()

    # ① OBZ total
    tt = obz.dono_tt()
    with st.container(border=True):
        st.markdown("**① 🎯 Dono do OBZ total** — responde por tudo o que não tiver dono no departamento ou na conta.")
        c1, c2 = st.columns([3, 1])
        novo_tt = c1.selectbox("Dono do OBZ total", ids, index=ids.index(tt) if tt in ids else 0,
                               format_func=lambda i: "— sem dono —" if i is None else gest.get(i, str(i)),
                               key="obz_cas_tt", disabled=not pode, label_visibility="collapsed")
        if pode and c2.button("Salvar", key="obz_cas_tt_s", type="primary", **ui.LARGURA):
            ui.acao(obz.salvar_dono_tt, novo_tt, sucesso="Dono do OBZ total salvo.")

    n_her_d = int(areas["dono_gestor_id"].isna().sum())
    n_her_c = int((cas["nivel"] != "conta").sum()) if not cas.empty else 0
    n_sem = int(cas["dono_vale"].isna().sum()) if not cas.empty else 0
    st.caption(f"🏢 {len(areas)} departamentos · {n_her_d} herdam do OBZ total · 🧾 {len(cas)} contas · "
               f"{n_her_c} herdam de cima · {'⚠️ ' if n_sem else ''}{n_sem} sem dono nenhum")

    # ② departamento
    def rot_area(a: str) -> str:
        d = areas.set_index("nome").at[a, "dono_gestor_id"]
        return f"🏢 {a} — 👤 {nome(d)}" if pd.notna(d) else f"🏢 {a} — ↳ {nome(tt) or 'sem dono'} (herda do OBZ)"
    with st.container(border=True):
        st.markdown("**② 🏢 Departamento e o dono dele**")
        c1, c2, c3 = st.columns([2.2, 2, 0.9])
        area = c1.selectbox("Departamento", areas["nome"].tolist(), key="obz_cas_area", format_func=rot_area)
        atual = areas.set_index("nome").at[area, "dono_gestor_id"]
        atual = int(atual) if pd.notna(atual) else None
        herda_txt = f"↳ herdar do OBZ total ({nome(tt) or 'sem dono'})"
        dono_d = c2.selectbox("Dono do departamento", ids, index=ids.index(atual) if atual in ids else 0,
                              format_func=lambda i: herda_txt if i is None else gest.get(i, str(i)),
                              key=f"obz_cas_dd_{area}", disabled=not pode)
        c3.write("")
        if pode and c3.button("Salvar", key=f"obz_cas_dd_s_{area}", type="primary", **ui.LARGURA):
            ui.acao(obz.salvar_area, area, dono_d, sucesso="Dono do departamento salvo.")

    # ③ contas do departamento
    sub = cas[cas["area"] == area].sort_values(["vbz", "conta"]).reset_index(drop=True) if not cas.empty else cas
    with st.container(border=True):
        st.markdown(f"**③ 🧾 Contas de {area}** — vazio = herda o dono do departamento.")
        if sub.empty:
            st.caption("Nenhuma conta mapeada neste departamento.")
            return
        busca = st.text_input("🔎", key=f"obz_cas_busca_{area}", label_visibility="collapsed",
                              placeholder="🔎 Pesquisar conta (código, nome ou VBZ)…")
        sub = filtrar(sub, busca, colunas=["conta", "nome", "vbz"])
        dono_do_depto = nome(atual) or nome(tt)
        ed = pd.DataFrame({
            "conta": sub["conta"], "VBZ": sub["vbz"], "Conta": sub["conta"] + " · " + sub["nome"].fillna(""),
            "Dono da conta": [nome(x) for x in sub["dono_conta"]],
            "Vale": [(f"👤 {nome(c)}" if c is not None and c == c else
                      f"↳ {dono_do_depto} ({'depto' if atual else 'OBZ total'})" if dono_do_depto else "⚠️ sem dono")
                     for c in sub["dono_conta"]]})
        novo = st.data_editor(ed, hide_index=True, key=f"obz_cas_ed_{area}_{busca}", **ui.LARGURA, height=320,
                              disabled=["conta", "VBZ", "Conta", "Vale"] if pode else True,
                              column_order=["VBZ", "Conta", "Dono da conta", "Vale"],
                              column_config={"Dono da conta": st.column_config.SelectboxColumn(
                                  "👤 Dono da conta ✏️", options=list(gest.values())),
                                  "Vale": st.column_config.TextColumn("Quem responde")})
        if pode and st.button("💾 Salvar donos das contas", key=f"obz_cas_ct_s_{area}", type="primary"):
            por_nome = {v: k for k, v in gest.items()}
            n = 0
            for (_, o), (_, r) in zip(ed.iterrows(), novo.iterrows()):
                if (o["Dono da conta"] or None) != (r["Dono da conta"] or None):
                    obz.salvar_resp(area, o["conta"], por_nome.get(r["Dono da conta"]))
                    n += 1
            ui.avisar(f"{n} conta(s) atualizada(s).")
            st.rerun()
