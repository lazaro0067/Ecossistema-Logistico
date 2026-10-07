"""Puxada › Frota própria › 🔧 Agendamento de manutenção das placas."""
import datetime as dt
import html

import pandas as pd
import streamlit as st

from config.settings import PERFIS_VEICULO, STATUS_MANUTENCAO, TIPOS_MANUTENCAO
from core import tema, tempo, ui
from repositories import logistica_repo
from repositories import manutencao_repo as repo
from services import manutencao_service as svc
from services.erros import RegraNegocioError

ICONE = {"Programada": "🗓️", "Em andamento": "🔧", "Concluída": "✅", "Cancelada": "⛔"}
COR = {"Programada": "#2a5ca8", "Em andamento": "#c2571a", "Concluída": "#146c43", "Cancelada": "#77766f"}


def _e(v) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))


def _card(r: dict, perfis: dict) -> str:
    cor = COR.get(r["status"], "#52514e")
    pri = '<span class="mt-pri">⭐ PRIORIDADE</span>' if r.get("prioridade") == 1 or r.get("prioridade") == 1.0 else ""
    d = dt.date.fromisoformat(str(r["data"])[:10])
    pf = r.get("previsao_fim")
    ate = f" até {dt.date.fromisoformat(pf):%d/%m}" if isinstance(pf, str) and pf else ""
    perfil = perfis.get(str(r["placa"]).upper())
    desc = f'<div class="mt-l">📝 {_e(r["descricao"])}</div>' if isinstance(r.get("descricao"), str) and r["descricao"] else ""
    ofi = f'<div class="mt-l">🏪 {_e(r["oficina"])}</div>' if isinstance(r.get("oficina"), str) and r["oficina"] else ""
    return (f'<div class="mt-card" style="--c:{cor}"><div class="mt-top"><b>🚛 {_e(r["placa"])}</b>'
            f'{f"<span class=mt-perfil>{_e(perfil)}</span>" if perfil else ""}{pri}'
            f'<span class="mt-st">{ICONE.get(r["status"], "")} {_e(r["status"])}</span></div>'
            f'<div class="mt-l">📅 {d:%d/%m/%Y}{" às " + _e(r["hora"]) if isinstance(r.get("hora"), str) and r["hora"] else ""}'
            f'{ate} · <b>{_e(r["tipo"])}</b></div>'
            f'{desc}{ofi}'
            f'<div class="mt-rod">programada por {_e(r.get("criado_por"))}</div></div>')


_CSS = """
<style>
.mt-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:.7rem; margin:.4rem 0 .8rem; }
.mt-card { background:#fff; border:1px solid #dfe5ee; border-left:5px solid var(--c); border-radius:14px; padding:.7rem .85rem; }
.mt-top { display:flex; align-items:center; gap:.4rem; flex-wrap:wrap; }
.mt-top b { color:#0B1F3A; margin-right:auto; }
.mt-st { font-size:.72rem; font-weight:800; padding:.1rem .5rem; border-radius:999px; color:var(--c);
    background: color-mix(in srgb, var(--c) 12%, white); }
.mt-pri { font-size:.7rem; font-weight:800; padding:.1rem .45rem; border-radius:6px; background:#fff1db; color:#a35c00; }
.mt-perfil { font-size:.7rem; font-weight:800; padding:.05rem .45rem; border-radius:6px; background:#eef3fa; color:#2a5ca8; }
.mt-l { font-size:.82rem; color:#3d3c39; margin-top:.25rem; }
.mt-rod { font-size:.72rem; color:#77766f; margin-top:.35rem; }
</style>
"""


def _form(usuario: dict, operacao_id: int, atual: dict | None, chave: str) -> None:
    carretas = logistica_repo.carretas_df(operacao_id)
    if carretas.empty:
        st.info("Cadastre as placas em **⚙️ Cadastros › 🚛 Carretas**.")
        return
    placas = carretas["placa"].tolist()
    perfis = {str(r["placa"]): r.get("perfil") for r in carretas.to_dict("records")}
    a, b, c, d = st.columns([1.3, 1, 0.8, 1.1])
    placa = a.selectbox("🚛 Placa *", placas, key=f"{chave}_p",
                        index=placas.index(atual["placa"]) if atual and atual["placa"] in placas else 0,
                        format_func=lambda p: f"{p} · {perfis.get(p)} ({PERFIS_VEICULO.get(perfis.get(p), '?')} pal.)"
                        if isinstance(perfis.get(p), str) else p)
    data = b.date_input("📅 Data *", value=dt.date.fromisoformat(atual["data"]) if atual else tempo.hoje(),
                        format="DD/MM/YYYY", key=f"{chave}_d")
    hora_atual = dt.datetime.strptime(atual["hora"], "%H:%M").time() if atual and isinstance(atual.get("hora"), str) \
        and atual["hora"] else None
    hora = c.time_input("Hora", value=hora_atual, step=dt.timedelta(minutes=30), key=f"{chave}_h")
    tipo = d.selectbox("Tipo *", TIPOS_MANUTENCAO, key=f"{chave}_t",
                       index=TIPOS_MANUTENCAO.index(atual["tipo"]) if atual and atual.get("tipo") in TIPOS_MANUTENCAO else 0)
    e, f, g = st.columns([2, 1.2, 1])
    desc = e.text_input("Descrição", value=(atual or {}).get("descricao") or "", key=f"{chave}_desc",
                        placeholder="ex.: troca de lonas de freio do 2º eixo")
    oficina = f.text_input("Oficina / local", value=(atual or {}).get("oficina") or "", key=f"{chave}_of")
    pf = (atual or {}).get("previsao_fim")
    prev = g.date_input("Previsão de término", value=dt.date.fromisoformat(pf) if isinstance(pf, str) and pf else None,
                        format="DD/MM/YYYY", key=f"{chave}_pf")
    prioridade = st.checkbox("⭐ Prioridade para o armazém (descarregar esta placa primeiro)",
                             value=bool((atual or {}).get("prioridade")), key=f"{chave}_pri")
    if st.button("💾 Salvar manutenção" if not atual else "💾 Salvar alteração", type="primary", key=f"{chave}_ok"):
        try:
            svc.salvar(operacao_id, atual["id"] if atual else None, placa, data, hora, tipo, desc, oficina, prev,
                       prioridade, usuario.get("nome") or "")
        except RegraNegocioError as err:
            st.error(str(err))
        else:
            st.session_state[f"mt_v_{operacao_id}"] = st.session_state.get(f"mt_v_{operacao_id}", 0) + 1
            ui.avisar(f"Manutenção da {placa} salva — o armazém já vê no Pátio/Descarga.")
            st.rerun()


