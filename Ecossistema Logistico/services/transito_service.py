"""Trânsito: o que o motorista já carregou na fábrica e está vindo para o armazém.

Viagem do App Carreteiro com "Pedido carregado" registrado:
  • ainda em viagem  → os itens do pedido (Puxada Marcada) contam como TRÂNSITO;
  • em qualquer caso → o pedido sai de D0/D1/D2 (não conta duas vezes).
"""
import datetime as dt

import pandas as pd

from core import tempo
from repositories import carreteiro_repo
from repositories import pedidos_puxada_repo as ped_repo
from repositories import ressuprimento_repo


def _viagens_carregadas(operacao_id: int) -> pd.DataFrame:
    de = (tempo.hoje() - dt.timedelta(days=20)).isoformat()
    v = carreteiro_repo.viagens_df(operacao_id, de)
    if v.empty:
        return v
    car = v["ts_carregado"].map(lambda x: isinstance(x, str) and x.strip() != "")
    return v[car]


def numeros_carregados(operacao_id: int) -> set[str]:
    v = _viagens_carregadas(operacao_id)
    if v.empty:
        return set()
    return {ressuprimento_repo._num(n) for t in v["numero_pedido"] for n in ped_repo.numeros(t)} - {""}


def itens_em_transito(operacao_id: int) -> pd.DataFrame:
    """Itens dos pedidos carregados que ainda não chegaram/descarregaram (viagem em andamento)."""
    v = _viagens_carregadas(operacao_id)
    v = v[v["status"] == carreteiro_repo.EM_VIAGEM] if not v.empty else v
    if v.empty:
        return pd.DataFrame(columns=["numero_pedido", "cod", "descricao", "paletes", "cx_marcadas", "placa"])
    nums = [n for t in v["numero_pedido"] for n in ped_repo.numeros(t)]
    it = ressuprimento_repo.itens_dos_pedidos(operacao_id, nums)
    if it.empty:
        return it.assign(placa=None)
    placa = {ressuprimento_repo._num(n): p for t, p in zip(v["numero_pedido"], v["placa"]) for n in ped_repo.numeros(t)}
    return it.assign(placa=it["numero_pedido"].map(lambda n: placa.get(ressuprimento_repo._num(n))))


def transito_por_cod(operacao_id: int) -> pd.Series:
    it = itens_em_transito(operacao_id)
    if it.empty:
        return pd.Series(dtype=float)
    return it.groupby("cod")["cx_marcadas"].sum()
