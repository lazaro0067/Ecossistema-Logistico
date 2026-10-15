"""🏗️ Gestão de Capex — orçamento de investimentos do próximo ano.

Cada projeto tem valor, mês de início, forma (à vista, financiado, leasing/locação), vida útil, custo operacional e
economia esperada. Os aprovados entram no Simulador OBZ como custo mensal da conta escolhida:
  à vista / financiado → depreciação (valor ÷ vida útil) + juros do financiamento (SAC) + opex − economia
  leasing / locação     → parcela (valor do contrato ÷ parcelas) + opex − economia
"""
import pandas as pd

from core import tempo
from database.connection import execute, get_conn, query_df, query_one
from repositories import operacoes_repo
from services.erros import RegraNegocioError

CATEGORIAS = ["🚚 Veículos e frota", "🏭 Máquinas e equipamentos", "💻 TI e sistemas", "🏢 Imóveis e obras",
              "🔌 Instalações e infraestrutura", "🛡️ Segurança e SSMA", "📦 Outros"]
TIPOS = ["Expansão", "Reposição", "Produtividade / melhoria", "Obrigatório / legal", "Estratégico"]
PRIORIDADES = ["🔴 Alta", "🟡 Média", "🟢 Baixa"]
FORMAS = {"avista": "💵 Compra à vista", "financiado": "🏦 Financiado", "leasing": "📄 Leasing / locação"}
STATUS = {"proposto": "📝 Proposto", "aprovado": "✔️ Aprovado", "reprovado": "❌ Reprovado",
          "em_execucao": "🔧 Em execução", "concluido": "✅ Concluído"}
ENTRA_NO_ORCAMENTO = ("aprovado", "em_execucao", "concluido")
_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def agora() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M")


def pode_aprovar(u: dict) -> bool:
    from core.auth import e_master
    from services import obz_service as obz

    ok = set(obz.usuarios_papel("fin_dono")) | set(obz.usuarios_papel("diretor")) | set(obz.usuarios_papel("ceo"))
    return e_master(u) or u.get("id") in ok


