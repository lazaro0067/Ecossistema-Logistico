"""☁️ Arquivos que o 🤖 robô enviou para o sistema na nuvem.

O robô roda no computador/servidor da empresa e, sem acesso direto ao banco, manda cada relatório baixado para a
pasta `entrada/` de um repositório PRIVADO no GitHub: o de entrada do robô (Secrets ROBO_GITHUB_TOKEN /
ROBO_GITHUB_REPO — chave que só mexe nele) ou, se não houver, o do backup (BACKUP_GITHUB_*).
Servidor sem tela: o robô pede o código do celular em entrada/_pedidos e o Master responde aqui (_respostas). Aqui o sistema pega
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


def _cfg() -> tuple[str, str] | None:
    from core.segredos import segredo

    token = segredo("ROBO_GITHUB_TOKEN") or segredo("BACKUP_GITHUB_TOKEN")
    repo = segredo("ROBO_GITHUB_REPO") or segredo("BACKUP_GITHUB_REPO")
    if not token or not repo or "/" not in str(repo):
        return None
    return str(token).strip(), str(repo).strip().strip("/")


def configurado() -> bool:
    return _cfg() is not None


def _api(metodo: str, caminho: str, corpo: dict | None = None, raw: bool = False):
    """GitHub do repositório de entrada (contents API). 404 = None."""
    import json
    import urllib.error
    import urllib.request

    from services.backup_auto import BackupErro

    token, repo = _cfg()
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(f"https://api.github.com/repos/{repo}/contents/{caminho}", data=dados, method=metodo,
                               headers={"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28",
                                        "User-Agent": "ecossistema",
                                        "Accept": "application/vnd.github.raw+json" if raw
                                        else "application/vnd.github+json",
                                        **({"Content-Type": "application/json"} if dados else {})})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            c = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise BackupErro(f"GitHub respondeu {e.code}: {e.read().decode(errors='ignore')[:200]}") from e
    except OSError as e:
        raise BackupErro(f"Sem conexão com o GitHub: {e}") from e
    return c if raw else (json.loads(c) if c else {})


def pendentes() -> list[dict]:
    """Arquivos esperando na entrada (mais antigos primeiro)."""
    itens = _api("GET", f"{PASTA}?t={time.time_ns()}") or []
    arqs = [i for i in itens if isinstance(i, dict) and i.get("type") == "file" and i["name"].count("__") >= 3]
    return sorted(arqs, key=lambda i: i["name"].split("__")[2])


def _operacao(revenda: str) -> int:
    from repositories import operacoes_repo

    for o in operacoes_repo.listar(apenas_ativas=False):
        if slug(o["nome"]) == revenda:
            return int(o["id"])
    raise RuntimeError(f"Revenda '{revenda}' não encontrada no sistema (confira 'revenda' no config.toml do robô).")


def _apagar(item: dict, motivo: str) -> None:
    _api("DELETE", urllib.parse.quote(item["path"]), {"message": motivo, "sha": item["sha"]})


def _mover_para_erro(item: dict, dados: bytes) -> None:
    import base64

    _api("PUT", f"{PASTA}/erro/{urllib.parse.quote(item['name'])}",
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
        from services import robo_service as rs

        saida = []
        for item in pendentes():
            tipo, revenda, _quando, resto = item["name"].split("__", 3)
            dados = _api("GET", urllib.parse.quote(item["path"]), raw=True)
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


# --- 🔐 pedidos do robô no servidor (código do celular / avisos) -------------------------------------------------
_PED = {"quando": 0.0, "lista": []}


def pedidos(cache_seg: int = 20) -> list[dict]:
    """Pedidos abertos do robô (mais antigos primeiro). Consulta o GitHub no máximo a cada `cache_seg` segundos."""
    import json

    if not configurado():
        return []
    if time.time() - _PED["quando"] < cache_seg:
        return _PED["lista"]
    _PED["quando"] = time.time()
    try:
        itens = _api("GET", f"{PASTA}/_pedidos?t={time.time_ns()}") or []
        out = []
        for i in sorted([i for i in itens if isinstance(i, dict) and i.get("name", "").endswith(".json")],
                        key=lambda i: i["name"]):
            d = json.loads(_api("GET", urllib.parse.quote(i["path"]), raw=True) or b"{}")
            out.append({**d, "_sha": i["sha"], "_path": i["path"]})
        _PED["lista"] = out
    except Exception:  # noqa: BLE001 — nunca atrapalha a tela
        pass
    return _PED["lista"]


def responder(pedido: dict, codigo: str | None) -> None:
    """Grava a resposta (o robô pega em até 10 s) e fecha o pedido. codigo=None só dispensa (avisos)."""
    import base64

    from services.backup_auto import BackupErro
    from services.erros import RegraNegocioError

    try:
        _responder(pedido, codigo, base64)
    except BackupErro as e:
        raise RegraNegocioError(f"Não consegui falar com o GitHub: {e}") from e


def _responder(pedido: dict, codigo: str | None, base64) -> None:
    if codigo:
        _api("PUT", f"{PASTA}/_respostas/{pedido['id']}.txt",
             {"message": "Ecossistema: código para o robô", "content": base64.b64encode(codigo.strip().encode()).decode()})
    _api("DELETE", urllib.parse.quote(pedido["_path"]), {"message": "Ecossistema: pedido atendido",
                                                         "sha": pedido["_sha"]})
    _PED["quando"] = 0.0
