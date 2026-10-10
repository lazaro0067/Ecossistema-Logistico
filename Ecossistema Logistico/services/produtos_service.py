"""Classificação de SKUs Ambev a partir da descrição (portado do sistema original)."""
import re


def tipo_sku(desc) -> str:
    d = str(desc or "").upper()
    if any(k in d for k in ("CERVEJA", "CHOPP", "BRAHMA", "SKOL", "BUDWEISER", "SPATEN", "CORONA", "BECK",
                             " RET", "KEG", "ANTARCTICA", "ORIGINAL", "STELLA")):
        return "CERVEJA"
    if any(k in d for k in ("REFRIGERANTE", "GUARANA", "PEPSI", "SUKITA", "H2O", "AGUA", "ENERGETICO",
                             "TONICA", "NAB")):
        return "NAB"
    if any(k in d for k in ("MARKETPLACE", "PIRACANJUBA", "RED BULL")):
        return "MARKETPLACE"
    return "OUTROS"


def embalagem(txt) -> str | None:
    """Coluna D da linear: 'DESCARTAVÉL' → Descartável · 'RETORNÁVEL' → Retornável · 'CHOP' → Chopp."""
    import unicodedata

    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode().upper().strip()
    if not t or t in ("NAN", "NONE"):
        return None
    if t.startswith("DESC"):
        return "Descartável"
    if t.startswith("RET"):
        return "Retornável"
    if t.startswith("CHOP"):
        return "Chopp"
    return t.title()


EMBALAGENS = ["Retornável", "Descartável", "Chopp", "Outros"]


def categoria_detalhada(desc, categoria=None) -> str:
    """Embalagem: a da linear (cadastro) quando existir; senão, deduzida da descrição."""
    emb = embalagem(categoria) if categoria is not None else None
    if emb in EMBALAGENS:
        return emb
    d = str(desc or "").upper()
    if "CHOPP" in d or "KEG" in d or "BARRIL" in d:
        return "Chopp"
    if "RET" in d or "RGB" in d:
        return "Retornável"
    if any(k in d for k in ("DESC", "LATA", " LT", "LONG", "PET")):
        return "Descartável"
    return "Outros"


_MARCAS = [
    (("BC ", "BR "), ("BRAHMA",), "BRAHMA"), (("SK ",), ("SKOL",), "SKOL"),
    (("ANT ",), ("ANTARCTICA",), "ANTARCTICA"), (("ORG ",), ("ORIGINAL",), "ORIGINAL"),
    (("BUD",), ("BUDWEISER",), "BUDWEISER"), (("SPAT",), ("SPATEN",), "SPATEN"),
    (("COR ",), ("CORONA",), "CORONA"), (("SLA ",), ("ARTOIS", "STELLA"), "STELLA ARTOIS"),
    (("SU ", "SUK"), ("SUKITA",), "SUKITA"), (("PC ",), ("PEPSI",), "PEPSI"),
    (("GCA ",), ("GUARANA",), "GUARANÁ"), (("CHP BR",), ("CHOPP",), "CHOPP BRAHMA"),
    (("BECK",), ("BECKS",), "BECKS"), ((), ("H2O",), "H2OH!"),
]


def marca(desc) -> str:
    d = str(desc or "").upper().strip()
    for prefixos, contem, nome in _MARCAS:
        if d.startswith(prefixos) or any(c in d for c in contem):
            return nome
    return "OUTROS"


def codigo_do_sku(sku: str) -> int:
    """'BEB / 12345 - SKOL LT' -> 12345 ; '12345 SKOL' -> 12345."""
    s = str(sku or "").strip()
    partes = s.split("/")
    alvo = partes[1].strip() if len(partes) >= 2 else s
    m = re.search(r"^\d+", alvo)
    return int(m.group()) if m else 0
