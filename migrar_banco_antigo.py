r"""Migra os dados dos bancos antigos (puxada_ambev.db) para o novo schema.

Uso (na pasta do projeto, com o venv ativado):

    Para gravar no banco da NUVEM (Supabase), defina antes a variável:
        set DATABASE_URL=postgresql://...        (Windows)
    Sem a variável, grava no banco local data\ecossistema.db.


    python scripts/migrar_banco_antigo.py --antigo "..\\puxada_ambev.db" ^
        --puxada "..\\Sistema Puxada\\puxada_ambev.db" --operacao-puxada "Lima Rio Verde"

- --antigo:  banco principal antigo (operações, estoque, produtos, curva ABC,
             ressuprimento, pedidos marcados, armazéns, usuários).
- --puxada:  (opcional) banco do "Sistema Puxada" (OD, trechos, transportadoras,
             cotações, meta OBZ). Esses dados não tinham operação; serão
             vinculados à operação informada em --operacao-puxada.

Pode ser rodado mais de uma vez: registros já existentes são atualizados.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import MODULOS  # noqa: E402
from core.auth import hash_senha  # noqa: E402
from database.connection import get_conn  # noqa: E402
from database.schema import init_db  # noqa: E402
from repositories.base import upsert  # noqa: E402


def _abrir(caminho: str) -> sqlite3.Connection:
    if not Path(caminho).exists():
        sys.exit(f"Arquivo não encontrado: {caminho}")
    c = sqlite3.connect(caminho)
    c.row_factory = sqlite3.Row
    return c


def _tem_tabela(c, nome) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def _linhas(c, sql) -> list[dict]:
    return [dict(r) for r in c.execute(sql)]


def _data_br_para_iso(d: str | None) -> str | None:
    if d and len(d) == 10 and d[2] == "/":
        return f"{d[6:]}-{d[3:5]}-{d[:2]}"
    return d


def _mes_br_para_iso(m: str | None) -> str | None:  # "06/2026" -> "2026-06"
    if m and len(m) == 7 and m[2] == "/":
        return f"{m[3:]}-{m[:2]}"
    return m


def _ops() -> dict[str, int]:
    with get_conn() as conn:
        return {r.get("nome"): r.get("id") for r in conn.execute("SELECT id, nome FROM operacoes")}


def _log(rotulo: str, n: int) -> None:
    print(f"  ✔ {rotulo}: {n}")


_DEPTOS = {"puxada": "puxada", "ressuprimento": "ressuprimento", "vendas": "vendas", "armaz": "armazem",
           "distribui": "distribuicao", "frota": "frota", "financeiro": "financeiro", "compras": "compras",
           "gente": "gente", "relat": "relatorios"}


def _permissoes_antigas(u: dict) -> list[str]:
    deps = str(u.get("permissoes_deptos") or "")
    if deps.upper() == "TODOS":
        return list(MODULOS)
    perms = {m for m in MODULOS if u.get(f"perm_{m}") == 1}
    for parte in deps.split(","):
        p = parte.strip().lower()
        perms |= {mod for trecho, mod in _DEPTOS.items() if trecho in p}
    return sorted(perms) or ["puxada"]


def migrar_principal(c) -> None:
    print("\n[Banco principal]")
    if _tem_tabela(c, "operacoes"):
        _log("operações", upsert("operacoes", [
            {"nome": r.get("nome"), "cnpj": r.get("cnpj"), "cidade": r.get("cidade"), "uf": r.get("uf")}
            for r in _linhas(c, "SELECT * FROM operacoes")], ["nome"]))
    ops = _ops()

    def op(nome):
        from repositories import operacoes_repo
        return ops.get(nome) or (operacoes_repo.resolver_por_texto(nome) if nome else None)

    # Usuários: senhas antigas (texto puro) viram hash e a troca no 1º acesso é obrigatória
    if _tem_tabela(c, "usuarios"):
        n = 0
        for u in _linhas(c, "SELECT * FROM usuarios"):
            login = str(u.get("nome")).strip().lower().replace(" ", ".")
            with get_conn() as conn:
                if conn.execute("SELECT 1 FROM usuarios WHERE login = ?", (login,)).fetchone():
                    continue
                cur = conn.execute(
                    """INSERT INTO usuarios (login, nome, senha_hash, email, cargo, perfil, e_aprovador, alcada, ativo,
                       trocar_senha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (login, u.get("nome"), hash_senha(str(u.get("senha") or "123456")), u.get("email"), u.get("cargo"),
                     u.get("perfil") if u.get("perfil") in ("Master", "Gestor", "Operacional") else "Operacional",
                     int(u.get("e_aprovador") == "Sim"), u.get("alcada_reais") or 0,
                     0 if u.get("status") == "Inativo" else 1))
                conn.executemany("INSERT INTO usuario_modulos (usuario_id, modulo) VALUES (?, ?)",
                                 [(cur.lastrowid, m) for m in _permissoes_antigas(u)])
                n += 1
        _log("usuários novos (troca de senha obrigatória)", n)

    if _tem_tabela(c, "base_01_11"):
        prod = {r.get("cod_clean"): {"cod": r.get("cod_clean"), "descricao": r.get("descricao"), "fator_hl": r.get("fator_hl"),
                                 "cx_pallet": r.get("cx_pallet"), "tipo": None, "categoria": None}
                for r in _linhas(c, "SELECT * FROM base_01_11")}
        if _tem_tabela(c, "base_linear"):
            for r in _linhas(c, "SELECT * FROM base_linear"):
                p = prod.setdefault(r.get("cod_clean"), {"cod": r.get("cod_clean"), "descricao": None, "fator_hl": 0,
                                                     "cx_pallet": 0, "tipo": None, "categoria": None})
                p["tipo"], p["categoria"] = r.get("tipo"), r.get("categoria")
        _log("produtos", upsert("produtos", list(prod.values()), ["cod"]))

    ops_com_estoque = []
    if _tem_tabela(c, "base_estoque_02"):
        linhas = [{"operacao_id": op(r.get("operacao")), "cod": r.get("cod_clean"), "descricao": (r.get("descricao") or "").strip(),
                   "inicial": r.get("inicial"), "entrada": r.get("entrada"), "saida": r.get("saida"),
                   "disponivel": r.get("disponivel"), "saldo_dia": r.get("saldo_dia"), "dt_atualizacao": r.get("dt_atualizacao")}
                  for r in _linhas(c, "SELECT * FROM base_estoque_02") if op(r.get("operacao"))]
        ops_com_estoque = sorted({l["operacao_id"] for l in linhas})
        _log("estoque", upsert("estoque", linhas, ["operacao_id", "cod"]))

    if _tem_tabela(c, "base_linear"):
        alvo = ops_com_estoque or list(ops.values())[:1]
        linhas = [{"operacao_id": o, "cod": r.get("cod_clean"), "linear_cx_dia": r.get("linear_vendas"),
                   "dt_atualizacao": r.get("dt_atualizacao")}
                  for r in _linhas(c, "SELECT * FROM base_linear") for o in alvo]
        _log("linear de vendas", upsert("linear_vendas", linhas, ["operacao_id", "cod"]))

    if _tem_tabela(c, "metas_doi"):
        _log("metas DOI", upsert("metas_doi", [
            {"operacao_id": op(r.get("operacao")), "cod": r.get("cod_prod"), "doi_meta": r.get("doi_meta")}
            for r in _linhas(c, "SELECT * FROM metas_doi") if op(r.get("operacao"))], ["operacao_id", "cod"]))

    if _tem_tabela(c, "historico_curva_abc"):
        _log("curva ABC", upsert("curva_abc", [
            {"operacao_id": op(r.get("operacao")), "mes_ano": _mes_br_para_iso(r.get("mes_ano")), "cod": r.get("cod_clean"),
             "descricao": (r.get("descricao") or "").strip(), "total_qtde": r.get("total_qtde"),
             "pct_acumulado": r.get("pct_acumulado"), "classe": r.get("classe_abc"), "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM historico_curva_abc") if op(r.get("operacao"))],
            ["operacao_id", "mes_ano", "cod"]))

    if _tem_tabela(c, "armazens"):
        cap = {r.get("operacao"): r for r in _linhas(c, "SELECT * FROM armazem_capacidade")} \
            if _tem_tabela(c, "armazem_capacidade") else {}
        _log("armazéns", upsert("armazens", [
            {"operacao_id": op(r.get("operacao")), "nome": r.get("nome_armazem"),
             "cap_hl": (cap.get(r.get("operacao")) or {}).get("cap_hl", 0),
             "cap_paletes": (cap.get(r.get("operacao")) or {}).get("cap_paletes", 0)}
            for r in _linhas(c, "SELECT * FROM armazens") if op(r.get("operacao"))], ["operacao_id", "nome"]))

    if _tem_tabela(c, "pedidos_marcados"):
        from repositories.base import substituir
        linhas = [{"operacao_id": op(r.get("operacao")), "data_puxada": _data_br_para_iso(r.get("data_puxada")),
                   "cod": r.get("cod_clean"), "descricao": r.get("descricao"), "cx_solicitadas": r.get("cx_solicitadas"),
                   "cx_marcadas": r.get("cx_marcadas"), "hl_marcado": r.get("hl_marcado"), "status_item": r.get("status_item"),
                   "numero_pedido": str(r.get("numero_pedido") or "").lstrip("'"), "dt_atualizacao": r.get("dt_atualizacao")}
                  for r in _linhas(c, "SELECT * FROM pedidos_marcados") if op(r.get("operacao"))]
        _log("pedidos marcados", substituir("pedidos_marcados", "1 = 1", (), linhas, None))

    if _tem_tabela(c, "gestao_ressuprimento_diario"):
        _log("ressuprimento diário", upsert("ressuprimento_diario", [
            {"operacao_id": op(r.get("operacao")), "data": r.get("data_registro"), "cesta": r.get("cesta"),
             "volume_sellin_hl": r.get("volume_sellin_hl"), "volume_real_hl": r.get("volume_real_hl"),
             "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM gestao_ressuprimento_diario") if op(r.get("operacao"))],
            ["operacao_id", "data", "cesta"]))

    if _tem_tabela(c, "metas_ressuprimento_mensal"):
        _log("metas de ressuprimento", upsert("metas_ressuprimento", [
            {"operacao_id": op(r.get("operacao")), "mes_ano": f"{r['ano']:04d}-{r['mes']:02d}", "cesta": r.get("cesta"),
             "meta_volume_hl": r.get("meta_volume_hl")}
            for r in _linhas(c, "SELECT * FROM metas_ressuprimento_mensal") if op(r.get("operacao"))],
            ["operacao_id", "mes_ano", "cesta"]))

    # Tabelas de registros com colunas iguais (estavam vazias, mas migram se houver dados)
    for tabela, cols in {
        "distribuicao_rotas": ["data", "rota", "motorista", "otif_percent", "devolucao_caixas", "status"],
        "frota_manutencao": ["data", "placa", "tipo_servico", "valor", "km_atual", "status"],
        "gente_ssma": ["data", "dds_tema", "incidentes_qtd", "absenteismo_percent", "turnover_percent"],
        "financeiro_obz": ["mes_ano", "pacote", "orcado", "realizado"],
        "compras_pedidos": ["data", "item", "quantidade", "valor_unitario", "fornecedor", "solicitante", "status"],
    }.items():
        if _tem_tabela(c, tabela):
            linhas = [{"operacao_id": op(r.get("operacao")), **{k: r.get(k) for k in cols}}
                      for r in _linhas(c, f"SELECT * FROM {tabela}") if op(r.get("operacao"))]
            if linhas:
                from repositories.base import inserir_lote
                _log(tabela, inserir_lote(tabela, linhas))


    migrar_sistema_publicado(c, op)


