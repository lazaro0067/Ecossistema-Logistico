"""☁️ Arquivos que o 🤖 robô enviou para o sistema na nuvem.

O robô roda no computador da empresa e, sem acesso direto ao banco, manda cada relatório baixado para a pasta
`entrada/` do repositório PRIVADO do backup no GitHub (o mesmo dos Secrets BACKUP_GITHUB_*). Aqui o sistema pega
esses arquivos, importa com as MESMAS funções do upload manual e apaga da entrada (com erro, vai para entrada/erro/).

Nome do arquivo: <tipo>__<revenda>__<AAAAMMDD-HHMMSS>__<arquivo>.<ext>   (revenda em slug: lima-rio-verde)
Verifica sozinho a cada 10 minutos enquanto o sistema estiver aberto, ou na hora pelo botão em 📥 Atualizar
relatórios › 🤖 Robô de relatórios.
"""
from __future__ import annotations

import re
import tempfile
import threading
import time
import unicodedata
import urllib.parse
from pathlib import Path

from core import tempo

PASTA = "entrada"
MINUTOS = 10
_lock = threading.Lock()
_estado = {"ultima": 0.0, "resultado": None}


def slug(txt: str) -> str:
    """Mesmo código do robô (robo/robo.py)."""
    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def configurado() -> bool:
    from services import backup_auto

    return backup_auto.configurado()


def pendentes() -> list[dict]:
    """Arquivos esperando na entrada (mais antigos primeiro)."""
    from services import backup_auto as ba

    itens = ba._req("GET", ba._url(f"/contents/{PASTA}?t={time.time_ns()}")) or []
    arqs = [i for i in itens if isinstance(i, dict) and i.get("type") == "file" and i["name"].count("__") >= 3]
    return sorted(arqs, key=lambda i: i["name"].split("__")[2])


def _operacao(revenda: str) -> int:
    from repositories import operacoes_repo

    for o in operacoes_repo.listar(apenas_ativas=False):
        if slug(o["nome"]) == revenda:
            return int(o["id"])
    raise RuntimeError(f"Revenda '{revenda}' não encontrada no sistema (confira 'revenda' no config.toml do robô).")


def _apagar(item: dict, motivo: str) -> None:
    from services import backup_auto as ba

    ba._req("DELETE", ba._url(f"/contents/{urllib.parse.quote(item['path'])}"),
            {"message": motivo, "sha": item["sha"]})


def _mover_para_erro(item: dict, dados: bytes) -> None:
    import base64

    from services import backup_auto as ba

    ba._req("PUT", ba._url(f"/contents/{PASTA}/erro/{urllib.parse.quote(item['name'])}"),
            {"message": "robô: arquivo com erro", "content": base64.b64encode(dados).decode()})
    _apagar(item, "robô: movido para entrada/erro")


def processar() -> list[str]:
    """Importa tudo o que estiver na entrada. Devolve uma linha por arquivo."""
    if not configurado():
        return []
    if not _lock.acquire(blocking=False):  # outra verificação já está rodando
        return ["⏳ Já estou importando os arquivos do robô — aguarde um instante."]
    try:
        from robo import importadores
        from services import backup_auto as ba
        from services import robo_service as rs

        saida = []
        for item in pendentes():
            tipo, revenda, _quando, resto = item["name"].split("__", 3)
            dados = ba._req("GET", ba._url(f"/contents/{urllib.parse.quote(item['path'])}"), raw=True)
            if dados is None:
                continue
            op, eid = None, None
            try:
                op = _operacao(revenda)
                eid = rs.inicio(op, tipo, "☁️ robô → nuvem")
                with tempfile.TemporaryDirectory() as d:
                    caminho = Path(d) / resto
                    caminho.write_bytes(dados)
                    msg = importadores.importar(tipo, caminho, op)
                rs.fim(eid, "ok", msg, resto)
                _apagar(item, f"robô: importado ({tipo})")
                saida.append(f"✅ {rs.NOMES.get(tipo, tipo)}: {msg}")
            except Exception as e:  # noqa: BLE001 — um arquivo ruim não trava os outros
                erro = f"{type(e).__name__}: {e}"
                if eid is None:
                    eid = rs.inicio(op, tipo, "☁️ robô → nuvem")
                rs.fim(eid, "erro", erro, resto)
                try:
                    _mover_para_erro(item, dados)
                except Exception:  # noqa: BLE001
                    pass
                saida.append(f"❌ {rs.NOMES.get(tipo, tipo)}: {erro}")
        _estado["resultado"] = (tempo.agora().strftime("%d/%m %H:%M"), saida)
        return saida
    finally:
        _estado["ultima"] = time.time()
        _lock.release()


def _rodar() -> None:
    try:
        processar()
    except Exception as e:  # noqa: BLE001 — nunca derruba o app
        _estado["resultado"] = (tempo.agora().strftime("%d/%m %H:%M"), [f"❌ {e}"])


def verificar_em_segundo_plano() -> None:
    """Chamado a cada carregamento de página: no máximo uma verificação a cada MINUTOS, sem travar a tela."""
    if time.time() - _estado["ultima"] < MINUTOS * 60 or _lock.locked() or not configurado():
        return
    _estado["ultima"] = time.time()
    threading.Thread(target=_rodar, name="robo-nuvem", daemon=True).start()


def ultimo_resultado():
    return _estado["resultado"]
