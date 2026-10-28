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
PAPEIS = {"lancador": "📝 Lança tendências", "aprovador": "✔️ Aprova (financeiro)",
          "plan": "🎯 Pode alterar o Plan (liberado pelo Master)",
          "dre_editar": "✏️ Pode editar o DRE (liberado pelo Master)",
          "fin_dono": "🏦 Dono do financeiro — monta e aprova o simulador OBZ",
          "diretor": "🎩 Diretor — aprova o orçamento do simulador",
          "ceo": "🏛️ Corporativo / CEO — aprovação final do orçamento"}
# papéis que só o Master concede
PAPEIS_MASTER = {"plan", "dre_editar", "fin_dono", "diretor", "ceo"}
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


def e_bonificacao(nome) -> bool:
    n = _n(nome)
    return "bonif" in n or "amostra" in n


def pacote_padrao(codigo: str, nome: str) -> tuple[str, str, int]:
    """(pacote, natureza, entra no OBZ)"""
    c, n = str(codigo), " " + _n(nome)
    if c[:1] in ("1", "2", "3"):
        return "Patrimonial", "despesa", 0
    if c in ("4008", "4009") or "compras a prazo" in n:
        return "Compras de mercadoria", "despesa", 0
    if "bonif" in n or "amostra" in n:  # bonificação é comercial — não entra no OBZ/financeiro
        return "Bonificações", "despesa", 0
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
    df = query_df("SELECT codigo, nome, ativo, area FROM obz_departamentos" + (" WHERE ativo = 1" if so_ativos else ""))
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
    """Master, lançadores, ou o gestor do usuário como dono do departamento / sub-dono da conta."""
    from core.auth import e_master
    from services import gestores_service

    if e_master(usuario) or usuario["id"] in usuarios_papel("lancador"):
        return True
    r = query_one("SELECT usuario_id FROM obz_subdonos WHERE conta = ? AND depto = ?", (str(conta), str(depto)))
    if r and r["usuario_id"] == usuario["id"]:
        return True
    gid = gestores_service.gestor_do_usuario(usuario["id"])
    if not gid:
        return False
    area = area_de(str(conta), str(depto))
    a = query_one("SELECT dono_gestor_id FROM obz_areas WHERE nome = ?", (area,))
    if a and a["dono_gestor_id"] == gid:
        return True
    r = query_one("SELECT gestor_id FROM obz_resp WHERE area = ? AND conta = ?", (area, str(conta)))
    if r and r["gestor_id"] == gid:
        return True
    return dono_tt() == gid  # o dono do OBZ total responde por tudo (cascata)


def pode_plan(usuario: dict) -> bool:
    from core.auth import e_master

    return e_master(usuario) or usuario["id"] in usuarios_papel("plan")


# --- Departamentos (áreas do OBZ), mapa conta × depto → área, donos -----------------------------------------
SEM_AREA = "Sem departamento"


def areas() -> pd.DataFrame:
    df = query_df("""SELECT a.nome, a.dono_gestor_id, a.ordem, g.nome AS dono FROM obz_areas a
                     LEFT JOIN gestores g ON g.id = a.dono_gestor_id ORDER BY a.ordem, a.nome""")
    return df


def salvar_area(nome: str, dono_gestor_id=None, ordem: int | None = None, novo_nome: str | None = None) -> None:
    nome = (nome or "").strip()
    if not nome:
        raise RegraNegocioError("Informe o nome do departamento.")
    atual = query_one("SELECT * FROM obz_areas WHERE nome = ?", (nome,))
    if atual:
        execute("UPDATE obz_areas SET dono_gestor_id = ?, ordem = ? WHERE nome = ?",
                (dono_gestor_id, ordem if ordem is not None else atual["ordem"], nome))
        if novo_nome and novo_nome.strip() and novo_nome.strip() != nome:
            nn = novo_nome.strip()
            for t, c in (("obz_areas", "nome"), ("obz_mapa", "area"), ("obz_resp", "area"),
                         ("obz_departamentos", "area")):
                execute(f"UPDATE {t} SET {c} = ? WHERE {c} = ?", (nn, nome))
    else:
        execute("INSERT INTO obz_areas (nome, dono_gestor_id, ordem) VALUES (?, ?, ?)",
                (nome, dono_gestor_id, ordem or 0))


def excluir_area(nome: str) -> None:
    execute("UPDATE obz_mapa SET area = NULL WHERE area = ?", (nome,))
    execute("UPDATE obz_departamentos SET area = NULL WHERE area = ?", (nome,))
    execute("DELETE FROM obz_resp WHERE area = ?", (nome,))
    execute("DELETE FROM obz_areas WHERE nome = ?", (nome,))


def _mapas() -> tuple[dict, dict, dict]:
    m = query_df("SELECT conta, depto, area, vbz FROM obz_mapa")
    d = query_df("SELECT codigo, area FROM obz_departamentos WHERE area IS NOT NULL")
    par = {(c, dp): a for c, dp, a in zip(m["conta"], m["depto"], m["area"]) if a}
    vbz = {(c, dp): v for c, dp, v in zip(m["conta"], m["depto"], m["vbz"]) if v}
    return par, dict(zip(d["codigo"], d["area"])), vbz


