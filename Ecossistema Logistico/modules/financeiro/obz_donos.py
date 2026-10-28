"""Financeiro › 👤 Donos — árvore OBZ total → departamento → VBZ → conta, com o dono de cada nível escolhido entre
os acessos criados no sistema (🔑 Gestão de Acessos). Quem fica sem dono herda o de cima.

Por baixo, cada acesso escolhido vira (ou reaproveita) o cadastro de gestor — é ele que o resto do OBZ usa para
tendências, justificativas, críticas do orçamento e alertas."""
import html as _h

import pandas as pd
import streamlit as st

from core import tema, ui
from repositories import usuarios_repo
from services import gestores_service as gs
from services import obz_service as obz

_CORES_VBZ = {"Pessoal": "#e87ba4", "Gerais": "#2a78d6", "Instalações": "#eda100", "Transporte": "#1baf7a"}
_CSS = """<style>
.dn-raiz{background:linear-gradient(120deg,#0B1F3A,#2a78d6);color:#fff;border-radius:16px;padding:.8rem 1rem;
 margin:.3rem 0 .7rem;display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem;align-items:center}
.dn-raiz b{font-size:1.15rem}.dn-raiz span{opacity:.9;font-size:.85rem}
.dn-grade{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:.6rem;margin-bottom:.8rem}
.dn-dep{background:#fff;border:1px solid #dfe5ee;border-radius:14px;border-left:6px solid var(--c);padding:.1rem .2rem}
.dn-dep summary{cursor:pointer;list-style:none;padding:.55rem .6rem}
.dn-dep summary::-webkit-details-marker{display:none}
.dn-dep .t{font-weight:800;color:#0B1F3A;font-size:.95rem}
.dn-dep .s{font-size:.8rem;color:#52514e;margin-top:.15rem}
.dn-dep .barra{height:6px;background:#eef1f6;border-radius:4px;margin:.4rem 0 .1rem;overflow:hidden}
.dn-dep .barra i{display:block;height:100%;background:#1baf7a}
.dn-vbz{margin:.2rem .6rem .5rem}
.dn-vbz h5{margin:.45rem 0 .2rem;font-size:.75rem;text-transform:uppercase;letter-spacing:.03em;color:var(--v)}
.dn-ct{display:flex;justify-content:space-between;gap:.4rem;font-size:.8rem;padding:.18rem 0;border-bottom:1px dashed #eef1f6}
.dn-ct span:first-child{color:#2b2f36;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dn-chip{border-radius:10px;padding:0 .45rem;font-size:.72rem;white-space:nowrap;font-weight:700}
.dn-chip.p{background:#e7f7f0;color:#0f6b4a}.dn-chip.h{background:#f1f3f7;color:#6b7280}
.dn-chip.x{background:#fdecec;color:#b42318}
</style>"""


def _e(t) -> str:
    return _h.escape(str(t or ""), quote=True)


def _usuarios() -> dict[int, str]:
    return {int(u["id"]): f"{u['nome']}" + (f" · {u['email']}" if u.get("email") else "")
            for u in usuarios_repo.listar(apenas_ativos=True)}


