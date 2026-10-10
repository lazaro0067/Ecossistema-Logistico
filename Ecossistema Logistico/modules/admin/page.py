"""Painel Master — usuários, permissões por pasta e operações."""
import pandas as pd
import streamlit as st

from config.settings import MODULOS, PERFIL_MASTER, PERFIL_MOTORISTA, PERFIS

PERFIS_SISTEMA = [p for p in PERFIS if p != PERFIL_MOTORISTA]  # motorista é criado no App Carreteiro
from core import tema, ui
from repositories import operacoes_repo, usuarios_repo
from services import cadastros_service, email_service, usuarios_service
from services.erros import RegraNegocioError


# --- Árvore de permissões (pastas e subpastas) ---------------------------
def _arvore_permissoes(chave: str, atuais: list[str]) -> list[str]:
    """Um bloco por pasta: 'pasta inteira' ou abas escolhidas. Devolve a lista de chaves."""
    escolhidas: list[str] = []
    cols = st.columns(3)
    for i, (mod, info) in enumerate(MODULOS.items()):
        with cols[i % 3].container(border=True):
            tem_inteira = mod in atuais
            abas_atuais = [a for a in info["abas"] if f"{mod}.{a}" in atuais]
            inteira = st.checkbox(f"{info['icone']} **{info['rotulo']}** — pasta inteira",
                                  value=tem_inteira, key=f"{chave}_p_{mod}",
                                  help="Acesso a todas as abas, inclusive as que forem criadas no futuro.")
            abas_marcadas = [aba for aba, rotulo in info["abas"].items()
                             if st.checkbox(f"↳ {rotulo}", value=aba in abas_atuais or tem_inteira,
                                            key=f"{chave}_p_{mod}_{aba}")]
            if inteira:
                escolhidas.append(mod)
            else:
                escolhidas += [f"{mod}.{aba}" for aba in abas_marcadas]
    return escolhidas


