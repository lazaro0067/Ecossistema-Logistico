"""🤖 Robô de relatórios — baixa os relatórios dos sites (Promax, WMS…), salva na pasta e importa no sistema.

Roda no computador da empresa (Windows), agendado. Cada relatório tem uma "receita" (robo/receitas/<nome>.py):
os cliques para entrar no site e exportar o arquivo, gravados uma vez com `python robo.py --gravar <nome>`.

Comandos (na pasta robo):
  python robo.py --senha promax          guarda a senha do site no cofre do Windows (nunca em arquivo)
  python robo.py --senha banco           guarda o DATABASE_URL do sistema no cofre do Windows
  python robo.py --entrar powerbi        abre o site no navegador do robô para VOCÊ entrar (o login fica salvo)
  python robo.py --gravar vendas         abre o navegador gravando os cliques → vira a receita "vendas"
  python robo.py --testar vendas         roda só essa receita com o navegador aparecendo
  python robo.py                         roda todos os relatórios do config.toml (é o que o agendador chama)
  python robo.py --so vendas,compra      roda só esses
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import importlib.util
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

AQUI = Path(__file__).resolve().parent
APP = AQUI.parent
sys.path.insert(0, str(APP))
COFRE = "eco-robo"
RECEITAS = AQUI / "receitas"
PERFIL = AQUI / "perfil_navegador"  # o navegador do robô guarda aqui os logins (Microsoft/Power BI, Promax…)


# --- configuração ------------------------------------------------------------------------------------------------
def config() -> dict:
    import tomllib

    arq = AQUI / "config.toml"
    if not arq.exists():
        sys.exit("Falta o robo/config.toml — copie o config.exemplo.toml para config.toml e preencha.")
    return tomllib.loads(arq.read_text(encoding="utf-8"))


def cofre_ler(nome: str) -> str | None:
    import keyring

    return keyring.get_password(COFRE, nome)


def cofre_gravar(nome: str) -> None:
    import keyring

    v = None
    try:  # janelinha: no Prompt o campo escondido não aceita colar (Ctrl+V)
        import tkinter as tk
        from tkinter import simpledialog

        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        v = simpledialog.askstring("Robô de relatórios — cofre do Windows",
                                   f"Cole (Ctrl+V) ou digite o valor de '{nome}' e clique em OK:", show="•",
                                   parent=raiz)
        raiz.destroy()
    except Exception:  # noqa: BLE001 — sem janela: pede no Prompt
        v = getpass.getpass(f"Digite o valor de '{nome}' (não aparece na tela): ")
    v = (v or "").strip().strip('"').strip()
    if not v:
        sys.exit("Nada digitado.")
    keyring.set_password(COFRE, nome, v)
    print(f"✅ '{nome}' guardado no cofre do Windows.")


class Log:
    def __init__(self):
        (AQUI / "logs").mkdir(exist_ok=True)
        self.arq = AQUI / "logs" / f"{dt.date.today():%Y-%m-%d}.log"

    def __call__(self, msg: str) -> None:
        linha = f"{dt.datetime.now():%H:%M:%S} {msg}"
        with open(self.arq, "a", encoding="utf-8") as f:  # grava antes: o arquivo é o registro que vale
            f.write(linha + "\n")
        try:
            print(linha, flush=True)
        except Exception:  # noqa: BLE001 — tela sem emoji (rodando pelo agendador) não pode derrubar o robô
            print(linha.encode("ascii", "replace").decode(), flush=True)


log = Log()


# --- contexto que a receita recebe -------------------------------------------------------------------------------
class Ctx:
    """O que a receita usa: login do site, datas prontas e onde salvar o download."""

    def __init__(self, site: dict, nome_site: str, pasta_dia: Path, relatorio: str, hoje: dt.date | None = None):
        self.url = site.get("url", "")
        self.usuario = site.get("usuario", "")
        self.senha = cofre_ler(nome_site) or ""
        self.relatorio = relatorio
        self.pasta = pasta_dia
        h = hoje or dt.date.today()
        self.hoje = h
        self.ontem = h - dt.timedelta(days=1)
        self.ini_mes = h.replace(day=1)
        prox = (self.ini_mes + dt.timedelta(days=32)).replace(day=1)
        self.fim_mes = prox - dt.timedelta(days=1)
        self.ini_mes_ant = (self.ini_mes - dt.timedelta(days=1)).replace(day=1)
        self.fim_mes_ant = self.ini_mes - dt.timedelta(days=1)
        for nome in ("hoje", "ontem", "ini_mes", "fim_mes", "ini_mes_ant", "fim_mes_ant"):
            d = getattr(self, nome)
            setattr(self, f"{nome}_br", d.strftime("%d/%m/%Y"))
        self.arquivo: Path | None = None
        self.revenda = ""    # revenda do sistema deste relatório (ex.: Lima Barreiras)
        self.operacao = ""   # como a operação aparece no site (operacao_site no config; padrão = revenda)

    def login_microsoft(self, page, espera_seg: int = 300) -> None:
        """Se o site (Power BI) mandar para o login da Microsoft: preenche e-mail e senha (do cofre), pede o código
        que chega no celular numa janelinha e confirma "continuar conectado". Já logado = não faz nada."""
        import time as _t

        page.wait_for_timeout(4000)
        fim = _t.time() + espera_seg
        avisou = False

        def ve(sel: str) -> bool:
            try:
                return page.locator(sel).first.is_visible()
            except Exception:  # noqa: BLE001
                return False
        while _t.time() < fim:
            if not re.search(r"login\.(microsoftonline|live)\.com|login\.microsoft", page.url):
                return
            if ve('input[name="loginfmt"]'):
                if not self.usuario:
                    raise RuntimeError("A Microsoft pediu o e-mail: coloque usuario = \"seu@email\" em [powerbi] no "
                                       "config.toml (ou entre com robo.bat --entrar powerbi).")
                page.fill('input[name="loginfmt"]', self.usuario)
                page.click('input[type="submit"]')
            elif ve('input[name="passwd"]'):
                if not self.senha:
                    raise RuntimeError("A Microsoft pediu a senha: guarde com robo.bat --senha powerbi.")
                page.fill('input[name="passwd"]', self.senha)
                page.click('input[type="submit"]')
            elif ve('input[name="otc"]'):
                codigo = pedir_codigo("O Power BI mandou um código para o seu celular.\nDigite o código:")
                if not codigo:
                    raise RuntimeError("Código do celular não informado.")
                page.fill('input[name="otc"]', codigo.strip())
                page.click('input[type="submit"]')
            elif ve("#idSIButton9") and ve("#KmsiCheckboxField, #idBtn_Back"):  # "Continuar conectado?"
                if ve("#KmsiCheckboxField"):
                    page.check("#KmsiCheckboxField")
                page.click("#idSIButton9")
            elif not avisou and ve("#idRichContext_DisplaySign, .displaySign"):
                numero = page.locator("#idRichContext_DisplaySign, .displaySign").first.inner_text()
                avisar(f"Aprove o login no app Microsoft Authenticator do celular digitando o número {numero}.")
                avisou = True
            page.wait_for_timeout(2500)
        raise RuntimeError("O login da Microsoft não terminou a tempo.")

    def salvar(self, download) -> Path:
        """Guarda o arquivo baixado na pasta do dia (nome original, com o relatório na frente)."""
        nome = f"{self.relatorio}__{download.suggested_filename}"
        destino = self.pasta / nome
        download.save_as(destino)
        self.arquivo = destino
        return destino


def navegador(cfg: dict, site: str, rel: dict | None = None) -> str | None:
    """Qual navegador usar: "msedge" (Edge instalado no Windows), "chrome" ou "chromium" (o do robô)."""
    n = (rel or {}).get("navegador") or cfg.get(site, {}).get("navegador") or cfg.get("navegador") or "chromium"
    return None if str(n).lower() == "chromium" else str(n).lower()


def pedir_codigo(texto: str) -> str | None:
    """Janelinha para digitar o código que chegou no celular (sem janela: pede no Prompt)."""
    log("🔐 " + texto.replace("\n", " "))
    try:
        import tkinter as tk
        from tkinter import simpledialog

        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        v = simpledialog.askstring("Robô de relatórios — código de acesso", texto, parent=raiz)
        raiz.destroy()
        return v
    except Exception:  # noqa: BLE001 — sem janela (servidor sem tela): pede no Prompt
        try:
            return input(texto + " ")
        except Exception:  # noqa: BLE001
            return None


def avisar(texto: str) -> None:
    log("📱 " + texto)
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        messagebox.showinfo("Robô de relatórios", texto, parent=raiz)
        raiz.destroy()
    except Exception:  # noqa: BLE001
        pass


# --- receitas ----------------------------------------------------------------------------------------------------
def carregar_receita(nome: str):
    arq = RECEITAS / f"{nome}.py"
    if not arq.exists():
        raise FileNotFoundError(f"Receita '{nome}' não existe — grave com: python robo.py --gravar {nome}")
    spec = importlib.util.spec_from_file_location(f"receita_{nome}", arq)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def baixar(rel: dict, cfg: dict, ver: bool = False) -> Path:
    from playwright.sync_api import sync_playwright

    site = rel.get("site", "promax")
    pasta_dia = Path(cfg["pasta"]) / f"{dt.date.today():%Y-%m-%d}"
    pasta_dia.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(cfg.get(site, {}), site, pasta_dia, rel["nome"])
    ctx.revenda = rel.get("revenda") or cfg.get("revenda", "")
    ctx.operacao = str(rel.get("operacao_site") or ctx.revenda)  # a mesma receita serve para todas as operações
    receita = carregar_receita(rel.get("receita", rel["nome"]))
    # Power BI/Microsoft não carrega direito com o navegador escondido (login e desenho do relatório): por padrão
    # ele abre visível e fecha sozinho no fim. Para esconder: mostrar = false no relatório ou na seção do site.
    padrao = site == "powerbi"
    mostrar = ver or bool(rel.get("mostrar", cfg.get(site, {}).get("mostrar", cfg.get("mostrar", padrao))))
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PERFIL), channel=navegador(cfg, site, rel), headless=not mostrar, accept_downloads=True,
            locale="pt-BR", viewport={"width": 1440, "height": 900})
        context.set_default_timeout(int(rel.get("espera_seg", cfg.get("espera_seg", 120))) * 1000)
        page = context.new_page()
        try:
            r = receita.baixar(page, ctx)
        except Exception:
            try:  # print da tela no momento do erro, para ver onde parou
                page.screenshot(path=str(AQUI / "logs" / f"{dt.date.today():%Y-%m-%d}_{rel['nome']}_erro.png"))
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            context.close()
    arq = Path(r) if r else ctx.arquivo
    if not arq or not arq.exists():
        raise RuntimeError("A receita terminou sem baixar arquivo.")
    return arq


# --- gravar e converter receita --------------------------------------------------------------------------------
_MODELO = '''"""Receita: {nome} — gerada de uma gravação em {quando}. Ajuste se o site mudar."""


def baixar(page, ctx):
{corpo}
'''


def entrar(cfg: dict, site: str) -> None:
    """Abre o navegador do robô no site para VOCÊ entrar (login, código no celular…). O login fica salvo no perfil
    do robô e ele reaproveita nas próximas vezes. Feche o navegador quando terminar."""
    from playwright.sync_api import sync_playwright

    url = cfg.get(site, {}).get("url")
    if not url:
        sys.exit(f"Falta a url do site [{site}] no config.toml.")
    print("Entre no site normalmente (marque 'manter conectado' se aparecer). Depois feche o navegador.")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(PERFIL), channel=navegador(cfg, site), headless=False,
                                                       locale="pt-BR", viewport={"width": 1440, "height": 900})
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url)
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001 — navegador fechado
            pass
        try:
            context.close()
        except Exception:  # noqa: BLE001
            pass
    print("✅ Login guardado no perfil do robô.")


def gravar(nome: str, cfg: dict, site: str) -> None:
    url = cfg.get(site, {}).get("url")
    if not url:
        sys.exit(f"Falta a url do site [{site}] no config.toml.")
    RECEITAS.mkdir(exist_ok=True)
    bruto = RECEITAS / f"_gravado_{nome}.py"
    print("Vai abrir o navegador gravando. Faça o caminho completo: entrar, abrir o relatório, filtrar e EXPORTAR.")
    print("Use as datas de HOJE / ontem / 1º do mês que o robô troca sozinho pelas datas do dia em que rodar.")
    print("Quando o arquivo terminar de baixar, feche o navegador.")
    canal = navegador(cfg, site)
    cmd = [sys.executable, "-m", "playwright", "codegen", "--target", "python", "-o", str(bruto),
           "--user-data-dir", str(PERFIL), "--viewport-size", "1440, 900"]
    if canal:
        cmd += ["--channel", canal]
    subprocess.run(cmd + [url], check=False)
    if not bruto.exists():
        sys.exit("Nada gravado.")
    converter(nome, bruto, cfg, site)


def converter(nome: str, bruto: Path, cfg: dict, site: str) -> None:
    """Transforma a gravação do Playwright na receita: tira senha/usuário (vira ctx.senha/ctx.usuario), troca as
    datas digitadas pelas datas do dia e salva o download na pasta."""
    txt = bruto.read_text(encoding="utf-8")
    linhas = txt.splitlines()
    # o corpo começa depois da abertura do navegador (browser/context/page = …), que muda conforme o modo da gravação
    abre = [i for i, l in enumerate(linhas) if re.match(r"\s*(browser|context|page)\s*=", l)]
    if not abre:
        sys.exit("Gravação vazia — grave de novo.")
    ini = abre[0]
    while ini < len(linhas) and re.match(r"\s*(browser|context|page)\s*=", linhas[ini]):
        ini += 1
    fim = next((i for i, l in enumerate(linhas) if l.strip().startswith("# ----") or "context.close()" in l), len(linhas))
    corpo = [l[4:] if l.startswith("    ") else l for l in linhas[ini:fim] if l.strip()
             and "edge://" not in l and "chrome://" not in l]
    texto = "\n".join(corpo)
    senha = cofre_ler(site) or ""
    usuario = cfg.get(site, {}).get("usuario", "")
    if senha:
        texto = texto.replace(repr(senha), "ctx.senha").replace(f'"{senha}"', "ctx.senha")
    if usuario:
        texto = texto.replace(f'"{usuario}"', "ctx.usuario")
    url = cfg.get(site, {}).get("url", "")
    if url:
        texto = texto.replace(f'page.goto("{url}")', "page.goto(ctx.url)")
    c = Ctx({}, site, Path("."), nome)
    for campo in ("hoje", "ontem", "ini_mes", "fim_mes", "ini_mes_ant", "fim_mes_ant"):
        d = getattr(c, campo)
        for fmt, suf in (("%d/%m/%Y", "_br"), ("%d%m%Y", "_br.replace('/', '')"), ("%Y-%m-%d", ".isoformat()")):
            texto = texto.replace(f'"{d.strftime(fmt)}"', f"ctx.{campo}{suf}")
    if "download_info.value" in texto:
        texto = re.sub(r"^(\s*)(\w+) = download_info\.value\s*$", r"\1\2 = download_info.value\n\1return ctx.salvar(\2)",
                       texto, flags=re.M)
    else:
        texto += "\n# ATENÇÃO: a gravação não pegou o download — refaça clicando em exportar/baixar no fim."
    if senha and senha in texto:
        texto = texto.replace(senha, "***")
    corpo_final = "\n".join("    " + l for l in texto.splitlines())
    destino = RECEITAS / f"{nome}.py"
    destino.write_text(_MODELO.format(nome=nome, quando=f"{dt.date.today():%d/%m/%Y}", corpo=corpo_final),
                       encoding="utf-8")
    bruto.unlink(missing_ok=True)  # a gravação crua pode ter a senha: apaga
    print(f"✅ Receita salva: {destino}")
    print(f"   Teste com: python robo.py --testar {nome}")


# --- execução ------------------------------------------------------------------------------------------------------
def preparar_sistema(cfg: dict) -> bool:
    """True = conectado ao banco do sistema (baixa e importa). False = sem banco: só baixa e salva na pasta."""
    url = (cofre_ler("banco") or "").strip().strip('"')
    if not url.startswith(("postgresql://", "postgres://")):
        if nuvem(cfg):
            log("☁️ Modo nuvem: baixa, salva na pasta e envia para o sistema importar.")
        else:
            log("⚠️ Sem o banco do sistema e sem o envio para a nuvem (robo.bat --senha github): modo TESTE — só "
                "baixa e salva na pasta.")
        return False
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("ECO_DATA_DIR", str(Path(tempfile.gettempdir()) / "eco_robo"))
    for k, v in (cfg.get("sistema") or {}).items():
        os.environ.setdefault(str(k).upper(), str(v))
    return True


# --- envio para o sistema na nuvem (pelo repositório PRIVADO do backup no GitHub) ----------------------------------
def slug(txt: str) -> str:
    """Mesmo código do sistema (services/robo_nuvem.py): 'Lima Rio Verde' → 'lima-rio-verde'."""
    import unicodedata

    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def nuvem(cfg: dict) -> tuple[str, str] | None:
    """(token, repositório) se o envio para a nuvem estiver ligado: robo.bat --senha github + repo_nuvem no config."""
    repo = str(cfg.get("repo_nuvem") or "").strip().strip("/")
    if not repo or "/" not in repo:
        return None
    try:
        token = (cofre_ler("github") or "").strip()
    except Exception:  # noqa: BLE001
        token = ""
    return (token, repo) if token else None


def enviar_nuvem(rel: dict, cfg: dict, arq: Path) -> str:
    """Manda o arquivo para entrada/ no repositório privado; o sistema importa sozinho (em até ~10 min, ou na hora
    pelo botão em 📥 Atualizar relatórios › 🤖 Robô)."""
    import base64
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    token, repo = nuvem(cfg)
    tipo = rel.get("importar", "so_baixar")
    revenda = rel.get("revenda") or cfg["revenda"]
    nome = f"{tipo}__{slug(revenda)}__{dt.datetime.now():%Y%m%d-%H%M%S}__{slug(arq.stem)}{arq.suffix.lower()}"
    url = f"https://api.github.com/repos/{repo}/contents/entrada/{urllib.parse.quote(nome)}"
    corpo = json.dumps({"message": f"robô: {rel['nome']} ({revenda})",
                        "content": base64.b64encode(arq.read_bytes()).decode()}).encode()
    r = urllib.request.Request(url, data=corpo, method="PUT", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "eco-robo",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120):
            pass
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub respondeu {e.code}: {e.read().decode(errors='ignore')[:200]}") from e
    return nome


def so_baixar(rel: dict, cfg: dict, ver: bool) -> bool:
    try:
        log(f"[{rel['nome']}] baixando…")
        arq = baixar(rel, cfg, ver)
        log(f"[{rel['nome']}] ✅ baixado e salvo: {arq} ({arq.stat().st_size / 1024 ** 2:.1f} MB)")
        if nuvem(cfg) and rel.get("importar", "so_baixar") != "so_baixar":
            nome = enviar_nuvem(rel, cfg, arq)
            log(f"[{rel['nome']}] ☁️ enviado para o sistema ({nome}) — ele importa em instantes.")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"[{rel['nome']}] ❌ {type(e).__name__}: {e}")
        (AQUI / "logs" / f"{dt.date.today():%Y-%m-%d}_{rel['nome']}_erro.txt").write_text(
            traceback.format_exc(), encoding="utf-8")
        return False


def operacao(nome: str) -> int:
    from repositories import operacoes_repo

    o = operacoes_repo.buscar_por_nome(nome)
    if not o:
        raise RuntimeError(f"Revenda '{nome}' não encontrada no sistema (confira o nome no config.toml).")
    return int(o["id"])


def rodar(rel: dict, cfg: dict, ver: bool = False) -> bool:
    from robo import importadores
    from services import robo_service

    tipo = rel.get("importar", "so_baixar")
    op = operacao(rel.get("revenda") or cfg["revenda"])
    eid = robo_service.inicio(op, tipo, socket.gethostname())
    tentativas = int(rel.get("tentativas", cfg.get("tentativas", 2)))
    arq = None
    for t in range(1, tentativas + 1):
        try:
            log(f"[{rel['nome']}] baixando (tentativa {t})…")
            arq = baixar(rel, cfg, ver)
            log(f"[{rel['nome']}] baixado: {arq.name} ({arq.stat().st_size / 1024 ** 2:.1f} MB)")
            msg = importadores.importar(tipo, arq, op)
            log(f"[{rel['nome']}] ✅ {msg}")
            robo_service.fim(eid, "ok", msg, arq.name)
            return True
        except Exception as e:  # noqa: BLE001 — registra e tenta de novo
            erro = f"{type(e).__name__}: {e}"
            log(f"[{rel['nome']}] ❌ {erro}")
            (AQUI / "logs" / f"{dt.date.today():%Y-%m-%d}_{rel['nome']}_erro.txt").write_text(
                traceback.format_exc(), encoding="utf-8")
            if t < tentativas:
                time.sleep(30)
    robo_service.fim(eid, "erro", erro, arq.name if arq else "")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Robô de relatórios do Ecossistema Logístico")
    ap.add_argument("--senha", help="guarda no cofre do Windows: o nome do site (ex.: powerbi), 'banco' ou 'github'")
    ap.add_argument("--gravar", help="grava a receita de um relatório")
    ap.add_argument("--entrar", help="abre o site no navegador do robô para você fazer o login (fica salvo)")
    ap.add_argument("--site", default="promax", help="site da gravação (seção do config.toml), padrão promax")
    ap.add_argument("--testar", help="roda uma receita com o navegador aparecendo")
    ap.add_argument("--so", help="roda só estes relatórios (separados por vírgula)")
    ap.add_argument("--grupo", help="roda só os relatórios deste grupo (ex.: grade, a cada 2 h)")
    ap.add_argument("--ver", action="store_true", help="mostra o navegador")
    a = ap.parse_args()
    if a.senha:
        cofre_gravar(a.senha)
        return
    cfg = config()
    if a.entrar:
        entrar(cfg, a.entrar)
        return
    if a.gravar:
        gravar(a.gravar, cfg, a.site)
        return
    rels = cfg.get("relatorios", [])
    log(f"▶️ Início ({'teste' if a.testar else 'só ' + a.so if a.so else 'grupo ' + a.grupo if a.grupo else 'agendado/rodada completa'})")
    if a.testar:
        rels = [r for r in rels if r["nome"] == a.testar] or [{"nome": a.testar, "importar": "so_baixar",
                                                               "site": a.site}]
        a.ver = True
    elif a.so:
        quer = {x.strip() for x in a.so.split(",")}
        rels = [r for r in rels if r["nome"] in quer]
    elif a.grupo:  # ex.: grade de cada revenda, a cada 2 h (agendar_grade.bat)
        rels = [r for r in rels if str(r.get("grupo") or "") == a.grupo]
    else:  # rodada normal (07:00/09:00): os relatórios com grupo têm agendamento próprio
        rels = [r for r in rels if not r.get("grupo")]
    hoje = dt.date.today().weekday()  # 0 = segunda
    rels = [r for r in rels if a.testar or a.so or (r.get("ativo", True) and hoje in _dias(r.get("dias", "seg-sab")))]
    if a.grupo and not rels:
        log(f"Nenhum relatório ativo no grupo '{a.grupo}' (confira grupo/ativo no config.toml).")
        return
    if not rels:
        log("Nenhum relatório para rodar agora.")
        return
    if preparar_sistema(cfg):
        from database.schema import init_db

        init_db()
        ok = sum(rodar(r, cfg, a.ver) for r in rels)
    else:
        ok = sum(so_baixar(r, cfg, a.ver) for r in rels)
    log(f"Fim: {ok} de {len(rels)} relatório(s) ok.")
    sys.exit(0 if ok == len(rels) else 1)


def _dias(txt: str) -> set[int]:
    nomes = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    t = str(txt).lower().replace("á", "a").replace(" ", "")
    if t in ("todos", "todo-dia", "diario"):
        return set(range(7))
    out = set()
    for parte in t.split(","):
        if "-" in parte:
            a, b = parte.split("-")
            i, j = nomes.index(a[:3]), nomes.index(b[:3])
            out |= set(range(i, j + 1)) if i <= j else set(range(i, 7)) | set(range(0, j + 1))
        elif parte[:3] in nomes:
            out.add(nomes.index(parte[:3]))
    return out


if __name__ == "__main__":
    main()