def listar(operacao_id: int, ano: str | None = None) -> pd.DataFrame:
    trecho, p = operacoes_repo.filtro("operacao_id", operacao_id)
    sql, params = f"SELECT * FROM obz_capex WHERE {trecho}", list(p)
    if ano:
        sql += " AND ano = ?"
        params.append(str(ano))
    df = query_df(sql + " ORDER BY id", params)
    for c in ("valor", "taxa_aa", "vida_util", "opex_mensal", "economia_mensal", "valor_realizado"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def buscar(cid: int) -> dict | None:
    r = query_one("SELECT * FROM obz_capex WHERE id = ?", (int(cid),))
    return dict(r) if r else None


def salvar(operacao_id: int, ano: str, dados: dict, usuario: dict, cid: int | None = None) -> int:
    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma revenda (não a visão consolidada) para cadastrar o capex.")
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise RegraNegocioError("Dê um nome ao projeto.")
    if float(dados.get("valor") or 0) <= 0:
        raise RegraNegocioError("Informe o valor do investimento.")
    if not dados.get("area"):
        raise RegraNegocioError("Escolha o departamento.")
    forma = dados.get("forma") if dados.get("forma") in FORMAS else "avista"
    campos = {"codigo": (dados.get("codigo") or "").strip() or None, "nome": nome, "area": dados.get("area"),
              "conta": dados.get("conta") or None, "conta_juros": dados.get("conta_juros") or None,
              "categoria": dados.get("categoria"), "tipo": dados.get("tipo"), "prioridade": dados.get("prioridade"),
              "justificativa": (dados.get("justificativa") or "").strip() or None, "valor": float(dados["valor"]),
              "mes_ini": min(max(int(dados.get("mes_ini") or 1), 1), 12), "forma": forma,
              "parcelas": max(int(dados.get("parcelas") or 1), 1), "taxa_aa": float(dados.get("taxa_aa") or 0),
              "vida_util": max(float(dados.get("vida_util") or 5), 0.5),
              "opex_mensal": float(dados.get("opex_mensal") or 0),
              "economia_mensal": float(dados.get("economia_mensal") or 0),
              "responsavel": (dados.get("responsavel") or "").strip() or None}
    quem = usuario.get("nome") or usuario.get("login")
    if cid:
        atual = buscar(cid)
        if atual and atual["status"] not in ("proposto", "reprovado") and not pode_aprovar(usuario):
            raise RegraNegocioError("Projeto já aprovado — só o financeiro / diretoria altera.")
        sets = ", ".join(f"{k} = ?" for k in campos)
        execute(f"UPDATE obz_capex SET {sets}, atualizado_por = ?, atualizado_em = ? WHERE id = ?",
                (*campos.values(), quem, agora(), int(cid)))
        _log(cid, None, usuario, "Projeto alterado")
        return int(cid)
    cols = ["operacao_id", "ano", *campos, "status", "criado_por", "criado_em"]
    novo = execute(f"INSERT INTO obz_capex ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   (operacao_id, str(ano), *campos.values(), "proposto", quem, agora()))
    _log(novo, "proposto", usuario, "Projeto cadastrado")
    return int(novo)


def _log(cid: int, status: str | None, usuario: dict, comentario: str = "") -> None:
    execute("INSERT INTO obz_capex_log (capex_id, status, usuario, em, comentario) VALUES (?, ?, ?, ?, ?)",
            (int(cid), status, usuario.get("nome") or usuario.get("login"), agora(), comentario or None))


def historico(cid: int) -> pd.DataFrame:
    return query_df("SELECT * FROM obz_capex_log WHERE capex_id = ? ORDER BY id DESC", (int(cid),))


def mudar_status(cid: int, status: str, usuario: dict, comentario: str = "", valor_realizado=None) -> None:
    if status not in STATUS:
        raise RegraNegocioError("Status inválido.")
    if status in ("aprovado", "reprovado") and not pode_aprovar(usuario):
        raise RegraNegocioError("Só o dono do financeiro, o diretor ou o CEO aprovam capex (papéis liberados pelo "
                                "Master).")
    if status == "reprovado" and not (comentario or "").strip():
        raise RegraNegocioError("Para reprovar, escreva o motivo.")
    execute("UPDATE obz_capex SET status = ?, comentario = ?, valor_realizado = COALESCE(?, valor_realizado), "
            "atualizado_por = ?, atualizado_em = ? WHERE id = ?",
            (status, (comentario or "").strip() or None,
             float(valor_realizado) if valor_realizado not in (None, "") else None,
             usuario.get("nome") or usuario.get("login"), agora(), int(cid)))
    _log(cid, status, usuario, comentario)


def excluir(cid: int, usuario: dict) -> None:
    p = buscar(cid)
    if p and p["status"] not in ("proposto", "reprovado") and not pode_aprovar(usuario):
        raise RegraNegocioError("Projeto aprovado — só o financeiro / diretoria exclui.")
    with get_conn() as conn:
        conn.execute("DELETE FROM obz_capex_log WHERE capex_id = ?", (int(cid),))
        conn.execute("DELETE FROM obz_capex WHERE id = ?", (int(cid),))


# --- Cálculos ------------------------------------------------------------------------------------------------------
def fluxo(p: dict) -> pd.DataFrame:
    """Mês a mês (1–12) do ano do orçamento: desembolso de caixa e impacto no resultado (OBZ)."""
    ini = int(p.get("mes_ini") or 1)
    valor = float(p.get("valor") or 0)
    forma = p.get("forma") or "avista"
    n = max(int(p.get("parcelas") or 1), 1)
    tx = float(p.get("taxa_aa") or 0) / 100 / 12
    vida = max(float(p.get("vida_util") or 5), 0.5) * 12
    opex, econ = float(p.get("opex_mensal") or 0), float(p.get("economia_mensal") or 0)
    linhas = []
    saldo = valor
    for m in range(1, 13):
        ativo = m >= ini
        k = m - ini  # parcela de ordem k (0 = primeira)
        desemb = deprec = juros = parcela = 0.0
        if ativo:
            if forma == "avista":
                desemb = valor if m == ini else 0.0
                deprec = valor / vida
            elif forma == "financiado":
                if k < n:
                    amort = valor / n
                    juros = saldo * tx
                    desemb = amort + juros
                    saldo -= amort
                deprec = valor / vida
            else:  # leasing / locação
                parcela = valor / n if k < n else 0.0
                desemb = parcela
        impacto = deprec + juros + parcela + (opex - econ if ativo else 0.0)
        linhas.append({"mes": m, "desembolso": desemb, "depreciacao": deprec, "juros": juros, "parcela": parcela,
                       "opex": opex if ativo else 0.0, "economia": econ if ativo else 0.0, "impacto": impacto})
    return pd.DataFrame(linhas)


def payback_meses(p: dict) -> float | None:
    ganho = float(p.get("economia_mensal") or 0) - float(p.get("opex_mensal") or 0)
    return float(p.get("valor") or 0) / ganho if ganho > 0 else None


def resumo(operacao_id: int, ano: str) -> pd.DataFrame:
    """Um projeto por linha com totais do ano (desembolso, impacto) e payback."""
    df = listar(operacao_id, ano)
    if df.empty:
        return df
    fl = [fluxo(r) for r in df.to_dict("records")]
    df["desembolso_ano"] = [float(f["desembolso"].sum()) for f in fl]
    df["impacto_ano"] = [float(f["impacto"].sum()) for f in fl]
    df["deprec_ano"] = [float(f["depreciacao"].sum()) for f in fl]
    df["juros_ano"] = [float(f["juros"].sum()) for f in fl]
    df["payback"] = [payback_meses(r) for r in df.to_dict("records")]
    return df


def total_aprovado(operacao_id: int, ano: str) -> float:
    df = listar(operacao_id, ano)
    return float(df.loc[df["status"].isin(ENTRA_NO_ORCAMENTO), "valor"].sum()) if not df.empty else 0.0


def impactos_orcamento(operacao_id: int, ano: str) -> list[tuple[str, str, str, float, str]]:
    """(area, conta, mes 'AAAA-MM', valor, projeto) dos projetos aprovados — entra no Simulador OBZ."""
    df = listar(operacao_id, ano)
    out = []
    if df.empty:
        return out
    for p in df[df["status"].isin(ENTRA_NO_ORCAMENTO)].to_dict("records"):
        if not p.get("conta"):
            continue
        f = fluxo(p)
        cj = p.get("conta_juros") or p["conta"]
        for r in f.itertuples(index=False):
            mes = f"{ano}-{int(r.mes):02d}"
            v = r.impacto - r.juros
            if abs(v) >= 0.005:
                out.append((p["area"], p["conta"], mes, v, p["nome"]))
            if abs(r.juros) >= 0.005:
                out.append((p["area"], cj, mes, r.juros, p["nome"]))
    return out