def _form_usuario(existente: dict | None, operacoes: list[dict]) -> None:
    u = existente or {}
    chave = f"u{u.get('id', 'novo')}_{st.session_state.get('_adm_ver', 0)}"

    with st.form(f"{chave}_form", border=False):
        st.markdown("**🏢 Revendas com acesso** — marque uma ou mais *")
        filiais = [o for o in operacoes if not operacoes_repo.e_consolidada(o["id"])]
        atuais_ops = set(u.get("operacoes") or [])
        todas_ops = st.checkbox("Todas as revendas (inclusive as que forem criadas depois)",
                                value=bool(existente) and not atuais_ops, key=f"{chave}_ops_todas")
        cols_op = st.columns(max(len(filiais), 1))
        marcadas = [o["id"] for col, o in zip(cols_op, filiais)
                    if col.checkbox(f"🏢 {o['nome']}", value=o["id"] in atuais_ops, key=f"{chave}_op_{o['id']}")]
        st.caption("A visão consolidada (ex.: Bahia) aparece sozinha para quem tem todas as filiais dela.")
        st.divider()
        st.markdown("**Dados de acesso** — o e-mail é o login")
        c1, c2, c3 = st.columns(3)
        email = c1.text_input("E-mail (login) *", value=u.get("email") or "", key=f"{chave}_email",
                              placeholder="nome@grupolima.com.br")
        nome = c2.text_input("Nome completo *", value=u.get("nome", ""), key=f"{chave}_nome")
        smtp_ok = email_service.configurado()
        rot_senha = ("Nova senha (vazio = manter)" if existente else
                     "Senha inicial (vazio = gerar e enviar por e-mail)" if smtp_ok else "Senha inicial (vazio = gerar)")
        senha = c3.text_input(rot_senha, type="password", key=f"{chave}_senha")
        c5, c6 = st.columns([2, 1])
        cargo = c5.text_input("Cargo", value=u.get("cargo") or "", key=f"{chave}_cargo")
        perfil = c6.selectbox("Perfil", PERFIS_SISTEMA, index=PERFIS_SISTEMA.index(u.get("perfil", "Operacional"))
                              if u.get("perfil", "Operacional") in PERFIS_SISTEMA else 2,
                              key=f"{chave}_perfil",
                              help="Master: acesso total e gestão de acessos. Gestor: define metas. "
                                   "Operacional: usa as pastas liberadas.")
        c7, c8, c9, c10 = st.columns(4)
        aprov = c7.checkbox("Aprova fretes", value=bool(u.get("e_aprovador")), key=f"{chave}_aprov")
        alcada = c8.number_input("Alçada (R$)", min_value=0.0, value=float(u.get("alcada") or 0), step=1000.0,
                                 key=f"{chave}_alc", help="Só vale se “Aprova fretes” estiver marcado.")
        ativo = c9.checkbox("Usuário ativo", value=bool(u.get("ativo", 1)), key=f"{chave}_ativo")
        trocar = c10.checkbox("Exigir troca de senha", value=bool(u.get("trocar_senha", 1)), key=f"{chave}_troca",
                              help="No próximo login o usuário cria a própria senha.")


        st.markdown("**📁 Permissões por pasta** — marque a pasta inteira ou só as telas (↳). "
                    "Nada é gravado até clicar em **Salvar**.")
        permissoes = _arvore_permissoes(chave, u.get("modulos", []))
        st.caption("Perfil Master acessa todas as pastas, independentemente das marcações.")
        salvar = st.form_submit_button("💾 Salvar usuário", type="primary")
    if salvar:
        if perfil == PERFIL_MASTER:
            permissoes = []
        if not todas_ops and not marcadas and perfil != PERFIL_MASTER:
            st.error("Escolha a(s) revenda(s) que o usuário vai acessar (ou marque “Todas as revendas”).")
            return
        ops = [] if todas_ops else marcadas
        try:
            res = usuarios_service.salvar_usuario(
                id=u.get("id"), nome=nome, senha=senha, email=email, cargo=cargo, perfil=perfil,
                e_aprovador=aprov, alcada=alcada, ativo=ativo, trocar_senha=trocar, permissoes=permissoes,
                operacoes=ops, enviar_email=True)
        except RegraNegocioError as e:
            st.error(str(e))
            return
        st.session_state["_adm_ver"] = st.session_state.get("_adm_ver", 0) + 1  # limpa o formulário
        if res["email_enviado"]:
            ui.avisar(f"Usuário '{nome}' criado! Os dados de acesso foram enviados para {email.strip().lower()}.")
        elif res["senha_provisoria"]:
            st.session_state["_adm_senha"] = (nome, email.strip().lower(), res["senha_provisoria"])
            ui.avisar(f"Usuário '{nome}' criado!")
        else:
            ui.avisar(f"Usuário '{nome}' salvo!")
        st.rerun()


# --- Lista de usuários em cartões -------------------------------------------
_CSS_USR = """
<style>
.usr-card { display:flex; gap:.8rem; align-items:flex-start; }
.usr-av { flex:0 0 2.7rem; height:2.7rem; border-radius:50%; display:grid; place-items:center; font-weight:800;
    color:#fff; font-size:1rem; background:var(--av); }
.usr-info { min-width:0; flex:1; }
.usr-nome { font-weight:800; font-size:1.02rem; color:#0B1F3A; line-height:1.2; }
.usr-mail { color:#5f6b7a; font-size:.84rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.usr-cargo { color:#3d3c39; font-size:.84rem; margin-top:.1rem; }
.usr-tags { display:flex; flex-wrap:wrap; gap:.3rem; margin-top:.45rem; }
.usr-tag { font-size:.72rem; font-weight:700; padding:.12rem .5rem; border-radius:999px; background:#eef3fa; color:#2a5ca8; }
.usr-tag.master { background:#fff1db; color:#a35c00; } .usr-tag.gestor { background:#ece8fb; color:#5b3fc4; }
.usr-tag.ok { background:#e8f6ee; color:#146c43; } .usr-tag.off { background:#f0efec; color:#77766f; }
.usr-tag.aprov { background:#e6f4f7; color:#0d6e80; } .usr-tag.novo { background:#fff6d6; color:#8a6100; }
.usr-rod { color:#77766f; font-size:.76rem; margin-top:.45rem; line-height:1.35; }
</style>
"""
_CORES_AV = ["#2a78d6", "#7a4fc9", "#0d8a6a", "#c2571a", "#b8336a", "#3f6fb5", "#5d7d1f"]


