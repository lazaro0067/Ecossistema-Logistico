"""🤖 Robô de relatórios — baixa os relatórios dos sites (Promax, WMS…), salva na pasta e importa no sistema.

Roda no computador da empresa (Windows), agendado. Cada relatório tem uma "receita" (robo/receitas/<nome>.py):
os cliques para entrar no site e exportar o arquivo, gravados uma vez com `python robo.py --gravar <nome>`.

Comandos (na pasta robo):
  python robo.py --senha promax          guarda a senha do site no cofre do Windows (nunca em arquivo)
  python robo.py --senha banco           guarda o DATABASE_URL do sistema no cofre do Windows
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

    v = getpass.getpass(f"Digite o valor de '{nome}' (não aparece na tela): ")
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
        print(linha)
        with open(self.arq, "a", encoding="utf-8") as f:
            f.write(linha + "\n")


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
    receita = carregar_receita(rel.get("receita", rel["nome"]))
    with sync_playwright() as p:
        canal = navegador(cfg, site, rel)
        browser = p.chromium.launch(headless=not ver, channel=canal)
        context = browser.new_context(accept_downloads=True, locale="pt-BR")
        context.set_default_timeout(int(rel.get("espera_seg", cfg.get("espera_seg", 120))) * 1000)
        page = context.new_page()
        try:
            r = receita.baixar(page, ctx)
        finally:
            context.close()
            browser.close()
    arq = Path(r) if r else ctx.arquivo
    if not arq or not arq.exists():
        raise RuntimeError("A receita terminou sem baixar arquivo.")
    return arq


# --- gravar e converter receita --------------------------------------------------------------------------------
_MODELO = '''"""Receita: {nome} — gerada de uma gravação em {quando}. Ajuste se o site mudar."""


def baixar(page, ctx):
{corpo}
'''


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
    cmd = [sys.executable, "-m", "playwright", "codegen", "--target", "python", "-o", str(bruto)]
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
    try:
        ini = next(i for i, l in enumerate(linhas) if "new_page()" in l) + 1
    except StopIteration:
        sys.exit("Gravação sem 'new_page()' — grave de novo.")
    fim = next((i for i, l in enumerate(linhas) if l.strip().startswith("# ----") or "context.close()" in l), len(linhas))
    corpo = [l[4:] if l.startswith("    ") else l for l in linhas[ini:fim] if l.strip()]
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
    url = cofre_ler("banco")
    if not url:
        log("⚠️ Sem o banco do sistema (robo.bat --senha banco): modo TESTE — só baixa e salva na pasta.")
        return False
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("ECO_DATA_DIR", str(Path(tempfile.gettempdir()) / "eco_robo"))
    for k, v in (cfg.get("sistema") or {}).items():
        os.environ.setdefault(str(k).upper(), str(v))
    return True


def so_baixar(rel: dict, cfg: dict, ver: bool) -> bool:
    try:
        log(f"[{rel['nome']}] baixando…")
        arq = baixar(rel, cfg, ver)
        log(f"[{rel['nome']}] ✅ baixado e salvo: {arq} ({arq.stat().st_size / 1024 ** 2:.1f} MB)")
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
    ap.add_argument("--senha", help="guarda no cofre do Windows: o nome do site (ex.: promax) ou 'banco'")
    ap.add_argument("--gravar", help="grava a receita de um relatório")
    ap.add_argument("--site", default="promax", help="site da gravação (seção do config.toml), padrão promax")
    ap.add_argument("--testar", help="roda uma receita com o navegador aparecendo")
    ap.add_argument("--so", help="roda só estes relatórios (separados por vírgula)")
    ap.add_argument("--ver", action="store_true", help="mostra o navegador")
    a = ap.parse_args()
    if a.senha:
        cofre_gravar(a.senha)
        return
    cfg = config()
    if a.gravar:
        gravar(a.gravar, cfg, a.site)
        return
    rels = cfg.get("relatorios", [])
    if a.testar:
        rels = [r for r in rels if r["nome"] == a.testar] or [{"nome": a.testar, "importar": "so_baixar",
                                                               "site": a.site}]
        a.ver = True
    elif a.so:
        quer = {x.strip() for x in a.so.split(",")}
        rels = [r for r in rels if r["nome"] in quer]
    hoje = dt.date.today().weekday()  # 0 = segunda
    rels = [r for r in rels if a.testar or a.so or hoje in _dias(r.get("dias", "seg-sab"))]
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
