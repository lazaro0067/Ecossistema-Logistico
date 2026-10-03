"""Importação de planilhas (Excel/CSV) para o banco.

Cada LAYOUT descreve: tabela de destino, campos esperados e como gravar.
A tela de importação lê a planilha, sugere o "de/para" das colunas
(pelos apelidos abaixo) e o usuário confirma antes de gravar.
"""
import datetime as dt
import re
import unicodedata

import pandas as pd

from repositories.base import apagar_onde, inserir_lote, upsert
from services import curva_abc_service
from services.erros import RegraNegocioError

# campo: (rótulo, tipo, obrigatório, apelidos de coluna aceitos)
LAYOUTS = {
    "produtos": {
        "rotulo": "Cadastro de Produtos (Base 01.11)",
        "tabela": "produtos", "chaves": ["cod"], "por_operacao": False, "modo": "upsert",
        "campos": {
            "cod": ("Código", "int", True, ["cod", "codigo", "cod_produto", "cod_clean", "sku"]),
            "descricao": ("Descrição", "str", False, ["descricao", "produto", "desc"]),
            "fator_hl": ("Fator HL", "float", False, ["fator_hl", "fator", "hl", "fator hl"]),
            "cx_pallet": ("Caixas por palete", "float", False, ["cx_pallet", "cx_palete", "caixas_palete", "lastro"]),
            "tipo": ("Tipo (Cerveja/NAB...)", "str", False, ["tipo"]),
            "categoria": ("Categoria", "str", False, ["categoria", "embalagem"]),
        },
    },
    "estoque": {
        "rotulo": "Posição de Estoque (02)",
        "tabela": "estoque", "chaves": ["operacao_id", "cod"], "por_operacao": True, "modo": "substituir_operacao",
        "campos": {
            "cod": ("Código", "int", True, ["cod", "codigo", "cod_produto", "cod_clean", "produto"]),
            "descricao": ("Descrição", "str", False, ["descricao", "desc"]),
            "inicial": ("Estoque inicial", "float", False, ["inicial", "estoque_inicial"]),
            "entrada": ("Entradas", "float", False, ["entrada", "entradas"]),
            "saida": ("Saídas", "float", False, ["saida", "saidas"]),
            "disponivel": ("Disponível", "float", True, ["disponivel", "saldo", "estoque"]),
            "saldo_dia": ("Saldo do dia", "float", False, ["saldo_dia", "saldo dia"]),
        },
    },
    "linear": {
        "rotulo": "Linear de Vendas (cx/dia)",
        "tabela": "linear_vendas", "chaves": ["operacao_id", "cod"], "por_operacao": True, "modo": "upsert",
        "campos": {
            "cod": ("Código", "int", True, ["cod", "codigo", "cod_clean", "sku"]),
            "linear_cx_dia": ("Linear (cx/dia)", "float", True, ["linear", "linear_vendas", "media", "cx_dia"]),
        },
    },
    "metas_doi": {
        "rotulo": "Metas de DOI por SKU",
        "tabela": "metas_doi", "chaves": ["operacao_id", "cod"], "por_operacao": True, "modo": "upsert",
        "campos": {
            "cod": ("Código", "int", True, ["cod", "codigo", "cod_prod", "cod_clean"]),
            "doi_meta": ("Meta DOI (dias)", "float", True, ["doi", "doi_meta", "meta", "dias"]),
        },
    },
    "curva_abc": {
        "rotulo": "Vendas do mês → Curva ABC",
        "tabela": "curva_abc", "chaves": ["operacao_id", "mes_ano", "cod"], "por_operacao": True,
        "modo": "curva_abc", "pede_mes": True,
        "campos": {
            "cod": ("Código", "int", True, ["cod", "codigo", "cod_clean", "sku"]),
            "descricao": ("Descrição", "str", False, ["descricao", "produto"]),
            "total_qtde": ("Quantidade vendida", "float", True, ["qtde", "quantidade", "total", "volume", "total_qtde"]),
        },
    },
    "pedidos_marcados": {
        "rotulo": "Pedidos Marcados (Puxada)",
        "tabela": "pedidos_marcados", "chaves": [], "por_operacao": True, "modo": "substituir_data",
        "campos": {
            "data_puxada": ("Data da puxada", "date", True, ["data", "data_puxada", "dt"]),
            "numero_pedido": ("Nº do pedido", "str", False, ["pedido", "numero_pedido", "n_pedido"]),
            "cod": ("Código", "int", True, ["cod", "codigo", "sku"]),
            "descricao": ("Descrição", "str", False, ["descricao", "produto"]),
            "cx_solicitadas": ("Caixas solicitadas", "float", False, ["solicitado", "cx_solicitadas", "qtd_solicitada"]),
            "cx_marcadas": ("Caixas marcadas", "float", False, ["marcado", "cx_marcadas", "qtd_marcada"]),
            "hl_marcado": ("HL marcado", "float", False, ["hl", "hl_marcado"]),
            "status_item": ("Status", "str", False, ["status", "status_item", "situacao"]),
        },
    },
    "ressuprimento": {
        "rotulo": "Ressuprimento diário por cesta",
        "tabela": "ressuprimento_diario", "chaves": ["operacao_id", "data", "cesta"], "por_operacao": True,
        "modo": "upsert",
        "campos": {
            "data": ("Data", "date", True, ["data", "dia", "data_registro"]),
            "cesta": ("Cesta", "str", True, ["cesta", "categoria"]),
            "volume_sellin_hl": ("Sell-in (HL)", "float", False, ["sellin", "sell_in", "volume_sellin_hl"]),
            "volume_real_hl": ("Real (HL)", "float", True, ["real", "volume_real_hl", "realizado"]),
        },
    },
}


