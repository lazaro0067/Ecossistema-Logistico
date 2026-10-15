"""💾 Backup automático num repositório PRIVADO do GitHub.

Por que: no Streamlit Cloud sem DATABASE_URL o banco (SQLite) é apagado quando o servidor reinicia
(novo código, app parado por falta de uso, "Reboot"). Com o backup automático:

  • a cada AUTO_MINUTOS minutos (e ao desligar o servidor) o sistema gera o backup e, se algo mudou,
    grava no repositório privado (cada gravação vira um commit — dá para voltar versões antigas);
  • ao ligar com o banco vazio (só o admin), o sistema baixa o último backup e restaura sozinho.

Configuração (Streamlit › Settings › Secrets):
    BACKUP_GITHUB_TOKEN = "github_pat_..."     # token fine-grained: só esse repositório, Contents: Read and write
    BACKUP_GITHUB_REPO  = "usuario/eco-backup"  # repositório PRIVADO
O repositório público do sistema NUNCA recebe o backup (tem senhas criptografadas, CPF etc.).
"""
import atexit
import base64
import datetime as dt
import hashlib
import io
import json
import threading
import time
import urllib.error
import urllib.request
import zipfile

from core import tempo
from core.segredos import segredo
from database.connection import query_one

AUTO_MINUTOS = 5
CAMINHO = "backup/ecossistema.zip"
_API = "https://api.github.com"

_lock = threading.Lock()
_estado = {"iniciado": False, "ultimo_hash": None, "ultimo_envio": None, "ultima_verificacao": None,
           "erro": None, "restaurado": None, "pode_salvar": False}


class BackupErro(Exception):
    pass


# --- GitHub -----------------------------------------------------------------------------------
def _cfg() -> tuple[str, str] | None:
    token, repo = segredo("BACKUP_GITHUB_TOKEN"), segredo("BACKUP_GITHUB_REPO")
    if not token or not repo or "/" not in str(repo):
        return None
    return str(token).strip(), str(repo).strip().strip("/")


def configurado() -> bool:
    return _cfg() is not None


def _req(metodo: str, url: str, corpo: dict | None = None, raw: bool = False):
    token, _ = _cfg()
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(url, data=dados, method=metodo, headers={
        "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ecossistema",
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        **({"Content-Type": "application/json"} if dados else {})})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            conteudo = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        msg = e.read().decode(errors="ignore")[:200]
        raise BackupErro(f"GitHub respondeu {e.code}: {msg}") from e
    except OSError as e:
        raise BackupErro(f"Sem conexão com o GitHub: {e}") from e
    return conteudo if raw else (json.loads(conteudo) if conteudo else {})


def _url(caminho: str = "") -> str:
    _, repo = _cfg()
    return f"{_API}/repos/{repo}{caminho}"


def verificar_repositorio() -> None:
    """O backup só vai para repositório privado."""
    info = _req("GET", _url())
    if info is None:
        raise BackupErro("Repositório de backup não encontrado (confira BACKUP_GITHUB_REPO e o acesso do token).")
    if not info.get("private"):
        raise BackupErro("O repositório de backup é PÚBLICO — o backup tem dados pessoais. Torne-o privado.")


def _sha_atual() -> str | None:
    # o parâmetro muda a cada chamada: evita o GitHub devolver a versão anterior em cache logo após um envio
    info = _req("GET", _url(f"/contents/{CAMINHO}?t={time.time_ns()}"))
    return info.get("sha") if info else None


def baixar() -> bytes | None:
    return _req("GET", _url(f"/contents/{CAMINHO}"), raw=True)


def enviar(arquivo: bytes, mensagem: str) -> None:
    """Envia o backup. Se outro envio (outra aba/instância) gravou no meio do caminho, o GitHub responde 409
    (versão do arquivo mudou): busca a versão nova e tenta de novo."""
    conteudo = base64.b64encode(arquivo).decode()
    for tentativa in range(4):
        corpo = {"message": mensagem, "content": conteudo}
        sha = _sha_atual()
        if sha:
            corpo["sha"] = sha
        try:
            _req("PUT", _url(f"/contents/{CAMINHO}"), corpo)
            return
        except BackupErro as e:
            conflito = "respondeu 409" in str(e) or ("respondeu 422" in str(e) and "sha" in str(e).lower())
            if not conflito or tentativa == 3:
                raise
            time.sleep(2 + 2 * tentativa)