def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() in ("", "None", "nan", "NaT")


def _quando(v) -> str:
    from core import tempo

    if _vazio(v):
        return "Nunca acessou"
    d = tempo.parse_dt(str(v))
    if not d:
        return str(v)
    seg = (tempo.agora() - d).total_seconds()
    if seg < 3600:
        return f"há {max(int(seg // 60), 1)} min"
    if seg < 86400:
        return f"há {int(seg // 3600)} h"
    if seg < 86400 * 7:
        return f"há {int(seg // 86400)} dia(s)"
    return f"{d:%d/%m/%Y}"


def _tabela_usuarios(df: pd.DataFrame) -> pd.DataFrame:
    """Versão de leitura (detalhes dos cards e download)."""
    if df.empty:
        return pd.DataFrame(columns=["Nome", "E-mail", "Cargo", "Perfil", "Situação", "Aprova frete", "Operações",
                                     "Pastas liberadas", "Último acesso"])
    return pd.DataFrame({
        "Nome": df["nome"], "E-mail": df["email"].map(lambda v: "—" if _vazio(v) else v),
        "Cargo": df["cargo"].map(lambda v: "—" if _vazio(v) else v), "Perfil": df["perfil"],
        "Situação": df["situacao"].map(lambda v: "🟢 Ativo" if v == "Ativo" else "⚪ Inativo"),
        "Aprova frete": [ui.moeda(a) if s == "Sim" else "—" for s, a in zip(df["aprovador"], df["alcada"])],
        "Operações": df["operacoes"],
        "Pastas liberadas": [("Todas" if p == PERFIL_MASTER else int(n or 0)) for p, n in zip(df["perfil"], df["pastas"])],
        "Último acesso": df["ultimo_acesso"].map(_quando),
    })


def _abrir(uid: int, modo: str) -> None:
    st.session_state["adm_modo"] = modo
    st.session_state["adm_edit"] = uid


def _cards_usuarios(df: pd.DataFrame) -> None:
    import html

    if df.empty:
        st.info("Nenhum usuário encontrado com esse filtro.")
        return
    st.markdown(_CSS_USR, unsafe_allow_html=True)
    e = lambda v: html.escape("" if _vazio(v) else str(v))  # noqa: E731
    regs = df.to_dict("records")
    for ini in range(0, len(regs), 3):
        for col, r in zip(st.columns(3), regs[ini:ini + 3]):
            iniciais = "".join(p[0] for p in str(r["nome"]).split()[:2]).upper() or "?"
            cor = _CORES_AV[int(r["id"]) % len(_CORES_AV)]
            perfil = str(r["perfil"])
            tags = [f'<span class="usr-tag {perfil.lower()}">{e(perfil)}</span>',
                    '<span class="usr-tag ok">● Ativo</span>' if r["situacao"] == "Ativo"
                    else '<span class="usr-tag off">○ Inativo</span>']
            if r["aprovador"] == "Sim":
                tags.append(f'<span class="usr-tag aprov">✅ Aprova até {e(ui.moeda(r["alcada"]))}</span>')
            if _vazio(r["ultimo_acesso"]):
                tags.append('<span class="usr-tag novo">⏳ 1º login pendente</span>')
            cargo = "" if _vazio(r["cargo"]) else f'<div class="usr-cargo">{e(r["cargo"])}</div>'
            pastas = "todas as pastas" if perfil == PERFIL_MASTER else f"{int(r['pastas'] or 0)} pasta(s)/tela(s)"
            with col.container(border=True, key=f"usr_{r['id']}"):
                st.markdown(
                    f'<div class="usr-card"><div class="usr-av" style="--av:{cor}">{e(iniciais)}</div>'
                    f'<div class="usr-info"><div class="usr-nome">{e(r["nome"])}</div>'
                    f'<div class="usr-mail">{e(r["email"]) or "sem e-mail"}</div>'
                    f'{cargo}'
                    f'<div class="usr-tags">{"".join(tags)}</div>'
                    f'<div class="usr-rod">🏢 {e(r["operacoes"])} · 📁 {pastas}<br>🕒 Último acesso: '
                    f'{e(_quando(r["ultimo_acesso"]))}</div></div></div>', unsafe_allow_html=True)
                b1, b2 = st.columns(2)
                b1.button("✏️ Editar", key=f"usr_ed_{r['id']}", on_click=_abrir, args=(int(r["id"]), "✏️ Editar usuário"),
                          **ui.LARGURA)
                b2.button("🔁 Senha", key=f"usr_pw_{r['id']}", on_click=_abrir, args=(int(r["id"]), "🔁 Resetar senha"),
                          **ui.LARGURA)


