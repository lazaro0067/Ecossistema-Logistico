"""Acesso do RN ao Portal Comercial: login por CPF e senha.

O Master libera o CPF (nome e revendas) em 🔑 Gestão de Acessos › 🔗 Links do Portal Comercial. No primeiro acesso o
próprio RN cria a senha. O link da revenda continua valendo — mas agora só abre para RN liberado naquela revenda.
"""
import hashlib
import hmac
import re
import time

import pandas as pd

from core import tempo
from core.auth import hash_senha, verificar_senha
from database.connection import execute, query_df, query_one
from services.erros import RegraNegocioError

TOKEN_DIAS = 30


def limpar_cpf(cpf) -> str:
    return re.sub(r"\D", "", str(cpf or ""))


def cpf_valido(cpf: str) -> bool:
    c = limpar_cpf(cpf)
    if len(c) != 11 or c == c[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        dig = (soma * 10) % 11 % 10
        if dig != int(c[n]):
            return False
    return True


def formatar_cpf(cpf: str) -> str:
    c = limpar_cpf(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else c


def listar() -> pd.DataFrame:
    return query_df("SELECT id, cpf, nome, operacoes, ativo, senha_hash IS NOT NULL AS tem_senha, criado_por, "
                    "criado_em, ultimo_acesso FROM portal_rn ORDER BY nome")


def salvar(cpf: str, nome: str, operacoes: list[int], usuario: str = "", rn_id: int | None = None,
           ativo: bool = True) -> int:
    c = limpar_cpf(cpf)
    if not cpf_valido(c):
        raise RegraNegocioError("CPF inválido.")
    if not (nome or "").strip():
        raise RegraNegocioError("Informe o nome do RN.")
    if not operacoes:
        raise RegraNegocioError("Escolha pelo menos uma revenda.")
    ops = ",".join(str(int(o)) for o in operacoes)
    outro = query_one("SELECT id FROM portal_rn WHERE cpf = ?", (c,))
    if outro and int(outro["id"]) != (rn_id or 0):
        raise RegraNegocioError("Este CPF já está cadastrado.")
    if rn_id:
        execute("UPDATE portal_rn SET cpf = ?, nome = ?, operacoes = ?, ativo = ? WHERE id = ?",
                (c, nome.strip(), ops, 1 if ativo else 0, int(rn_id)))
        return int(rn_id)
    return execute("INSERT INTO portal_rn (cpf, nome, operacoes, ativo, criado_por, criado_em) VALUES (?, ?, ?, 1, ?, ?)",
                   (c, nome.strip(), ops, usuario, tempo.agora().strftime("%Y-%m-%d %H:%M")))


def excluir(rn_id: int) -> None:
    execute("DELETE FROM portal_rn WHERE id = ?", (int(rn_id),))


def resetar_senha(rn_id: int) -> None:
    """Apaga a senha: no próximo acesso o RN cria uma nova."""
    execute("UPDATE portal_rn SET senha_hash = NULL WHERE id = ?", (int(rn_id),))


def _buscar(cpf: str) -> dict | None:
    return query_one("SELECT * FROM portal_rn WHERE cpf = ?", (limpar_cpf(cpf),))


def situacao(cpf: str, operacao_id: int) -> str:
    """'sem_cadastro' | 'bloqueado' | 'sem_revenda' | 'criar_senha' | 'ok'"""
    r = _buscar(cpf)
    if not r:
        return "sem_cadastro"
    if not int(r["ativo"] or 0):
        return "bloqueado"
    if str(operacao_id) not in str(r["operacoes"] or "").split(","):
        return "sem_revenda"
    return "criar_senha" if not r["senha_hash"] else "ok"


def criar_senha(cpf: str, senha: str, confirmacao: str) -> dict:
    r = _buscar(cpf)
    if not r or not int(r["ativo"] or 0):
        raise RegraNegocioError("CPF não liberado. Peça o acesso à gestão.")
    if r["senha_hash"]:
        raise RegraNegocioError("Este CPF já tem senha. Entre com ela (ou peça para a gestão zerar).")
    if len(senha or "") < 6:
        raise RegraNegocioError("A senha precisa ter pelo menos 6 caracteres.")
    if senha != confirmacao:
        raise RegraNegocioError("As senhas não conferem.")
    execute("UPDATE portal_rn SET senha_hash = ? WHERE id = ?", (hash_senha(senha), int(r["id"])))
    return entrar(cpf, senha)


def entrar(cpf: str, senha: str) -> dict:
    from services import seguranca_service as seg

    chave = limpar_cpf(cpf)
    falta = seg.minutos_bloqueado(chave, "portal_rn")
    if falta:
        raise RegraNegocioError(f"Muitas tentativas com senha errada. Tente de novo em {falta} minuto(s).")
    r = _buscar(cpf)
    if not r or not r["senha_hash"] or not int(r["ativo"] or 0) or not verificar_senha(senha or "", r["senha_hash"]):
        seg.registrar_tentativa(chave, "portal_rn", False)
        raise RegraNegocioError("CPF ou senha inválidos.")
    seg.registrar_tentativa(chave, "portal_rn", True, {"id": None, "nome": f"RN {r['nome']}", "cpf": chave})
    execute("UPDATE portal_rn SET ultimo_acesso = ? WHERE id = ?",
            (tempo.agora().strftime("%Y-%m-%d %H:%M"), int(r["id"])))
    return {"id": int(r["id"]), "nome": r["nome"], "cpf": r["cpf"],
            "operacoes": [int(x) for x in str(r["operacoes"] or "").split(",") if x]}


def _assinar(rn_id: int, expira: int, senha_hash: str) -> str:
    return hmac.new(senha_hash.encode(), f"rn.{rn_id}.{expira}".encode(), hashlib.sha256).hexdigest()[:32]


def gerar_token(rn: dict) -> str | None:
    r = query_one("SELECT senha_hash FROM portal_rn WHERE id = ?", (rn["id"],))
    if not r or not r["senha_hash"]:
        return None
    expira = int(time.time()) + TOKEN_DIAS * 86400
    return f"{rn['id']}.{expira}.{_assinar(rn['id'], expira, r['senha_hash'])}"


def por_token(token: str) -> dict | None:
    try:
        rid, expira, ass = str(token).split(".")
        rid, expira = int(rid), int(expira)
    except (ValueError, AttributeError):
        return None
    if expira < time.time():
        return None
    r = query_one("SELECT * FROM portal_rn WHERE id = ?", (rid,))
    if not r or not r["senha_hash"] or not int(r["ativo"] or 0) or \
            not hmac.compare_digest(_assinar(rid, expira, r["senha_hash"]), ass):
        return None
    return {"id": rid, "nome": r["nome"], "cpf": r["cpf"],
            "operacoes": [int(x) for x in str(r["operacoes"] or "").split(",") if x]}
