"""Regras de negócio: cadastros (operações, OD, trechos, transportadoras, CC)."""
import sqlite3
from contextlib import contextmanager

from config.settings import TIPOS_OD
from repositories import cadastros_repo, operacoes_repo
from services.erros import RegraNegocioError


@contextmanager
def _sem_duplicidade(msg: str):
    try:
        yield
    except sqlite3.IntegrityError as e:
        if "FOREIGN KEY" in str(e):
            raise RegraNegocioError("Registro em uso por outros lançamentos — não pode ser excluído.")
        raise RegraNegocioError(msg)


def _obrigatorio(valor: str, campo: str) -> str:
    valor = (valor or "").strip()
    if not valor:
        raise RegraNegocioError(f"Informe {campo}.")
    return valor


# --- Operações ------------------------------------------------------------
def criar_operacao(nome, cnpj, cidade, uf):
    with _sem_duplicidade("Já existe uma operação com esse nome."):
        operacoes_repo.inserir(_obrigatorio(nome, "o nome"), cnpj.strip(), cidade.strip(), uf.strip())


def atualizar_operacao(oid, nome, cnpj, cidade, uf, ativo):
    with _sem_duplicidade("Já existe uma operação com esse nome."):
        operacoes_repo.atualizar(oid, _obrigatorio(nome, "o nome"), cnpj.strip(), cidade.strip(), uf.strip(), ativo)


# --- Transportadoras / CC -------------------------------------------------
def criar_transportadora(nome, cnpj, contato):
    with _sem_duplicidade("Transportadora já cadastrada."):
        cadastros_repo.inserir_transportadora(_obrigatorio(nome, "o nome").upper(), cnpj.strip(), contato.strip())


def excluir_transportadora(tid):
    with _sem_duplicidade(""):
        cadastros_repo.excluir_transportadora(tid)


def criar_centro_custo(nome):
    with _sem_duplicidade("Centro de custo já cadastrado."):
        cadastros_repo.inserir_centro_custo(_obrigatorio(nome, "o nome"))


def excluir_centro_custo(cid):
    with _sem_duplicidade(""):
        cadastros_repo.excluir_centro_custo(cid)


# --- Origens/Destinos e Trechos ------------------------------------------
def criar_od(operacao_id, nome, cidade, uf, tipo):
    if tipo not in TIPOS_OD:
        raise RegraNegocioError("Tipo inválido.")
    with _sem_duplicidade("Já existe uma origem/destino com esse nome nesta operação."):
        cadastros_repo.inserir_od(operacao_id, _obrigatorio(nome, "o nome"), cidade.strip(), uf.strip(), tipo)


def excluir_od(od_id):
    with _sem_duplicidade(""):
        cadastros_repo.excluir_od(od_id)


def salvar_trecho(operacao_id, origem_id, destino_id, km, pedagio, remunerado, frete):
    if not origem_id or not destino_id:
        raise RegraNegocioError("Selecione origem e destino.")
    if origem_id == destino_id:
        raise RegraNegocioError("Origem e destino não podem ser iguais.")
    cadastros_repo.salvar_trecho(operacao_id, origem_id, destino_id, km, pedagio, remunerado, frete)


def excluir_trecho(trecho_id):
    cadastros_repo.excluir_trecho(trecho_id)