def _aba_usuarios(usuario_logado: dict) -> None:
    if st.session_state.get("_adm_senha"):
        nome, email, senha = st.session_state["_adm_senha"]
        st.success(f"Envie ao usuário **{nome}** — login: **{email}** · senha provisória:")
        st.code(senha, language=None)
        if st.button("✓ Já anotei", key="adm_senha_ok"):
            st.session_state.pop("_adm_senha")
            st.rerun()
    if not email_service.configurado():
        st.info("📧 O envio de e-mail não está configurado: senhas provisórias aparecem na tela e o "
                "“Esqueci minha senha” fica indisponível. Veja o README (seção E-mail) para ativar.")
    todos_df = usuarios_repo.listar_df()
    df = todos_df[todos_df["perfil"] != PERFIL_MOTORISTA].reset_index(drop=True) if not todos_df.empty else todos_df
    n_mot = int((todos_df["perfil"] == PERFIL_MOTORISTA).sum()) if not todos_df.empty else 0
    vis = _tabela_usuarios(df)
    ativos = df[df["situacao"] == "Ativo"]
    nunca = df[df["ultimo_acesso"].map(_vazio)]
    tema.kpis([
        {"titulo": "Usuários ativos", "valor": len(ativos), "icone": "👤", "status": "info",
         "detalhe": f"de {len(df)} cadastrados", "dados": vis[vis["Situação"].str.contains("Ativo")]},
        {"titulo": "Masters", "valor": int((df["perfil"] == PERFIL_MASTER).sum()), "icone": "🔑", "status": "info",
         "dados": vis[vis["Perfil"] == PERFIL_MASTER]},
        {"titulo": "Aprovadores de frete", "valor": int((df["aprovador"] == "Sim").sum()), "icone": "✅",
         "status": "info", "dados": vis[vis["Aprova frete"] != "—"]},
        {"titulo": "Nunca acessaram", "valor": len(nunca), "icone": "⏳",
         "status": "atencao" if len(nunca) else "bom", "selo": "aguardando 1º login" if len(nunca) else None,
         "dados": vis[vis["Último acesso"] == "Nunca acessou"]},
    ], key="kp_admin")
    st.caption(f"🚛 Os {n_mot} motorista(s) do App Carreteiro não aparecem aqui — o acesso deles é só pelo app "
               "e fica em **Puxada › App Carreteiro › Acessos** (ou ⚙️ Cadastros › 👤 Motoristas).")

    c1, c2, c3 = st.columns([2, 1, 1])
    busca = c1.text_input("🔎 Buscar", placeholder="nome, e-mail ou cargo", key="adm_busca",
                          label_visibility="collapsed")
    f_perfil = c2.selectbox("Perfil", ["Todos os perfis"] + PERFIS_SISTEMA, key="adm_f_perfil",
                            label_visibility="collapsed")
    f_sit = c3.selectbox("Situação", ["Ativos", "Inativos", "Todos"], key="adm_f_sit", label_visibility="collapsed")
    lista = df
    if busca.strip():
        t = busca.strip().lower()
        lista = lista[lista[["nome", "email", "cargo"]].fillna("").astype(str).agg(" ".join, axis=1)
                      .str.lower().str.contains(t, regex=False)]
    if f_perfil != "Todos os perfis":
        lista = lista[lista["perfil"] == f_perfil]
    if f_sit != "Todos":
        lista = lista[lista["situacao"] == ("Ativo" if f_sit == "Ativos" else "Inativo")]
    _cards_usuarios(lista)
    ui.downloads(vis, "usuarios_sistema", key="dl_usuarios")

    operacoes = operacoes_repo.listar()
    modo = st.radio("O que deseja fazer?", ["➕ Novo usuário", "✏️ Editar usuário", "🔁 Resetar senha"],
                    horizontal=True, key="adm_modo")
    with st.container(border=True):
        if modo.startswith("➕"):
            _form_usuario(None, operacoes)
        else:
            todos = [r for r in usuarios_repo.listar(apenas_ativos=False) if r["perfil"] != PERFIL_MOTORISTA]
            regs = [{"id": r["id"], "nome": f"{r['nome']} ({r['email'] or r['login']})"} for r in todos]
            uid = ui.select_registro("Usuário", regs, key="adm_edit")
            if not uid:
                return
            if modo.startswith("✏️"):
                _form_usuario({**usuarios_repo.buscar(uid), **usuarios_repo.carregar_sessao(uid)}, operacoes)
            else:
                alvo = usuarios_repo.buscar(uid)
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Código por e-mail** — o próprio usuário cria a nova senha.")
                    if st.button(f"📧 Enviar código para {alvo['email'] or '—'}", key="adm_codigo",
                                 disabled=not (email_service.configurado() and alvo["email"])):
                        try:
                            usuarios_service.solicitar_codigo(alvo["email"])
                        except RegraNegocioError as e:
                            st.error(str(e))
                        else:
                            st.success("Código enviado. O usuário usa “Esqueci minha senha” na tela de login.")
                with c2:
                    st.write("**Senha provisória** — troca obrigatória no próximo login.")
                    if st.button("Gerar senha provisória", type="primary", key="adm_reset"):
                        nova = usuarios_service.resetar_senha(uid)
                        st.success("Senha provisória gerada. Envie ao usuário:")
                        st.code(nova, language=None)