def area_de(conta: str, depto: str, mapas=None) -> str:
    par, por_depto, _ = mapas or _mapas()
    return par.get((conta, depto)) or por_depto.get(depto) or SEM_AREA


def salvar_resp(area: str, conta: str, gestor_id: int | None) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM obz_resp WHERE area = ? AND conta = ?", (area, str(conta)))
        if gestor_id:
            conn.execute("INSERT INTO obz_resp (area, conta, gestor_id) VALUES (?, ?, ?)",
                         (area, str(conta), int(gestor_id)))


# --- 👤 Donos em cascata: OBZ total → departamento → conta (quem não tem dono herda o de cima) ---------------
def dono_tt() -> int | None:
    r = query_one("SELECT codigo FROM setor_operacoes WHERE setor = 'obz_dono_tt'")
    try:
        return int(r["codigo"]) if r and r["codigo"] else None
    except (TypeError, ValueError):
        return None


def salvar_dono_tt(gestor_id: int | None) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM setor_operacoes WHERE setor = 'obz_dono_tt'")
        if gestor_id:
            conn.execute("INSERT INTO setor_operacoes (setor, codigo) VALUES ('obz_dono_tt', ?)", (str(int(gestor_id)),))


def donos_cascata() -> pd.DataFrame:
    """Uma linha por departamento × conta com o dono próprio e o dono que vale (herdado de cima quando vazio).
    nivel = 'conta' | 'departamento' | 'OBZ total' | None (ninguém)."""
    from services import gestores_service as gs

    nomes = gs.nomes()
    tt = dono_tt()
    a = areas().set_index("nome")["dono_gestor_id"].to_dict() if not areas().empty else {}
    mapa = query_df("""SELECT DISTINCT m.area, m.conta, m.vbz, c.nome FROM obz_mapa m
                       LEFT JOIN obz_contas c ON c.codigo = m.conta WHERE m.area IS NOT NULL""")
    r = resp_df()
    rs = {(x, c): g for x, c, g in zip(r["area"], r["conta"], r["gestor_id"])} if not r.empty else {}
    linhas = []
    for ar, conta, vbz, nome in zip(mapa["area"], mapa["conta"], mapa["vbz"], mapa["nome"]):
        dc = rs.get((ar, conta))
        dd = a.get(ar)
        dc = int(dc) if dc is not None and dc == dc else None
        dd = int(dd) if dd is not None and dd == dd else None
        vale, nivel = ((dc, "conta") if dc else (dd, "departamento") if dd else (tt, "OBZ total") if tt
                       else (None, None))
        linhas.append({"area": ar, "conta": conta, "vbz": vbz, "nome": nome, "dono_conta": dc, "dono_depto": dd,
                       "dono_vale": vale, "nivel": nivel, "dono_vale_nome": nomes.get(vale) if vale else None})
    return pd.DataFrame(linhas, columns=["area", "conta", "vbz", "nome", "dono_conta", "dono_depto", "dono_vale",
                                         "nivel", "dono_vale_nome"])


def resp_df() -> pd.DataFrame:
    return query_df("""SELECT r.area, r.conta, r.gestor_id, g.nome AS subdono FROM obz_resp r
                       LEFT JOIN gestores g ON g.id = r.gestor_id""")


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
    return _gravar_real(operacao_id, d, nome, usuario)


def _e_resultado(conta: str) -> bool:
    try:
        return 4000 <= int(conta) < 8000
    except ValueError:
        return False


