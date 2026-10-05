"""Regras dos motoristas: cadastro, validade da CNH (alertas semanais ao gestor) e remuneração.

Alertas de CNH
  • A partir de CNH_ALERTA_DIAS (90 dias = 3 meses) antes do vencimento, o gestor responsável
    pelo motorista recebe uma notificação no sistema (🔔 no menu e no Início) — e por e-mail,
    se o envio de e-mail estiver configurado.
  • O aviso se repete a cada CNH_ALERTA_INTERVALO_DIAS (7 dias) até a validade ser atualizada.
  • Motorista sem gestor definido: os avisos vão para os usuários Master.

Remuneração
  • Variável = soma das viagens do mês × valor da viagem cadastrado para a fábrica (por filial).
  • Total = salário fixo (nominal) + variável.
  • Viagens = pedidos vinculados do mês (os do App Carreteiro entram sozinhos).
"""
import datetime as dt
import re
import time
import unicodedata

import pandas as pd

from config.settings import CNH_ALERTA_DIAS, CNH_ALERTA_INTERVALO_DIAS
from core import tempo
from repositories import logistica_repo
from repositories import motoristas_repo as repo
from services.erros import RegraNegocioError

_ULTIMA_VERIFICACAO = {"t": 0.0}


# --- CNH -----------------------------------------------------------------------
def _data(v) -> dt.date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    d = tempo.parse_dt(str(v))
    return d.date() if d else None


def status_cnh(validade) -> tuple[str, str, int | None]:
    """(status de cor, rótulo, dias até vencer)."""
    d = _data(validade)
    if not d:
        return "neutro", "⚪ Sem validade", None
    dias = (d - tempo.hoje()).days
    if dias < 0:
        return "critico", f"🔴 Vencida há {-dias} dia(s)", dias
    if dias <= 30:
        return "critico", f"🔴 Vence em {dias} dia(s)", dias
    if dias <= CNH_ALERTA_DIAS:
        return "atencao", f"🟡 Vence em {dias} dias", dias
    return "bom", f"🟢 Em dia ({d:%d/%m/%Y})", dias


# --- Cadastro --------------------------------------------------------------------
def salvar_motorista(operacao_id: int, mid: int | None, nome: str, cpf: str = "", telefone: str = "",
                     cnh: str = "", cnh_validade=None, gestor_id: int | None = None,
                     salario_fixo: float | None = 0.0) -> int:
    nome = re.sub(r"\s+", " ", (nome or "").strip())
    if not nome:
        raise RegraNegocioError("Informe o nome do motorista.")
    cpf = re.sub(r"\D", "", str(cpf or ""))
    if cpf and len(cpf) != 11:
        raise RegraNegocioError("O CPF precisa ter 11 números.")
    validade = _data(cnh_validade)
    if cnh_validade not in (None, "") and not validade:
        raise RegraNegocioError("Validade da CNH inválida. Use DD/MM/AAAA.")
    try:
        salario = float(salario_fixo or 0)
    except (TypeError, ValueError):
        raise RegraNegocioError("Salário fixo inválido.")
    if salario < 0:
        raise RegraNegocioError("O salário fixo não pode ser negativo.")
    return logistica_repo.salvar_motorista(
        operacao_id, mid, nome, (cnh or "").strip(), (telefone or "").strip(), cpf=cpf or None,
        cnh_validade=validade.isoformat() if validade else None, gestor_id=int(gestor_id) if gestor_id else None,
        salario_fixo=salario)


# --- Alertas semanais -------------------------------------------------------------
def verificar_alertas_cnh(forcar: bool = False) -> int:
    """Cria as notificações de CNH vencendo (no máximo 1 por motorista por semana para cada gestor).
    É chamado a cada acesso ao sistema, mas só trabalha de verdade a cada 30 minutos."""
    agora_seg = time.time()
    if not forcar and agora_seg - _ULTIMA_VERIFICACAO["t"] < 1800:
        return 0
    _ULTIMA_VERIFICACAO["t"] = agora_seg
    hoje, agora = tempo.hoje(), tempo.agora()
    agora_txt = agora.strftime("%Y-%m-%d %H:%M:%S")
    masters = [m["id"] for m in repo.masters()]
    por_destinatario: dict[int, list[str]] = {}
    criadas = 0
    for m in repo.todos_com_cnh():
        validade = _data(m["cnh_validade"])
        if not validade or (validade - hoje).days > CNH_ALERTA_DIAS:
            continue
        _, rotulo, dias = status_cnh(validade)
        destinatarios = [m["gestor_id"]] if m.get("gestor_id") else masters
        chave = f"cnh:{m['id']}:{validade.isoformat()}"
        titulo = (f"CNH de {m['nome']} vencida" if dias < 0 else f"CNH de {m['nome']} vence em {dias} dia(s)")
        texto = (f"{m['nome']} ({m['operacao']}) — CNH {m.get('cnh') or 's/ número'} com validade em "
                 f"{validade:%d/%m/%Y}. Atualize a validade em Puxada › Cadastros › Motoristas depois da renovação.")
        for uid in destinatarios:
            ultima = repo.ultima_notificacao(uid, chave)
            if ultima:
                quando = tempo.parse_dt(ultima["criado_em"])
                if quando and (agora - quando).days < CNH_ALERTA_INTERVALO_DIAS:
                    continue
            repo.criar_notificacao(uid, "cnh", chave, titulo, texto, "puxada", agora_txt)
            por_destinatario.setdefault(uid, []).append(f"{rotulo.split(' ', 1)[-1]} — {texto}")
            criadas += 1
    if por_destinatario:
        _enviar_emails(por_destinatario)
    return criadas


