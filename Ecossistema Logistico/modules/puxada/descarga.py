"""Puxada › Agendamento e gestão de descarga (pátio)."""
import datetime as dt

import pandas as pd
import streamlit as st

from core import graficos, tema, tempo, ui
from modules.componentes.autosave import editor_autosave
from repositories import logistica_repo
from services.erros import RegraNegocioError

STATUS = ["Agendado", "A caminho", "Chegou", "Descarregando", "Descarregado", "Cancelado", "No-show"]
# As carretas do App Carreteiro entram sozinhas: "A caminho" na saída da cervejaria (com previsão de
# chegada), "Chegou" na chegada à revenda e "Descarregado" quando o motorista finaliza a viagem.
COLUNAS = {"id": None, "data": None, "viagem_id": None, "placa": "Placa", "motorista": "Motorista (app)",
           "pedido_app": "Pedido (app)", "tipo_carga": "Carga", "criado_por": "Agendado por"}
TIPOS = ["Descartável", "Retornável", "Misto"]
HORAS = [f"{h:02d}:{m:02d}" for h in range(5, 23) for m in (0, 30)]


def agendar(operacao_id: int, data: dt.date, hora: str, placa: str, slot: str, tipo: str, obs: str, usuario: str):
    placa, slot = (placa or "").strip().upper(), (slot or "").strip()
    if not placa or not slot:
        raise RegraNegocioError("Informe a placa e o slot da descarga.")
    if logistica_repo.slot_ocupado(operacao_id, data.isoformat(), hora, slot):
        raise RegraNegocioError(f"O {slot} já está reservado em {data:%d/%m} às {hora}. Escolha outro horário ou slot.")
    logistica_repo.inserir_agendamento(operacao_id, data.isoformat(), hora, placa, slot, tipo, obs.strip(), usuario)


def painel_dia(operacao_id: int, dia: dt.date, editar: bool, key: str) -> pd.DataFrame:
    df = logistica_repo.agendamentos_df(operacao_id, dia.isoformat(), dia.isoformat())
    vis = df.drop(columns=["id", "viagem_id"]) if not df.empty else df

    def filtro(*status):
        return vis[vis["status"].isin(status)] if not vis.empty else vis

    no_patio, a_caminho = filtro("Chegou", "Descarregando"), filtro("A caminho")
    perdidos = filtro("No-show", "Cancelado")
    tema.kpis([
        {"titulo": f"Agendados em {dia:%d/%m}", "valor": len(df), "icone": "🗓️", "status": "info", "dados": vis},
        {"titulo": "A caminho (App)", "valor": len(a_caminho), "icone": "🛣️", "status": "info", "dados": a_caminho,
         "detalhe": "saíram da cervejaria"},
        {"titulo": "No pátio agora", "valor": len(no_patio), "icone": "🅿️",
         "status": "atencao" if len(no_patio) else "info", "dados": no_patio},
        {"titulo": "Descarregados", "valor": len(filtro("Descarregado")), "icone": "✅", "status": "bom",
         "dados": filtro("Descarregado")},
        {"titulo": "No-show / cancelados", "valor": len(perdidos), "icone": "⚠️",
         "status": "serio" if len(filtro("No-show")) else "info", "dados": perdidos},
    ], key=f"kp_desc_{key}")
    if df.empty:
        st.info("Nenhuma descarga agendada para este dia.")
        return df
    df["faixa"] = df["hora"].fillna("--").str[:2] + "h"
    por_hora = df.groupby("faixa").size()
    graficos.mostrar(graficos.barras(por_hora.index, {"Descargas": por_hora.values}, titulo="Descargas por hora"),
                     key=f"g_desc_{key}", detalhe=(df.drop(columns=["id", "viagem_id"]), "faixa"), titulo="Descargas")
    df = df.drop(columns=["faixa"])
    if editar:
        editor_autosave(df, f"ed_desc_{key}_{dia}", ["status", "slot", "hora", "observacao"],
                        lambda l, alt: logistica_repo.atualizar_agendamento(int(l["id"]), **alt), column_config={
                            **COLUNAS,
                            "status": st.column_config.SelectboxColumn("Status ✏️", options=STATUS),
                            "hora": st.column_config.SelectboxColumn("Hora ✏️", options=HORAS),
                            "slot": "Slot ✏️", "observacao": "Observação ✏️"})
        st.caption("📱 Linhas com motorista vieram do App Carreteiro e acompanham a viagem sozinhas.")
    else:
        ui.tabela(df.drop(columns=["id", "viagem_id"]))
    return df


def render(usuario: dict, operacao_id: int) -> None:
    c1, c2 = st.columns([1, 3])
    dia = c1.date_input("Dia", value=tempo.hoje(), format="DD/MM/YYYY", key="desc_dia")
    consolidada = ui.somente_leitura(operacao_id)
    if not consolidada:
        with st.expander("➕ Novo agendamento de descarga", expanded=False):
            carretas = logistica_repo.carretas_df(operacao_id)["placa"].tolist()
            with st.form("f_desc", clear_on_submit=True):
                a, b, c, d = st.columns(4)
                data = a.date_input("Data", value=dia, format="DD/MM/YYYY")
                hora = b.selectbox("Hora", HORAS, index=HORAS.index("08:00"))
                slot = c.text_input("Slot (ex.: Doca 03)")
                tipo = d.selectbox("Tipo de carga", TIPOS)
                e, f = st.columns([1, 2])
                placa_sel = e.selectbox("Carreta cadastrada", ["— digitar placa —"] + carretas)
                placa_txt = f.text_input("Placa (se não estiver cadastrada)")
                obs = st.text_area("Observação")
                if st.form_submit_button("🚚 Agendar descarga", type="primary"):
                    placa = placa_txt if placa_sel.startswith("—") else placa_sel
                    ui.acao(agendar, operacao_id, data, hora, placa, slot, tipo, obs, usuario["login"],
                            sucesso="Descarga agendada!")
    painel_dia(operacao_id, dia, editar=not consolidada, key="pux")
    with st.expander("📋 Próximos 7 dias"):
        prox = logistica_repo.agendamentos_df(operacao_id, tempo.hoje().isoformat(),
                                              (tempo.hoje() + dt.timedelta(days=7)).isoformat())
        ui.tabela(prox.drop(columns=["id", "viagem_id"]) if not prox.empty else prox)
        ui.downloads(prox, "agendamentos_descarga", key="dl_desc")