def _gravar_real(operacao_id: int, d: pd.DataFrame, nome: str, usuario: str) -> dict:
    """d: conta, nome, data (datetime), historico, depto, debito, credito. Só contas de resultado (4xxx–7xxx) ou
    já cadastradas — o razão completo traz clientes e fornecedores, que não são OBZ."""
    from services.produtividade_entrega_service import _log, _py

    d = d[d["data"].notna() & (d["conta"] != "0")]
    cad = set(contas()["codigo"])
    d = d[d["conta"].isin(cad) | d["conta"].map(_e_resultado)]
    if d.empty:
        raise RegraNegocioError("Nenhum lançamento de conta de resultado com data válida.")
    d = d.copy()
    d["mes"] = d["data"].dt.strftime("%Y-%m")
    d["data"] = d["data"].dt.strftime("%Y-%m-%d")
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
    alertas = alertar_dispersoes(operacao_id, sorted(g["mes"].unique()))
    return {"alertas": alertas, "lancamentos": len(d), "contas": d["conta"].nunique(), "deptos": d["depto"].nunique(),
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
    # justificativas da aba 📝 Justificar Dispersão (valem para o painel, os alertas e a reunião)
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    js = query_df(f"SELECT conta, depto, texto, status FROM obz_just WHERE {trecho} AND mes = ? "
                  "AND status <> 'reprovada'", (*p, mes))
    df["just_status"] = None
    if not js.empty:
        jm = {(c, d): (t, st) for c, d, t, st in zip(js["conta"], js["depto"], js["texto"], js["status"])}
        df["justificativa"] = [jm[(c, d)][0] if (c, d) in jm else j
                               for c, d, j in zip(df["conta"], df["depto"], df["justificativa"])]
        df["just_status"] = [jm.get((c, d), (None, None))[1] for c, d in zip(df["conta"], df["depto"])]
    return df.sort_values(["pacote", "conta", "depto"]).reset_index(drop=True)


def salvar_tend(operacao_id: int, mes: str, conta: str, depto: str, valor: float, usuario: dict,
                justificativa: str = "", plan: float = 0.0, sugerido: float | None = None) -> str:
    """Grava a tendência. Se a dispersão for crítica, exige justificativa e manda para aprovação."""
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda para lançar tendências.")
    if not pode_lancar(usuario, conta, depto):
        raise RegraNegocioError("Você não está cadastrado como dono, sub-dono ou lançador desta conta.")
    from services import obz_just_service

    aberta, motivo = obz_just_service.tend_aberta(operacao_id, mes)
    if not aberta:
        raise RegraNegocioError(f"Tendência de {nome_mes(mes)} fechada — {motivo}. Só o dono do financeiro reabre.")
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
    if disp > 0 and plan:
        alertar_dispersoes(operacao_id, [mes])
    return status


def _avisar_aprovadores(operacao_id, mes, conta, depto, disp, quem) -> None:
    try:
        from repositories import motoristas_repo

        for uid in usuarios_papel("aprovador"):
            motoristas_repo.criar_notificacao(uid, "obz", f"obz:{operacao_id}:{mes}:{conta}:{depto}:{agora()}",
                                              f"🎯 OBZ: justificativa para aprovar ({nome_mes(mes)})",
                                              f"Conta {conta} · depto {depto} · dispersão {_brl(disp)} — lançada "
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
    """Despesas líquidas do mês por departamento do OBZ (despesa − receita), só contas do OBZ (sem bonificação).
    Coluna "pacote" = departamento (mantém o nome para quem já usa). None = sem realizado."""
    rl = real_df(operacao_id, mes, mes)
    if rl.empty:
        return None
    ct = contas()
    obz_ok = set(ct.loc[ct["no_obz"].fillna(1).astype(int) == 1, "codigo"])
    nat = dict(zip(ct["codigo"], ct["natureza"]))
    mp = _mapas()

    def _agrupa(x):
        x = x[x["conta"].isin(obz_ok)].copy()
        if x.empty:
            return pd.Series(dtype=float)
        x["liq"] = [v if nat.get(c) != "receita" else -v for v, c in zip(x["valor"], x["conta"])]
        x["pacote"] = [area_de(c, d, mp) for c, d in zip(x["conta"], x["depto"])]
        return x.groupby("pacote")["liq"].sum()

    r_ = _agrupa(rl)
    pl = plan_df(operacao_id, mes, mes)
    p_ = _agrupa(pl) if not pl.empty else pd.Series(dtype=float)
    idx = sorted(set(r_.index) | set(p_.index))
    g = pd.DataFrame({"pacote": idx, "realizado": [float(r_.get(i, 0.0)) for i in idx],
                      "orcado": [float(p_.get(i, 0.0)) for i in idx]})
    return g.sort_values("realizado", ascending=False).reset_index(drop=True)


# --- Alertas de dispersão para os donos ---------------------------------------------------------------------
def _brl(v: float, casas: int = 2) -> str:
    return f"R$ {v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _uid_gestor() -> dict:
    g = query_df("SELECT id, usuario_id FROM gestores WHERE usuario_id IS NOT NULL")
    return {int(a): int(b) for a, b in zip(g["id"], g["usuario_id"])}


def alertar_dispersoes(operacao_id: int, meses_: list[str]) -> int:
    """Cada conta com real/tend acima do plan (dispersão crítica desfavorável) e sem justificativa vira alerta para o
    dono do departamento, o sub-dono da conta e o dono da conta — um aviso por pessoa e mês, com as contas.
    Sem dono cadastrado, avisa os aprovadores do financeiro. Devolve quantos avisos novos foram criados."""
    try:
        from repositories import motoristas_repo

        if operacoes_repo.e_consolidada(operacao_id):
            return 0
        atual = mes_atual()
        ug = _uid_gestor()
        ar = areas()
        dono_area = {n: ug.get(int(g)) for n, g in zip(ar["nome"], ar["dono_gestor_id"]) if pd.notna(g)}
        rp = query_df("SELECT area, conta, gestor_id FROM obz_resp")
        sub_conta = {(a, c): ug.get(int(g)) for a, c, g in zip(rp["area"], rp["conta"], rp["gestor_id"]) if pd.notna(g)}
        sd = subdonos()
        sub_old = {(c, d): int(u) for c, d, u in zip(sd["conta"], sd["depto"], sd["usuario_id"]) if pd.notna(u)}
        ct = contas()
        dono_conta = {c: int(u) for c, u in zip(ct["codigo"], ct["dono_id"]) if pd.notna(u)}
        aprov = usuarios_papel("aprovador")
        if not aprov:  # sem aprovador cadastrado: o Master recebe
            from config.settings import PERFIL_MASTER

            aprov = [int(x) for x in query_df("SELECT id FROM usuarios WHERE perfil = ? AND ativo = 1",
                                              (PERFIL_MASTER,))["id"]]
        mp = _mapas()
        novos = 0
        for mes in meses_:
            if mes > atual:
                continue
            b = base(operacao_id, mes)
            if b.empty:
                continue
            b = b[b["critica"] & (b["desfavoravel"] > 0) & b["justificativa"].isna()]
            por_uid: dict[int, list] = {}
            for r in b.itertuples(index=False):
                area = area_de(r.conta, r.depto, mp)
                uids = {u for u in (dono_area.get(area), sub_conta.get((area, r.conta)), sub_old.get((r.conta, r.depto)),
                                    dono_conta.get(r.conta)) if u} or set(aprov)
                for u in uids:
                    por_uid.setdefault(u, []).append((r.conta, r.nome_conta, area, float(r.disp)))
            for uid, itens in por_uid.items():
                total = sum(x[3] for x in itens)
                chave = f"obz-disp:{operacao_id}:{mes}:{len(itens)}:{round(total)}"
                if motoristas_repo.ultima_notificacao(uid, chave):
                    continue
                itens.sort(key=lambda x: -x[3])
                lista = "; ".join(f"{c} {str(n or '')[:28]} ({a}) +{_brl(v, 0)}" for c, n, a, v in itens[:5])
                fonte = "realizado" if fechado(mes) else "tendência"
                motoristas_repo.criar_notificacao(
                    uid, "obz", chave, f"⚠️ OBZ {nome_mes(mes)}: {len(itens)} conta(s) acima do plan — justificar",
                    f"O {fonte} passou do plan em {_brl(total)}. {lista}"
                    + (" …" if len(itens) > 5 else "") + " Abra Financeiro › 📝 Justificar Dispersão e clique no ✏️.",
                    "financeiro", agora() + ":00")
                novos += 1
        return novos
    except Exception:
        return 0


# --- Base OBZ (planilha com uma aba por departamento) ---------------------------------------------------------
_MESES_NOME = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
               "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
_IGNORAR_ABAS = {"16.03.01", "simulador", "base", "resumo"}


def _vbz(t) -> str:
    t = str(t or "").strip()
    return {"gente": "Pessoal"}.get(t.lower(), t[:1].upper() + t[1:].lower()) if t else "Gerais"


_MES_ABREV = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10,
              "nov": 11, "dez": 12}


def _cod_num(v) -> str:
    """Código que pode vir como 501, 501.0 ou '501' (o _cod tiraria só o ponto e viraria 5010)."""
    try:
        return str(int(float(str(v).replace(",", "."))))
    except (TypeError, ValueError):
        return _cod(v)


def _mes_de(t) -> int | None:
    t = _n(t).replace("ç", "c")
    if not t:
        return None
    if t in _MESES_NOME:
        return _MESES_NOME[t]
    return _MES_ABREV.get(t[:3]) if t[:3] in _MES_ABREV and (len(t) <= 4 or t in _MESES_NOME) else None


def _ler_consolidado(xl: "pd.ExcelFile") -> tuple[list[dict], str | None, str]:
    """Layout com uma aba CONSOLIDADA: UNIDADE · DEP · DONO · DPT · DESCRIÇÃO CONTA · Nº CONTA · PLAN <mês> / Real
    <mês> (ou mês em cima e Plano/Real/R-P embaixo). Usa a aba com mais linhas/departamentos como base e só
    acrescenta departamento que ela não tem (ex.: Puxada numa aba à parte) — sem somar em dobro.
    Devolve (linhas, unidade, nome da aba base)."""
    abas = []
    for aba in xl.sheet_names:
        if _n(aba).strip() in _IGNORAR_ABAS:
            continue
        df = xl.parse(aba, header=None)
        if len(df) < 2:
            continue
        hr = None
        for i in range(min(4, len(df))):
            cab = [_n(x) for x in df.iloc[i].tolist()]
            if "dono" in cab and any(c.startswith("n") and "conta" in c for c in cab):
                hr = i
                break
        if hr is None:
            continue
        cab = [_n(x) for x in df.iloc[hr].tolist()]
        topo = [_n(x) for x in df.iloc[hr - 1].tolist()] if hr > 0 else [""] * len(cab)
        col = lambda nome: cab.index(nome) if nome in cab else None  # noqa: E731
        c_conta = next(j for j, c in enumerate(cab) if c.startswith("n") and "conta" in c)
        c_dep, c_dpt, c_dono, c_uni = col("dep"), col("dpt"), col("dono"), col("unidade")
        c_nome = next((j for j, c in enumerate(cab) if "descricao" in c), None)
        if c_dep is None:  # sem o código do departamento não dá para ligar ao 16.03.01
            continue
        plan, real, mes_topo = {}, {}, None
        for j, h in enumerate(cab):
            if _mes_de(topo[j]):
                mes_topo = _mes_de(topo[j])
            m = re.match(r"^(plan[o]?|real)\s+([a-z]+)", h)
            if m and _mes_de(m.group(2)):
                (plan if m.group(1).startswith("plan") else real).setdefault(_mes_de(m.group(2)), j)
            elif h == "plano" and mes_topo:
                plan.setdefault(mes_topo, j)
            elif h == "real" and mes_topo:
                real.setdefault(mes_topo, j)
        if not plan:
            continue
        area_aba = re.sub(r"^obz[_ ]?\d{4}[_ ]*", "", str(aba).strip(), flags=re.I).strip() or str(aba).strip()
        itens, unidade = [], None
        for _, r in df.iloc[hr + 1:].iterrows():
            conta = pd.to_numeric(r[c_conta], errors="coerce")
            dep = pd.to_numeric(r[c_dep], errors="coerce")
            if pd.isna(conta) or pd.isna(dep):
                continue
            dpt = str(r[c_dpt]).strip() if c_dpt is not None and pd.notna(r[c_dpt]) else ""
            area = dpt if dpt and not re.fullmatch(r"[\d.,]+", dpt) else area_aba
            if c_uni is not None and pd.notna(r[c_uni]) and not unidade:
                unidade = str(r[c_uni]).strip()
            itens.append({"area": area, "vbz": _vbz(r[c_dono] if c_dono is not None else ""),
                          "depto": _cod_num(dep), "nome": str(r[c_nome] if c_nome is not None else "").strip(),
                          "conta": _cod_num(conta),
                          "plan": {m: pd.to_numeric(r[j], errors="coerce") for m, j in plan.items()},
                          "real": {m: pd.to_numeric(r[j], errors="coerce") for m, j in real.items()}})
        if itens:
            abas.append((aba, itens, unidade, len({i["area"] for i in itens})))
    if not abas:
        return [], None, ""
    base = max(abas, key=lambda a: (a[3], len(a[1])))  # a consolidada: mais departamentos e mais linhas
    linhas = list(base[1])
    vistos = {(i["depto"], i["conta"]) for i in linhas}
    areas_base = {_n(i["area"]) for i in linhas}
    for aba, itens, _u, _n_areas in abas:
        if aba == base[0]:
            continue
        for it in itens:  # só departamento que a consolidada não tem (ex.: Puxada numa aba à parte)
            k = (it["depto"], it["conta"])
            if k not in vistos and _n(it["area"]) not in areas_base:
                vistos.add(k)
                linhas.append({**it, "_aba": str(aba)})
    unidade = base[2] or next((a[2] for a in abas if a[2]), None)
    return linhas, unidade, str(base[0])


def _operacao_da_unidade(unidade: str | None) -> int | None:
    """'LIMA BARREIRAS' / 'LIMA SÃO FELIX' → id da revenda com o mesmo nome (sem acento e maiúscula)."""
    if not unidade:
        return None
    alvo = re.sub(r"[^a-z0-9]+", " ", _n(unidade)).strip()
    for o in operacoes_repo.listar():
        if operacoes_repo.e_consolidada(o["id"]):
            continue
        if re.sub(r"[^a-z0-9]+", " ", _n(o["nome"])).strip() == alvo:
            return int(o["id"])
    return None


def _area_existente(nome: str) -> str:
    """Reaproveita o departamento já cadastrado com o mesmo nome (sem acento/maiúscula): ARMAZÉM = Armazém."""
    alvo = _n(nome)
    for a in areas()["nome"].tolist():
        if _n(a) == alvo:
            return a
    return nome


def importar_base(conteudo: bytes, nome: str, operacao_id: int, ano: str, usuario: str = "",
                  importar_real_aba: bool = True) -> dict:
    """Base OBZ: cada aba é um departamento (colunas: DONO/VBZ, DPT, Nome da conta, Conta, e por mês Plano/Real/R-P).
    A aba "Folha" é distribuída nos departamentos pelo código do DPT (coluna B). A aba "16.03.01" (razão do ano)
    vira o realizado. Grava departamentos, contas, mapa conta × depto → departamento e o plan de todos os meses."""
    try:
        xl = pd.ExcelFile(io.BytesIO(conteudo))
    except Exception as e:
        raise RegraNegocioError(f"Não consegui abrir a planilha: {e}") from e
    linhas, folha = [], []
    for aba in xl.sheet_names:
        if _n(aba).strip() in _IGNORAR_ABAS:
            continue
        df = xl.parse(aba, header=None)
        if len(df) < 3 or len(df.columns) < 5:
            continue
        cab = [_n(x) for x in df.iloc[1].tolist()]
        if "conta" not in cab or "dpt" not in cab:
            continue
        meses_col = {}
        for j, v in enumerate(df.iloc[0].tolist()):
            m = _MESES_NOME.get(_n(v).replace("ç", "c"))
            if m:
                meses_col[m] = j  # coluna do "Plano" daquele mês
        corpo = df.iloc[2:]
        for _, r in corpo.iterrows():
            conta = _cod(r[cab.index("conta")])
            if conta == "0":
                continue
            item = {"area": str(aba).strip(), "vbz": _vbz(r[0]), "depto": _cod(r[1]),
                    "nome": str(r[2] or "").strip(), "conta": conta,
                    "plan": {m: pd.to_numeric(r[j], errors="coerce") for m, j in meses_col.items()},
                    "real": {m: pd.to_numeric(r[j + 1], errors="coerce") for m, j in meses_col.items()
                             if j + 1 < len(r)}}
            (folha if _n(aba) == "folha" else linhas).append(item)
    layout, aba_base, revenda_arquivo = "abas por departamento", None, None
    if not linhas and not folha:  # 2º layout: aba consolidada (UNIDADE, DEP, DONO, DPT, Nº CONTA, PLAN/Real por mês)
        linhas, unidade, aba_base = _ler_consolidado(xl)
        if linhas:
            layout = f"consolidado (aba {aba_base})"
            op_arq = _operacao_da_unidade(unidade)
            if op_arq and op_arq != operacao_id:
                operacao_id = op_arq  # o arquivo diz de qual revenda é (coluna UNIDADE)
            if op_arq:
                revenda_arquivo = (operacoes_repo.buscar(op_arq) or {}).get("nome")
            for it in linhas:
                it["area"] = _area_existente(it["area"])
    if not linhas and not folha:
        raise RegraNegocioError("Não achei as abas de departamento (cabeçalho DONO, DPT, Nome da Conta, Conta) nem a "
                                "aba consolidada (UNIDADE, DEP, DONO, DPT, Nº CONTA, PLAN por mês).")
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para subir a Base OBZ.")
    # código do depto → departamento (o mais comum entre as abas)
    cont: dict[str, dict[str, int]] = {}
    for it in linhas:
        cont.setdefault(it["depto"], {}).setdefault(it["area"], 0)
        cont[it["depto"]][it["area"]] += 1
    por_depto = {d: max(a.items(), key=lambda x: x[1])[0] for d, a in cont.items()}
    for it in folha:
        it["area"] = por_depto.get(it["depto"], "Folha")
    todos = linhas + folha
    ordem = {}
    for it in linhas:
        ordem.setdefault(it["area"], len(ordem))
    for a in {it["area"] for it in todos}:
        atual = query_one("SELECT nome FROM obz_areas WHERE nome = ?", (a,))
        if not atual:
            salvar_area(a, None, ordem.get(a, 99))
    for d, a in por_depto.items():
        execute("""INSERT INTO obz_departamentos (codigo, nome, ativo, area) VALUES (?, ?, 1, ?)
                   ON CONFLICT(codigo) DO UPDATE SET area = excluded.area,
                   nome = CASE WHEN obz_departamentos.nome IS NULL OR obz_departamentos.nome = ''
                               THEN excluded.nome ELSE obz_departamentos.nome END""", (d, a, a))
    cad = set(contas()["codigo"])
    for it in todos:
        bonif = e_bonificacao(it["nome"])
        if it["conta"] not in cad:
            salvar_conta(it["conta"], it["nome"], pacote="Bonificações" if bonif else it["vbz"], no_obz=not bonif)
            cad.add(it["conta"])
        elif not bonif:
            execute("""UPDATE obz_contas SET no_obz = 1 WHERE codigo = ?
                       AND LOWER(COALESCE(nome, '')) NOT LIKE '%bonif%'
                       AND LOWER(COALESCE(nome, '')) NOT LIKE '%amostra%'""", (it["conta"],))
    with get_conn() as conn:
        for it in todos:
            conn.execute("""INSERT INTO obz_mapa (conta, depto, area, vbz) VALUES (?, ?, ?, ?)
                            ON CONFLICT(conta, depto) DO UPDATE SET area = excluded.area, vbz = excluded.vbz""",
                         (it["conta"], it["depto"], it["area"], it["vbz"]))
    plan = {}
    for it in todos:
        for m, v in it["plan"].items():
            if pd.notna(v) and float(v) != 0:
                k = (f"{ano}-{m:02d}", it["conta"], it["depto"])
                plan[k] = plan.get(k, 0.0) + float(v)
    with get_conn() as conn:
        meses_plan = sorted({k[0] for k in plan})
        for mes in meses_plan:
            conn.execute("DELETE FROM obz_plan WHERE operacao_id = ? AND mes = ?", (operacao_id, mes))
        conn.executemany("INSERT INTO obz_plan (operacao_id, mes, conta, depto, valor) VALUES (?, ?, ?, ?, ?)",
                         [(operacao_id, *k, v) for k, v in plan.items()])
    res = {"departamentos": len({it["area"] for it in todos}), "contas": len({it["conta"] for it in todos}),
           "linhas": len(todos), "folha": len(folha), "meses_plan": meses_plan, "plan": sum(plan.values()),
           "real": None, "layout": layout, "operacao_id": operacao_id, "revenda": revenda_arquivo,
           "abas_extra": sorted({it["_aba"] for it in todos if it.get("_aba")})}
    if importar_real_aba and "16.03.01" in xl.sheet_names:
        rz = xl.parse("16.03.01")
        c = list(rz.columns)
        if len(c) >= 9:
            d = pd.DataFrame({"conta": rz[c[0]].map(_cod), "nome": rz[c[1]].astype(str).str.strip(),
                              "data": pd.to_datetime(rz[c[2]], errors="coerce", dayfirst=True),
                              "historico": rz[c[3]].astype(str).str.strip(), "depto": rz[c[5]].map(_cod),
                              "debito": pd.to_numeric(rz[c[7]], errors="coerce").fillna(0.0),
                              "credito": pd.to_numeric(rz[c[8]], errors="coerce").fillna(0.0)})
            res["real"] = _gravar_real(operacao_id, d, f"{nome} (aba 16.03.01)", usuario)
    # realizado dos meses que não têm 16.03.01 carregado: vem da coluna "Real" das abas (histórico)
    # o real histórico das abas (lancamentos = 0) da subida anterior sai: subir de novo SUBSTITUI, não soma
    execute("DELETE FROM obz_real WHERE operacao_id = ? AND mes LIKE ? AND COALESCE(lancamentos, 0) = 0",
            (operacao_id, f"{ano}-%"))
    com_razao = set(query_df("SELECT DISTINCT mes FROM obz_real WHERE operacao_id = ?", (operacao_id,))["mes"])
    hist = {}
    limite_hist = tempo.hoje().strftime("%Y-%m") if aba_base else "9999-99"  # consolidado: só meses fechados
    for it in todos:
        for m, v in it["real"].items():
            mes = f"{ano}-{m:02d}"
            if mes not in com_razao and mes < limite_hist and pd.notna(v) and float(v) != 0:
                k = (mes, it["conta"], it["depto"])
                hist[k] = hist.get(k, 0.0) + float(v)
    if hist:
        agora_ = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.executemany("""INSERT INTO obz_real (operacao_id, mes, conta, depto, debito, credito, valor,
                                                      lancamentos, importado_em) VALUES (?, ?, ?, ?, ?, 0, ?, 0, ?)""",
                             [(operacao_id, *k, v, v, agora_) for k, v in hist.items()])
    res["meses_historico"] = sorted({k[0] for k in hist})
    from services.produtividade_entrega_service import _log

    _log(operacao_id, "obz_base", len(todos), nome, usuario)
    res["alertas"] = alertar_dispersoes(operacao_id, sorted(set(meses_plan) | set(res["meses_historico"])
                                                            | set((res["real"] or {}).get("meses", []))))
    return res


def zerar_base(operacao_id: int, usuario: dict, ano: str | None = None) -> dict:
    """🧹 Apaga o plan e o realizado (razão 16.03.01 e real das abas) de UMA revenda — para subir a Base OBZ do zero.
    Não mexe em departamentos, contas e donos (são de todas as revendas) nem no que foi lançado à mão
    (justificativas, tendências, ações, CAPEX, simulador). Só o Master."""
    from core.auth import e_master

    if not e_master(usuario):
        raise RegraNegocioError("Só o Master pode zerar a Base OBZ.")
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada).")
    filtro, p = ("AND mes LIKE ?", (f"{ano}-%",)) if ano else ("", ())
    out = {}
    with get_conn() as conn:
        for t in ("obz_plan", "obz_real", "obz_real_lanc"):
            n = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE operacao_id = ? {filtro}",
                             (int(operacao_id), *p)).fetchone()[0]
            conn.execute(f"DELETE FROM {t} WHERE operacao_id = ? {filtro}", (int(operacao_id), *p))
            out[t] = int(n)
    try:
        from services.produtividade_entrega_service import _log

        _log(operacao_id, "obz_zerar", sum(out.values()), f"zerou {ano or 'tudo'}", usuario.get("nome", ""))
    except Exception:  # noqa: BLE001
        pass
    return out


