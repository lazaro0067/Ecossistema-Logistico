"""🛡️ Segurança: bloqueio de login após tentativas erradas e registro de acessos.

- 5 senhas erradas seguidas (sem um acerto no meio) em 15 minutos → aquele login fica bloqueado 15 minutos.
  Vale para o sistema, o Portal Comercial (RN) e o app de recontagem.
- Registro de acessos: entradas, tentativas erradas, bloqueios e as páginas abertas — Gestão de Acessos › 🕵️.
  Guarda 180 dias.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from core import tempo
from database.connection import execute, query_df, query_one

MAX_ERROS = 5
JANELA_MIN = 15
DIAS_REGISTRO = 180


def _agora() -> dt.datetime:
    return tempo.agora().replace(tzinfo=None)


def _txt(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S")


def _chave(login: str) -> str:
    return str(login or "").strip().lower()[:120]


def minutos_bloqueado(login: str, tipo: str = "sistema") -> int:
    """Minutos que faltam para liberar o login (0 = liberado)."""
    ch = _chave(login)
    if not ch:
        return 0
    desde = _txt(_agora() - dt.timedelta(minutes=JANELA_MIN))
    d = query_df("SELECT sucesso, quando FROM seg_tentativas WHERE chave = ? AND tipo = ? AND quando >= ? "
                 "ORDER BY quando DESC", (ch, tipo, desde))
    erros = []
    for s, q in zip(d["sucesso"], d["quando"]):
        if int(s or 0):
            break
        erros.append(str(q))
    if len(erros) < MAX_ERROS:
        return 0
    libera = pd.to_datetime(erros[MAX_ERROS - 1]) + dt.timedelta(minutes=JANELA_MIN)
    falta = (libera - pd.Timestamp(_agora())).total_seconds() / 60
    return max(int(falta) + 1, 0) if falta > 0 else 0


def registrar_tentativa(login: str, tipo: str, sucesso: bool, usuario: dict | None = None) -> None:
    try:
        execute("INSERT INTO seg_tentativas (chave, tipo, sucesso, quando) VALUES (?, ?, ?, ?)",
                (_chave(login), tipo, 1 if sucesso else 0, _txt(_agora())))
        if sucesso:
            registrar(usuario, "login", tipo, login)
        else:
            registrar(None, "senha errada", tipo, login)
            if minutos_bloqueado(login, tipo):
                registrar(None, "bloqueado", tipo, login)
    except Exception:  # noqa: BLE001 — o registro nunca impede o login
        pass


def registrar(usuario: dict | None, evento: str, detalhe: str = "", login: str = "") -> None:
    try:
        u = usuario or {}
        execute("INSERT INTO seg_acessos (usuario_id, nome, login, evento, detalhe, quando) VALUES (?, ?, ?, ?, ?, ?)",
                (u.get("id"), str(u.get("nome") or "")[:120], _chave(login or u.get("email") or u.get("login") or
                                                                       u.get("cpf") or ""),
                 evento[:40], str(detalhe or "")[:200], _txt(_agora())))
    except Exception:  # noqa: BLE001
        pass


def acessos(dias: int = 7) -> pd.DataFrame:
    limite = _txt(_agora() - dt.timedelta(days=DIAS_REGISTRO))
    try:
        execute("DELETE FROM seg_acessos WHERE quando < ?", (limite,))
        execute("DELETE FROM seg_tentativas WHERE quando < ?", (limite,))
    except Exception:  # noqa: BLE001
        pass
    desde = _txt(_agora() - dt.timedelta(days=int(dias)))
    return query_df("SELECT quando, nome, login, evento, detalhe FROM seg_acessos WHERE quando >= ? "
                    "ORDER BY quando DESC", (desde,))


def resumo(dias: int = 7) -> dict:
    d = acessos(dias)
    return {"logins": int((d["evento"] == "login").sum()), "erros": int((d["evento"] == "senha errada").sum()),
            "bloqueios": int((d["evento"] == "bloqueado").sum()),
            "usuarios": int(d.loc[d["evento"] == "login", "login"].nunique())}
