"""App Carreteiro — entrada do TERCEIRO (frete spot).

1. Na cotação de frete a Puxada informa o(s) pedido(s) e a placa.
2. O terceiro abre o app, toca em "Entrar como terceiro" e digita o número do pedido:
   placa, transportadora e destino (fábrica) vêm da cotação; ele toca em INICIAR VIAGEM.
3. Daí em diante registra as etapas como qualquer motorista (só a viagem — sem outras telas e sem
   bloqueio de interjornada). A Puxada acompanha no 📡 Ao vivo.
4. Se a fábrica da cotação for diferente da fábrica do pedido (📋 Pedidos D0 a D+3), gera um alerta.
"""
import re
import secrets
import unicodedata

from config.settings import PREFIXO_TERCEIRO, StatusFrete
from core import tempo
from database.connection import execute, query_all, query_one
from repositories import carreteiro_repo as repo
from repositories import pedidos_puxada_repo
from services.erros import RegraNegocioError

ATIVOS = (StatusFrete.PENDENTE, StatusFrete.APROVADO, StatusFrete.FINALIZADO)


def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()


def _num(t) -> str:
    return re.sub(r"\D", "", str(t or "")).lstrip("0")


def numeros(texto) -> list[str]:
    return [n for n in re.split(r"[\s,;/+]+", str(texto or "")) if _num(n)]


def normalizar_numeros(texto) -> str:
    lista = numeros(texto)
    if len({_num(n) for n in lista}) != len(lista):
        raise RegraNegocioError("Há número de pedido repetido.")
    return ", ".join(lista)


# --- Cotação ---------------------------------------------------------------------------------
def cotacao_por_pedido(numero: str) -> dict | None:
    """Cotação de frete (pendente, aprovada ou finalizada) que tem esse pedido — a mais recente."""
    alvo = _num(numero)
    if not alvo:
        return None
    linhas = query_all(f"""SELECT c.*, o.nome AS origem, d.nome AS destino, t.nome AS transportadora, op.nome AS revenda
                           FROM cotacoes_frete c
                           LEFT JOIN origens_destinos o ON o.id = c.origem_id
                           LEFT JOIN origens_destinos d ON d.id = c.destino_id
                           LEFT JOIN transportadoras t ON t.id = c.transportadora_id
                           LEFT JOIN operacoes op ON op.id = c.operacao_id
                           WHERE c.numeros_pedido LIKE ? AND c.status IN ({', '.join('?' * len(ATIVOS))})
                           ORDER BY c.id DESC""", (f"%{alvo}%", *ATIVOS))
    for c in linhas:
        if alvo in {_num(n) for n in numeros(c.get("numeros_pedido"))}:
            return c
    return None


def verificar_destino(cot: dict) -> str | None:
    """Compara a fábrica da cotação com a fábrica do(s) pedido(s) lançados pela Puxada. Devolve o alerta."""
    if not cot:
        return None
    fab_cot = _n(cot.get("origem"))
    alertas = []
    for n in numeros(cot.get("numeros_pedido")):
        p = pedidos_puxada_repo.pedido_por_numero(cot["operacao_id"], n)
        fab = p.get("fabrica") if p else None
        if fab and fab_cot and _n(fab) != fab_cot and _n(fab) not in fab_cot and fab_cot not in _n(fab):
            alertas.append(f"pedido {n}: cotação para {cot.get('origem')}, mas o pedido é da {fab}")
    return "⚠️ Destino diferente — " + " · ".join(alertas) if alertas else None


def registrar_alerta(cotacao_id: int) -> str | None:
    """Grava (ou limpa) o alerta de destino na cotação e avisa a Puxada quando aparecer."""
    cot = query_one("""SELECT c.*, o.nome AS origem, t.nome AS transportadora FROM cotacoes_frete c
                       LEFT JOIN origens_destinos o ON o.id = c.origem_id
                       LEFT JOIN transportadoras t ON t.id = c.transportadora_id WHERE c.id = ?""", (cotacao_id,))
    if not cot:
        return None
    alerta = verificar_destino(cot)
    if alerta != (cot.get("alerta_destino") or None):
        execute("UPDATE cotacoes_frete SET alerta_destino = ? WHERE id = ?", (alerta, cotacao_id))
        if alerta:
            _avisar_puxada(cot["operacao_id"], f"⚠️ Frete #{cotacao_id}: destino diferente do pedido", alerta,
                           f"destino:{cotacao_id}:{tempo.agora():%Y%m%d%H%M}")
    return alerta