def salvar_plan_valor(operacao_id: int, mes: str, conta: str, depto: str, valor: float, usuario: dict) -> None:
    if not pode_plan(usuario):
        raise RegraNegocioError("Só quem o Master liberou pode alterar o Plan.")
    execute("""INSERT INTO obz_plan (operacao_id, mes, conta, depto, valor) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(operacao_id, mes, conta, depto) DO UPDATE SET valor = excluded.valor""",
            (operacao_id, mes, str(conta), str(depto), float(valor or 0)))


# --- Painel (mês ou período) -------------------------------------------------------------------------------------
def enriquecer(b: pd.DataFrame) -> pd.DataFrame:
    """Departamento (área), VBZ, dono do departamento e sub-dono da conta."""
    if b.empty:
        return b
    mp = _mapas()
    b = b.copy()
    b["area"] = [area_de(c, d, mp) for c, d in zip(b["conta"], b["depto"])]
    b["vbz"] = [mp[2].get((c, d)) or p for c, d, p in zip(b["conta"], b["depto"], b["pacote"])]
    ar = areas().set_index("nome")
    b["dono_area"] = b["area"].map(ar["dono"]) if not ar.empty else None
    rp = resp_df()
    rpi = rp.set_index(["area", "conta"])["subdono"] if not rp.empty else pd.Series(dtype=object)
    b["subdono_conta"] = [rpi.get((a, c)) for a, c in zip(b["area"], b["conta"])]
    b["responsavel"] = b["subdono_conta"].fillna(b["dono_area"]).fillna("Sem dono")
    return b


