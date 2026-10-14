"""Financeiro › 🎯 Gestão OBZ — Plan × Tend × Real, dispersão, L-E, justificativas, aprovação e reuniões.

Realizado: relatório 16.03.01 (razão por conta). Coluna H = débito, coluna I = crédito.
  Conta de despesa: real = débito − crédito · conta de receita: real = crédito − débito (sempre positivo = normal).
Plan: metas mensais por conta × departamento (planilha modelo: baixar → preencher → subir).
Tend: tendência de fechamento do mês. O sistema sugere (fechamento do mês anterior, ou o real projetado se o mês
  já passou dele); quem lança confirma ou ajusta. Dispersão acima do limite (% da conta, ou o padrão) é CRÍTICA:
  exige justificativa (fica registrado quem criticou) e vai para aprovação do financeiro.
Dispersão = (Real no mês fechado | Tend no mês aberto) − Plan. Para despesa, positivo = gastou acima do plano.
L-E (latest estimate) do ano = real dos meses fechados + tend do mês aberto + plan dos meses que faltam.
"""
import io
import re
import unicodedata

import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services.erros import RegraNegocioError

LIMITE_PADRAO = 10.0
STATUS = {"lancada": "✅ Lançada", "aguardando": "⏳ Aguardando aprovação", "aprovada": "✔️ Aprovada",
          "reprovada": "❌ Reprovada — revisar", "sugerida": "💡 Sugestão (não lançada)"}
PAPEIS = {"lancador": "📝 Lança tendências", "aprovador": "✔️ Aprova (financeiro)"}
_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()


