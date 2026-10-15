"""📑 DRE › ✏️ DRE editado (ajustes manuais com autor) e 📧 versão para e-mail."""
import html as _h

import pandas as pd
import streamlit as st

from core import tema, tempo, ui
from modules.corporativo.estoque_dre import (_div, _fmt, _kpis_dre, _linhas_dre, _m, _nome_mes, _p,
                                             montar_tabela)
from repositories import operacoes_repo
from services import estoque_valor_service as ev
from services.erros import RegraNegocioError


def _ordem(v: dict) -> list[str]:
    fixas = ["receita_bruta", "icms", "pis_cofins", "ei", "compras", "ef"]
    deps = sorted((k for k in v if k.startswith("dep:")), key=lambda k: -(v.get(k) or 0))
    return [k for k in fixas if k in v] + deps + ["conta_corrente"]


def _dados(op: int, lista: list[str]):
    trios = [ev.dre_editado_mes(op, m) for m in lista]
    res = [t[1] for t in trios]
    tot = ev.dre_editado_periodo(op, lista) if len(lista) > 1 else res[0]
    eds = pd.concat([t[2].assign(mes=m) for t, m in zip(trios, lista)], ignore_index=True)
    return trios, res, tot, eds


def _selo(eds: pd.DataFrame) -> str:
    if eds.empty:
        return "📑 Igual ao gerado — nenhuma linha foi editada."
    ult = eds.sort_values("editado_em").iloc[-1]
    quando = pd.to_datetime(ult["editado_em"]).strftime("%d/%m/%Y %H:%M") if ult["editado_em"] else ""
    return (f"✏️ **Editado** — {len(eds)} linha(s) alterada(s) · última edição por **{ult['editado_por']}** "
            f"em {quando}.")


def render(usuario: dict, op: int, lista: list[str], rotulo: str) -> None:
    pode = ev.pode_editar_dre(usuario)
    consolidada = operacoes_repo.e_consolidada(op)
    with st.spinner("Montando o DRE editado..."):
        trios, res, tot, eds = _dados(op, lista)
    st.info(_selo(eds))
    _kpis_dre(tot, rotulo, key="kp_dre_ed")
    if len(lista) == 1:
        gerado, editado, ed = trios[0]
        _editor(usuario, op, lista[0], gerado, editado, ed, pode and not consolidada, consolidada)
        tema.secao("📑 DRE gerado × editado", "As linhas alteradas aparecem com ✏️ e o nome de quem editou.")
        lg = {l_[0]: l_ for l_ in _linhas_dre(gerado)}
        le = _linhas_dre(editado)
        quem = {ev.rotulo_chave(k): (p_, e_) for k, p_, e_ in zip(ed["chave"], ed["editado_por"], ed["editado_em"])}
        linhas = []
        for rot, v, t in le:
            g_ = lg.get(rot, (rot, None, t))[1]
            base = rot.replace("(−) ", "").replace("(±) ", "").replace(" ✏️", "").strip()
            autor = quem.get(base)
            dif = (v - g_) if t == "m" and v is not None and g_ is not None else None
            linhas.append({"": "✏️" if autor else "", "Conta": rot, "Gerado": _fmt(g_, t), "Editado": _fmt(v, t),
                           "Diferença": _m(dif) if dif and abs(dif) >= .005 else "",
                           "Editado por": f"{autor[0]} · {pd.to_datetime(autor[1]).strftime('%d/%m %H:%M')}"
                           if autor and autor[1] else ""})
        vis = pd.DataFrame(linhas)
        ui.tabela(vis, baixar=f"DRE_editado_{lista[0]}", height=(len(vis) + 1) * 35 + 25)
    else:
        vis = montar_tabela(lista, res, tot, rotulo)
        meses_ed = set(eds["mes"]) if not eds.empty else set()
        vis = vis.rename(columns={_nome_mes(m)[:3]: _nome_mes(m)[:3] + " ✏️" for m in meses_ed})
        st.caption("Meses com ✏️ no título têm linhas editadas. Para editar, escolha 🗓️ Mês.")
        ui.tabela(vis, baixar=f"DRE_editado_{lista[0]}_{lista[-1]}", height=(len(vis) + 1) * 35 + 25)
    log = ev.log_edicoes(op, lista[0] if len(lista) == 1 else None)
    if len(lista) > 1 and not log.empty:
        log = log[log["mes"].isin(lista)]
    with st.expander(f"🕒 Histórico de edições ({len(log)})"):
        if log.empty:
            st.caption("Nenhuma edição registrada.")
        else:
            ui.tabela(pd.DataFrame({
                "Quando": pd.to_datetime(log["em"]).dt.strftime("%d/%m/%Y %H:%M"), "Mês": log["mes"].map(_nome_mes),
                "Linha": log["rotulo"], "De": log["de"].map(_m), "Para": log["para"].map(_m),
                "Quem": log["usuario"]}), baixar="dre_historico_edicoes")


