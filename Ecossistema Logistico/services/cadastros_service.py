"""Regras de negócio: cadastros (operações, OD, trechos, transportadoras, CC)."""
from contextlib import contextmanager

from config.settings import TIPOS_OD
from database.connection import tipo_violacao
from repositories import cadastros_repo, operacoes_repo
from services.erros import RegraNegocioError


@contextmanager
def _sem_duplicidade(msg: str):
    try:
        yield
    except Exception as e:
        tipo = tipo_violacao(e)
        if tipo == "fk":
            raise RegraNegocioError("Registro em uso por outros lançamentos — não pode ser excluído.")
        if tipo == "unica":
            raise RegraNegocioError(msg)
        raise


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


def atualizar_transportadora(tid, nome, cnpj, contato):
    with _sem_duplicidade("Já existe uma transportadora com esse nome."):
        cadastros_repo.atualizar_transportadora(tid, _obrigatorio(nome, "o nome").upper(), (cnpj or "").strip(),
                                                (contato or "").strip())


def atualizar_centro_custo(cid, nome):
    with _sem_duplicidade("Já existe um centro de custo com esse nome."):
        cadastros_repo.atualizar_centro_custo(cid, _obrigatorio(nome, "o nome"))


def atualizar_od(od_id, nome, cidade, uf, tipo):
    if tipo not in TIPOS_OD:
        raise RegraNegocioError("Tipo inválido.")
    with _sem_duplicidade("Já existe uma origem/destino com esse nome nesta operação."):
        cadastros_repo.atualizar_od(od_id, _obrigatorio(nome, "o nome"), (cidade or "").strip(), (uf or "").strip(), tipo)


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
def garantir_od_padrao(operacao_id: int) -> int:
    """Para cotar frete sem cadastro duplicado: as fábricas viram ORIGENS e a própria revenda vira DESTINO
    (só cria o que ainda não existe). Sem nenhuma transportadora, cria "FROTA PRÓPRIA". Devolve quantos criou."""
    import unicodedata

    from repositories import logistica_repo, operacoes_repo

    if not operacao_id or operacoes_repo.e_consolidada(operacao_id):
        return 0

    def n(t):
        return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()

    existentes = {n(o["nome"]) for o in cadastros_repo.listar_od(operacao_id)}
    criados = 0
    for f in logistica_repo.fabricas_df().to_dict("records"):
        if n(f["nome"]) not in existentes:
            cadastros_repo.inserir_od(operacao_id, f["nome"], f.get("cidade") or "", f.get("uf") or "", "Apenas Origem")
            existentes.add(n(f["nome"]))
            criados += 1
    op = operacoes_repo.buscar(operacao_id)
    if op and n(op["nome"]) not in existentes:
        cadastros_repo.inserir_od(operacao_id, op["nome"], op.get("cidade") or "", op.get("uf") or "", "Apenas Destino")
        criados += 1
    if not cadastros_repo.listar_transportadoras():
        cadastros_repo.inserir_transportadora("FROTA PRÓPRIA", "", "")
        criados += 1
    return criados


def criar_od(operacao_id, nome, cidade, uf, tipo):
    if tipo not in TIPOS_OD:
        raise RegraNegocioError("Tipo inválido.")
    with _sem_duplicidade("Já existe uma origem/destino com esse nome nesta operação."):
        cadastros_repo.inserir_od(operacao_id, _obrigatorio(nome, "o nome"), cidade.strip(), uf.strip(), tipo)


def excluir_od(od_id):
    with _sem_duplicidade(""):
        cadastros_repo.excluir_od(od_id)


def salvar_trecho(operacao_id, origem_id, destino_id, km, pedagio, remunerado, frete,
                  transportadora_id=None, aprovador_id=None):
    if not origem_id or not destino_id:
        raise RegraNegocioError("Selecione origem e destino.")
    if origem_id == destino_id:
        raise RegraNegocioError("Origem e destino não podem ser iguais.")
    if frete <= 0:
        raise RegraNegocioError("Informe o valor do frete do trecho.")
    cadastros_repo.salvar_trecho(operacao_id, origem_id, destino_id, km, pedagio, remunerado, frete,
                                 transportadora_id, aprovador_id)


def excluir_trecho(trecho_id):
    cadastros_repo.excluir_trecho(trecho_id)