# --- Salvar / restaurar -----------------------------------------------------------------------
def _hash_conteudo(arquivo: bytes) -> str:
    """Hash das tabelas (sem a data do manifesto) — só envia quando algo mudou."""
    h = hashlib.sha256()
    with zipfile.ZipFile(io.BytesIO(arquivo)) as z:
        for n in sorted(z.namelist()):
            if n != "manifesto.json":
                h.update(n.encode())
                h.update(z.read(n))
    return h.hexdigest()


def _n_usuarios() -> int:
    r = query_one("SELECT COUNT(*) AS n FROM usuarios")
    return int(r["n"]) if r else 0


def salvar_agora(motivo: str = "automático", forcar: bool = False) -> bool:
    """Gera o backup e envia se mudou. Devolve True se enviou."""
    from services import backup_service

    if not configurado():
        raise BackupErro("Backup automático não configurado.")
    with _lock:
        if not _estado["pode_salvar"]:
            raise BackupErro("Salvamento pausado: a conferência do backup ao ligar não terminou. "
                             "Use “Tentar de novo”.")
        arquivo = backup_service.exportar()
        h = _hash_conteudo(arquivo)
        _estado["ultima_verificacao"] = tempo.agora()
        if h == _estado["ultimo_hash"] and not forcar:
            return False
        enviar(arquivo, f"Backup {motivo} · {tempo.agora():%d/%m/%Y %H:%M}")
        _estado.update(ultimo_hash=h, ultimo_envio=tempo.agora(), erro=None, pode_salvar=True)
        return True


def restaurar_se_vazio() -> str | None:
    """Ao ligar: banco novo (só o admin) + backup existente → restaura tudo. Devolve a mensagem."""
    from services import backup_service

    if _n_usuarios() > 1:
        return None
    arquivo = baixar()
    if not arquivo:
        return None
    man = backup_service.ler_manifesto(arquivo)
    if int(man.get("tabelas", {}).get("usuarios", 0)) <= _n_usuarios():
        return None
    backup_service.importar(arquivo)
    _estado["ultimo_hash"] = _hash_conteudo(arquivo)
    return f"Banco restaurado automaticamente do backup de {man.get('gerado_em', '?')}."


def _ciclo() -> None:
    while True:
        time.sleep(AUTO_MINUTOS * 60)
        try:
            salvar_agora()
        except Exception as e:  # noqa: BLE001 — nunca derruba o app
            _estado["erro"] = f"{tempo.agora():%d/%m %H:%M} · {e}"


def _ao_desligar() -> None:
    try:
        salvar_agora("ao desligar o servidor")
    except Exception:
        pass


def iniciar() -> None:
    """Chamado uma vez por processo, depois do init_db: restaura (se preciso) e liga o salvamento automático."""
    with _lock:
        if _estado["iniciado"] or not configurado():
            return
        _estado["iniciado"] = True
    try:
        verificar_repositorio()
        _estado["restaurado"] = restaurar_se_vazio()
        _estado["pode_salvar"] = True  # só salva depois de conferir/restaurar (não sobrescreve o backup bom)
    except Exception as e:  # noqa: BLE001
        _estado["erro"] = f"{tempo.agora():%d/%m %H:%M} · {e}"
        return
    if not any(t.name == "backup-auto" and t.is_alive() for t in threading.enumerate()):
        threading.Thread(target=_ciclo, name="backup-auto", daemon=True).start()
        atexit.register(_ao_desligar)
    # o 1º backup roda em segundo plano, 1 minuto depois de ligar (não pesa na partida do servidor)
    threading.Thread(target=_primeiro_backup, name="backup-inicio", daemon=True).start()


def _primeiro_backup() -> None:
    time.sleep(60)
    try:
        salvar_agora("ao iniciar")
    except Exception as e:  # noqa: BLE001
        _estado["erro"] = f"{tempo.agora():%d/%m %H:%M} · {e}"


def tentar_de_novo() -> None:
    _estado.update(iniciado=False, erro=None)
    iniciar()


def estado() -> dict:
    return dict(_estado, configurado=configurado())
