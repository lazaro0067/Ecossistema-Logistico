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


def _sha_atual(caminho: str = CAMINHO) -> str | None:
    # o parâmetro muda a cada chamada: evita o GitHub devolver a versão anterior em cache logo após um envio
    info = _req("GET", _url(f"/contents/{caminho}?t={time.time_ns()}"))
    return info.get("sha") if isinstance(info, dict) and info else None


def baixar(caminho: str = CAMINHO) -> bytes | None:
    return _req("GET", _url(f"/contents/{caminho}"), raw=True)


def enviar(arquivo: bytes, mensagem: str, caminho: str = CAMINHO) -> None:
    """Envia o backup. Se outro envio (outra aba/instância) gravou no meio do caminho, o GitHub responde 409
    (versão do arquivo mudou): busca a versão nova e tenta de novo."""
    conteudo = base64.b64encode(arquivo).decode()
    for tentativa in range(4):
        corpo = {"message": mensagem, "content": conteudo}
        sha = _sha_atual(caminho)
        if sha:
            corpo["sha"] = sha
        try:
            _req("PUT", _url(f"/contents/{caminho}"), corpo)
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


# --- Bases de relatório (vendas, compra, PCD, 02.05.02, razão…): um arquivo por tabela -------------------------
# Ficam fora do backup principal (são grandes). Sem isso, a cada Reboot do Streamlit Cloud (banco temporário)
# elas sumiam e a Gestão Corporativa ficava vazia. Agora: backup separado e restauração quando a tabela está vazia.
PASTA_BASES = "backup/bases"
BASES_MINUTOS = 5  # confere a cada 5 min (barato: só COUNT/MAX); envia só a base que mudou
_MAX_BYTES_BASE = 70 * 1024 * 1024  # limite de arquivo do GitHub (com folga)
_bases = {"assin": {}, "ultimo": 0.0, "restaurado": False, "msg": None, "erro": None}


def _assinatura(t: str) -> str:
    """Muda quando a tabela muda: linhas + maior data de carga (quando a tabela tem)."""
    from database.connection import get_conn
    from services.backup_service import _colunas

    with get_conn() as conn:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        cols = [c for c in _colunas(conn, t) if c in ("importado_em", "dt_atualizacao", "atualizado_em", "data",
                                                     "mes", "criado_em")]
        extra = [str(conn.execute(f"SELECT MAX({c}) FROM {t}").fetchone()[0]) for c in cols]
    return f"{n}|{'|'.join(extra)}"


def _tabelas_bases() -> list[str]:
    from database.connection import get_conn
    from services.backup_service import BASES_RELATORIO, _tabelas_do_banco

    with get_conn() as conn:
        return [t for t in _tabelas_do_banco(conn) if t in BASES_RELATORIO]


def restaurar_bases_vazias() -> list[str]:
    """Base de relatório vazia no banco + arquivo no backup → restaura. Devolve as tabelas restauradas."""
    from database.connection import get_conn
    from services import backup_service

    feitas = []
    for t in _tabelas_bases():
        with get_conn() as conn:
            if conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]:
                continue
        arq = baixar(f"{PASTA_BASES}/{t}.zip")
        if not arq:
            continue
        backup_service.importar(arq, [t])
        feitas.append(t)
    return feitas


def salvar_bases(forcar: bool = False) -> list[str]:
    """Envia as bases que mudaram desde o último envio (nunca envia tabela vazia por cima de um backup)."""
    from services import backup_service

    if not _bases["restaurado"]:
        return []
    enviadas = []
    for t in _tabelas_bases():
        assin = _assinatura(t)
        if assin.startswith("0|") or (assin == _bases["assin"].get(t) and not forcar):
            continue
        arq = backup_service.exportar(so_tabelas={t})
        if len(arq) > _MAX_BYTES_BASE:
            _bases["erro"] = f"{t}: {len(arq) // 1024 ** 2} MB — grande demais para o backup no GitHub."
            continue
        enviar(arq, f"Backup base {t} · {tempo.agora():%d/%m/%Y %H:%M}", f"{PASTA_BASES}/{t}.zip")
        _bases["assin"][t] = assin
        enviadas.append(t)
    _bases["ultimo"] = time.time()
    return enviadas


def _iniciar_bases() -> None:
    """Ao ligar (em segundo plano): restaura as bases vazias e só então libera o envio delas."""
    try:
        feitas = restaurar_bases_vazias()
        if feitas:
            _bases["msg"] = f"Bases de relatório restauradas do backup: {', '.join(feitas)}."
        for t in _tabelas_bases():  # o que já está no backup não precisa reenviar logo ao ligar
            if t in feitas:
                _bases["assin"][t] = _assinatura(t)
    except Exception as e:  # noqa: BLE001
        _bases["erro"] = f"{tempo.agora():%d/%m %H:%M} · restaurar bases: {e}"
    finally:
        _bases["restaurado"] = True


def _sou_o_atual() -> bool:
    """Depois de uma atualização "a quente" (o Streamlit troca o código sem reiniciar), o laço da versão antiga
    encerra e o da versão nova assume — senão o backup ficava rodando com o código velho (ou parado)."""
    import sys

    return sys.modules.get(__name__) is _ESTE_MODULO


def _ciclo() -> None:
    primeiro = True
    while True:
        # 1ª volta em 1 min (não espera 5 min depois de ligar/atualizar); depois a cada AUTO_MINUTOS
        time.sleep(60 if primeiro else AUTO_MINUTOS * 60)
        primeiro = False
        if not _sou_o_atual():
            return
        try:
            salvar_agora()
        except Exception as e:  # noqa: BLE001 — nunca derruba o app
            _estado["erro"] = f"{tempo.agora():%d/%m %H:%M} · {e}"
        if time.time() - _bases["ultimo"] >= BASES_MINUTOS * 60:
            try:
                salvar_bases()
            except Exception as e:  # noqa: BLE001
                _bases["erro"] = f"{tempo.agora():%d/%m %H:%M} · {e}"


def _ao_desligar() -> None:
    try:
        salvar_agora("ao desligar o servidor")
    except Exception:
        pass
    try:
        salvar_bases()
    except Exception:  # noqa: BLE001
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
    if not any(t.name == _NOME_CICLO and t.is_alive() for t in threading.enumerate()):
        threading.Thread(target=_ciclo, name=_NOME_CICLO, daemon=True).start()
        atexit.register(_ao_desligar)
    # o 1º backup roda em segundo plano, 1 minuto depois de ligar (não pesa na partida do servidor)
    threading.Thread(target=_primeiro_backup, name="backup-inicio", daemon=True).start()
    threading.Thread(target=_iniciar_bases, name="backup-bases", daemon=True).start()


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
    return dict(_estado, configurado=configurado(), bases=dict(_bases))


_ESTE_MODULO = __import__("sys").modules[__name__]
_NOME_CICLO = f"backup-auto-{id(_ESTE_MODULO)}"  # um laço por versão carregada do código