def migrar_sistema_publicado(c, op) -> None:
    """Tabelas do app publicado no Streamlit (pátio, viagens, política, financeiro, DPO...)."""
    from core import tempo
    from repositories.base import inserir_lote
    from services import produtos_service

    def lote(tabela, linhas, rotulo):
        linhas = [l for l in linhas if l.get("operacao_id", 1)]
        if linhas:
            _log(rotulo, inserir_lote(tabela, linhas))

    if _tem_tabela(c, "transportadoras_gestao"):
        _log("transportadoras (gestão)", upsert("transportadoras", [
            {"nome": r.get("nome"), "cnpj": r.get("cnpj"), "contato": r.get("contato")}
            for r in _linhas(c, "SELECT * FROM transportadoras_gestao") if r.get("nome")], ["nome"]))
    if _tem_tabela(c, "fabricas"):
        _log("fábricas", upsert("fabricas", [{"nome": r.get("nome"), "cidade": r.get("cidade"), "uf": r.get("uf")}
                                             for r in _linhas(c, "SELECT * FROM fabricas") if r.get("nome")], ["nome"]))
    if _tem_tabela(c, "carretas"):
        _log("carretas", upsert("carretas", [
            {"operacao_id": op(r.get("operacao")), "placa": r.get("placa"), "modelo": r.get("modelo"),
             "capacidade_hl": r.get("capacidade_hl") or 0, "status": r.get("status") or "Disponível"}
            for r in _linhas(c, "SELECT * FROM carretas") if op(r.get("operacao"))], ["operacao_id", "placa"]))
    if _tem_tabela(c, "motoristas"):
        lote("motoristas", [{"operacao_id": op(r.get("operacao")), "nome": r.get("nome"), "cnh": r.get("cnh"),
                             "telefone": r.get("telefone")} for r in _linhas(c, "SELECT * FROM motoristas")], "motoristas")
    if _tem_tabela(c, "agendamentos_descarga"):
        lote("agendamentos_descarga", [
            {"operacao_id": op(r.get("operacao")), "data": str(r.get("data_descarga"))[:10], "hora": None,
             "placa": r.get("placa"), "slot": r.get("slot"), "tipo_carga": r.get("tipo_carga"), "status": "Agendado",
             "observacao": r.get("observacao"), "criado_por": "migração", "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM agendamentos_descarga")], "agendamentos de descarga")
    if _tem_tabela(c, "vinculos_pedidos"):
        lote("vinculos_pedidos", [
            {"operacao_id": op(r.get("operacao")), "numero_pedido": r.get("numero_pedido"),
             "data_puxada": str(r.get("data_puxada"))[:10], "placa": r.get("placa"), "fabrica": r.get("fabrica"),
             "transportadora": r.get("transportadora"), "motorista": r.get("motorista"),
             "notas_fiscais": r.get("notas_fiscais"), "hl_carregado": 0, "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM vinculos_pedidos")], "pedidos vinculados")
    if _tem_tabela(c, "politica_estoque_base"):
        lote("politica_estoque", [
            {"operacao_id": op(r.get("operacao")), "data_registro": r.get("data_registro") or tempo.hoje().isoformat(),
             "cod": r.get("cod_clean"), "sku_original": r.get("sku_original"),
             "tipo": r.get("tipo") or produtos_service.tipo_sku(r.get("sku_original")), "categoria": r.get("categoria"),
             **{k: r.get(k) or 0 for k in ("estoque", "demanda", "doi_atual", "pe_min_dias", "pe_obj_dias",
                                           "pe_max_dias", "pe_min_hl", "pe_obj_hl", "pe_max_hl")},
             "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM politica_estoque_base") if r.get("cod_clean")], "política de estoque")
    if _tem_tabela(c, "financeiro_contas_pagar"):
        lote("contas_pagar", [
            {"operacao_id": op(r.get("operacao")), "pacote": r.get("pacote"), "departamento": r.get("departamento"),
             "data_vencimento": r.get("data_vencimento"), "documento": r.get("documento"),
             "fornecedor": r.get("nome_fornecedor"), "historico": r.get("historico"),
             "conta_gerencial": r.get("conta_gerencial"),
             "valor": r.get("valor_col_n") or r.get("comprometido") or 0, "realizado": r.get("realizado") or 0,
             "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM financeiro_contas_pagar")], "contas a pagar")
    if _tem_tabela(c, "padroes_dpo"):
        _log("padrões DPO", upsert("padroes_dpo", [
            {"operacao_id": op(r.get("operacao")), "modulo": r.get("modulo"), "subbloco": r.get("subbloco"),
             "titulo": r.get("titulo_padrao"), "conteudo": r.get("conteudo_padrao"), "responsavel": "",
             "status": "Em elaboração", "atualizado_por": "migração", "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM padroes_dpo") if op(r.get("operacao"))],
            ["operacao_id", "modulo", "subbloco"]))
    if _tem_tabela(c, "layout_armazem"):
        lote("layouts_armazem", [
            {"operacao_id": op(r.get("operacao")), "area": r.get("nome_area"), "nome_arquivo": r.get("nome_arquivo"),
             "tipo": r.get("tipo_arquivo"), "conteudo": r.get("dados_blob"), "dt_atualizacao": r.get("dt_atualizacao")}
            for r in _linhas(c, "SELECT * FROM layout_armazem") if r.get("dados_blob")], "plantas do armazém")
    if _tem_tabela(c, "cadastro_trechos_frete"):
        _migrar_trechos_publicados(c, op)