def _editor(usuario, op, mes, gerado, editado, ed, pode, consolidada) -> None:
    vg = ev.valores_dre(gerado)
    ve = ev.valores_dre(editado)
    edi = ed.set_index("chave") if not ed.empty else None
    chaves = _ordem({**vg, **ve})
    tab = pd.DataFrame({
        "chave": chaves, "Linha": [("Despesa · " if k.startswith("dep:") else "") + ev.rotulo_chave(k) for k in chaves],
        "Gerado": [vg.get(k) for k in chaves], "Editado": [ve.get(k) for k in chaves],
        "Editado por": [(f"{edi.at[k, 'editado_por']} · {pd.to_datetime(edi.at[k, 'editado_em']).strftime('%d/%m %H:%M')}"
                         if edi is not None and k in edi.index else "") for k in chaves]})
    with st.expander("✏️ Editar valores do DRE", expanded=pode):
        if consolidada:
            st.caption("Na visão consolidada aparece a soma das edições de cada revenda. Escolha uma revenda para editar.")
        elif not pode:
            st.warning("Você pode ver o DRE editado, mas **editar** precisa ser liberado pelo Master "
                       "(💰 Financeiro › ⚙️ Cadastros OBZ › 🔑 Papéis › “✏️ Pode editar o DRE”).")
        st.caption("Edite a coluna **Editado** — os totais (receita líquida, CMV, lucro bruto, despesas e resultado) "
                   "são recalculados. Valor igual ao gerado volta a ser “gerado”. Fica gravado quem editou e quando.")
        din = st.column_config.NumberColumn
        novo = st.data_editor(tab, hide_index=True, key=f"dre_ed_{op}_{mes}", **ui.LARGURA,
                              disabled=[c for c in tab.columns if c != "Editado"] if pode else list(tab.columns),
                              column_order=["Linha", "Gerado", "Editado", "Editado por"],
                              column_config={"Gerado": din(format="R$ %.2f"), "Editado": din("Editado ✏️",
                                                                                             format="R$ %.2f"),
                                             "Linha": st.column_config.TextColumn(width="large")})
        if pode:
            b1, b2, _ = st.columns([1, 1, 2])
            if b1.button("💾 Salvar DRE editado", type="primary", key="dre_ed_salvar"):
                try:
                    n = ev.salvar_edicao(op, mes, dict(zip(novo["chave"], novo["Editado"])), usuario)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    ui.avisar(f"DRE de {_nome_mes(mes)} salvo como editado ({n} linha(s) alterada(s))." if n
                              else "Nada mudou.")
                    st.rerun()
            if not ed.empty and b2.button("↩️ Voltar tudo ao gerado", key="dre_ed_reset"):
                ui.acao(ev.voltar_ao_gerado, op, mes, usuario, sucesso="O DRE voltou a ser o gerado.")


# --- 📧 Para e-mail -----------------------------------------------------------------------------------------------
_COR = {"azul": "#0B1F3A", "verde": "#1baf7a", "vermelho": "#e34948", "cinza": "#6b7280", "fundo": "#F4F6FA"}


def _cartao(titulo, valor, detalhe, cor) -> str:
    e = _h.escape
    return (f'<td style="padding:6px;width:20%;vertical-align:top"><div style="background:#fff;border:1px solid #e3e6ec;'
            f'border-left:5px solid {cor};border-radius:10px;padding:10px 12px">'
            f'<div style="font-size:11px;color:#52514e;font-weight:700;text-transform:uppercase">{e(titulo)}</div>'
            f'<div style="font-size:15px;font-weight:800;color:#0B1F3A;margin-top:3px;white-space:nowrap">{e(valor)}</div>'
            f'<div style="font-size:11px;color:#6b7280;margin-top:2px">{e(detalhe)}</div></div></td>')