# --- Utilidades de conversão ---------------------------------------------
def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", txt).strip("_")


def ler_arquivo(nome: str, conteudo) -> pd.DataFrame:
    if nome.lower().endswith(".csv"):
        df = pd.read_csv(conteudo, sep=None, engine="python", dtype=str, encoding="utf-8-sig")
    else:
        df = pd.read_excel(conteudo, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")


def sugerir_mapeamento(layout_key: str, colunas: list[str]) -> dict[str, str | None]:
    normalizadas = {_norm(c): c for c in colunas}
    sugestao = {}
    for campo, (_, _, _, apelidos) in LAYOUTS[layout_key]["campos"].items():
        sugestao[campo] = next((normalizadas[_norm(a)] for a in [campo, *apelidos] if _norm(a) in normalizadas), None)
    return sugestao


def _to_float(s: pd.Series) -> pd.Series:
    def conv(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        v = str(v).strip().replace("R$", "").replace(" ", "")
        if "," in v:  # formato brasileiro 1.234,56
            v = v.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", v):  # 1.000 / 12.345.678 = milhar
            v = v.replace(".", "")
        try:
            return float(v)
        except ValueError:
            return 0.0
    return s.map(conv)


def _to_int(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True) \
            .replace("", pd.NA).astype("Int64")


def _to_date(s: pd.Series) -> pd.Series:
    iso = s.astype(str).str.match(r"^\d{4}-\d{2}-\d{2}")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    out[iso] = pd.to_datetime(s[iso].str[:10], errors="coerce", format="%Y-%m-%d")
    out[~iso] = pd.to_datetime(s[~iso], errors="coerce", dayfirst=True)
    return out.dt.strftime("%Y-%m-%d")


def preparar(layout_key: str, df: pd.DataFrame, mapeamento: dict[str, str | None]) -> pd.DataFrame:
    """Aplica o de/para e converte tipos. Levanta erro se faltar campo obrigatório."""
    layout = LAYOUTS[layout_key]
    saida = pd.DataFrame(index=df.index)
    for campo, (rotulo, tipo, obrig, _) in layout["campos"].items():
        col = mapeamento.get(campo)
        if not col:
            if obrig:
                raise RegraNegocioError(f"Informe a coluna para o campo obrigatório: {rotulo}.")
            continue
        serie = df[col]
        if tipo == "int":
            saida[campo] = _to_int(serie)
        elif tipo == "float":
            saida[campo] = _to_float(serie)
        elif tipo == "date":
            saida[campo] = _to_date(serie)
        else:
            saida[campo] = serie.fillna("").astype(str).str.strip()
    obrig = [c for c, (_, _, o, _) in layout["campos"].items() if o]
    saida = saida.dropna(subset=obrig)
    if saida.empty:
        raise RegraNegocioError("Nenhuma linha válida após a conversão. Confira o de/para das colunas.")
    return saida


def gravar(layout_key: str, dados: pd.DataFrame, operacao_id: int | None, mes_ano: str | None = None) -> int:
    layout = LAYOUTS[layout_key]
    df = dados.copy()
    modo = layout["modo"]

    if modo == "curva_abc":
        if not mes_ano:
            raise RegraNegocioError("Informe o mês de referência.")
        if "descricao" not in df:
            df["descricao"] = ""
        df = curva_abc_service.calcular(df)
        df["mes_ano"] = mes_ano

    if layout["por_operacao"]:
        df.insert(0, "operacao_id", operacao_id)
    if layout["tabela"] in ("estoque", "linear_vendas", "curva_abc", "pedidos_marcados", "ressuprimento_diario"):
        df["dt_atualizacao"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    df = df.astype(object).where(pd.notna(df), None)
    linhas = df.to_dict("records")
    for l in linhas:  # Int64 -> int nativo
        for k, v in l.items():
            if hasattr(v, "item"):
                l[k] = v.item()

    if modo == "substituir_operacao":
        apagar_onde(layout["tabela"], "operacao_id = ?", (operacao_id,))
        return upsert(layout["tabela"], linhas, layout["chaves"])
    if modo == "substituir_data":
        for d in df["data_puxada"].dropna().unique():
            apagar_onde(layout["tabela"], "operacao_id = ? AND data_puxada = ?", (operacao_id, d))
        return inserir_lote(layout["tabela"], linhas)
    if modo == "curva_abc":
        apagar_onde("curva_abc", "operacao_id = ? AND mes_ano = ?", (operacao_id, mes_ano))
    # upsert agregando duplicados pela chave (última linha vence)
    return upsert(layout["tabela"], linhas, layout["chaves"])
