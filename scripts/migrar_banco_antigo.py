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
        return {r["nome"]: r["id"] for r in conn.execute("SELECT id, nome FROM operacoes")}


def _log(rotulo: str, n: int) -> None:
    print(f"  ✔ {rotulo}: {n}")


def migrar_principal(c) -> None:
    print("\n[Banco principal]")
    if _tem_tabela(c, "operacoes"):
        _log("operações", upsert("operacoes", [
            {"nome": r["nome"], "cnpj": r.get("cnpj"), "cidade": r.get("cidade"), "uf": r.get("uf")}
            for r in _linhas(c, "SELECT * FROM operacoes")], ["nome"]))
    ops = _ops()

    def op(nome):
        return ops.get(nome)

    # Usuários (senhas antigas em texto puro são convertidas para hash)
    if _tem_tabela(c, "usuarios"):
        n = 0
        for u in _linhas(c, "SELECT * FROM usuarios"):
            login = str(u["nome"]).strip().lower()
            with get_conn() as conn:
                if conn.execute("SELECT 1 FROM usuarios WHERE login = ?", (login,)).fetchone():
                    continue
                cur = conn.execute(
                    """INSERT INTO usuarios (login, nome, senha_hash, email, cargo, perfil, e_aprovador, alcada)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (login, u["nome"], hash_senha(u.get("senha") or "123456"), u.get("email"), u.get("cargo"),
                     u.get("perfil") or "Operacional", int(u.get("e_aprovador") == "Sim"), u.get("alcada_reais") or 0))
                mods = [m for m in MODULOS if u.get(f"perm_{m}") == 1]
                conn.executemany("INSERT INTO usuario_modulos VALUES (?, ?)", [(cur.lastrowid, m) for m in mods])
                n += 1
        _log("usuários novos", n)

    if _tem_tabela(c, "base_01_11"):
        prod = {r["cod_clean"]: {"cod": r["cod_clean"], "descricao": r["descricao"], "fator_hl": r["fator_hl"],
                                 "cx_pallet": r["cx_pallet"], "tipo": None, "categoria": None}
                for r in _linhas(c, "SELECT * FROM base_01_11")}
        if _tem_tabela(c, "base_linear"):
            for r in _linhas(c, "SELECT * FROM base_linear"):
                p = prod.setdefault(r["cod_clean"], {"cod": r["cod_clean"], "descricao": None, "fator_hl": 0,
                                                     "cx_pallet": 0, "tipo": None, "categoria": None})
                p["tipo"], p["categoria"] = r["tipo"], r["categoria"]
        _log("produtos", upsert("produtos", list(prod.values()), ["cod"]))

    ops_com_estoque = []
    if _tem_tabela(c, "base_estoque_02"):
        linhas = [{"operacao_id": op(r["operacao"]), "cod": r["cod_clean"], "descricao": (r["descricao"] or "").strip(),
                   "inicial": r["inicial"], "entrada": r["entrada"], "saida": r["saida"],
                   "disponivel": r["disponivel"], "saldo_dia": r["saldo_dia"], "dt_atualizacao": r["dt_atualizacao"]}
                  for r in _linhas(c, "SELECT * FROM base_estoque_02") if op(r["operacao"])]
        ops_com_estoque = sorted({l["operacao_id"] for l in linhas})
        _log("estoque", upsert("estoque", linhas, ["operacao_id", "cod"]))

    if _tem_tabela(c, "base_linear"):
        alvo = ops_com_estoque or list(ops.values())[:1]
        linhas = [{"operacao_id": o, "cod": r["cod_clean"], "linear_cx_dia": r["linear_vendas"],
                   "dt_atualizacao": r["dt_atualizacao"]}
                  for r in _linhas(c, "SELECT * FROM base_linear") for o in alvo]
        _log("linear de vendas", upsert("linear_vendas", linhas, ["operacao_id", "cod"]))

    if _tem_tabela(c, "metas_doi"):
        _log("metas DOI", upsert("metas_doi", [
            {"operacao_id": op(r["operacao"]), "cod": r["cod_prod"], "doi_meta": r["doi_meta"]}
            for r in _linhas(c, "SELECT * FROM metas_doi") if op(r["operacao"])], ["operacao_id", "cod"]))

    if _tem_tabela(c, "historico_curva_abc"):
        _log("curva ABC", upsert("curva_abc", [
            {"operacao_id": op(r["operacao"]), "mes_ano": _mes_br_para_iso(r["mes_ano"]), "cod": r["cod_clean"],
             "descricao": (r["descricao"] or "").strip(), "total_qtde": r["total_qtde"],
             "pct_acumulado": r["pct_acumulado"], "classe": r["classe_abc"], "dt_atualizacao": r["dt_atualizacao"]}
            for r in _linhas(c, "SELECT * FROM historico_curva_abc") if op(r["operacao"])],
            ["operacao_id", "mes_ano", "cod"]))

    if _tem_tabela(c, "armazens"):
        cap = {r["operacao"]: r for r in _linhas(c, "SELECT * FROM armazem_capacidade")} \
            if _tem_tabela(c, "armazem_capacidade") else {}
        _log("armazéns", upsert("armazens", [
            {"operacao_id": op(r["operacao"]), "nome": r["nome_armazem"],
             "cap_hl": (cap.get(r["operacao"]) or {}).get("cap_hl", 0),
             "cap_paletes": (cap.get(r["operacao"]) or {}).get("cap_paletes", 0)}
            for r in _linhas(c, "SELECT * FROM armazens") if op(r["operacao"])], ["operacao_id", "nome"]))

    if _tem_tabela(c, "pedidos_marcados"):
        from repositories.base import substituir
        linhas = [{"operacao_id": op(r["operacao"]), "data_puxada": _data_br_para_iso(r["data_puxada"]),
                   "cod": r["cod_clean"], "descricao": r["descricao"], "cx_solicitadas": r["cx_solicitadas"],
                   "cx_marcadas": r["cx_marcadas"], "hl_marcado": r["hl_marcado"], "status_item": r["status_item"],
                   "numero_pedido": str(r["numero_pedido"] or "").lstrip("'"), "dt_atualizacao": r["dt_atualizacao"]}
                  for r in _linhas(c, "SELECT * FROM pedidos_marcados") if op(r["operacao"])]
        _log("pedidos marcados", substituir("pedidos_marcados", "1 = 1", (), linhas, None))

    if _tem_tabela(c, "gestao_ressuprimento_diario"):
        _log("ressuprimento diário", upsert("ressuprimento_diario", [
            {"operacao_id": op(r["operacao"]), "data": r["data_registro"], "cesta": r["cesta"],
             "volume_sellin_hl": r["volume_sellin_hl"], "volume_real_hl": r["volume_real_hl"],
             "dt_atualizacao": r["dt_atualizacao"]}
            for r in _linhas(c, "SELECT * FROM gestao_ressuprimento_diario") if op(r["operacao"])],
            ["operacao_id", "data", "cesta"]))

    if _tem_tabela(c, "metas_ressuprimento_mensal"):
        _log("metas de ressuprimento", upsert("metas_ressuprimento", [
            {"operacao_id": op(r["operacao"]), "mes_ano": f"{r['ano']:04d}-{r['mes']:02d}", "cesta": r["cesta"],
             "meta_volume_hl": r["meta_volume_hl"]}
            for r in _linhas(c, "SELECT * FROM metas_ressuprimento_mensal") if op(r["operacao"])],
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
            linhas = [{"operacao_id": op(r["operacao"]), **{k: r.get(k) for k in cols}}
                      for r in _linhas(c, f"SELECT * FROM {tabela}") if op(r["operacao"])]
            if linhas:
                from repositories.base import inserir_lote
                _log(tabela, inserir_lote(tabela, linhas))


def migrar_puxada(c, nome_operacao: str) -> None:
    print(f"\n[Banco Sistema Puxada → operação '{nome_operacao}']")
    ops = _ops()
    if nome_operacao not in ops:
        sys.exit(f"Operação '{nome_operacao}' não existe. Opções: {', '.join(ops)}")
    oid = ops[nome_operacao]

    _log("transportadoras", upsert("transportadoras", [
        {"nome": r["nome"], "cnpj": r["cnpj"]} for r in _linhas(c, "SELECT * FROM transportadoras")], ["nome"]))
    if _tem_tabela(c, "centros_custo"):
        _log("centros de custo", upsert("centros_custo", [
            {"nome": r["nome"]} for r in _linhas(c, "SELECT * FROM centros_custo")], ["nome"]))
    _log("origens/destinos", upsert("origens_destinos", [
        {"operacao_id": oid, "nome": r["nome"], "cidade": r["cidade"], "uf": r["uf"], "tipo": r["tipo"]}
        for r in _linhas(c, "SELECT * FROM origens_destinos")], ["operacao_id", "nome"]))

    with get_conn() as conn:
        od = {r["nome"]: r["id"] for r in conn.execute("SELECT id, nome FROM origens_destinos WHERE operacao_id=?", (oid,))}
        tr = {r["nome"]: r["id"] for r in conn.execute("SELECT id, nome FROM transportadoras")}
        cc = {r["nome"]: r["id"] for r in conn.execute("SELECT id, nome FROM centros_custo")}
        us = {r["login"]: r["id"] for r in conn.execute("SELECT id, login FROM usuarios")}

    _log("trechos", upsert("trechos", [
        {"operacao_id": oid, "origem_id": od[r["origem"]], "destino_id": od[r["destino"]],
         "distancia_km": r["distancia_km"], "pedagio": r["pedagio"],
         "valor_remunerado": r["valor_remunerado"], "valor_frete": r["valor_frete"]}
        for r in _linhas(c, "SELECT * FROM trechos") if r["origem"] in od and r["destino"] in od],
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
                        (oid, od.get(r["origem"]), od.get(r["destino"]), tr.get(r["transportadora"]),
                         cc.get(r["centro_custo"]), r["data_requisicao"], r["data_frete"], r["motivo"],
                         r["valor_negociado"], us.get(str(r["solicitante"]).lower()),
                         us.get(str(r["aprovador"]).lower()), r["observacao"], r["status"],
                         r.get("nf_nome"), r.get("cte_nome")))
                n += 1
            _log("cotações", n)

    if _tem_tabela(c, "meta_obz"):
        _log("metas OBZ", upsert("metas_obz", [
            {"operacao_id": oid, "mes_ano": r["mes_ano"], "meta_valor": r["meta_valor"]}
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