def html_dre(revenda: str, rotulo: str, tot: dict, res: list[dict], lista: list[str], fonte: str,
             observacao: str = "") -> str:
    e = _h.escape
    bruta, lb, resu = tot["receita_bruta"], tot["lucro_bruto"], tot["resultado"]
    mb, mo = _div(lb, bruta), _div(resu, bruta)
    cards = "".join([
        _cartao("Faturamento", _m(bruta), f"líquida {_m(tot['receita'])}", "#2a78d6"),
        _cartao("CMV", _m(tot["cmv"]), "inicial + compras − final", "#eda100"),
        _cartao("Lucro bruto", _m(lb), f"margem {_p(mb * 100 if mb is not None else None)}", _COR["verde"]),
        _cartao("OBZ (despesas)", _m(tot["despesas"]), f"plan {_m(tot.get('orcado'))}", "#7c3aed"),
        _cartao("Resultado operacional", _m(resu), f"margem {_p(mo * 100 if mo is not None else None)}",
                _COR["verde"] if (resu or 0) >= 0 else _COR["vermelho"]),
    ])
    th = 'style="text-align:{a};padding:8px 10px;background:#D3E3F8;color:#0B1F3A;font-size:12px"'
    linhas_html = []
    if len(lista) == 1:
        cab = f'<tr><th {th.format(a="left")}>Conta</th><th {th.format(a="right")}>{e(rotulo)}</th>' \
              f'<th {th.format(a="right")}>% receita</th></tr>'
        for i, (rot, v, t) in enumerate(_linhas_dre(tot)):
            forte = rot.startswith("(=)")
            sub = rot.startswith("      ")
            cor = _COR["vermelho"] if t == "m" and v is not None and v < 0 else "#0b0b0b"
            fundo = "#EEF3FB" if forte else ("#fff" if i % 2 else "#FAFBFD")
            pct = _p(_div(v, bruta) * 100) if t == "m" and v is not None and bruta else ""
            linhas_html.append(
                f'<tr style="background:{fundo}"><td style="padding:6px 10px;font-size:13px;'
                f'{"font-weight:800;" if forte else ""}{"padding-left:26px;color:#52514e;" if sub else ""}">'
                f'{e(rot.strip().replace(" ✏️", ""))}</td><td style="padding:6px 10px;text-align:right;font-size:13px;'
                f'color:{cor};{"font-weight:800;" if forte else ""}">{e(_fmt(v, t))}</td>'
                f'<td style="padding:6px 10px;text-align:right;font-size:12px;color:#6b7280">{e(pct)}</td></tr>')
    else:
        cols = ["Mês", "Faturamento", "CMV", "Lucro bruto", "Margem", "OBZ", "Resultado"]
        cab = "<tr>" + "".join(f'<th {th.format(a="left" if c == "Mês" else "right")}>{c}</th>' for c in cols) + "</tr>"
        for i, (m, r) in enumerate(list(zip(lista, res)) + [("TOTAL", tot)]):
            forte = m == "TOTAL"
            vals = [_nome_mes(m) if not forte else f"Total {rotulo}", _m(r["receita_bruta"]), _m(r["cmv"]),
                    _m(r["lucro_bruto"]),
                    _p(_div(r["lucro_bruto"], r["receita_bruta"]) * 100 if r["lucro_bruto"] is not None and
                       r["receita_bruta"] else None), _m(r["despesas"]), _m(r["resultado"])]
            fundo = "#EEF3FB" if forte else ("#fff" if i % 2 else "#FAFBFD")
            linhas_html.append(f'<tr style="background:{fundo}">' + "".join(
                f'<td style="padding:6px 10px;font-size:13px;text-align:{"left" if j == 0 else "right"};'
                f'{"font-weight:800;" if forte else ""}'
                f'{"color:" + _COR["vermelho"] + ";" if j == 6 and (r["resultado"] or 0) < 0 else ""}">{e(x)}</td>'
                for j, x in enumerate(vals)) + "</tr>")
    obs = (f'<div style="margin:14px 0 0;padding:10px 12px;background:#FFF8E6;border-radius:8px;font-size:13px">'
           f'<b>Observações:</b> {e(observacao)}</div>') if observacao.strip() else ""
    agora = tempo.agora().strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>DRE {e(revenda)} · {e(rotulo)}</title></head>
