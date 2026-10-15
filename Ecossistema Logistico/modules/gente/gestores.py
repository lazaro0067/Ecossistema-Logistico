"""Gente › 👔 Gestores — cadastro, acesso ao sistema e vínculos de dono no OBZ."""
import pandas as pd
import streamlit as st

from core import tema, ui
from core.auth import e_master, operacoes_permitidas
from services import gestores_service as gs
from services import obz_service as obz
from services.erros import RegraNegocioError


def render(usuario: dict, operacao_id: int) -> None:
    tema.secao("👔 Gestores", "Cadastre os gestores; depois crie o acesso ao sistema e vincule como dono de "
               "departamento e sub-dono de contas do OBZ (💰 Financeiro › ⚙️ Cadastros OBZ › 🌳 Árvore de donos).")
    pode = e_master(usuario) or obz.pode_aprovar(usuario)
    areas = obz.areas()["nome"].tolist()
    with st.expander("➕ Novo gestor", expanded=gs.listar().empty):
        with st.form("ges_novo", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            nome = c1.text_input("Nome *")
            cargo = c2.text_input("Cargo")
            depto = c3.selectbox("Departamento", [""] + areas)
            c4, c5 = st.columns(2)
            email = c4.text_input("E-mail (vira o login)")
            tel = c5.text_input("Telefone")
            if st.form_submit_button("Cadastrar", type="primary", disabled=not pode):
                ui.acao(gs.salvar, None, nome, cargo, email, tel, depto, sucesso="Gestor cadastrado.")
    df = gs.listar()
    if df.empty:
        st.info("Nenhum gestor cadastrado ainda.")
        return
    # vínculos atuais
    ar = obz.areas()
    dono_de = ar.dropna(subset=["dono_gestor_id"]).groupby("dono_gestor_id")["nome"].apply(lambda s: ", ".join(s))
    rp = obz.resp_df()
    n_contas = rp.groupby("gestor_id")["conta"].nunique() if not rp.empty else pd.Series(dtype=int)
    tema.kpis([
        {"titulo": "Gestores", "valor": ui.numero(len(df)), "icone": "👔", "status": "info"},
        {"titulo": "Com acesso ao sistema", "valor": ui.numero(df["usuario_id"].notna().sum()), "icone": "🔑",
         "status": "info"},
        {"titulo": "Donos de departamento", "valor": ui.numero(len(dono_de)), "icone": "🏢", "status": "info",
         "detalhe": f"{ar['dono_gestor_id'].isna().sum()} departamento(s) sem dono",},
        {"titulo": "Sub-donos de contas", "valor": ui.numero(len(n_contas)), "icone": "🧾", "status": "info"},
    ], key="kp_ges")
    vis = pd.DataFrame({"id": df["id"], "Nome": df["nome"], "Cargo": df["cargo"].fillna(""),
                        "Departamento": df["departamento"].fillna(""), "E-mail": df["email"].fillna(""),
                        "Telefone": df["telefone"].fillna(""), "Ativo": df["ativo"].astype(int) == 1,
                        "Acesso": [("✅ " + str(l_)) if pd.notna(u) else "—" for u, l_ in zip(df["usuario_id"],
                                                                                          df["login_acesso"])],
                        "Dono de": df["id"].map(dono_de).fillna(""),
                        "Contas (sub-dono)": df["id"].map(n_contas).fillna(0).astype(int), "Excluir": False})
    novo = st.data_editor(vis, hide_index=True, key="ges_ed", **ui.LARGURA,
                          disabled=["id", "Acesso", "Dono de", "Contas (sub-dono)"] if pode else True,
                          column_config={"id": None, "Departamento": st.column_config.SelectboxColumn(options=areas),
                                         "Excluir": st.column_config.CheckboxColumn("🗑️")})
    if pode and st.button("💾 Salvar gestores", key="ges_salvar"):
        try:
            for (_, o), (_, r) in zip(vis.iterrows(), novo.iterrows()):
                if r["Excluir"]:
                    gs.excluir(int(o["id"]))
                elif any(o[c] != r[c] for c in ("Nome", "Cargo", "Departamento", "E-mail", "Telefone", "Ativo")):
                    gs.salvar(int(o["id"]), r["Nome"], r["Cargo"], r["E-mail"], r["Telefone"], r["Departamento"] or "",
                              bool(r["Ativo"]))
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar("Gestores salvos.")
            st.rerun()

    tema.secao("🔑 Criar acesso ao sistema")
    sem = df[df["usuario_id"].isna() & (df["ativo"].astype(int) == 1)]
    if sem.empty:
        st.success("Todos os gestores ativos já têm acesso.")
        return
    c1, c2, c3 = st.columns([2, 2, 1])
    gid = c1.selectbox("Gestor", sem["id"].tolist(), format_func=dict(zip(sem["id"], sem["nome"])).get, key="ges_ac")
    ops = operacoes_permitidas(usuario)
    sel_ops = c2.multiselect("Revendas", [o["id"] for o in ops], default=[operacao_id] if operacao_id else [],
                             format_func={o["id"]: o["nome"] for o in ops}.get, key="ges_ac_ops")
    c3.write("")
    if c3.button("Criar acesso", type="primary", key="ges_ac_btn", disabled=not e_master(usuario)):
        try:
            r = gs.criar_acesso(int(gid), sel_ops)
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            if r.get("senha_provisoria"):
                st.success(f"Acesso criado. Senha provisória: **{r['senha_provisoria']}** (o gestor troca no primeiro "
                           "login).")
            else:
                ui.avisar("Acesso criado — senha enviada por e-mail.")
                st.rerun()
    st.caption("O acesso libera a 🎯 Gestão OBZ (painel, tendências, reuniões). Somente o Master cria acessos; ajuste "
               "pastas em 🔑 Gestão de Acessos.")
