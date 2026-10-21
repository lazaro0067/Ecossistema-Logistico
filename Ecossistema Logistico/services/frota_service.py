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
    if d.get("tipo") not in tipos():
        raise RegraNegocioError("Escolha o tipo de veículo (cadastre em 🏷️ Modelos & Tipos).")
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
    try:
        peso = float(str(d.get("peso_kg")).replace(",", ".")) if d.get("peso_kg") not in (None, "") else None
    except ValueError:
        raise RegraNegocioError("Capacidade de peso inválida.")
    peso = peso if peso is not None and peso == peso and peso > 0 else None
    dados = {"placa": placa, "operacao_id": int(d["operacao_id"]), "tipo": d.get("tipo"), "peso_kg": peso,
             "marca_modelo": (d.get("marca_modelo") or "").strip() or None, "ano": ano,
             "proprietario_id": int(d["proprietario_id"]) if d.get("proprietario_id") else None,
             "aluguel": aluguel, "locadora_id": int(locadora) if locadora else None, "area": d.get("area") or None,
             "motorista_id": int(d["motorista_id"]) if d.get("motorista_id") else None,
             "status": d.get("status") if d.get("status") in STATUS_PLACA else "Ativo",
             "observacao": (d.get("observacao") or "").strip() or None}
    return repo.salvar_placa(pid, dados, usuario)


# --- 🏷️ modelos e tipos de veículo --------------------------------------------------------------------------------
def _limpo(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip())


def _garantir_cadastros() -> None:
    """1ª vez: tipos padrão + os que já estão nas placas; modelos = os que já estão nas placas."""
    from database.connection import execute, query_df

    if query_df("SELECT COUNT(*) AS n FROM frota_tipos")["n"].iloc[0] == 0:
        usados = query_df("SELECT DISTINCT tipo FROM frota_placas WHERE tipo IS NOT NULL")["tipo"].tolist()
        for t in dict.fromkeys([*TIPOS_VEICULO, *[_limpo(x) for x in usados if _limpo(x)]]):
            execute("INSERT INTO frota_tipos (nome, ativo) VALUES (?, 1)", (t,))
    if query_df("SELECT COUNT(*) AS n FROM frota_modelos")["n"].iloc[0] == 0:
        m = query_df("SELECT marca_modelo, MAX(tipo) AS tipo FROM frota_placas WHERE marca_modelo IS NOT NULL "
                     "GROUP BY marca_modelo")
        for mm, tp in zip(m["marca_modelo"], m["tipo"]):
            if _limpo(mm):
                execute("INSERT INTO frota_modelos (modelo, tipo, ativo) VALUES (?, ?, 1)", (_limpo(mm), tp))


def tipos_df() -> pd.DataFrame:
    from database.connection import query_df

    _garantir_cadastros()
    return query_df("""SELECT t.id, t.nome, t.ativo, t.cap_cx, t.cap_baias, t.cap_kg,
                              (SELECT AVG(p.peso_kg) FROM frota_placas p WHERE p.tipo = t.nome AND p.peso_kg > 0)
                                  AS peso_placas,
                              (SELECT COUNT(*) FROM frota_placas p WHERE p.tipo = t.nome) AS placas,
                              (SELECT COUNT(*) FROM frota_modelos m WHERE m.tipo = t.nome) AS modelos
                       FROM frota_tipos t ORDER BY t.nome""")


def tipos(so_ativos: bool = False) -> list[str]:
    d = tipos_df()
    if so_ativos:
        d = d[d["ativo"].fillna(1).astype(int) == 1]
    return d["nome"].tolist()