def _aba_operacoes() -> None:
    st.caption("Cada operação (filial/CDD) tem seus próprios fretes, estoques e indicadores.")
    with st.form("f_op", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        nome, cnpj = c1.text_input("Nome"), c2.text_input("CNPJ")
        cidade, uf = c3.text_input("Cidade"), c4.text_input("UF", max_chars=2)
        if st.form_submit_button("➕ Cadastrar operação"):
            ui.acao(cadastros_service.criar_operacao, nome, cnpj, cidade, uf)

    ops = operacoes_repo.listar()
    ui.tabela(pd.DataFrame(ops))
    oid = ui.select_registro("Editar operação", ops, key="adm_op")
    if oid:
        o = operacoes_repo.buscar(oid)
        with st.form(f"f_op_{oid}"):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
            nome = c1.text_input("Nome", value=o["nome"])
            cnpj = c2.text_input("CNPJ", value=o["cnpj"] or "")
            cidade = c3.text_input("Cidade", value=o["cidade"] or "")
            uf = c4.text_input("UF", value=o["uf"] or "", max_chars=2)
            ativo = c5.checkbox("Ativa", value=bool(o["ativo"]))
            if st.form_submit_button("Salvar"):
                ui.acao(cadastros_service.atualizar_operacao, oid, nome, cnpj, cidade, uf, ativo)


def _aba_importar_antigo() -> None:
    import contextlib
    import io
    import sqlite3
    import tempfile

    st.caption("Traga os dados do sistema antigo (arquivo puxada_ambev.db). Os bancos antigos não são alterados; "
               "o que já existir aqui é atualizado, sem duplicar. Usuários antigos entram com troca de senha obrigatória.")
    c1, c2 = st.columns(2)
    principal = c1.file_uploader("Banco principal antigo (puxada_ambev.db)", type=["db", "sqlite", "sqlite3"],
                                 key="mig_principal")
    puxada = c2.file_uploader("Banco do 'Sistema Puxada' (opcional)", type=["db", "sqlite", "sqlite3"], key="mig_puxada")
    ops = [o["nome"] for o in operacoes_repo.listar(apenas_ativas=True) if not o.get("membros")]
    op_pux = (st.selectbox("Operação dos fretes do Sistema Puxada", ops, key="mig_op",
                           index=ops.index("Lima Rio Verde") if "Lima Rio Verde" in ops else 0)
              if puxada and ops else None)
    if not principal or not st.button("📦 Importar dados antigos", type="primary", key="mig_btn"):
        return
    from scripts import migrar_banco_antigo as mig

    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log), tempfile.TemporaryDirectory() as tmp:
            caminhos = []
            for nome, arq in (("principal.db", principal), ("puxada.db", puxada)):
                if arq:
                    caminho = f"{tmp}/{nome}"
                    with open(caminho, "wb") as f:
                        f.write(arq.getvalue())
                    caminhos.append(caminho)
            con = sqlite3.connect(caminhos[0])
            con.row_factory = sqlite3.Row
            mig.migrar_principal(con)
            if puxada and op_pux:
                con2 = sqlite3.connect(caminhos[1])
                con2.row_factory = sqlite3.Row
                mig.migrar_puxada(con2, op_pux)
    except Exception as e:
        st.error(f"A importação parou: {e}")
    else:
        st.success("Importação concluída!")
    st.code(log.getvalue() or "(sem saída)", language=None)


