"""Regras da Frota: cadastro de placas (revenda, proprietário, aluguel/locadora, área, motorista) e a gestão."""
import datetime as dt
import re

import pandas as pd

from config.settings import CATEGORIAS_CNH, MODULOS, STATUS_PLACA, TIPOS_VEICULO
from core import tempo
from repositories import frota_repo as repo
from repositories import operacoes_repo
from services.erros import RegraNegocioError

# Áreas = os departamentos do sistema (onde a placa trabalha) + Comercial/Administrativo
AREAS = [m["rotulo"] for k, m in MODULOS.items() if k not in ("relatorios",)] + ["Comercial", "Administrativo"]
_PLACA = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")


def revendas(ids_permitidos: list[int] | None = None) -> dict[int, str]:
    """Só as três revendas (as visões consolidadas não recebem placa)."""
    ops = [o for o in operacoes_repo.listar(apenas_ativas=True) if not operacoes_repo.e_consolidada(o["id"])]
    return {o["id"]: o["nome"] for o in ops if not ids_permitidos or o["id"] in ids_permitidos}


def normalizar_placa(txt: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(txt or "").upper())


def salvar_placa(pid: int | None, d: dict, usuario: str) -> int:
    placa = normalizar_placa(d.get("placa"))
    if not _PLACA.match(placa):
        raise RegraNegocioError("Placa inválida. Use o padrão ABC1D23 ou ABC1234.")
    outra = repo.placa_por_texto(placa)
    if outra and outra["id"] != pid:
        raise RegraNegocioError(f"A placa {placa} já está cadastrada.")
    if not d.get("operacao_id"):
        raise RegraNegocioError("Escolha a revenda.")
    if d.get("tipo") not in TIPOS_VEICULO:
        raise RegraNegocioError("Escolha o tipo de veículo.")
    aluguel = 1 if d.get("aluguel") in (1, True, "1", "Sim") else 0
    locadora = d.get("locadora_id") if aluguel else None
    if aluguel and not locadora:
        raise RegraNegocioError("Placa alugada: escolha a locadora.")
    if d.get("area") and d["area"] not in AREAS:
        raise RegraNegocioError("Área inválida.")
    ano = d.get("ano")
    try:
        ano = int(float(ano)) if ano not in (None, "") else None
    except (TypeError, ValueError):
        raise RegraNegocioError("Ano inválido.")
    if ano and not 1980 <= ano <= tempo.hoje().year + 1:
        raise RegraNegocioError("Ano fora do intervalo.")
    dados = {"placa": placa, "operacao_id": int(d["operacao_id"]), "tipo": d.get("tipo"),
             "marca_modelo": (d.get("marca_modelo") or "").strip() or None, "ano": ano,
             "proprietario_id": int(d["proprietario_id"]) if d.get("proprietario_id") else None,
             "aluguel": aluguel, "locadora_id": int(locadora) if locadora else None, "area": d.get("area") or None,
             "motorista_id": int(d["motorista_id"]) if d.get("motorista_id") else None,
             "status": d.get("status") if d.get("status") in STATUS_PLACA else "Ativo",
             "observacao": (d.get("observacao") or "").strip() or None}
    return repo.salvar_placa(pid, dados, usuario)


def salvar_empresa(tipo: str, eid: int | None, d: dict) -> int:
    nome = re.sub(r"\s+", " ", str(d.get("nome") or "").strip())
    if len(nome) < 2:
        raise RegraNegocioError("Informe o nome.")
    cnpj = re.sub(r"\D", "", str(d.get("cnpj") or ""))
    if cnpj and len(cnpj) != 14:
        raise RegraNegocioError("CNPJ precisa ter 14 números.")
    args = (eid, nome, cnpj or None, (d.get("contato") or "").strip() or None, (d.get("telefone") or "").strip() or None)
    try:
        return repo.salvar_locadora(*args) if tipo == "locadora" else repo.salvar_transportadora(*args)
    except Exception as e:  # nome repetido (UNIQUE)
        if "unique" in str(e).lower() or "duplic" in str(e).lower():
            raise RegraNegocioError(f"Já existe uma {tipo} com o nome {nome}.")
        raise


def excluir_transportadora(tid: int) -> None:
    if repo.transportadora_em_uso(tid):
        raise RegraNegocioError("Esta transportadora está em uso (placas, fretes ou trechos) — não pode ser excluída.")
    repo.excluir_transportadora(tid)


def salvar_motorista(eid: int | None, d: dict) -> int:
    from services import motoristas_service

    op = d.get("operacao_id")
    if not op:
        raise RegraNegocioError("Escolha a revenda do motorista.")
    cat = d.get("categoria_cnh") or None
    if cat and cat not in CATEGORIAS_CNH:
        raise RegraNegocioError("Categoria de CNH inválida.")
    atual_sal = None
    if eid:
        from database.connection import query_one

        r = query_one("SELECT salario_fixo FROM motoristas WHERE id = ?", (eid,))
        atual_sal = r["salario_fixo"] if r else None
        from database.connection import execute

        execute("UPDATE motoristas SET operacao_id = ? WHERE id = ?", (int(op), eid))
    mid = motoristas_service.salvar_motorista(int(op), eid, d.get("nome"), d.get("cpf") or "", d.get("telefone") or "",
                                              d.get("cnh") or "", d.get("cnh_validade"), d.get("gestor_id"),
                                              atual_sal or 0.0)
    repo.salvar_categoria_cnh(mid, cat)
    return mid


# --- Gestão -----------------------------------------------------------------------------------
def _cnh_dias(v) -> int | None:
    try:
        return (dt.date.fromisoformat(str(v)[:10]) - tempo.hoje()).days
    except (TypeError, ValueError):
        return None


def resumo(placas: pd.DataFrame) -> dict:
    if placas is None or placas.empty:
        return {"total": 0, "ativas": 0, "manut": 0, "alugadas": 0, "proprias": 0, "sem_motorista": 0, "cnh": 0}
    ativ = placas["status"].fillna("Ativo")
    alug = pd.to_numeric(placas["aluguel"], errors="coerce").fillna(0) == 1
    cnh = placas["motorista_cnh_validade"].map(_cnh_dias)
    return {"total": len(placas), "ativas": int((ativ == "Ativo").sum()),
            "manut": int((ativ == "Em manutenção").sum()), "alugadas": int(alug.sum()),
            "proprias": int((~alug).sum()),
            "sem_motorista": int(placas["motorista_id"].isna().sum()),
            "cnh": int(sum(1 for d in cnh if d is not None and d <= 30))}


def tabela(placas: pd.DataFrame) -> pd.DataFrame:
    if placas is None or placas.empty:
        return pd.DataFrame()
    def t(v):
        return "" if v is None or (isinstance(v, float) and v != v) else str(v)
    return pd.DataFrame({
        "Placa": placas["placa"], "Revenda": placas["revenda"].map(t), "Tipo": placas["tipo"].map(t),
        "Marca/modelo": placas["marca_modelo"].map(t),
        "Ano": [int(a) if a == a and a is not None else None for a in placas["ano"]],
        "Proprietário": placas["proprietario"].map(t),
        "Aluguel": ["Sim" if (a == a and a and int(a) == 1) else "Não" for a in placas["aluguel"]],
        "Locadora": placas["locadora"].map(t), "Área": placas["area"].map(t),
        "Motorista": placas["motorista"].map(t) if "motorista" in placas else "",
        "Status": placas["status"].map(t)})
