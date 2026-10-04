"""Situação de atualização das bases importadas (está em dia ou vencida?)."""
from core import tempo
from database.connection import query_one
from services.importacao_service import LAYOUTS

# base -> (tabela, filtra por operação?) para achar dados migrados sem histórico
_ORIGEM = {
    "produtos": ("produtos", False), "estoque": ("estoque", True), "linear": ("linear_vendas", True),
    "metas_doi": ("metas_doi", True), "pedidos_marcados": ("pedidos_marcados", True),
    "ressuprimento": ("ressuprimento_diario", True), "curva_abc": ("curva_abc", True),
}


def situacao(base: str, operacao_id: int) -> dict:
    """Devolve {dt, linhas, usuario, idade_dias, status, rotulo}."""
    layout = LAYOUTS[base]
    por_op = layout["por_operacao"]
    log = query_one(
        "SELECT dt, linhas, usuario FROM bases_log WHERE base = ?" + (" AND operacao_id = ?" if por_op else "")
        + " ORDER BY dt DESC LIMIT 1",
        (base, operacao_id) if por_op else (base,),
    )
    tabela, filtra = _ORIGEM[base]
    where = " WHERE operacao_id = ?" if filtra else ""
    params = (operacao_id,) if filtra else ()
    total = int(query_one(f"SELECT COUNT(*) AS n FROM {tabela}{where}", params)["n"])

    dt_ult = tempo.parse_dt(log["dt"]) if log else None
    if dt_ult is None and total and tabela not in ("produtos", "metas_doi"):
        r = query_one(f"SELECT MAX(dt_atualizacao) AS d FROM {tabela}{where}", params)
        dt_ult = tempo.parse_dt(r["d"]) if r else None

    freq = layout.get("frequencia_dias", 30)
    if not total:
        status, rotulo, idade = "critico", "Nunca importado", None
    elif dt_ult is None:
        status, rotulo, idade = "neutro", "Carregado (sem data)", None
    else:
        idade = (tempo.agora() - dt_ult).total_seconds() / 86400
        if idade <= freq:
            status, rotulo = "bom", "Em dia"
        elif idade <= freq * 2:
            status, rotulo = "atencao", "Atualizar"
        else:
            status, rotulo = "critico", "Desatualizado"
    return {"dt": dt_ult, "linhas": total, "usuario": (log or {}).get("usuario"),
            "idade_dias": idade, "status": status, "rotulo": rotulo}


def idade_txt(idade_dias: float | None) -> str:
    if idade_dias is None:
        return "—"
    horas = idade_dias * 24
    if horas < 1:
        return "agora há pouco"
    if horas < 24:
        return f"há {int(horas)} h"
    return f"há {int(idade_dias)} dia(s)"
