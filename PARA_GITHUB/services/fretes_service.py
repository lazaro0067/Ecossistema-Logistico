"""Regras de negócio: cotações de frete (Puxada) e OBZ.

Fluxo:  Pendente Aprovação → Aprovado → Finalizado (com NF + CT-e)
                           ↘ Rejeitado
        Pendente/Aprovado  → Cancelado (pelo solicitante ou Master)
"""
import datetime as dt
import re

from config.settings import PERFIL_MASTER, StatusFrete
from core import tempo
from repositories import cadastros_repo, fretes_repo, usuarios_repo
from services.erros import RegraNegocioError


def _agora() -> str:
    return tempo.agora_str()


def valor_tabela(operacao_id: int, origem_id: int | None, destino_id: int | None) -> float | None:
    """Valor de frete cadastrado no trecho (referência para a negociação)."""
    if not origem_id or not destino_id:
        return None
    t = cadastros_repo.buscar_trecho(operacao_id, origem_id, destino_id)
    return float(t["valor_frete"]) if t else None


def criar_cotacao(*, operacao_id: int, solicitante_id: int, origem_id: int, destino_id: int,
                  transportadora_id: int, centro_custo_id: int | None, aprovador_id: int,
                  data_frete: dt.date, motivo: str, valor_negociado: float, observacao: str) -> int:
    if not all([origem_id, destino_id, transportadora_id, aprovador_id]):
        raise RegraNegocioError("Preencha origem, destino, transportadora e aprovador.")
    if origem_id == destino_id:
        raise RegraNegocioError("Origem e destino não podem ser iguais.")
    if valor_negociado <= 0:
        raise RegraNegocioError("Informe o valor negociado.")

    aprovador = usuarios_repo.buscar(aprovador_id)
    if not aprovador or not aprovador["e_aprovador"]:
        raise RegraNegocioError("O usuário escolhido não é aprovador.")
    if aprovador["perfil"] != PERFIL_MASTER and valor_negociado > aprovador["alcada"]:
        raise RegraNegocioError(
            f"Valor acima da alçada de {aprovador['nome']} (R$ {aprovador['alcada']:,.2f}). "
            "Escolha um aprovador com alçada maior."
        )

    return fretes_repo.inserir(dict(
        operacao_id=operacao_id, origem_id=origem_id, destino_id=destino_id,
        transportadora_id=transportadora_id, centro_custo_id=centro_custo_id,
        data_requisicao=tempo.hoje().isoformat(), data_frete=data_frete.isoformat(),
        motivo=motivo, valor_negociado=float(valor_negociado),
        valor_tabela=valor_tabela(operacao_id, origem_id, destino_id),
        solicitante_id=solicitante_id, aprovador_id=aprovador_id,
        observacao=observacao.strip(), status=StatusFrete.PENDENTE,
    ))


def _pode_decidir(usuario: dict, cot: dict) -> None:
    if cot["status"] != StatusFrete.PENDENTE:
        raise RegraNegocioError(f"Cotação #{cot['id']} não está pendente.")
    if usuario["perfil"] == PERFIL_MASTER:
        return
    if usuario["id"] != cot["aprovador_id"]:
        raise RegraNegocioError("Somente o aprovador indicado pode decidir esta cotação.")
    if cot["valor_negociado"] > usuario["alcada"]:
        raise RegraNegocioError("Valor acima da sua alçada de aprovação.")


def aprovar(cotacao_id: int, usuario: dict) -> None:
    cot = fretes_repo.buscar(cotacao_id)
    _pode_decidir(usuario, cot)
    fretes_repo.atualizar(cotacao_id, status=StatusFrete.APROVADO, decidido_em=_agora())


def rejeitar(cotacao_id: int, usuario: dict, motivo: str) -> None:
    if not motivo.strip():
        raise RegraNegocioError("Informe o motivo da rejeição.")
    cot = fretes_repo.buscar(cotacao_id)
    _pode_decidir(usuario, cot)
    fretes_repo.atualizar(cotacao_id, status=StatusFrete.REJEITADO, decidido_em=_agora(),
                          motivo_rejeicao=motivo.strip())