<body style="margin:0;background:{_COR['fundo']};font-family:Segoe UI,Arial,sans-serif">
<div style="max-width:820px;margin:0 auto;padding:22px">
<div style="background:linear-gradient(120deg,#0B1F3A,#16305A 60%,#2a78d6);color:#fff;border-radius:14px;padding:18px 22px">
<div style="font-size:12px;opacity:.85;letter-spacing:.04em;text-transform:uppercase">Demonstrativo de resultado</div>
<div style="font-size:22px;font-weight:800;margin-top:2px">📑 DRE · {e(revenda)}</div>
<div style="font-size:14px;opacity:.9;margin-top:2px">{e(rotulo)} · {e(fonte)}</div></div>
<table role="presentation" style="width:100%;border-collapse:collapse;margin:12px 0"><tr>{cards}</tr></table>
<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e3e6ec;border-radius:10px;overflow:hidden">
{cab}{''.join(linhas_html)}</table>{obs}
<div style="font-size:11px;color:#898781;margin-top:14px">Gerado pelo Ecossistema Logístico em {agora}. Receita bruta = notas das
operações de venda · CMV = estoque inicial + compras − estoque final · Despesas = OBZ realizado por departamento.</div>
</div></body></html>"""


def render_email(usuario: dict, op: int, lista: list[str], rotulo: str) -> None:
    from services import email_service

    revenda = (operacoes_repo.buscar(op) or {}).get("nome", "")
    c1, c2 = st.columns([1.3, 2])
    with c1:
        fonte = ui._escolha("dre_mail_fonte", ["editado", "gerado"], "editado", pills=True,
                            formatar={"editado": "✏️ Versão editada", "gerado": "📑 Versão gerada"}.get)
    obs = c2.text_input("Observação no e-mail (opcional)", key="dre_mail_obs",
                        placeholder="Ex.: fechamento preliminar — CMV revisado")
    with st.spinner("Montando o e-mail..."):
        if fonte == "editado":
            _, res, tot, eds = _dados(op, lista)
            desc = "versão editada" + (f" (última edição por {eds.sort_values('editado_em').iloc[-1]['editado_por']})"
                                       if not eds.empty else " (sem edições)")
        else:
            res = [ev.dre_mes(op, m) for m in lista]
            tot = ev.dre_periodo(op, lista) if len(lista) > 1 else res[0]
            desc = "versão gerada pelo sistema"
    doc = html_dre(revenda, rotulo, tot, res, lista, desc, obs or "")
    nome_arq = f"DRE_{revenda.replace(' ', '_')}_{lista[0]}{'_' + lista[-1] if len(lista) > 1 else ''}.html"
    b1, b2 = st.columns([1, 2])
    b1.download_button("⬇️ Baixar para anexar (.html)", doc.encode("utf-8"), nome_arq, "text/html",
                       key="dre_mail_baixar", type="primary")
    b2.caption("Abra o arquivo baixado no navegador e use Ctrl+P › Salvar como PDF, ou anexe direto no e-mail.")
    with st.form("dre_mail_form", border=True):
        st.markdown("**📧 Enviar por e-mail**")
        para = st.text_input("Para (separe vários e-mails com vírgula)", key="dre_mail_para")
        assunto = st.text_input("Assunto", value=f"DRE {revenda} · {rotulo}", key="dre_mail_assunto")
        if not email_service.configurado():
            st.caption("⚠️ O envio automático ainda não está configurado (SMTP nos Secrets) — por enquanto, baixe e "
                       "anexe no seu e-mail.")
        if st.form_submit_button("Enviar", type="primary"):
            try:
                texto = (f"DRE {revenda} · {rotulo}\nFaturamento: {_m(tot['receita_bruta'])}\nCMV: {_m(tot['cmv'])}\n"
                         f"Lucro bruto: {_m(tot['lucro_bruto'])}\nOBZ: {_m(tot['despesas'])}\n"
                         f"Resultado operacional: {_m(tot['resultado'])}")
                email_service.enviar_html(para.replace(";", ",").split(","), assunto, doc, texto)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.success("E-mail enviado. ✅")
    tema.secao("👀 Prévia do e-mail")
    try:
        import streamlit.components.v1 as components

        components.html(doc, height=620 if len(lista) > 1 else 1250, scrolling=True)
    except Exception:  # noqa: BLE001
        st.markdown(doc, unsafe_allow_html=True)