def _avisar_puxada(operacao_id: int, titulo: str, texto: str, chave: str) -> None:
    try:
        from config.settings import PERFIL_MOTORISTA
        from core.auth import pode_acessar_aba
        from repositories import motoristas_repo, usuarios_repo

        agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
        for u in usuarios_repo.listar(apenas_ativos=True):
            if u["perfil"] == PERFIL_MOTORISTA:
                continue
            sessao = usuarios_repo.carregar_sessao(u["id"])
            if operacao_id not in (sessao.get("operacoes") or [operacao_id]):
                continue
            if pode_acessar_aba(sessao, "puxada", "carreteiro") or pode_acessar_aba(sessao, "puxada", "cotacao"):
                motoristas_repo.criar_notificacao(u["id"], "terceiro", chave, titulo, texto, "puxada", agora)
    except Exception:
        pass


# --- Viagem do terceiro ---------------------------------------------------------------------
def _motorista_terceiro(operacao_id: int, transportadora: str) -> int:
    nome = f"{PREFIXO_TERCEIRO}{transportadora or 'Transportadora'}"
    r = query_one("SELECT id FROM motoristas WHERE operacao_id = ? AND nome = ? AND COALESCE(terceiro, 0) = 1",
                  (operacao_id, nome))
    if r:
        return int(r["id"])
    return execute("INSERT INTO motoristas (operacao_id, nome, terceiro) VALUES (?, ?, 1)", (operacao_id, nome))


def _fabrica_id(nome: str) -> int | None:
    alvo = _n(nome)
    for f in repo.destinos():
        if _n(f["nome"]) == alvo:
            return int(f["id"])
    return None


def previa(numero: str) -> dict:
    """O que o terceiro vê antes de iniciar: placa, transportadora, destino e o alerta (se houver)."""
    cot = cotacao_por_pedido(numero)
    if not cot:
        raise RegraNegocioError("Pedido não encontrado em nenhuma cotação de frete. Confira o número ou fale com "
                                "a Puxada.")
    if cot["status"] == StatusFrete.PENDENTE:
        aviso = "O frete ainda está aguardando aprovação da Puxada."
    else:
        aviso = None
    ativa = query_one("SELECT id, terceiro_codigo FROM viagens_carreteiro WHERE cotacao_id = ? AND status = ?",
                      (cot["id"], repo.EM_VIAGEM))
    return {"cotacao": cot, "alerta": verificar_destino(cot), "aviso": aviso, "viagem_ativa": ativa}


def iniciar(numero: str, geo_inicio: dict | None = None) -> str:
    """Cria a viagem do terceiro e devolve o código que fica no endereço do app (para continuar depois)."""
    p = previa(numero)
    cot = p["cotacao"]
    if p["viagem_ativa"]:
        return p["viagem_ativa"]["terceiro_codigo"]
    placa = (cot.get("placa") or "").strip().upper()
    if not placa:
        raise RegraNegocioError("A cotação não tem placa. Peça à Puxada para informar a placa no frete.")
    outra = repo.viagem_ativa_placa(cot["operacao_id"], placa)
    if outra:
        raise RegraNegocioError(f"A placa {placa} já está em viagem.")
    mid = _motorista_terceiro(cot["operacao_id"], cot.get("transportadora"))
    codigo = secrets.token_urlsafe(9)
    ts = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
    vid = repo.criar_viagem({
        "operacao_id": cot["operacao_id"], "motorista_id": mid, "usuario_id": None,
        "numero_pedido": cot["numeros_pedido"], "agendamento": None, "destino_id": _fabrica_id(cot.get("origem")),
        "destino": cot.get("origem"), "placa": placa, "status": repo.EM_VIAGEM, "ts_inicio": ts,
        "terceiro": 1, "cotacao_id": cot["id"], "terceiro_codigo": codigo})
    from services import carreteiro_service

    repo.registrar_evento(vid, "inicio", ts, carreteiro_service._geo_com_raio(cot["operacao_id"], "inicio", geo_inicio))
    registrar_alerta(cot["id"])
    _avisar_puxada(cot["operacao_id"], f"🚚 Terceiro iniciou viagem: {placa}",
                   f"{cot.get('transportadora') or ''} · pedido {cot['numeros_pedido']} · {cot.get('origem') or ''}",
                   f"terc:{vid}")
    return codigo


def viagem_por_codigo(codigo: str) -> dict | None:
    if not codigo:
        return None
    r = query_one("SELECT id FROM viagens_carreteiro WHERE terceiro_codigo = ? AND COALESCE(terceiro, 0) = 1",
                  (str(codigo),))
    return repo.viagem(int(r["id"])) if r else None


def usuario_terceiro(v: dict) -> dict:
    """'Usuário' do terceiro para as funções da viagem (não tem login)."""
    return {"id": None, "nome": v.get("motorista") or "Terceiro", "terceiro": True, "codigo": v["terceiro_codigo"],
            "viagem_id": v["id"]}