def _enviar_emails(por_destinatario: dict[int, list[str]]) -> None:
    from html import escape

    from repositories import usuarios_repo
    from services import email_service

    if not email_service.configurado():
        return
    for uid, linhas in por_destinatario.items():
        u = usuarios_repo.buscar(uid)
        if not u or not u.get("email"):
            continue
        try:
            email_service.enviar(
                u["email"], f"⚠️ CNH de motorista vencendo ({len(linhas)})", "CNH de motoristas vencendo",
                "<p>Olá, {}!</p><p>Estas CNHs vencem nos próximos 3 meses (ou já venceram):</p><ul>{}</ul>"
                "<p>O aviso se repete toda semana até a validade ser atualizada no cadastro.</p>".format(
                    escape(u["nome"].split()[0]), "".join(f"<li>{escape(x)}</li>" for x in linhas)),
                "CNHs vencendo:\n" + "\n".join(f"- {x}" for x in linhas))
        except Exception:
            pass  # o aviso no sistema já foi criado; o e-mail é só um reforço


# --- Remuneração -------------------------------------------------------------------
def _norm(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()


def remuneracao(operacao_id: int, mes_ano: str) -> dict:
    """{"resumo": por motorista, "viagens": detalhe com valor, "sem_valor": fábricas sem valor, "fabricas": [...] }"""
    mots = repo.lista_df(operacao_id)
    valores = repo.valores_viagem(operacao_id)
    fabricas = logistica_repo.fabricas_df()
    fab_por_nome = {_norm(r.nome): r for r in fabricas.itertuples()}
    v = repo.viagens_mes(operacao_id, mes_ano)
    if not v.empty:
        v["fabrica"] = v["fabrica"].fillna("—")
        v["motorista"] = v["motorista"].fillna("—")
        v["valor"] = [valores.get(fab_por_nome[_norm(f)].id, 0.0) if _norm(f) in fab_por_nome else 0.0
                      for f in v["fabrica"]]
    else:
        v = v.assign(valor=pd.Series(dtype=float))
    sem_valor = sorted({f for f, val in zip(v["fabrica"], v["valor"]) if not val}) if not v.empty else []

    linhas = []
    nomes_cadastro = {_norm(n): n for n in mots["nome"]} if not mots.empty else {}
    for r in mots.to_dict("records"):
        minhas = v[v["motorista"].map(_norm) == _norm(r["nome"])] if not v.empty else v
        linhas.append({"motorista": r["nome"], "salario_fixo": float(r.get("salario_fixo") or 0),
                       "viagens": len(minhas), "variavel": float(minhas["valor"].sum()) if len(minhas) else 0.0,
                       **{f"fab::{f}": int((minhas["fabrica"] == f).sum()) for f in sorted(v["fabrica"].unique())}}
                      if not v.empty else {"motorista": r["nome"], "salario_fixo": float(r.get("salario_fixo") or 0),
                                           "viagens": 0, "variavel": 0.0})
    # viagens com motorista que não está no cadastro desta filial
    if not v.empty:
        for nome in sorted({n for n in v["motorista"] if _norm(n) not in nomes_cadastro}):
            minhas = v[v["motorista"] == nome]
            linhas.append({"motorista": f"{nome} (não cadastrado)", "salario_fixo": 0.0, "viagens": len(minhas),
                           "variavel": float(minhas["valor"].sum()),
                           **{f"fab::{f}": int((minhas["fabrica"] == f).sum()) for f in sorted(v["fabrica"].unique())}})
    resumo = pd.DataFrame(linhas)
    if resumo.empty:
        resumo = pd.DataFrame(columns=["motorista", "salario_fixo", "viagens", "variavel", "total"])
    else:
        resumo = resumo.fillna(0)
        resumo["total"] = resumo["salario_fixo"] + resumo["variavel"]
        resumo = resumo.sort_values(["total", "motorista"], ascending=[False, True]).reset_index(drop=True)
    return {"resumo": resumo, "viagens": v, "sem_valor": sem_valor,
            "fabricas": sorted(v["fabrica"].unique()) if not v.empty else []}