def render(usuario: dict, operacao_id: int) -> None:
    if ui.somente_leitura(operacao_id):
        st.info("A manutenção é programada por filial. Escolha uma filial no menu.")
        return
    hoje = tempo.hoje()
    df = repo.lista_df(operacao_id, (hoje - dt.timedelta(days=30)).isoformat())
    perfis = {str(r["placa"]).upper(): r.get("perfil") for r in logistica_repo.carretas_df(operacao_id).to_dict("records")
              if isinstance(r.get("perfil"), str)}
    abertas = df[df["status"].isin(["Programada", "Em andamento"])] if not df.empty else df
    vis = df.assign(prioridade=df["prioridade"].map(lambda p: "⭐" if p == 1 else ""))[
        ["data", "hora", "placa", "tipo", "descricao", "oficina", "status", "prioridade", "criado_por"]] if not df.empty else df
    tema.kpis([
        {"titulo": "Programadas", "valor": int((df["status"] == "Programada").sum()) if not df.empty else 0,
         "icone": "🗓️", "status": "info", "dados": vis[vis["status"] == "Programada"] if not df.empty else None},
        {"titulo": "Em andamento", "valor": int((df["status"] == "Em andamento").sum()) if not df.empty else 0,
         "icone": "🔧", "status": "atencao", "dados": vis[vis["status"] == "Em andamento"] if not df.empty else None},
        {"titulo": "⭐ Prioridades abertas", "valor": int((abertas["prioridade"] == 1).sum()) if not abertas.empty else 0,
         "icone": "", "status": "critico" if not abertas.empty and (abertas["prioridade"] == 1).any() else "bom",
         "dados": vis[(vis["prioridade"] == "⭐") & vis["status"].isin(["Programada", "Em andamento"])] if not df.empty else None},
        {"titulo": "Concluídas (30 dias)", "valor": int((df["status"] == "Concluída").sum()) if not df.empty else 0,
         "icone": "✅", "status": "bom", "dados": vis[vis["status"] == "Concluída"] if not df.empty else None},
    ], key="kp_manut")
    v = st.session_state.get(f"mt_v_{operacao_id}", 0)
    with st.expander("➕ Programar manutenção", expanded=abertas.empty):
        _form(usuario, operacao_id, None, f"mt_n_{v}")
    tema.secao("🔧 Manutenções abertas", "Na data programada a placa fica Indisponível Frota. O armazém vê no Pátio que, "
               "depois de descarregar, ela vai para a manutenção. ⭐ = prioridade para o armazém.")
    if abertas.empty:
        st.info("Nenhuma manutenção aberta.")
    else:
        ordenado = abertas.sort_values(["prioridade", "data"], ascending=[False, True])
        st.markdown(_CSS + '<div class="mt-grid">' + "".join(_card(r, perfis) for r in ordenado.to_dict("records"))
                    + "</div>", unsafe_allow_html=True)
        with st.container(key="cad_alt_mt"):
            st.markdown('<div class="eco-alt-titulo">✏️ Atualizar manutenção</div>', unsafe_allow_html=True)
            nomes = {int(r["id"]): f"{r['placa']} · {dt.date.fromisoformat(r['data']):%d/%m} · {r['tipo']} · {r['status']}"
                     for r in ordenado.to_dict("records")}
            mid = st.selectbox("Manutenção", [None, *nomes], key="mt_sel",
                               format_func=lambda i: "Selecione..." if i is None else nomes[i])
            if mid:
                atual = repo.buscar(mid)
                b1, b2, b3 = st.columns(3)
                if atual["status"] == "Programada" and b1.button("🔧 Iniciar (entrou na oficina)", key=f"mt_ini_{mid}"):
                    ui.acao(svc.mudar_status, mid, "Em andamento", sucesso="Manutenção iniciada.")
                if b2.button("✅ Concluir (placa liberada)", key=f"mt_fim_{mid}", type="primary"):
                    ui.acao(svc.mudar_status, mid, "Concluída", sucesso="Manutenção concluída — placa liberada.")
                if b3.button("⛔ Cancelar", key=f"mt_can_{mid}"):
                    ui.acao(svc.mudar_status, mid, "Cancelada", sucesso="Manutenção cancelada.")
                _form(usuario, operacao_id, atual, f"mt_a_{mid}_{v}")
    if not df.empty:
        with st.expander("📋 Histórico (30 dias)"):
            ui.tabela(vis.rename(columns={"data": "Data", "hora": "Hora", "placa": "Placa", "tipo": "Tipo",
                                          "descricao": "Descrição", "oficina": "Oficina", "status": "Status",
                                          "prioridade": "⭐", "criado_por": "Programada por"}), baixar="manutencoes")
