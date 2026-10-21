"""🤖 Agente de Resultados — responde perguntas sobre a operação buscando os números dentro do sistema.

Usa a API do Claude (Anthropic) com "ferramentas": o modelo pede os dados (resumo do mês, DRE, ranking, entrega,
estoque, consulta ao banco só de leitura) e o sistema responde com os números calculados aqui — o agente não inventa
número, ele lê do sistema. A revenda é escolhida na tela (o agente só enxerga a revenda escolhida).

Secrets: ANTHROPIC_API_KEY = "sk-ant-..."  ·  AGENTE_MODELO = "claude-sonnet-5-5" (opcional)
"""
from __future__ import annotations

import json
import re

import pandas as pd

from core import tempo
from core.segredos import segredo
from database.connection import query_df
from repositories import operacoes_repo
from services import resultados_service as rs

MODELO_PADRAO = "claude-sonnet-5-5"
MAX_PASSOS = 8
_LIMITE_LINHAS = 200

# tabelas que o agente pode consultar direto (nada de usuários, senhas, acessos ou tokens)
TABELAS = {
    "notas_dia": "venda/compra por dia (origem 'venda'|'compra', operacao_cod, status, valor, hl, qtde, notas)",
    "notas_produto_mes": "venda/compra por produto e mês (mes AAAA-MM, produto, descricao, valor, hl, qtde)",
    "notas_cliente_mes": "venda por cliente e mês (cliente, nome, valor, hl, notas)",
    "notas_prod_dia": "produto por dia (origem, data, produto, descricao, qtde em caixas, hl, cliente=fábrica na compra)",
    "entregas_mapas": "viagens de entrega do PCD (data, mapa, placa, veiculo, entregas, caixas, ocup_cx, peso, "
                      "ocup_peso, km_prev, classificacao)",
    "estoque_saldos": "02.05.02 saldo inicial/final do mês (mes, tipo_saldo, produto, qtd_venda, valor, hl)",
    "frota_placas": "cadastro de placas (placa, tipo, marca_modelo, area, status)",
    "inv_inventarios": "inventários (mes, nome, status, tipo mensal|diario, data)",
    "idade_contagens": "contagens com validade (data)",
    "idade_itens": "itens da contagem com validade (contagem_id, area, endereco, produto, qtd_un, validade)",
    "fin_contab": "financeiro da contabilidade (mes, departamento, subpacote, nome da conta, valor — negativo = despesa)",
    "dre_manual": "valores manuais do DRE (mes, icms, pis_cofins, conta_corrente)",
    "operacoes": "revendas (id, nome)",
}
_PROIBIDO = re.compile(r"\b(usuario|usuarios|senha|token|seg_|portal_rn|inv_conferentes|codigo_recuperacao|"
                       r"insert|update|delete|drop|alter|create|grant|revoke|truncate|attach|pragma|copy|vacuum)\b",
                       re.I)


def configurado() -> bool:
    return bool(segredo("ANTHROPIC_API_KEY"))


def modelo() -> str:
    return str(segredo("AGENTE_MODELO", MODELO_PADRAO) or MODELO_PADRAO)


# --- serialização ----------------------------------------------------------------------------------------------
def _v(x):
    if x is None:
        return None
    if isinstance(x, float):
        return None if pd.isna(x) else round(x, 2)
    if isinstance(x, (int, str, bool)):
        return x
    if hasattr(x, "isoformat"):
        return x.isoformat()[:10]
    try:
        f = float(x)
        return None if pd.isna(f) else round(f, 2)
    except (TypeError, ValueError):
        return str(x)


def _df(d: pd.DataFrame, n: int = 30) -> list[dict]:
    if not isinstance(d, pd.DataFrame) or d.empty:
        return []
    return [{k: _v(v) for k, v in r.items()} for r in d.head(n).to_dict("records")]


def _limpo(bloco):
    if isinstance(bloco, dict):
        return {k: (_df(v) if isinstance(v, pd.DataFrame) else _limpo(v)) for k, v in bloco.items()
                if not k.startswith("_") and k not in ("lista",)}
    return _v(bloco)


