"""Gestão Corporativa › ⚙️ Cadastros — quais operações (coluna C do 03.02.37) contam em cada setor."""
import pandas as pd
import streamlit as st

from core import tema, ui
from services import faturamento_service as fs
from services.erros import RegraNegocioError


def render(usuario: dict, operacao_id: int) -> None:
    tema.secao("⚙️ Operações por setor",
               "Escolha as operações que entram na conta de cada visão. Os nomes vêm do 📥 Relatório de operações; "
               "as operações que já apareceram nos 03.02.37 carregados também entram na lista.")
    nomes = fs.nomes_operacoes()
    bases = fs.operacoes_nas_bases()
    codigos = set(nomes) | set(bases["codigo"].astype(str)) if not bases.empty else set(nomes)
    for setor, (_, padrao) in fs.SETORES.items():
        codigos |= set(padrao) | set(fs.operacoes_do_setor(setor))
    opcoes = sorted(codigos, key=lambda c: (len(c), c))
    rot = lambda c: fs.rotulo_op(c, nomes)  # noqa: E731

    for setor, (titulo, padrao) in fs.SETORES.items():
        origem = "compra" if setor in ("compra", "hl_compra") else "venda"
        vistos = set(bases.loc[bases["origem"] == origem, "codigo"].astype(str)) if not bases.empty else set()
        lista = sorted(set(opcoes) if not vistos else vistos | set(fs.operacoes_do_setor(setor)),
                       key=lambda c: (len(c), c))
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            sel = c1.multiselect(titulo, lista, default=[c for c in fs.operacoes_do_setor(setor) if c in lista],
                                 format_func=rot, key=f"cad_setor_{setor}",
                                 help=f"Padrão do sistema: {', '.join(padrao)}. Lista: operações que aparecem nas "
                                      f"notas de {'compra' if origem == 'compra' else 'venda'} já carregadas.")
            c2.write("")
            if c2.button("Salvar", key=f"cad_salvar_{setor}", type="primary"):
                ui.acao(fs.salvar_setor, setor, sel, sucesso=f"{titulo}: {len(sel)} operação(ões).")

    tema.secao("🏷️ Nomes das operações", "Ajuste ou complete o nome (ex.: as operações de entrada, que não vêm "
               "no relatório de operações de saída).")
    tab = pd.DataFrame({"codigo": opcoes, "nome": [nomes.get(c, "") for c in opcoes]})
    if not bases.empty:
        resumo = bases.groupby("codigo").agg(origem=("origem", lambda s: " / ".join(sorted(set(s)))),
                                             valor=("valor", "sum"), notas=("notas", "sum"))
        tab = tab.merge(resumo, left_on="codigo", right_index=True, how="left")
        tab["valor"] = tab["valor"].map(lambda v: ui.moeda(v) if pd.notna(v) else "")
        tab["notas"] = tab["notas"].map(lambda v: ui.numero(v) if pd.notna(v) else "")
        tab["origem"] = tab["origem"].fillna("")
    so_usadas = st.toggle("Mostrar só as operações que aparecem nas notas", value=not bases.empty, key="cad_so_usadas")
    if so_usadas and "origem" in tab:
        tab = tab[tab["origem"] != ""]
    editado = st.data_editor(tab, hide_index=True, key="cad_nomes", disabled=[c for c in tab.columns if c != "nome"],
                             column_config={"codigo": "Código", "nome": st.column_config.TextColumn("Nome ✏️"),
                                            "origem": "Aparece em", "valor": "Valor nas notas", "notas": "Notas"},
                             **ui.LARGURA)
    if st.button("💾 Salvar nomes", key="cad_nomes_salvar"):
        try:
            mudou = 0
            for c, n in zip(editado["codigo"], editado["nome"]):
                if (n or "") != nomes.get(c, ""):
                    fs.salvar_nome_operacao(c, n or "")
                    mudou += 1
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            ui.avisar(f"{mudou} nome(s) atualizado(s).")
            st.rerun()