def _migrar_trechos_publicados(c, op) -> None:
    """Trechos do app publicado tinham texto 'Origem -> Destino' e eram globais: vão para a 1ª filial."""
    ops = _ops()
    oid = ops.get("Lima Rio Verde") or next(iter(ops.values()))
    n = 0
    for r in _linhas(c, "SELECT * FROM cadastro_trechos_frete"):
        origem = (r.get("origem") or str(r.get("trecho") or "").split("->")[0]).strip()
        destino = (r.get("destino") or (str(r.get("trecho") or "").split("->") + [""])[1]).strip()
        if not origem or not destino:
            continue
        with get_conn() as conn:
            for nome, tipo in ((origem, "Apenas Origem"), (destino, "Apenas Destino")):
                if not conn.execute("SELECT 1 FROM origens_destinos WHERE operacao_id = ? AND nome = ?",
                                    (oid, nome)).fetchone():
                    conn.execute("INSERT INTO origens_destinos (operacao_id, nome, tipo) VALUES (?, ?, ?)",
                                 (oid, nome, "Origem e destino"))
            o = conn.execute("SELECT id FROM origens_destinos WHERE operacao_id = ? AND nome = ?", (oid, origem)).fetchone()[0]
            d = conn.execute("SELECT id FROM origens_destinos WHERE operacao_id = ? AND nome = ?", (oid, destino)).fetchone()[0]
            tr = None
            if r.get("transportadora"):
                row = conn.execute("SELECT id FROM transportadoras WHERE nome = ?", (r.get("transportadora"),)).fetchone()
                tr = row[0] if row else conn.execute("INSERT INTO transportadoras (nome) VALUES (?)",
                                                     (r.get("transportadora"),)).lastrowid
            ap = conn.execute("SELECT id FROM usuarios WHERE lower(nome) = lower(?) OR login = lower(?)",
                              (r.get("aprovador") or "", r.get("aprovador") or "")).fetchone()
        upsert("trechos", [{"operacao_id": oid, "origem_id": o, "destino_id": d, "distancia_km": 0, "pedagio": 0,
                            "valor_remunerado": 0, "valor_frete": r.get("valor_frete") or 0, "transportadora_id": tr,
                            "aprovador_id": ap[0] if ap else None}], ["operacao_id", "origem_id", "destino_id"])
        n += 1
    _log("trechos (app publicado)", n)