def _aba_links(usuario: dict) -> None:
    """Um link do Portal Comercial por revenda — o Master copia, troca o código ou desativa."""
    from modules.puxada.app_motorista import link_whatsapp
    from repositories import operacoes_repo
    from services import links_service

    tema.secao("🔗 Links do Portal Comercial por revenda",
               "Cada revenda tem o seu link (somente leitura, sem login) e só enxerga o estoque dela. "
               "“Gerar novo link” troca o código: o link antigo para de funcionar na hora.")
    revendas = [o for o in operacoes_repo.listar(apenas_ativas=True) if not operacoes_repo.e_consolidada(o["id"])]
    for o in revendas:
        link = links_service.obter(o["id"], usuario=usuario.get("nome") or "")
        ativo = bool(int(link.get("ativo") or 0))
        url = links_service.url(o["id"])
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**🏢 {o['nome']}** · {'🟢 ativo' if ativo else '🔴 desativado'}"
                       f"  \n<span style='color:#6b6a65;font-size:.8rem'>atualizado por {link.get('atualizado_por') or '—'}"
                       f" em {link.get('atualizado_em') or '—'}</span>", unsafe_allow_html=True)
            novo = b.toggle("Link ativo", value=ativo, key=f"lk_at_{o['id']}")
            if novo != ativo:
                links_service.ativar(o["id"], novo, usuario=usuario.get("nome") or "")
                ui.avisar(f"Link de {o['nome']} {'ativado' if novo else 'desativado'}.")
                st.rerun()
            if ativo:
                st.code(url, language=None)
            c1, c2, c3 = st.columns(3)
            if ativo:
                c1.link_button("🔗 Abrir", url, **ui.LARGURA)
                msg = f"🛍️ Portal Comercial — {o['nome']}\nEstoque do dia com as puxadas D0, D1 e D2:\n{url}"
                c2.link_button("📲 Enviar pelo WhatsApp", link_whatsapp(msg), **ui.LARGURA)
            with c3.popover("♻️ Gerar novo link", **ui.LARGURA):
                st.caption("O link atual deixa de funcionar. Envie o novo para o time da revenda.")
                if st.button("Confirmar", key=f"lk_nv_{o['id']}", type="primary"):
                    links_service.renovar(o["id"], usuario=usuario.get("nome") or "")
                    ui.avisar(f"Novo link gerado para {o['nome']}.")
                    st.rerun()


def render(usuario: dict, operacao_id: int | None) -> None:
    ui.cabecalho("Gestão de Acessos", "Usuários, senhas, permissões por pasta e operações", "🔑")
    a1, a2, a4, a3 = st.tabs(["👤 Usuários & Permissões", "🏢 Operações", "🔗 Links do Portal Comercial",
                              "📦 Importar sistema antigo"])
    with a1:
        _aba_usuarios(usuario)
    with a2:
        _aba_operacoes()
    with a4:
        _aba_links(usuario)
    with a3:
        _aba_importar_antigo()
