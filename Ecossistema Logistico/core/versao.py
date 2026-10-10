"""Última atualização do sistema (deploy): data/hora dos arquivos do programa + versão do banco."""
import datetime as dt
from pathlib import Path

from config.settings import BASE_DIR

_CACHE: dict = {}


def ultima_atualizacao() -> dt.datetime | None:
    if "quando" not in _CACHE:
        try:
            pastas = [BASE_DIR / p for p in ("app.py", "config", "core", "database", "modules", "repositories", "services")]
            arquivos = [p for x in pastas for p in ([x] if x.is_file() else x.rglob("*.py"))]
            ts = max(p.stat().st_mtime for p in arquivos)
            from core import tempo

            utc = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
            _CACHE["quando"] = tempo.para_local(utc) if hasattr(tempo, "para_local") else _local(utc)
        except Exception:
            _CACHE["quando"] = None
    return _CACHE["quando"]


def _local(utc: dt.datetime) -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo

        from config.settings import FUSO

        return utc.astimezone(ZoneInfo(FUSO)).replace(tzinfo=None)
    except Exception:
        return utc.replace(tzinfo=None)


def versao_banco() -> str:
    try:
        from database.schema import MIGRACOES

        return MIGRACOES[-1][0].split("_")[0]
    except Exception:
        return "?"


def texto() -> str:
    q = ultima_atualizacao()
    return f"🆕 Sistema atualizado em {q:%d/%m/%Y às %H:%M}" + f" · versão {versao_banco()}" if q else \
        f"🆕 Versão {versao_banco()}"


def mostrar(st_obj=None) -> None:
    import streamlit as st

    (st_obj or st).caption(texto())