def migrar_puxada(c, nome_operacao: str) -> None:
    print(f"\n[Banco Sistema Puxada → operação '{nome_operacao}']")
    ops = _ops()
    if nome_operacao not in ops:
        raise ValueError(f"Operação '{nome_operacao}' não existe. Opções: {', '.join(ops)}")
    oid = ops[nome_operacao]

    _log("transportadoras", upsert("transportadoras", [
        {"nome": r.get("nome"), "cnpj": r.get("cnpj")} for r in _linhas(c, "SELECT * FROM transportadoras")], ["nome"]))
    if _tem_tabela(c, "centros_custo"):
        _log("centros de custo", upsert("centros_custo", [
            {"nome": r.get("nome")} for r in _linhas(c, "SELECT * FROM centros_custo")], ["nome"]))
    _log("origens/destinos", upsert("origens_destinos", [
        {"operacao_id": oid, "nome": r.get("nome"), "cidade": r.get("cidade"), "uf": r.get("uf"), "tipo": r.get("tipo")}
        for r in _linhas(c, "SELECT * FROM origens_destinos")], ["operacao_id", "nome"]))

    with get_conn() as conn:
        od = {r.get("nome"): r.get("id") for r in conn.execute("SELECT id, nome FROM origens_destinos WHERE operacao_id=?", (oid,))}
        tr = {r.get("nome"): r.get("id") for r in conn.execute("SELECT id, nome FROM transportadoras")}
        cc = {r.get("nome"): r.get("id") for r in conn.execute("SELECT id, nome FROM centros_custo")}
        us = {r.get("login"): r.get("id") for r in conn.execute("SELECT id, login FROM usuarios")}

    _log("trechos", upsert("trechos", [
        {"operacao_id": oid, "origem_id": od[r.get("origem")], "destino_id": od[r.get("destino")],
         "distancia_km": r.get("distancia_km"), "pedagio": r.get("pedagio"),
         "valor_remunerado": r.get("valor_remunerado"), "valor_frete": r.get("valor_frete")}
        for r in _linhas(c, "SELECT * FROM trechos") if r.get("origem") in od and r.get("destino") in od],
        ["operacao_id", "origem_id", "destino_id"]))

    if _tem_tabela(c, "cotacoes"):
        n = 0
        with get_conn() as conn:
            ja = conn.execute("SELECT COUNT(*) FROM cotacoes_frete WHERE operacao_id = ?", (oid,)).fetchone()[0]
        if ja:
            print("  • cotações: já existem cotações nesta operação — pulando para não duplicar.")
        else:
            for r in _linhas(c, "SELECT * FROM cotacoes"):
                with get_conn() as conn:
                    conn.execute(
                        """INSERT INTO cotacoes_frete (operacao_id, origem_id, destino_id, transportadora_id,
                           centro_custo_id, data_requisicao, data_frete, motivo, valor_negociado,
                           solicitante_id, aprovador_id, observacao, status, nf_arquivo, cte_arquivo)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (oid, od.get(r.get("origem")), od.get(r.get("destino")), tr.get(r.get("transportadora")),
                         cc.get(r.get("centro_custo")), r.get("data_requisicao"), r.get("data_frete"), r.get("motivo"),
                         r.get("valor_negociado"), us.get(str(r.get("solicitante")).lower()),
                         us.get(str(r.get("aprovador")).lower()), r.get("observacao"), r.get("status"),
                         r.get("nf_nome"), r.get("cte_nome")))
                n += 1
            _log("cotações", n)

    if _tem_tabela(c, "meta_obz"):
        _log("metas OBZ", upsert("metas_obz", [
            {"operacao_id": oid, "mes_ano": r.get("mes_ano"), "meta_valor": r.get("meta_valor")}
            for r in _linhas(c, "SELECT * FROM meta_obz")], ["operacao_id", "mes_ano"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--antigo", required=True)
    ap.add_argument("--puxada")
    ap.add_argument("--operacao-puxada", default="Lima Rio Verde")
    a = ap.parse_args()

    from database.connection import is_postgres
    print("Destino:", "PostgreSQL (nuvem)" if is_postgres() else "SQLite local (data/ecossistema.db)")
    init_db()
    migrar_principal(_abrir(a.antigo))
    if a.puxada:
        migrar_puxada(_abrir(a.puxada), a.operacao_puxada)
    print("\nMigração concluída.")


if __name__ == "__main__":
    main()
