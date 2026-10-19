"""Plano da empresa desta instância (cada empresa cliente roda a sua cópia do sistema, com o seu banco).

Configurado nos Secrets / variáveis de ambiente da instância — nada no código muda de uma empresa para outra:
  EMPRESA_NOME   = "Grupo Lima"            nome que aparece no sistema e nas mensagens
  PLANO          = "completo"              essencial | profissional | completo
  MODULOS_EXTRAS = "frota,financeiro"      (opcional) módulos vendidos à parte, além do plano
  MAX_USUARIOS   = "30"                    (opcional) sobrepõe o limite do plano
  MAX_REVENDAS   = "5"                     (opcional) sobrepõe o limite do plano
Sem nada configurado = plano completo, sem limite (é como o Grupo Lima roda hoje).
"""
from __future__ import annotations

from core.segredos import segredo

PLANOS = {
    "essencial": {"rotulo": "Essencial", "modulos": ["puxada", "ressuprimento", "armazem"],
                  "usuarios": 10, "revendas": 1},
    "profissional": {"rotulo": "Profissional",
                     "modulos": ["puxada", "ressuprimento", "armazem", "vendas", "distribuicao", "frota", "compras",
                                 "gente"], "usuarios": 30, "revendas": 3},
    "completo": {"rotulo": "Completo", "modulos": None, "usuarios": None, "revendas": None},  # None = tudo / sem limite
}
SEMPRE = {"relatorios"}  # bases e relatórios: todo plano tem


def empresa() -> str:
    return str(segredo("EMPRESA_NOME", "Grupo Lima")).strip() or "Grupo Lima"


def plano() -> str:
    p = str(segredo("PLANO", "completo")).strip().lower()
    return p if p in PLANOS else "completo"


def rotulo() -> str:
    return PLANOS[plano()]["rotulo"]


def _extras() -> set[str]:
    return {m.strip().lower() for m in str(segredo("MODULOS_EXTRAS", "") or "").split(",") if m.strip()}


def modulos_liberados() -> set[str] | None:
    """None = todos os módulos."""
    base = PLANOS[plano()]["modulos"]
    if base is None:
        return None
    return set(base) | SEMPRE | _extras()


def modulo_liberado(modulo: str) -> bool:
    lib = modulos_liberados()
    return lib is None or modulo in lib


def _limite(chave: str, segredo_nome: str) -> int | None:
    v = segredo(segredo_nome)
    if v not in (None, ""):
        try:
            return int(v)
        except (TypeError, ValueError):
            pass
    return PLANOS[plano()][chave]


def limite_usuarios() -> int | None:
    return _limite("usuarios", "MAX_USUARIOS")


def limite_revendas() -> int | None:
    return _limite("revendas", "MAX_REVENDAS")