def render(usuario: dict, operacao_id: int) -> None:
    from core.auth import e_master

    st.markdown(_CSS, unsafe_allow_html=True)
    pode = e_master(usuario) or obz.pode_aprovar(usuario)
    areas = obz.areas()
    if areas.empty:
        st.info("Suba a Base OBZ (⚙️ OBZ: bases & cadastros › 📥 Realizado & Base) para montar os departamentos.")
        return
    us = _usuarios()
    if not us:
        st.warning("Nenhum acesso ativo. Crie os usuários em 🔑 Gestão de Acessos e volte aqui.")
        return
    g2u = gs.usuario_do_gestor()
    gest = gs.nomes()
    cas = obz.donos_cascata()
    tt_g = obz.dono_tt()

    def nome_g(gid) -> str | None:
        if gid is None or gid != gid:
            return None
        gid = int(gid)
        u = g2u.get(gid)
        if u in us:
            return us[u].split(" · ")[0]
        return f"{gest.get(gid, 'gestor ' + str(gid))} (sem acesso)"

    # ---------------- árvore
    n_ct = cas["conta"].nunique() if not cas.empty else 0
    sem = int(cas["dono_vale"].isna().sum()) if not cas.empty else 0
    st.markdown(f'<div class="dn-raiz"><div><b>🎯 OBZ total</b><br><span>👤 {_e(nome_g(tt_g) or "sem dono")}</span>'
                f'</div><span>🏢 {len(areas)} departamentos · 🧾 {n_ct} contas · '
                f'{"⚠️ " if sem else "✅ "}{sem} sem nenhum dono</span></div>', unsafe_allow_html=True)
    cards = []
    for a in areas.itertuples(index=False):
        sub = cas[cas["area"] == a.nome] if not cas.empty else cas
        dono_d = nome_g(a.dono_gestor_id)
        proprios = int(sub["dono_conta"].notna().sum()) if not sub.empty else 0
        tot = len(sub)
        cor = "#1baf7a" if dono_d and "(sem acesso)" not in dono_d else "#eda100" if tt_g else "#e34948"
        blocos = []
        for vbz, gv in sub.sort_values(["vbz", "conta"]).groupby("vbz", dropna=False):
            linhas = []
            for r in gv.itertuples(index=False):
                if r.dono_conta is not None and r.dono_conta == r.dono_conta:
                    chip = f'<span class="dn-chip p">👤 {_e(nome_g(r.dono_conta))}</span>'
                elif r.dono_vale is not None and r.dono_vale == r.dono_vale:
                    chip = f'<span class="dn-chip h">↳ {_e(nome_g(r.dono_vale))}</span>'
                else:
                    chip = '<span class="dn-chip x">⚠️ sem dono</span>'
                linhas.append(f'<div class="dn-ct"><span>{_e(r.conta)} · {_e(str(r.nome or "")[:34])}</span>{chip}</div>')
            v = vbz if isinstance(vbz, str) and vbz else "Sem VBZ"
            blocos.append(f'<div class="dn-vbz" style="--v:{_CORES_VBZ.get(v, "#6b7280")}"><h5>{_e(v)}</h5>'
                          + "".join(linhas) + "</div>")
        cards.append(f'<details class="dn-dep" style="--c:{cor}"><summary><div class="t">🏢 {_e(a.nome)}</div>'
                     f'<div class="s">👤 {_e(dono_d) if dono_d else "↳ herda do OBZ total"} · {tot} contas · '
                     f'{proprios} com dono próprio</div><div class="barra"><i style="width:'
                     f'{(proprios / tot * 100) if tot else 0:.0f}%"></i></div></summary>{"".join(blocos)}</details>')
    st.markdown('<div class="dn-grade">' + "".join(cards) + "</div>", unsafe_allow_html=True)
    st.caption("Clique num departamento para abrir os VBZ e as contas. 👤 = dono próprio · ↳ = herdado de cima.")
    antigos = sorted({nome_g(g) for g in list(areas["dono_gestor_id"].dropna()) +
                      (list(cas["dono_conta"].dropna()) if not cas.empty else []) + ([tt_g] if tt_g else [])
                      if "(sem acesso)" in str(nome_g(g))})
    if antigos:
        st.warning("Donos sem acesso ao sistema (cadastro antigo de gestor): **" + ", ".join(antigos) + "**. "
                   "Troque pelo acesso da pessoa abaixo — assim ela recebe os avisos e lança as tendências.")
    if not pode:
        st.info("🔒 Só o Master e os aprovadores do financeiro alteram os donos.")
        return

    # ---------------- edição
    tema.secao("✏️ Definir donos", "Escolha entre os acessos criados em 🔑 Gestão de Acessos.")
    ids = [None] + list(us)
    fmt = lambda i, vazio="— sem dono —": vazio if i is None else us.get(i, str(i))  # noqa: E731
    liberar = st.toggle("Liberar as telas do OBZ (painel, L.E, tendências, justificativas) para quem virar dono",
                        value=True, key="dn_liberar")

    def _gid(uid):
        if uid is None:
            return None
        gid = gs.gestor_de_usuario(int(uid))
        if liberar:
            gs.liberar_telas_obz(int(uid))
        return gid

    with st.container(border=True):
        st.markdown("**① 🎯 Dono do OBZ total** — responde por tudo o que não tiver dono no departamento ou na conta.")
        c1, c2 = st.columns([3, 1])
        atual = g2u.get(tt_g) if tt_g else None
        novo = c1.selectbox("Dono do OBZ total", ids, index=ids.index(atual) if atual in ids else 0,
                            format_func=fmt, key="dn_tt", label_visibility="collapsed")
        if c2.button("Salvar", key="dn_tt_s", type="primary", **ui.LARGURA):
            ui.acao(lambda: obz.salvar_dono_tt(_gid(novo)), sucesso="Dono do OBZ total salvo.")

    with st.container(border=True):
        st.markdown("**② 🏢 Donos dos departamentos** — vazio = herda o dono do OBZ total.")
        rot_u = {v: k for k, v in us.items()}
        ed = pd.DataFrame({"Departamento": areas["nome"],
                           "Dono": [us.get(g2u.get(int(g))) if pd.notna(g) else None for g in areas["dono_gestor_id"]],
                           "Hoje": [nome_g(g) or "↳ OBZ total" for g in areas["dono_gestor_id"]]})
        novo_d = st.data_editor(ed, hide_index=True, key="dn_dep_ed", **ui.LARGURA, disabled=["Departamento", "Hoje"],
                                column_config={"Dono": st.column_config.SelectboxColumn(
                                    "👤 Dono do departamento ✏️", options=list(us.values()), width="large"),
                                    "Hoje": st.column_config.TextColumn("Como está hoje")})
        if st.button("💾 Salvar donos dos departamentos", key="dn_dep_s", type="primary"):
            n = 0
            for (_, o), (_, r) in zip(ed.iterrows(), novo_d.iterrows()):
                if (o["Dono"] or None) != (r["Dono"] or None) or ("(sem acesso)" in str(o["Hoje"]) and r["Dono"]):
                    obz.salvar_area(o["Departamento"], _gid(rot_u.get(r["Dono"])))
                    n += 1
            ui.avisar(f"{n} departamento(s) atualizado(s).")
            st.rerun()

    with st.container(border=True):
        st.markdown("**③ 🧾 Donos das contas** — vazio = herda o dono do departamento.")
        c1, c2 = st.columns([1.3, 2])
        area = c1.selectbox("Departamento", areas["nome"].tolist(), key="dn_ct_area")
        busca = c2.text_input("🔎 Pesquisar", key=f"dn_ct_busca_{area}", placeholder="código, nome ou VBZ")
        sub = cas[cas["area"] == area].sort_values(["vbz", "conta"]).reset_index(drop=True) if not cas.empty else cas
        if busca and not sub.empty:
            b = busca.lower()
            sub = sub[sub["conta"].astype(str).str.contains(b) | sub["nome"].fillna("").str.lower().str.contains(b)
                      | sub["vbz"].fillna("").str.lower().str.contains(b)]
        if sub.empty:
            st.caption("Nenhuma conta neste departamento.")
            return
        ed = pd.DataFrame({"conta": sub["conta"], "VBZ": sub["vbz"],
                           "Conta": sub["conta"].astype(str) + " · " + sub["nome"].fillna(""),
                           "Dono": [us.get(g2u.get(int(g))) if pd.notna(g) else None for g in sub["dono_conta"]],
                           "Quem responde": [(f"👤 {nome_g(c)}" if pd.notna(c) else
                                              f"↳ {nome_g(v)} ({n})" if pd.notna(v) else "⚠️ sem dono")
                                             for c, v, n in zip(sub["dono_conta"], sub["dono_vale"], sub["nivel"])]})
        novo_c = st.data_editor(ed, hide_index=True, key=f"dn_ct_ed_{area}_{busca}", **ui.LARGURA, height=360,
                                disabled=["conta", "VBZ", "Conta", "Quem responde"],
                                column_order=["VBZ", "Conta", "Dono", "Quem responde"],
                                column_config={"Dono": st.column_config.SelectboxColumn(
                                    "👤 Dono da conta ✏️", options=list(us.values()), width="large")})
        a1, a2 = st.columns([1, 1.4])
        if a1.button("💾 Salvar donos das contas", key=f"dn_ct_s_{area}", type="primary"):
            n = 0
            for (_, o), (_, r) in zip(ed.iterrows(), novo_c.iterrows()):
                if (o["Dono"] or None) != (r["Dono"] or None):
                    obz.salvar_resp(area, o["conta"], _gid(rot_u.get(r["Dono"])))
                    n += 1
            ui.avisar(f"{n} conta(s) atualizada(s).")
            st.rerun()
        with a2.popover("👥 Mesmo dono para todas as contas listadas"):
            todos = st.selectbox("Dono", ids, format_func=lambda i: fmt(i, "— limpar (herdar do departamento) —"),
                                 key=f"dn_ct_todos_{area}")
            if st.button("Aplicar", key=f"dn_ct_todos_s_{area}"):
                gid = _gid(todos)
                for c in ed["conta"]:
                    obz.salvar_resp(area, c, gid)
                ui.avisar(f"{len(ed)} conta(s) atualizada(s).")
                st.rerun()