def salvar_tipo(tid: int | None, d: dict) -> int:
    from database.connection import execute, query_one

    nome = _limpo(d.get("nome"))
    if len(nome) < 2:
        raise RegraNegocioError("Informe o tipo.")
    outro = query_one("SELECT id FROM frota_tipos WHERE LOWER(nome) = LOWER(?)", (nome,))
    if outro and int(outro["id"]) != int(tid or 0):
        raise RegraNegocioError(f"O tipo {nome} já existe.")
    ativo = 0 if d.get("ativo") in (0, "0", False, "Não") else 1

    def num(v):
        try:
            x = float(str(v).replace(",", ".")) if v not in (None, "") else None
        except ValueError:
            raise RegraNegocioError("Capacidade inválida.")
        if x is not None and (x != x or x <= 0):
            return None
        return x
    cx, baias = num(d.get("cap_cx")), num(d.get("cap_baias"))  # o peso é por placa (🚚 Cadastro de Placas)
    if tid:
        antes = query_one("SELECT nome FROM frota_tipos WHERE id = ?", (int(tid),))
        execute("UPDATE frota_tipos SET nome = ?, ativo = ?, cap_cx = ?, cap_baias = ? WHERE id = ?",
                (nome, ativo, cx, baias, int(tid)))
        if antes and antes["nome"] != nome:  # renomeou: leva junto placas e modelos
            execute("UPDATE frota_placas SET tipo = ? WHERE tipo = ?", (nome, antes["nome"]))
            execute("UPDATE frota_modelos SET tipo = ? WHERE tipo = ?", (nome, antes["nome"]))
        return int(tid)
    return execute("INSERT INTO frota_tipos (nome, ativo, cap_cx, cap_baias) VALUES (?, ?, ?, ?)",
                   (nome, ativo, cx, baias))


def excluir_tipo(tid: int) -> None:
    from database.connection import execute, query_one

    r = query_one("SELECT nome FROM frota_tipos WHERE id = ?", (int(tid),))
    if r and query_one("SELECT COUNT(*) AS n FROM frota_placas WHERE tipo = ?", (r["nome"],))["n"]:
        raise RegraNegocioError("Este tipo está em placas — troque o tipo delas ou desative em vez de excluir.")
    execute("DELETE FROM frota_tipos WHERE id = ?", (int(tid),))


def modelos_df() -> pd.DataFrame:
    from database.connection import query_df

    _garantir_cadastros()
    return query_df("""SELECT m.id, m.modelo, m.tipo, m.observacao, m.ativo,
                              (SELECT COUNT(*) FROM frota_placas p WHERE p.marca_modelo = m.modelo) AS placas
                       FROM frota_modelos m ORDER BY m.modelo""")


def modelos(so_ativos: bool = False) -> list[str]:
    d = modelos_df()
    if so_ativos:
        d = d[d["ativo"].fillna(1).astype(int) == 1]
    return d["modelo"].tolist()


def salvar_modelo(mid: int | None, d: dict) -> int:
    from database.connection import execute, query_one

    nome = _limpo(d.get("modelo"))
    if len(nome) < 2:
        raise RegraNegocioError("Informe a marca / modelo.")
    tipo = d.get("tipo") or None
    if tipo and tipo not in tipos():
        raise RegraNegocioError("Tipo inválido.")
    outro = query_one("SELECT id FROM frota_modelos WHERE LOWER(modelo) = LOWER(?)", (nome,))
    if outro and int(outro["id"]) != int(mid or 0):
        raise RegraNegocioError(f"O modelo {nome} já existe.")
    ativo = 0 if d.get("ativo") in (0, "0", False, "Não") else 1
    obs = _limpo(d.get("observacao")) or None
    if mid:
        antes = query_one("SELECT modelo FROM frota_modelos WHERE id = ?", (int(mid),))
        execute("UPDATE frota_modelos SET modelo = ?, tipo = ?, observacao = ?, ativo = ? WHERE id = ?",
                (nome, tipo, obs, ativo, int(mid)))
        if antes and antes["modelo"] != nome:
            execute("UPDATE frota_placas SET marca_modelo = ? WHERE marca_modelo = ?", (nome, antes["modelo"]))
        return int(mid)
    return execute("INSERT INTO frota_modelos (modelo, tipo, observacao, ativo) VALUES (?, ?, ?, ?)",
                   (nome, tipo, obs, ativo))


def excluir_modelo(mid: int) -> None:
    from database.connection import execute

    execute("DELETE FROM frota_modelos WHERE id = ?", (int(mid),))


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