def _cod(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0") or "0"


def _num(s: pd.Series) -> pd.Series:
    t = s.astype(str).str.strip()
    br = t.str.contains(",", regex=False)
    t = t.where(~br, t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(t, errors="coerce").fillna(0.0)


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


def mes_atual() -> str:
    return tempo.hoje().strftime("%Y-%m")


def mes_anterior(mes: str) -> str:
    a, m = map(int, mes.split("-"))
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


def nome_mes(mes: str) -> str:
    return f"{_MESES[int(mes[5:]) - 1]}/{mes[:4]}"


# --- Pacote/natureza padrão por conta ---------------------------------------------------------------
_PACOTES = [
    (("combust", "pedagio", "pneu", "ipva", "lavagem", "pecas", "veicul", " cst"), "Frota"),
    (("carga e descarga", "empilhadeira", "fretes e carretos", "controle logistico", "freteiros"), "Logística"),
    (("alimentacao", "plano saude", "seguro de vida", "fgts", "uniforme", "estagio", "aprendiz", "exame",
      "ajuda de custo", "salario", "ferias", "13", "rescis", "inss", "funcionario"), "Gente"),
    (("assessoria", "servicos de", "contabilidade", "vigilancia", "portaria", "outros servicos", "limpeza contratada",
      "coleta de residuos"), "Serviços de terceiros"),
    (("aluguel", "alugueis", "predial", "agua e energia", "internet", "telefonia", "material de limpeza", "cantina"),
     "Estrutura & ocupação"),
    (("viage", "hospedagem", "passagem"), "Viagens"),
    (("evento", "patroc", "associac", "contribuic", "marketing", "brinde"), "Marketing & eventos"),
    (("sistema", "software", "informatica"), "TI"),
    (("reparo", "manutencao"), "Manutenção"),
    (("refugo", "quebra", "perda"), "Perdas"),
]


def pacote_padrao(codigo: str, nome: str) -> tuple[str, str, int]:
    """(pacote, natureza, entra no OBZ)"""
    c, n = str(codigo), " " + _n(nome)
    if c[:1] in ("1", "2", "3"):
        return "Patrimonial", "despesa", 0
    if c in ("4008", "4009") or "compras a prazo" in n:
        return "Compras de mercadoria", "despesa", 0
    if c.startswith("7") or "rendimento" in n or "receita" in n:
        return "Receitas financeiras", "receita", 1
    if c.startswith("6"):
        return "Despesas financeiras", "despesa", 1
    for chaves, pac in _PACOTES:
        if any(k in n for k in chaves):
            return pac, "despesa", 1
    return "Despesas gerais", "despesa", 1


# --- Cadastros -----------------------------------------------------------------------------------------
def departamentos(so_ativos: bool = False) -> pd.DataFrame:
    df = query_df("SELECT codigo, nome, ativo FROM obz_departamentos" + (" WHERE ativo = 1" if so_ativos else ""))
    return df.sort_values("codigo", key=lambda s: s.str.zfill(6)).reset_index(drop=True)


def nomes_deptos() -> dict[str, str]:
    d = departamentos()
    return dict(zip(d["codigo"], d["nome"].fillna("")))


def rotulo_depto(c: str, nomes: dict | None = None) -> str:
    nomes = nomes if nomes is not None else nomes_deptos()
    n = nomes.get(str(c)) or ""
    return f"{c} · {n}" if n else f"Depto {c}"


def salvar_depto(codigo: str, nome: str, ativo: bool = True) -> None:
    c = _cod(codigo) if str(codigo).strip() != "0" else "0"
    if not str(codigo).strip():
        raise RegraNegocioError("Informe o código do departamento.")
    execute("""INSERT INTO obz_departamentos (codigo, nome, ativo) VALUES (?, ?, ?)
               ON CONFLICT(codigo) DO UPDATE SET nome = excluded.nome, ativo = excluded.ativo""",
            (c, (nome or "").strip(), 1 if ativo else 0))


def excluir_depto(codigo: str) -> None:
    execute("DELETE FROM obz_departamentos WHERE codigo = ?", (str(codigo),))


def contas(so_obz: bool = False) -> pd.DataFrame:
    df = query_df("""SELECT c.codigo, c.nome, c.pacote, c.natureza, c.no_obz, c.limite_pct, c.dono_id,
                            u.nome AS dono FROM obz_contas c LEFT JOIN usuarios u ON u.id = c.dono_id"""
                  + (" WHERE c.no_obz = 1" if so_obz else ""))
    return df.sort_values("codigo", key=lambda s: s.str.zfill(8)).reset_index(drop=True)


def salvar_conta(codigo: str, nome: str, pacote: str | None = None, natureza: str | None = None,
                 no_obz: bool | None = None, limite_pct=None, dono_id=None) -> None:
    c = _cod(codigo)
    if c == "0":
        raise RegraNegocioError("Informe o código da conta.")
    pac, nat, obz = pacote_padrao(c, nome)
    atual = query_one("SELECT * FROM obz_contas WHERE codigo = ?", (c,))
    if atual:
        execute("""UPDATE obz_contas SET nome = ?, pacote = ?, natureza = ?, no_obz = ?, limite_pct = ?, dono_id = ?
                   WHERE codigo = ?""",
                ((nome or atual["nome"] or "").strip(), pacote if pacote is not None else atual["pacote"],
                 natureza if natureza is not None else atual["natureza"],
                 int(no_obz) if no_obz is not None else atual["no_obz"],
                 limite_pct if limite_pct is not None else atual["limite_pct"],
                 dono_id if dono_id is not None else atual["dono_id"], c))
    else:
        execute("""INSERT INTO obz_contas (codigo, nome, pacote, natureza, no_obz, limite_pct, dono_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (c, (nome or "").strip(), pacote or pac, natureza or nat, int(no_obz) if no_obz is not None else obz,
                 limite_pct, dono_id))


def excluir_conta(codigo: str) -> None:
    execute("DELETE FROM obz_contas WHERE codigo = ?", (str(codigo),))


def limite_padrao() -> float:
    r = query_one("SELECT codigo FROM setor_operacoes WHERE setor = 'obz_limite_padrao'")
    try:
        return float(r["codigo"]) if r else LIMITE_PADRAO
    except (TypeError, ValueError):
        return LIMITE_PADRAO


def salvar_limite_padrao(pct: float) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM setor_operacoes WHERE setor = 'obz_limite_padrao'")
        conn.execute("INSERT INTO setor_operacoes (setor, codigo) VALUES ('obz_limite_padrao', ?)", (str(float(pct)),))


def usuarios_papel(papel: str) -> list[int]:
    df = query_df("SELECT usuario_id FROM obz_papeis WHERE papel = ?", (papel,))
    return [int(x) for x in df["usuario_id"]]


def salvar_papel(papel: str, ids: list[int]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM obz_papeis WHERE papel = ?", (papel,))
        conn.executemany("INSERT INTO obz_papeis (usuario_id, papel) VALUES (?, ?)", [(int(i), papel) for i in ids])


def subdonos() -> pd.DataFrame:
    return query_df("""SELECT s.conta, s.depto, s.usuario_id, u.nome AS subdono FROM obz_subdonos s
                       LEFT JOIN usuarios u ON u.id = s.usuario_id ORDER BY s.conta, s.depto""")


def salvar_subdono(conta: str, depto: str, usuario_id: int | None) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM obz_subdonos WHERE conta = ? AND depto = ?", (str(conta), str(depto)))
        if usuario_id:
            conn.execute("INSERT INTO obz_subdonos (conta, depto, usuario_id) VALUES (?, ?, ?)",
                         (str(conta), str(depto), int(usuario_id)))


def pode_lancar(usuario: dict, conta: str, depto: str) -> bool:
    from core.auth import e_master

    if e_master(usuario) or usuario["id"] in usuarios_papel("lancador"):
        return True
    r = query_one("SELECT dono_id FROM obz_contas WHERE codigo = ?", (str(conta),))
    if r and r["dono_id"] == usuario["id"]:
        return True
    r = query_one("SELECT usuario_id FROM obz_subdonos WHERE conta = ? AND depto = ?", (str(conta), str(depto)))
    return bool(r and r["usuario_id"] == usuario["id"])


def pode_aprovar(usuario: dict) -> bool:
    from core.auth import e_master

    return e_master(usuario) or usuario["id"] in usuarios_papel("aprovador")


# --- Realizado (16.03.01) -------------------------------------------------------------------------------
def importar_real(conteudo: bytes, nome: str, operacao_id: int, usuario: str = "") -> dict:
    from services.produtividade_entrega_service import _abrir, _ler_csv, _log, _py

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir o 16.03.01.")
    df = _ler_csv(_abrir(conteudo, nome))
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    if len(df.columns) < 9:
        raise RegraNegocioError("Este arquivo não parece o 16.03.01 (esperava Conta, Nome, Dt Lcto, Histórico, "
                                "Contra Partida, Depto, Saldo Inicial, Débito na H e Crédito na I).")
    c = list(df.columns)
    d = pd.DataFrame({"conta": df[c[0]].map(_cod), "nome": df[c[1]].astype(str).str.strip(),
                      "data": pd.to_datetime(df[c[2]].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"),
                      "historico": df[c[3]].astype(str).str.strip(), "depto": df[c[5]].map(_cod),
                      "debito": _num(df[c[7]]), "credito": _num(df[c[8]])})
    d = d[d["data"].notna() & (d["conta"] != "0")]
    if d.empty:
        raise RegraNegocioError("Nenhum lançamento com data válida.")
    d["mes"] = d["data"].dt.strftime("%Y-%m")
    d["data"] = d["data"].dt.strftime("%Y-%m-%d")
    # cadastra contas e departamentos novos
    cad = set(contas()["codigo"])
    for conta, nome_c in d.drop_duplicates("conta")[["conta", "nome"]].itertuples(index=False):
        if conta not in cad:
            salvar_conta(conta, nome_c)
    deps = set(departamentos()["codigo"])
    for dep in d["depto"].unique():
        if dep not in deps:
            salvar_depto(dep, "Sem departamento" if dep == "0" else "")
    nat = dict(zip(contas()["codigo"], contas()["natureza"]))
    g = d.groupby(["mes", "conta", "depto"], as_index=False).agg(debito=("debito", "sum"), credito=("credito", "sum"),
                                                                  lancamentos=("data", "size"))
    g["valor"] = [(cr - db) if nat.get(ct) == "receita" else (db - cr)
                  for ct, db, cr in zip(g["conta"], g["debito"], g["credito"])]
    agora_ = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for mes in g["mes"].unique():
            conn.execute("DELETE FROM obz_real WHERE operacao_id = ? AND mes = ?", (operacao_id, mes))
            conn.execute("DELETE FROM obz_real_lanc WHERE operacao_id = ? AND mes = ?", (operacao_id, mes))
        tab = g.assign(operacao_id=operacao_id, importado_em=agora_)
        cols = list(tab.columns)
        conn.executemany(f"INSERT INTO obz_real ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         [tuple(_py(v) for v in r) for r in tab.itertuples(index=False)])
        lan = d[["mes", "data", "conta", "depto", "historico", "debito", "credito"]].assign(operacao_id=operacao_id)
        cols = list(lan.columns)
        conn.executemany(f"INSERT INTO obz_real_lanc ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         [tuple(_py(v) for v in r) for r in lan.itertuples(index=False)])
    _log(operacao_id, "obz_real", len(d), nome, usuario)
    return {"lancamentos": len(d), "contas": d["conta"].nunique(), "deptos": d["depto"].nunique(),
            "meses": sorted(g["mes"].unique()), "debito": float(d["debito"].sum()), "credito": float(d["credito"].sum())}


def lancamentos(operacao_id: int, mes: str, conta: str, depto: str | None = None) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    sql = f"SELECT data, conta, depto, historico, debito, credito FROM obz_real_lanc WHERE {trecho} AND mes = ? " \
          "AND conta = ?"
    params = [*p, mes, str(conta)]
    if depto is not None:
        sql += " AND depto = ?"
        params.append(str(depto))
    return query_df(sql + " ORDER BY data", params)


# --- Plan -----------------------------------------------------------------------------------------------
def modelo_plan(operacao_id: int, ano: str) -> bytes:
    """Planilha padrão: uma linha por conta × departamento (os que já aparecem no realizado + o plan atual)."""
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    pares = query_df(f"""SELECT DISTINCT conta, depto FROM obz_real WHERE {trecho}
                         UNION SELECT DISTINCT conta, depto FROM obz_plan WHERE {trecho}""", (*p, *p))
    ct = contas(so_obz=True)
    pares = pares[pares["conta"].isin(ct["codigo"])] if not pares.empty else pares
    if pares.empty:
        pares = pd.DataFrame({"conta": ct["codigo"], "depto": "0"})
    nomes_c = dict(zip(ct["codigo"], ct["nome"]))
    nomes_d = nomes_deptos()
    plan = plan_df(operacao_id, f"{ano}-01", f"{ano}-12")
    df = pd.DataFrame({"Conta": pares["conta"], "Nome da conta": pares["conta"].map(nomes_c),
                       "Depto": pares["depto"], "Nome do depto": pares["depto"].map(nomes_d)})
    for i, m in enumerate(_MESES, 1):
        mes = f"{ano}-{i:02d}"
        val = plan[plan["mes"] == mes].set_index(["conta", "depto"])["valor"] if not plan.empty else pd.Series(dtype=float)
        df[m] = [float(val.get((c, d), 0.0)) for c, d in zip(df["Conta"], df["Depto"])]
    df = df.sort_values(["Conta", "Depto"], key=lambda s: s.astype(str).str.zfill(8)).reset_index(drop=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=f"Plan {ano}")
        pd.DataFrame({"Como preencher": [
            "Uma linha por conta × departamento. Valores mensais em R$ (sem sinal).",
            "Conta de despesa: o gasto planejado. Conta de receita: a receita planejada.",
            "Pode incluir linhas novas (conta e depto). Linhas com zero são ignoradas.",
            "Suba em 🎯 Gestão OBZ › Plan."]}).to_excel(w, index=False, sheet_name="Instruções")
    return buf.getvalue()


def importar_plan(conteudo: bytes, nome: str, operacao_id: int, ano: str) -> int:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir o Plan.")
    try:
        df = pd.read_excel(io.BytesIO(conteudo), sheet_name=0, dtype=str) if not nome.lower().endswith(".csv") \
            else pd.read_csv(io.BytesIO(conteudo), sep=None, engine="python", dtype=str)
    except Exception as e:
        raise RegraNegocioError(f"Não consegui ler a planilha: {e}") from e
    cols = {_n(c): c for c in df.columns}
    if "conta" not in cols or "depto" not in cols:
        raise RegraNegocioError("Use a planilha modelo (colunas Conta, Depto e Jan…Dez).")
    linhas = []
    for i, m in enumerate(_MESES, 1):
        col = cols.get(_n(m))
        if not col:
            continue
        vals = _num(df[col].fillna("0"))
        for conta, depto, v in zip(df[cols["conta"]], df[cols["depto"]], vals):
            if str(conta).strip() and str(conta).lower() != "nan":
                linhas.append((operacao_id, f"{ano}-{i:02d}", _cod(conta), _cod(depto) if str(depto).strip() not in
                               ("", "nan") else "0", float(v)))
    if not linhas:
        raise RegraNegocioError("Nenhum valor encontrado (colunas Jan…Dez).")
    cad = set(contas()["codigo"])
    nomes_planilha = dict(zip(df[cols["conta"]].map(_cod), df[cols.get("nome da conta", cols["conta"])]))
    for _, _, conta, _, _ in linhas:
        if conta not in cad:
            salvar_conta(conta, str(nomes_planilha.get(conta, "")))
            cad.add(conta)
    with get_conn() as conn:
        conn.execute("DELETE FROM obz_plan WHERE operacao_id = ? AND mes BETWEEN ? AND ?",
                     (operacao_id, f"{ano}-01", f"{ano}-12"))
        conn.executemany("INSERT INTO obz_plan (operacao_id, mes, conta, depto, valor) VALUES (?, ?, ?, ?, ?)",
                         [x for x in linhas if x[4]])
    return len([x for x in linhas if x[4]])


def plan_df(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT mes, conta, depto, SUM(valor) AS valor FROM obz_plan WHERE {trecho} AND mes BETWEEN ? "
                    f"AND ? GROUP BY mes, conta, depto", (*p, de, ate))


def real_df(operacao_id: int, de: str, ate: str) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT mes, conta, depto, SUM(valor) AS valor, SUM(debito) AS debito, SUM(credito) AS credito "
                    f"FROM obz_real WHERE {trecho} AND mes BETWEEN ? AND ? GROUP BY mes, conta, depto", (*p, de, ate))


def meses(operacao_id: int) -> list[str]:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    r = query_df(f"SELECT DISTINCT mes FROM obz_real WHERE {trecho} UNION SELECT DISTINCT mes FROM obz_plan "
                 f"WHERE {trecho}", (*p, *p))
    ms = set(r["mes"]) | {mes_atual()}
    return sorted(ms, reverse=True)


# --- Tendência ------------------------------------------------------------------------------------------
def tend_df(operacao_id: int, mes: str) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT * FROM obz_tend WHERE {trecho} AND mes = ?", (*p, mes))


def fechado(mes: str) -> bool:
    return mes < mes_atual()


def base(operacao_id: int, mes: str) -> pd.DataFrame:
    """Conta × depto do mês: plan, real, sugestão, tend, dispersão, crítica, status."""
    pl = plan_df(operacao_id, mes, mes)
    rl = real_df(operacao_id, mes, mes)
    ant = real_df(operacao_id, mes_anterior(mes), mes_anterior(mes))
    td = tend_df(operacao_id, mes)
    chaves = ["conta", "depto"]
    partes = [x[chaves] for x in (pl, rl, ant, td) if not x.empty]
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes).drop_duplicates().reset_index(drop=True)
    ct = contas()
    df = df[df["conta"].isin(ct.loc[ct["no_obz"].astype(int) == 1, "codigo"])]
    if df.empty:
        return df
    for nome, x in (("plan", pl), ("real", rl), ("fech_ant", ant)):
        m = x.set_index(chaves)["valor"] if not x.empty else pd.Series(dtype=float)
        df[nome] = [float(m.get((c, d), 0.0)) for c, d in zip(df["conta"], df["depto"])]
    # sugestão: fechamento do mês anterior (sem ele, o plan); se o real do mês já passou disso, o próprio real
    if fechado(mes):
        df["sugerido"] = df["real"]
    else:
        ref = [a if a else p_ for a, p_ in zip(df["fech_ant"], df["plan"])]
        df["sugerido"] = [max(r, x) for r, x in zip(df["real"], ref)]
    tdi = td.set_index(chaves) if not td.empty else None
    def _get(c, d, col):
        if tdi is None or (c, d) not in tdi.index:
            return None
        return tdi.loc[(c, d), col]
    df["tend"] = [_get(c, d, "valor") for c, d in zip(df["conta"], df["depto"])]
    df["tend_lancada"] = df["tend"].notna()
    df["tend"] = pd.to_numeric(df["tend"], errors="coerce").fillna(df["sugerido"])
    for col in ("status", "justificativa", "lancado_por", "lancado_em", "criticado_por", "criticado_em", "aprovador",
                "aprovado_em", "comentario_aprov", "id"):
        df[col] = [_get(c, d, col) for c, d in zip(df["conta"], df["depto"])]
    df["status"] = df["status"].fillna("sugerida")
    df["fechamento"] = df["real"] if fechado(mes) else df["tend"]
    df["disp"] = df["fechamento"] - df["plan"]
    df["disp_pct"] = df["disp"] / df["plan"].where(df["plan"] != 0) * 100
    cmap = ct.set_index("codigo")
    padrao = limite_padrao()
    df["nome_conta"] = df["conta"].map(cmap["nome"])
    df["pacote"] = df["conta"].map(cmap["pacote"]).fillna("—")
    df["natureza"] = df["conta"].map(cmap["natureza"]).fillna("despesa")
    df["dono"] = df["conta"].map(cmap["dono"])
    df["limite"] = df["conta"].map(cmap["limite_pct"]).astype(float).fillna(padrao)
    # desfavorável: despesa acima do plano / receita abaixo do plano
    sinal = df["natureza"].map(lambda n: -1 if n == "receita" else 1)
    df["desfavoravel"] = df["disp"] * sinal
    df["critica"] = (df["disp_pct"].abs() >= df["limite"]) | ((df["plan"] == 0) & (df["fechamento"].abs() > 0))
    sd = subdonos()
    sdi = sd.set_index(["conta", "depto"])["subdono"] if not sd.empty else pd.Series(dtype=object)
    df["subdono"] = [sdi.get((c, d)) for c, d in zip(df["conta"], df["depto"])]
    nd = nomes_deptos()
    df["nome_depto"] = df["depto"].map(lambda d: nd.get(d) or f"Depto {d}")
    return df.sort_values(["pacote", "conta", "depto"]).reset_index(drop=True)


def salvar_tend(operacao_id: int, mes: str, conta: str, depto: str, valor: float, usuario: dict,
                justificativa: str = "", plan: float = 0.0, sugerido: float | None = None) -> str:
    """Grava a tendência. Se a dispersão for crítica, exige justificativa e manda para aprovação."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para lançar tendências.")
    if not pode_lancar(usuario, conta, depto):
        raise RegraNegocioError("Você não está cadastrado como dono, sub-dono ou lançador desta conta.")
    c = query_one("SELECT limite_pct FROM obz_contas WHERE codigo = ?", (str(conta),))
    limite = float(c["limite_pct"]) if c and c["limite_pct"] is not None else limite_padrao()
    disp = float(valor) - float(plan or 0)
    critica = (abs(disp / plan * 100) >= limite) if plan else abs(float(valor)) > 0
    just = (justificativa or "").strip()
    if critica and not just:
        raise RegraNegocioError(f"Dispersão crítica (limite {limite:.0f}%): escreva a justificativa.")
    status = "aguardando" if critica else "lancada"
    quem, quando = usuario.get("nome") or usuario.get("login"), agora()
    execute("""INSERT INTO obz_tend (operacao_id, mes, conta, depto, valor, sugerido, lancado_por, lancado_em,
                                     justificativa, criticado_por, criticado_em, status, aprovador, aprovado_em,
                                     comentario_aprov)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
               ON CONFLICT(operacao_id, mes, conta, depto) DO UPDATE SET valor = excluded.valor,
                 sugerido = excluded.sugerido, lancado_por = excluded.lancado_por, lancado_em = excluded.lancado_em,
                 justificativa = excluded.justificativa, criticado_por = excluded.criticado_por,
                 criticado_em = excluded.criticado_em, status = excluded.status, aprovador = NULL,
                 aprovado_em = NULL, comentario_aprov = NULL""",
            (operacao_id, mes, str(conta), str(depto), float(valor), sugerido, quem, quando, just or None,
             quem if critica else None, quando if critica else None, status))
    if critica:
        _avisar_aprovadores(operacao_id, mes, conta, depto, disp, quem)
    return status


def _avisar_aprovadores(operacao_id, mes, conta, depto, disp, quem) -> None:
    try:
        from repositories import motoristas_repo

        for uid in usuarios_papel("aprovador"):
            motoristas_repo.criar_notificacao(uid, "obz", f"obz:{operacao_id}:{mes}:{conta}:{depto}:{agora()}",
                                              f"🎯 OBZ: justificativa para aprovar ({nome_mes(mes)})",
                                              f"Conta {conta} · depto {depto} · dispersão R$ {disp:,.2f} — lançada "
                                              f"por {quem}.", "financeiro", agora() + ":00")
    except Exception:
        pass


def aprovar(tend_id: int, usuario: dict, aprovado: bool, comentario: str = "") -> None:
    if not pode_aprovar(usuario):
        raise RegraNegocioError("Só o financeiro (aprovadores cadastrados) aprova justificativas.")
    if not aprovado and not (comentario or "").strip():
        raise RegraNegocioError("Para reprovar, escreva o motivo.")
    execute("""UPDATE obz_tend SET status = ?, aprovador = ?, aprovado_em = ?, comentario_aprov = ? WHERE id = ?""",
            ("aprovada" if aprovado else "reprovada", usuario.get("nome") or usuario.get("login"), agora(),
             (comentario or "").strip() or None, int(tend_id)))


def pendentes(operacao_id: int) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("t.operacao_id", operacao_id)
    return query_df(f"""SELECT t.*, c.nome AS nome_conta, o.nome AS revenda FROM obz_tend t
                        LEFT JOIN obz_contas c ON c.codigo = t.conta LEFT JOIN operacoes o ON o.id = t.operacao_id
                        WHERE {trecho} AND t.status = 'aguardando' ORDER BY t.mes DESC, t.conta""", p)


# --- L-E (latest estimate) do ano --------------------------------------------------------------------------
def le_ano(operacao_id: int, ano: str) -> pd.DataFrame:
    atual = mes_atual()
    pl = plan_df(operacao_id, f"{ano}-01", f"{ano}-12")
    rl = real_df(operacao_id, f"{ano}-01", f"{ano}-12")
    linhas = []
    for i in range(1, 13):
        mes = f"{ano}-{i:02d}"
        p_ = pl[pl["mes"] == mes].groupby("conta")["valor"].sum() if not pl.empty else pd.Series(dtype=float)
        r_ = rl[rl["mes"] == mes].groupby("conta")["valor"].sum() if not rl.empty else pd.Series(dtype=float)
        if mes < atual:
            le, fonte = r_, "real"
        elif mes == atual:
            b = base(operacao_id, mes)
            le, fonte = (b.groupby("conta")["tend"].sum() if not b.empty else pd.Series(dtype=float)), "tend"
        else:
            le, fonte = p_, "plan"
        for conta in set(p_.index) | set(r_.index) | set(le.index):
            linhas.append({"mes": mes, "conta": conta, "plan": float(p_.get(conta, 0.0)),
                           "real": float(r_.get(conta, 0.0)), "le": float(le.get(conta, 0.0)), "fonte": fonte})
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    ct = contas()
    df = df[df["conta"].isin(ct.loc[ct["no_obz"].astype(int) == 1, "codigo"])]
    cmap = ct.set_index("codigo")
    df["nome_conta"] = df["conta"].map(cmap["nome"])
    df["pacote"] = df["conta"].map(cmap["pacote"])
    df["natureza"] = df["conta"].map(cmap["natureza"])
    return df


# --- Reunião: top dispersões e ações --------------------------------------------------------------------
def top_dispersoes(b: pd.DataFrame, n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(10 mais desfavoráveis, 10 mais favoráveis) por conta (somando departamentos)."""
    if b.empty:
        return b, b
    g = b.groupby(["conta", "nome_conta", "pacote", "natureza"], as_index=False)[["plan", "real", "tend", "fechamento",
                                                                                   "disp", "desfavoravel"]].sum()
    g["disp_pct"] = g["disp"] / g["plan"].where(g["plan"] != 0) * 100
    just = b.dropna(subset=["justificativa"]).groupby("conta")["justificativa"].apply(lambda s: " | ".join(s))
    g["justificativa"] = g["conta"].map(just)
    neg = g[g["desfavoravel"] > 0].nlargest(n, "desfavoravel")
    pos = g[g["desfavoravel"] < 0].nsmallest(n, "desfavoravel")
    return neg.reset_index(drop=True), pos.reset_index(drop=True)


def acoes(operacao_id: int, mes: str | None = None) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, params = f"SELECT * FROM obz_acoes WHERE {trecho}", list(p)
    if mes:
        sql += " AND mes = ?"
        params.append(mes)
    return query_df(sql + " ORDER BY id DESC", params)


def salvar_acao(operacao_id: int, mes: str, dados: dict, usuario: dict, acao_id: int | None = None) -> None:
    if not (dados.get("acao") or "").strip():
        raise RegraNegocioError("Descreva a ação.")
    if acao_id:
        execute("""UPDATE obz_acoes SET conta = ?, depto = ?, acao = ?, responsavel = ?, prazo = ?, status = ?
                   WHERE id = ?""", (dados.get("conta"), dados.get("depto"), dados["acao"].strip(),
                                     dados.get("responsavel"), dados.get("prazo"), dados.get("status") or "Aberta",
                                     int(acao_id)))
    else:
        execute("""INSERT INTO obz_acoes (operacao_id, mes, conta, depto, acao, responsavel, prazo, status, criado_por,
                                          criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (operacao_id, mes, dados.get("conta"), dados.get("depto"), dados["acao"].strip(),
                 dados.get("responsavel"), dados.get("prazo"), dados.get("status") or "Aberta",
                 usuario.get("nome"), agora()))


def excluir_acao(acao_id: int) -> None:
    execute("DELETE FROM obz_acoes WHERE id = ?", (int(acao_id),))


def reunioes(operacao_id: int, mes: str) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    return query_df(f"SELECT * FROM obz_reunioes WHERE {trecho} AND mes = ? ORDER BY id DESC", (*p, mes))


def salvar_reuniao(operacao_id: int, mes: str, data: str, participantes: str, ata: str, usuario: dict) -> None:
    if not (ata or "").strip():
        raise RegraNegocioError("Escreva a ata/pontos da reunião.")
    execute("""INSERT INTO obz_reunioes (operacao_id, mes, data, participantes, ata, criado_por)
               VALUES (?, ?, ?, ?, ?, ?)""", (operacao_id, mes, data, participantes, ata.strip(), usuario.get("nome")))


# --- Para o DRE ------------------------------------------------------------------------------------------
def despesas_dre(operacao_id: int, mes: str) -> pd.DataFrame | None:
    """Despesas líquidas do mês por pacote (despesa − receita), contas do OBZ. None = sem realizado."""
    rl = real_df(operacao_id, mes, mes)
    if rl.empty:
        return None
    ct = contas()
    rl = rl.merge(ct[["codigo", "pacote", "natureza", "no_obz"]], left_on="conta", right_on="codigo", how="left")
    rl = rl[rl["no_obz"].fillna(1).astype(int) == 1]
    rl["liq"] = [v if n != "receita" else -v for v, n in zip(rl["valor"], rl["natureza"])]
    pl = plan_df(operacao_id, mes, mes)
    pl = pl.merge(ct[["codigo", "pacote", "natureza"]], left_on="conta", right_on="codigo", how="left") \
        if not pl.empty else pl
    if not pl.empty:
        pl["liq"] = [v if n != "receita" else -v for v, n in zip(pl["valor"], pl["natureza"])]
    g = rl.groupby("pacote", as_index=False)["liq"].sum().rename(columns={"liq": "realizado"})
    if not pl.empty:
        g = g.merge(pl.groupby("pacote", as_index=False)["liq"].sum().rename(columns={"liq": "orcado"}), on="pacote",
                    how="outer").fillna(0.0)
    else:
        g["orcado"] = 0.0
    return g.sort_values("realizado", ascending=False).reset_index(drop=True)