# --- ferramentas --------------------------------------------------------------------------------------------------
FERRAMENTAS = [
    {"name": "resumo_do_mes", "description": "Resultados da revenda num mês: vendas (faturamento, HL, R$/HL), compras, "
     "DRE (receita, CMV, lucro bruto, despesas, resultado), entrega (viagens, ocupação, modal), estoque com risco de "
     "vencer e acuracidade do inventário — e o mesmo do mês anterior para comparar.",
     "input_schema": {"type": "object", "properties": {"mes": {"type": "string", "description": "AAAA-MM"}},
                      "required": ["mes"]}},
    {"name": "evolucao_mensal", "description": "Faturamento, HL, compras e resultado operacional mês a mês.",
     "input_schema": {"type": "object", "properties": {
         "meses": {"type": "integer", "description": "quantos meses para trás (até 24)"},
         "ate": {"type": "string", "description": "último mês AAAA-MM"}}, "required": ["meses"]}},
    {"name": "ranking", "description": "Maiores produtos ou clientes do mês por faturamento (com HL e R$/HL).",
     "input_schema": {"type": "object", "properties": {
         "mes": {"type": "string"}, "tipo": {"type": "string", "enum": ["produtos", "clientes"]},
         "quantidade": {"type": "integer"}}, "required": ["mes", "tipo"]}},
    {"name": "despesas_por_departamento", "description": "Despesas do DRE por departamento no mês (realizado × plan).",
     "input_schema": {"type": "object", "properties": {"mes": {"type": "string"}}, "required": ["mes"]}},
    {"name": "entrega_e_frota", "description": "Produtividade da entrega no mês: por tipo de veículo e frota sugerida "
     "por modal (VUC, Toco, Truck, Van, Fiorino…).",
     "input_schema": {"type": "object", "properties": {"mes": {"type": "string"}}, "required": ["mes"]}},
    {"name": "estoque_risco_vencer", "description": "Produtos com risco de vencer no armazém (shelf), com caixas e R$.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "consultar_banco", "description": "Consulta SQL SÓ DE LEITURA (um SELECT) nas tabelas do sistema, para "
     "perguntas que as outras ferramentas não cobrem. O sistema já limita cada tabela à revenda em análise (não "
     "precisa filtrar operacao_id). Use FROM/JOIN explícitos. "
     "Tabelas: " + "; ".join(f"{k} = {v}" for k, v in TABELAS.items()) + ". Datas em texto AAAA-MM-DD.",
     "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}},
]


def _tabelas_reais() -> set[str]:
    from database.connection import get_conn
    from services.backup_service import _tabelas_do_banco

    with get_conn() as conn:
        return {t.lower() for t in _tabelas_do_banco(conn)}


_PALAVRAS = ("where", "group", "order", "limit", "left", "right", "inner", "outer", "full", "cross", "join", "on",
             "union", "having", "natural", "using", "except", "intersect")


def _filtro(t: str, ids: list[int]) -> str:
    """De onde cada tabela liberada lê: só as linhas da(s) revenda(s) escolhida(s) na tela."""
    lista = ", ".join(str(int(i)) for i in ids)
    if t == "operacoes":
        return f"SELECT * FROM operacoes WHERE id IN ({lista})"
    if t == "idade_itens":
        return (f"SELECT * FROM idade_itens WHERE contagem_id IN "
                f"(SELECT id FROM idade_contagens WHERE operacao_id IN ({lista}))")
    return f"SELECT * FROM {t} WHERE operacao_id IN ({lista})"


def _restringir(s: str, ids: list[int]) -> str | None:
    """Reescreve o SELECT para que cada tabela liberada só enxergue a revenda escolhida (o modelo não consegue ler
    outra revenda nem que tente). Devolve None se a consulta usar a tabela de um jeito que não dá para garantir."""
    usadas: set[str] = set()
    ok = [0]
    nomes = "|".join(TABELAS)
    pal = "|".join(_PALAVRAS)

    def troca(m: re.Match) -> str:
        t = m.group(2).lower()
        usadas.add(t)
        ok[0] += 1
        alias = m.group(3)
        return f"{m.group(1)} _f_{t}" + (alias if alias else f" AS {t}")

    s2 = re.sub(rf"\b(from|join)\s+({nomes})\b(?!\s*\.)(\s+(?:as\s+)?(?!(?:{pal})\b)[a-z_]\w*)?", troca, s,
                flags=re.I)
    # toda menção restante a uma tabela liberada tem de ser qualificador de coluna (tabela.coluna) ou alias (AS tabela)
    soltas = re.findall(rf"(?<![\w.])(?<!_f_)(?<!as )({nomes})\b(?!\s*\.)", s2, re.I)
    if soltas or re.search(rf"\b(?:from|join)\s+[a-z_]\w*\s*\.", s, re.I) or re.search(r"\b(?:from|join)\s+[a-z_]\w*(?:\s+(?:as\s+)?[a-z_]\w*)?\s*,", s, re.I):
        return None
    if not usadas:
        return s2
    ctes = ", ".join(f"_f_{t} AS ({_filtro(t, ids)})" for t in sorted(usadas))
    if re.match(r"^\s*with\b", s2, re.I):
        return f"WITH {ctes}, " + re.sub(r"^\s*with\b", "", s2, count=1, flags=re.I)
    return f"WITH {ctes} {s2}"


def _consultar(sql: str, ids: list[int]) -> dict:
    s = (sql or "").strip().rstrip(";")
    if not re.match(r"^\s*(select|with)\b", s, re.I) or ";" in s:
        return {"erro": "Só é permitido um SELECT."}
    if _PROIBIDO.search(s) or re.search(r"\b(recursive|information_schema|pg_\w+|sqlite_\w+)\b", s, re.I):
        return {"erro": "Consulta não permitida (só leitura e sem tabelas de usuários/senhas)."}
    usadas = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", s, re.I)}
    fora = {t for t in usadas & _tabelas_reais() if t not in TABELAS}
    if fora:
        return {"erro": f"Tabela(s) não liberada(s): {', '.join(sorted(fora))}."}
    if not ids:
        return {"erro": "Revenda não identificada."}
    r = _restringir(s, ids)
    if r is None:
        return {"erro": "Use FROM/JOIN explícitos com o nome da tabela (sem vírgula entre tabelas, sem esquema)."}
    try:
        d = query_df(f"SELECT * FROM ({r}) q LIMIT {_LIMITE_LINHAS}")
    except Exception as e:  # noqa: BLE001
        return {"erro": f"SQL inválido: {e}"}
    return {"linhas": len(d), "dados": _df(d, _LIMITE_LINHAS)}


def executar(nome: str, entrada: dict, op: int) -> dict:
    """Roda a ferramenta pedida pelo modelo, sempre na revenda escolhida na tela."""
    mes = str(entrada.get("mes") or tempo.hoje().strftime("%Y-%m"))[:7]
    try:
        if nome == "resumo_do_mes":
            return _limpo(rs.resumo_mes(op, mes))
        if nome == "evolucao_mensal":
            n = max(1, min(int(entrada.get("meses") or 12), 24))
            return {"meses": _df(rs.evolucao(op, n, entrada.get("ate")), 24)}
        if nome == "ranking":
            q = max(1, min(int(entrada.get("quantidade") or 15), 50))
            return {"ranking": _df(rs.top(op, mes, entrada.get("tipo", "produtos"), q), q)}
        if nome == "despesas_por_departamento":
            d = rs.dre(op, mes)
            return {"fechado_pela_contabilidade": d["fechado"], "despesas_total": _v(d["despesas"]),
                    "departamentos": _df(d["departamentos"])}
        if nome == "entrega_e_frota":
            return _limpo(rs.entrega(op, mes))
        if nome == "estoque_risco_vencer":
            s_ = rs.shelf(op)
            return {"produtos": s_.get("produtos"), "valor": _v(s_.get("valor")), "caixas": _v(s_.get("caixas")),
                    "lista": _df(s_.get("lista"), 25)}
        if nome == "consultar_banco":
            return _consultar(entrada.get("sql", ""), operacoes_repo.ids_efetivos(op))
    except Exception as e:  # noqa: BLE001
        return {"erro": f"{type(e).__name__}: {e}"}
    return {"erro": f"ferramenta desconhecida: {nome}"}


def _sistema(op: int) -> str:
    nome = (operacoes_repo.buscar(op) or {}).get("nome", "")
    ids = operacoes_repo.ids_efetivos(op)
    hoje = tempo.hoje()
    return (
        "Você é o Agente de Resultados do Ecossistema Logístico (revenda Ambev). Responda SEMPRE em português do "
        "Brasil, de forma direta e executiva: comece pela resposta, traga os números (R$, HL, %) e compare com o "
        "mês anterior quando fizer sentido; termine com 1 a 3 pontos de atenção ou ações, se houver.\n"
        f"Revenda em análise: {nome} (operacao_id {', '.join(map(str, ids))}). Hoje é {hoje:%d/%m/%Y} "
        f"(mês atual {hoje:%Y-%m}). Se a pergunta não disser o mês, use o mês atual e diga isso.\n"
        "Use as ferramentas para buscar os dados — NUNCA invente números. Se um dado não estiver carregado no "
        "sistema (base vazia ou erro), diga qual relatório falta subir (ex.: 03.02.37 vendas, 02.05.02, PCD, "
        "Financeiro contabilidade). Valores de dinheiro no formato R$ 1.234,56. Use tabelas markdown curtas quando "
        "ajudar. Não mostre SQL nem nomes técnicos de tabelas na resposta."
    )


def perguntar(historico: list[dict], pergunta: str, op: int) -> tuple[str, list[dict], list[dict]]:
    """Devolve (resposta, histórico novo, consultas feitas). O histórico guarda só blocos simples (dicts)."""
    import anthropic

    cli = anthropic.Anthropic(api_key=str(segredo("ANTHROPIC_API_KEY")))
    msgs = list(historico) + [{"role": "user", "content": pergunta}]
    consultas = []
    for _ in range(MAX_PASSOS):
        r = cli.messages.create(model=modelo(), max_tokens=2500, system=_sistema(op), tools=FERRAMENTAS,
                                messages=msgs)
        blocos = [b.model_dump(exclude_none=True) for b in r.content]
        msgs.append({"role": "assistant", "content": blocos})
        if r.stop_reason != "tool_use":
            texto = "\n".join(b.get("text", "") for b in blocos if b.get("type") == "text").strip()
            return texto or "(sem resposta)", msgs, consultas
        resultados = []
        for b in blocos:
            if b.get("type") != "tool_use":
                continue
            saida = executar(b["name"], b.get("input") or {}, op)
            consultas.append({"ferramenta": b["name"], "entrada": b.get("input") or {}})
            resultados.append({"type": "tool_result", "tool_use_id": b["id"],
                               "content": json.dumps(saida, ensure_ascii=False, default=str)[:60_000]})
        msgs.append({"role": "user", "content": resultados})
    return "Não consegui fechar a resposta — tente uma pergunta mais específica.", msgs, consultas