def painel(operacao_id: int, meses_: list[str]) -> pd.DataFrame:
    """Soma conta × depto nos meses (fechamento = real nos fechados, tend no aberto) já com área/VBZ/donos."""
    partes = [base(operacao_id, m).assign(mes=m) for m in meses_]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame()
    b = pd.concat(partes, ignore_index=True)
    num = ["plan", "real", "tend", "fechamento", "disp", "desfavoravel"]
    info = b.drop_duplicates(["conta", "depto"], keep="last").set_index(["conta", "depto"])
    g = b.groupby(["conta", "depto"], as_index=False)[num].sum()
    for c in ("nome_conta", "pacote", "natureza", "limite", "nome_depto", "status", "justificativa"):
        g[c] = [info.at[(a, d), c] if (a, d) in info.index else None for a, d in zip(g["conta"], g["depto"])]
    g["disp_pct"] = g["disp"] / g["plan"].where(g["plan"] != 0) * 100
    g["critica"] = (g["disp_pct"].abs() >= g["limite"].astype(float)) | ((g["plan"] == 0) & (g["fechamento"] != 0))
    return enriquecer(g)


def serie_mensal(operacao_id: int, ano: str) -> pd.DataFrame:
    """Plan × real × fechamento por mês e departamento (para os gráficos)."""
    mp = _mapas()
    pl = plan_df(operacao_id, f"{ano}-01", f"{ano}-12")
    rl = real_df(operacao_id, f"{ano}-01", f"{ano}-12")
    ct = contas()
    obz_ok = set(ct.loc[ct["no_obz"].astype(int) == 1, "codigo"])
    out = []
    for nome, x in (("plan", pl), ("real", rl)):
        if x.empty:
            continue
        x = x[x["conta"].isin(obz_ok)].copy()
        x["area"] = [area_de(c, d, mp) for c, d in zip(x["conta"], x["depto"])]
        out.append(x.groupby(["mes", "area"], as_index=False)["valor"].sum().assign(tipo=nome))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["mes", "area", "valor", "tipo"])


