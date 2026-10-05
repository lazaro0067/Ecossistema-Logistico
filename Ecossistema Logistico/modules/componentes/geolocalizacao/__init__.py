"""Localização (GPS) do celular, sem bibliotecas extras.

Um pequeno componente HTML pede a localização ao navegador e devolve
{"lat", "lon", "precisao", "ts"} — ou {"erro": "..."} se o motorista negar.
Se nada vier (navegador antigo, sem permissão), o sistema segue funcionando sem GPS.
"""
import os

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_componente = None


def _carregar():
    global _componente
    if _componente is None:
        import streamlit.components.v1 as components

        _componente = components.declare_component("eco_geolocalizacao", path=_DIR)
    return _componente


def localizacao(key: str = "geo") -> dict | None:
    """Última localização conhecida (dict com lat/lon/precisao) ou dict com 'erro', ou None."""
    try:
        valor = _carregar()(key=key, default=None)
    except Exception:
        return None
    return valor if isinstance(valor, dict) else None


def ponto(valor: dict | None) -> dict | None:
    """Só a parte útil (lat/lon/precisão) quando a leitura é válida."""
    if valor and valor.get("lat") is not None and valor.get("lon") is not None:
        return {"lat": valor["lat"], "lon": valor["lon"], "precisao": valor.get("precisao")}
    return None