def cancelar(cotacao_id: int, usuario: dict) -> None:
    cot = fretes_repo.buscar(cotacao_id)
    if cot["status"] not in (StatusFrete.PENDENTE, StatusFrete.APROVADO):
        raise RegraNegocioError("Só é possível cancelar cotações pendentes ou aprovadas.")
    if usuario["perfil"] != PERFIL_MASTER and usuario["id"] != cot["solicitante_id"]:
        raise RegraNegocioError("Somente o solicitante ou o Master podem cancelar.")
    fretes_repo.atualizar(cotacao_id, status=StatusFrete.CANCELADO, decidido_em=_agora())


_LIMITE_ANEXO = 10 * 1024 * 1024  # 10 MB


def _salvar_arquivo(cotacao_id: int, tipo: str, nome: str, conteudo: bytes) -> str:
    """Guarda o arquivo no próprio banco (não se perde em reinícios da nuvem)."""
    if len(conteudo) > _LIMITE_ANEXO:
        raise RegraNegocioError(f"O arquivo {nome} passa de 10 MB.")
    nome_limpo = re.sub(r"[^\w.\-]", "_", nome)
    fretes_repo.salvar_anexo(cotacao_id, tipo, nome_limpo, conteudo)
    return nome_limpo


def finalizar(cotacao_id: int, numero_cte: str, notas_fiscais: str,
              arquivos: list[tuple[str, str, bytes]] | None = None) -> None:
    """Fecha o frete. Obrigatório: número/chave do CT-e e as NFs transportadas.
    `arquivos` (opcional) = [(tipo, nome, conteúdo)] — PDFs/XMLs ficam guardados no banco."""
    cot = fretes_repo.buscar(cotacao_id)
    if cot["status"] != StatusFrete.APROVADO:
        raise RegraNegocioError("Só é possível finalizar fretes aprovados.")
    numero_cte, notas_fiscais = (numero_cte or "").strip(), (notas_fiscais or "").strip()
    if not numero_cte or not notas_fiscais:
        raise RegraNegocioError("Para finalizar, informe o CT-e e as Notas Fiscais transportadas.")
    nomes = {"NF": [], "CT-e": []}
    for tipo, nome, conteudo in arquivos or []:
        nomes.setdefault(tipo, []).append(_salvar_arquivo(cotacao_id, tipo, nome, conteudo))
    fretes_repo.atualizar(
        cotacao_id, status=StatusFrete.FINALIZADO, numero_cte=numero_cte, notas_fiscais=notas_fiscais,
        nf_arquivo=", ".join(nomes["NF"]) or None, cte_arquivo=", ".join(nomes["CT-e"]) or None,
        finalizado_em=_agora(),
    )


def anexos(cotacao_id: int) -> list[dict]:
    return fretes_repo.listar_anexos(cotacao_id)


# --- OBZ ------------------------------------------------------------------
def resumo_obz(operacao_id: int, mes_ano: str) -> dict:
    meta = fretes_repo.buscar_meta(operacao_id, mes_ano)
    realizado = fretes_repo.total_por_status(operacao_id, mes_ano, StatusFrete.COMPROMETIDOS)
    pendente = fretes_repo.total_por_status(operacao_id, mes_ano, [StatusFrete.PENDENTE])
    return {
        "meta": meta,
        "realizado": realizado,
        "pendente": pendente,
        "saldo": meta - realizado,
        "pct": (realizado / meta * 100) if meta else 0.0,
    }


def historico_obz(operacao_id: int):
    import pandas as pd

    real = fretes_repo.gasto_mensal_df(operacao_id, StatusFrete.COMPROMETIDOS)
    metas = fretes_repo.metas_df(operacao_id)
    df = pd.merge(metas, real, on="mes_ano", how="outer").fillna(0).sort_values("mes_ano")
    df["saldo"] = df["meta"] - df["realizado"]
    return df