# --- R$/HL por departamento -------------------------------------------------------------------------------------
def hl_mensal(operacao_id: int, ano: str) -> dict:
    """HL vendido por mês (operações de HL de venda: venda + bonificação)."""
    from services import faturamento_service as fs

    dv = fs.dia_df(operacao_id, "venda", f"{ano}-01-01", f"{ano}-12-31", fs.STATUS_PADRAO["venda"])
    if dv.empty:
        return {}
    dv = dv[dv["operacao_cod"].astype(str).isin(fs.operacoes_do_setor("hl_venda"))]
    return dv.assign(mes=dv["data"].str[:7]).groupby("mes")["hl"].sum().to_dict()


def gastos_ano(operacao_id: int, ano: str) -> pd.DataFrame:
    """Despesa líquida (despesa − receita) do OBZ por mês × conta × depto, com departamento: real e plan."""
    ct = contas()
    obz_ok = set(ct.loc[ct["no_obz"].fillna(1).astype(int) == 1, "codigo"])
    nat = dict(zip(ct["codigo"], ct["natureza"]))
    nome = dict(zip(ct["codigo"], ct["nome"]))
    mp = _mapas()
    partes = []
    for tipo, x in (("real", real_df(operacao_id, f"{ano}-01", f"{ano}-12")),
                    ("plan", plan_df(operacao_id, f"{ano}-01", f"{ano}-12"))):
        if x.empty:
            continue
        x = x[x["conta"].isin(obz_ok)]
        g = x.groupby(["mes", "conta", "depto"], as_index=False)["valor"].sum()
        g["valor"] = [v if nat.get(c) != "receita" else -v for v, c in zip(g["valor"], g["conta"])]
        partes.append(g.rename(columns={"valor": tipo}))
    if not partes:
        return pd.DataFrame(columns=["mes", "conta", "depto", "area", "nome_conta", "real", "plan"])
    df = partes[0]
    for p in partes[1:]:
        df = df.merge(p, on=["mes", "conta", "depto"], how="outer")
    for c in ("real", "plan"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0) if c in df else 0.0
    df["area"] = [area_de(c, d, mp) for c, d in zip(df["conta"], df["depto"])]
    df["nome_conta"] = df["conta"].map(nome)
    return df
