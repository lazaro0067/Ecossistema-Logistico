"""💰 Financeiro › 📑 DRE › 🧾 Financeiro contabilidade — o financeiro fechado da contabilidade (fecha o DRE).

Relatório (ex.: OBZ_FECH_SET_WK.xlsx), por mês e revenda:
  A = código · B = classificação · C = nome · D = valor (negativo = despesa, positivo = crédito).
  Classificação "1" = total · "1.1" = departamento (PUXADA, ARMAZEM…) · "1.1.01" = subpacote ·
  "3.03.01.02.001.0002" = conta (fica no departamento/subpacote de cima).
No DRE: despesas do departamento = −(soma das contas) + ✍️ outras contas lançadas à mão.
O DRE do mês só fica 🔒 FECHADO quando esse relatório é subido; antes disso é prévia pelo OBZ.
"""
from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services.erros import RegraNegocioError

NOME = "Financeiro contabilidade"


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


def _norm(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper().strip()


def _valor(v) -> float | None:
    if v is None:
        return None
    t = str(v).strip()
    if not t or t.lower() == "nan":
        return None
    neg = t.endswith("-") or t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("-()").strip().replace("R$", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        x = float(t)
    except ValueError:
        return None
    return -x if neg else x


def _nivel(cls: str) -> str:
    c = str(cls or "").strip()
    if re.fullmatch(r"\d+", c):
        return "total"
    if re.fullmatch(r"\d+\.\d+", c):
        return "departamento"
    if re.fullmatch(r"\d+\.\d+\.\d{1,3}", c):
        return "subpacote"
    if re.fullmatch(r"[\d.]+", c) and c.count(".") >= 3:
        return "conta"
    return ""


def ler(conteudo: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Contas do relatório (com departamento e subpacote) + avisos de conferência dos totais."""
    txt = None
    for enc in ("utf-8-sig", "latin1"):
        try:
            txt = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    df = pd.read_csv(io.StringIO(txt or ""), sep=";", header=None, dtype=str, keep_default_na=False,
                     on_bad_lines="skip")
    return _ler_df(df)


def _ler_df(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if df.shape[1] < 4:
        raise RegraNegocioError("Este arquivo não parece o Financeiro contabilidade: esperava código (A), "
                                "classificação (B), nome (C) e valor (D).")
    df = df.fillna("")
    linhas, depto, sub, cab = [], None, None, {}
    for r in df.itertuples(index=False):
        cls = str(r[1]).strip()
        cls = cls[:-2] if re.fullmatch(r"\d+\.0", cls) else cls  # célula numérica do Excel (1 → "1.0")
        cod = str(r[0]).strip()
        cod = cod[:-2] if cod.endswith(".0") else cod
        cod, nome, val = cod, str(r[2]).strip(), _valor(r[3])
        nv = _nivel(cls)
        if not nv or val is None:
            continue
        if nv == "departamento":
            depto, sub = nome or cls, None
            cab[("d", depto)] = cab.get(("d", depto), 0.0) + val
        elif nv == "subpacote":
            sub = nome or cls
            cab[("s", depto, sub)] = cab.get(("s", depto, sub), 0.0) + val
        elif nv == "conta":
            linhas.append({"codigo": cod, "classificacao": cls, "nome": nome, "departamento": depto or "Sem departamento",
                           "subpacote": sub or "", "valor": val})
    if not linhas:
        raise RegraNegocioError("Nenhuma conta encontrada. A coluna B precisa ter a classificação (1.1, 1.1.01, "
                                "3.03.01…) e a D o valor.")
    out = pd.DataFrame(linhas)
    avisos = []
    for (tipo, *chave), v in cab.items():
        if tipo == "d":
            soma = out.loc[out["departamento"] == chave[0], "valor"].sum()
            if abs(soma - v) > 0.05:
                avisos.append(f"{chave[0]}: total do relatório {v:,.2f} × soma das contas {soma:,.2f}")
    return out, avisos


def importar(conteudo: bytes, nome: str, operacao_id: int, mes: str, usuario: str = "") -> dict:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir o Financeiro contabilidade.")
    if not re.fullmatch(r"\d{4}-\d{2}", str(mes or "")):
        raise RegraNegocioError("Escolha o mês do fechamento.")
    df, avisos = ler(conteudo)
    with get_conn() as conn:
        _gravar(conn, operacao_id, mes, df, nome, usuario)
    return {"contas": len(df), "departamentos": df["departamento"].nunique(), "despesa": float(-df["valor"].sum()),
            "avisos": avisos}


_ABA_MES = re.compile(r"^OBZ[ _]?(\d{1,2})$", re.I)
_MESES_TXT = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10,
              "nov": 11, "dez": 12}


def abas_mensais(conteudo: bytes) -> dict[int, pd.DataFrame]:
    """Planilha com uma aba por mês (OBZ01 … OBZ12, 'Período: jan'…): {mês 1–12: linhas da aba}.
    Abas de outros anos/empresas (ex.: OBZ_Por05_23) ficam de fora."""
    try:
        xl = pd.ExcelFile(io.BytesIO(conteudo))
    except Exception as e:  # noqa: BLE001
        raise RegraNegocioError(f"Não consegui abrir a planilha: {e}") from e
    out = {}
    for aba in xl.sheet_names:
        m = _ABA_MES.match(str(aba).strip())
        if not m or not 1 <= int(m.group(1)) <= 12:
            continue
        df = xl.parse(aba, header=None, dtype=object)
        # confere o mês pelo cabeçalho "Período: jan" quando houver
        per = next((str(c) for r in df.head(6).itertuples(index=False) for c in r
                    if isinstance(c, str) and "per" in c.lower() and ":" in c), "")
        mt = _MESES_TXT.get(per.split(":", 1)[1].strip()[:3].lower()) if per else None
        out[mt or int(m.group(1))] = df
    return out


def ler_planilha_mes(conteudo: bytes, mes: str) -> tuple[pd.DataFrame, list[str]] | None:
    """Se a planilha tem abas mensais (OBZ09…), lê só a aba do mês escolhido. None = não é desse formato."""
    abas = abas_mensais(conteudo)
    if not abas:
        return None
    m = int(mes[5:])
    if m not in abas:
        raise RegraNegocioError(f"A planilha tem abas mensais, mas não a de {mes[5:]}/{mes[:4]} (OBZ{m:02d}).")
    return _ler_df(abas[m].iloc[:, :4])


def _gravar(conn, operacao_id: int, mes: str, df: pd.DataFrame, nome: str, usuario: str) -> None:
    conn.execute("DELETE FROM fin_contab WHERE operacao_id = ? AND mes = ?", (int(operacao_id), mes))
    conn.executemany("INSERT INTO fin_contab (operacao_id, mes, codigo, classificacao, nome, departamento, "
                     "subpacote, valor, arquivo, criado_por, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     [(int(operacao_id), mes, r.codigo, r.classificacao, r.nome, r.departamento, r.subpacote,
                       float(r.valor), str(nome)[:200], usuario, agora()) for r in df.itertuples(index=False)])


def importar_planilha_mes(conteudo: bytes, nome: str, operacao_id: int, mes: str, usuario: str = "") -> dict | None:
    """Upload do mês com a planilha de abas mensais: grava só a aba do mês. None = não é esse formato."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir o Financeiro contabilidade.")
    r = ler_planilha_mes(conteudo, mes)
    if r is None:
        return None
    df, avisos = r
    with get_conn() as conn:
        _gravar(conn, operacao_id, mes, df, nome, usuario)
    return {"contas": len(df), "departamentos": df["departamento"].nunique(), "despesa": float(-df["valor"].sum()),
            "avisos": avisos}


def importar_consolidado(conteudo: bytes, nome: str, operacao_id: int, ano: str, usuario: str = "",
                         zerar_ano: bool = True) -> dict:
    """Retroativo de uma vez: planilha com uma aba por mês (OBZ01…OBZ12). Zera o ano da revenda (se pedido) e grava
    cada mês que tiver contas. Abas vazias (meses futuros) ficam de fora."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir o retroativo.")
    if not re.fullmatch(r"\d{4}", str(ano or "")):
        raise RegraNegocioError("Escolha o ano.")
    abas = abas_mensais(conteudo)
    if not abas:
        raise RegraNegocioError("Não achei abas mensais (OBZ01 … OBZ12) nesta planilha.")
    lidos, vazios = {}, []
    for m in sorted(abas):
        try:
            lidos[m] = _ler_df(abas[m].iloc[:, :4])
        except RegraNegocioError:
            vazios.append(m)
    if not lidos:
        raise RegraNegocioError("Nenhuma aba mensal tem contas lançadas.")
    with get_conn() as conn:
        if zerar_ano:
            conn.execute("DELETE FROM fin_contab WHERE operacao_id = ? AND mes LIKE ?", (int(operacao_id), f"{ano}-%"))
        for m, (df, _) in lidos.items():
            _gravar(conn, operacao_id, f"{ano}-{m:02d}", df, nome, usuario)
    return {"meses": {f"{ano}-{m:02d}": {"contas": len(df), "despesa": float(-df["valor"].sum()), "avisos": av}
                      for m, (df, av) in lidos.items()},
            "vazios": [f"{ano}-{m:02d}" for m in vazios], "zerado": zerar_ano}


def zerar(operacao_id: int, ano: str | None = None) -> int:
    """Apaga o Financeiro contabilidade da revenda (do ano, ou tudo). As ✍️ Outras contas ficam."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada).")
    filtro, p = ("AND mes LIKE ?", [f"{ano}-%"]) if ano else ("", [])
    r = query_one(f"SELECT COUNT(DISTINCT mes) AS n FROM fin_contab WHERE operacao_id = ? {filtro}",
                  (int(operacao_id), *p))
    execute(f"DELETE FROM fin_contab WHERE operacao_id = ? {filtro}", (int(operacao_id), *p))
    return int(r["n"]) if r else 0


def excluir_mes(operacao_id: int, mes: str) -> None:
    execute("DELETE FROM fin_contab WHERE operacao_id = ? AND mes = ?", (int(operacao_id), mes))


def meses(operacao_id: int) -> list[str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    d = query_df(f"SELECT DISTINCT mes FROM fin_contab WHERE {trecho} ORDER BY mes DESC", p)
    return d["mes"].astype(str).tolist()


def carga(operacao_id: int, mes: str) -> dict | None:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_one(f"SELECT COUNT(*) AS contas, MAX(arquivo) AS arquivo, MAX(criado_por) AS por, "
                     f"MAX(criado_em) AS em FROM fin_contab WHERE {trecho} AND mes = ? HAVING COUNT(*) > 0",
                     (*p, mes))


def fechado(operacao_id: int, mes: str) -> bool:
    """O DRE do mês só fecha com o relatório da contabilidade (na consolidada: todas as revendas subiram)."""
    ids = operacoes_repo.ids_efetivos(operacao_id)
    ph = ", ".join("?" * len(ids))
    d = query_df(f"SELECT DISTINCT operacao_id FROM fin_contab WHERE operacao_id IN ({ph}) AND mes = ?", (*ids, mes))
    return len(d) == len(ids) and len(ids) > 0


def contas(operacao_id: int, mes: str) -> pd.DataFrame:
    """Contas do relatório + outras contas, somadas nas revendas (consolidada). despesa = −valor."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    a = query_df(f"SELECT departamento, subpacote, codigo, classificacao, nome, SUM(valor) AS valor FROM fin_contab "
                 f"WHERE {trecho} AND mes = ? GROUP BY departamento, subpacote, codigo, classificacao, nome",
                 (*p, mes))
    a["origem"] = "relatório"
    b = query_df(f"SELECT departamento, '' AS subpacote, '' AS codigo, '' AS classificacao, conta AS nome, "
                 f"SUM(-despesa) AS valor FROM fin_contab_outras WHERE {trecho} AND mes = ? "
                 f"GROUP BY departamento, conta", (*p, mes))
    b["origem"] = "✍️ outras contas"
    df = pd.concat([a, b], ignore_index=True)
    if df.empty:
        return pd.DataFrame(columns=["departamento", "subpacote", "codigo", "classificacao", "nome", "valor",
                                     "origem", "despesa"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["despesa"] = -df["valor"]
    return df


def departamentos(operacao_id: int) -> list[str]:
    """Departamentos já usados (para lançar outras contas)."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    d = query_df(f"SELECT DISTINCT departamento FROM fin_contab WHERE {trecho} UNION "
                 f"SELECT DISTINCT departamento FROM fin_contab_outras WHERE {trecho}", (*p, *p))
    return sorted(x for x in d["departamento"].dropna().astype(str) if x)


def fora_dre(nome) -> bool:
    """Despesas de Jataí — ficam fora do operacional (linha "Despesas ADM Jataí", abaixo da margem operacional)."""
    return "JATAI" in _norm(nome)


ADM_JATAI = "Despesas ADM Jataí"
# pilares que formam a despesa operacional do DRE; o resto (investimento/imobilizado, Jataí…) vai abaixo
PILARES = {"ARMAZEM", "ENTREGA", "GENTE", "PUXADA", "MANUTENCAO", "VENDAS", "FROTA", "ADMINISTRATIVO",
           "ADMINISTRACAO", "ADM"}


def e_pilar(nome) -> bool:
    return _norm(nome) in PILARES


def nomes_obz() -> dict:
    try:
        from services import obz_service

        return {_norm(n): str(n) for n in obz_service.areas()["nome"].dropna()}
    except Exception:  # noqa: BLE001
        return {}


def nome_depto(nome, nomes: dict | None = None) -> str:
    """Mesmo nome para o mesmo departamento (ENTREGA = Entrega, ARMAZEM = Armazém): usa o nome da área do OBZ;
    sem ela, só a 1ª letra maiúscula."""
    n = _norm(nome)
    nomes = nomes_obz() if nomes is None else nomes
    if n in nomes:
        return nomes[n]
    t = str(nome or "").strip()
    return "/".join(p.strip().capitalize() for p in t.split("/")) if t.isupper() else t


def despesas_dre(operacao_id: int, mes: str) -> pd.DataFrame | None:
    """Mesmo formato do OBZ no DRE (pacote = departamento, realizado, orcado). None = relatório não subido.
    O plan vem do OBZ quando o nome do departamento é o mesmo."""
    if not fechado(operacao_id, mes):
        return None
    c = contas(operacao_id, mes)
    if c.empty:
        return None
    jat = c["departamento"].map(fora_dre) | c["subpacote"].fillna("").map(fora_dre)
    nomes = nomes_obz()
    c = c.assign(departamento=[ADM_JATAI if j else nome_depto(d, nomes) for d, j in zip(c["departamento"], jat)])
    g = c.groupby("departamento", sort=False)["despesa"].sum()
    orc = {}
    try:
        from services import obz_service

        o = obz_service.despesas_dre(operacao_id, mes)
        if o is not None:
            orc = {_norm(k): float(v) for k, v in zip(o["pacote"], o["orcado"])}
    except Exception:  # noqa: BLE001 — sem OBZ, plan fica zerado
        orc = {}
    out = pd.DataFrame({"pacote": g.index, "realizado": g.values.astype(float),
                        "orcado": [orc.get(_norm(k), 0.0) for k in g.index]})
    return out.reset_index(drop=True)


def _txt(v) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    t = str(v).strip()
    return "" if t.lower() in ("none", "nan") else t


# --- ✍️ outras contas ---------------------------------------------------------------------------------------------
def outras(operacao_id: int, mes: str) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT id, departamento, conta, despesa, obs, criado_por, criado_em FROM fin_contab_outras "
                    f"WHERE {trecho} AND mes = ? ORDER BY departamento, conta", (*p, mes))


def salvar_outras(operacao_id: int, mes: str, linhas: list[dict], usuario: str = "") -> int:
    """Substitui as outras contas do mês pelas linhas da tabela (despesa positiva; crédito negativo)."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para lançar outras contas.")
    boas = []
    for r in linhas:
        dep, conta = _txt(r.get("departamento")), _txt(r.get("conta"))
        v = r.get("despesa")
        if not dep and not conta and (v is None or pd.isna(v)):
            continue
        if not dep or not conta:
            raise RegraNegocioError("Cada linha precisa de departamento e conta.")
        if v is None or pd.isna(v):
            raise RegraNegocioError(f"Informe o valor de “{conta}”.")
        boas.append((int(operacao_id), mes, dep, conta, float(v), _txt(r.get("obs")), usuario, agora()))
    with get_conn() as conn:
        conn.execute("DELETE FROM fin_contab_outras WHERE operacao_id = ? AND mes = ?", (int(operacao_id), mes))
        conn.executemany("INSERT INTO fin_contab_outras (operacao_id, mes, departamento, conta, despesa, obs, "
                         "criado_por, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", boas)
    return len(boas)
