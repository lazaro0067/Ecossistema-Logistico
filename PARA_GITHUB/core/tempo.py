"""Datas e horas sempre no fuso de Brasília (o servidor na nuvem roda em UTC)."""
import datetime as dt
from zoneinfo import ZoneInfo

from config.settings import FUSO

_TZ = ZoneInfo(FUSO)


def agora() -> dt.datetime:
    return dt.datetime.now(_TZ).replace(tzinfo=None)


def agora_str() -> str:
    return agora().strftime("%Y-%m-%d %H:%M")


def hoje() -> dt.date:
    return agora().date()


def mes_atual() -> str:
    return hoje().strftime("%Y-%m")


def parse_dt(txt) -> dt.datetime | None:
    """Aceita 'AAAA-MM-DD HH:MM' ou 'DD/MM/AAAA HH:MM' (formato antigo)."""
    if not txt:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(str(txt).strip(), fmt)
        except ValueError:
            continue
    return None
