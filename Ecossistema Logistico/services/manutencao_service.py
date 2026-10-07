"""Agendamento de manutenção das placas (Puxada).

A manutenção programada:
  • deixa a placa como "Indisponível Frota" na Disponibilidade no dia programado;
  • aparece para o Armazém no Pátio/Descarga: quando essa placa descarregar, vai para a manutenção;
  • ⭐ prioridade: o armazém vê em destaque e no topo da lista.
"""
import datetime as dt
import re

from config.settings import STATUS_MANUTENCAO, TIPOS_MANUTENCAO
from core import tempo
from repositories import logistica_repo
from repositories import manutencao_repo as repo
from services.erros import RegraNegocioError


def salvar(operacao_id: int, mid: int | None, placa: str, data, hora, tipo: str, descricao: str, oficina: str,
           previsao_fim, prioridade: bool, usuario: str) -> int:
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial no menu para programar manutenção.")
    placas = set(logistica_repo.carretas_df(operacao_id)["placa"].str.upper())
    placa = (placa or "").strip().upper()
    if placa not in placas:
        raise RegraNegocioError("Escolha uma placa cadastrada.")
    if not isinstance(data, dt.date):
        raise RegraNegocioError("Informe a data da manutenção.")
    atual = repo.buscar(mid) if mid else None
    if not atual and data < tempo.hoje():
        raise RegraNegocioError("A data da manutenção não pode ser no passado.")
    if atual and atual["status"] in ("Concluída", "Cancelada"):
        raise RegraNegocioError(f"Esta manutenção está {atual['status'].lower()}.")
    if tipo not in TIPOS_MANUTENCAO:
        raise RegraNegocioError("Escolha o tipo de manutenção.")
    if tipo == "Outra" and len((descricao or "").strip()) < 3:
        raise RegraNegocioError("Descreva a manutenção.")
    h = hora.strftime("%H:%M") if isinstance(hora, dt.time) else (str(hora)[:5] if hora else None)
    if h and not re.fullmatch(r"\d{2}:\d{2}", h):
        raise RegraNegocioError("Hora inválida.")
    pf = previsao_fim.isoformat() if isinstance(previsao_fim, dt.date) else None
    if pf and pf < data.isoformat():
        raise RegraNegocioError("A previsão de término não pode ser antes do início.")
    dados = {"placa": placa, "data": data.isoformat(), "hora": h, "tipo": tipo,
             "descricao": (descricao or "").strip() or None, "oficina": (oficina or "").strip() or None,
             "previsao_fim": pf, "prioridade": 1 if prioridade else 0}
    novo = repo.salvar(operacao_id, mid, dados, usuario)
    _avisar(operacao_id, dados, usuario, editado=bool(mid))
    return novo


def mudar_status(mid: int, status: str) -> None:
    if status not in STATUS_MANUTENCAO:
        raise RegraNegocioError("Status inválido.")
    m = repo.buscar(mid)
    if not m:
        raise RegraNegocioError("Manutenção não encontrada.")
    repo.mudar_status(mid, status)


def depois_da_descarga(operacao_id: int, placa: str, data_descarga: str) -> dict | None:
    """Manutenção programada para a placa no dia da descarga ou no dia seguinte (o que o armazém precisa saber)."""
    if not placa or not data_descarga:
        return None
    d = dt.date.fromisoformat(str(data_descarga)[:10])
    lista = [m for m in repo.ativas_da_placa(operacao_id, placa, d.isoformat())
             if m["data"] <= (d + dt.timedelta(days=1)).isoformat()]
    return lista[0] if lista else None


def _avisar(operacao_id: int, m: dict, usuario: str, editado: bool) -> None:
    try:
        from config.settings import PERFIL_MOTORISTA
        from core.auth import pode_acessar_aba
        from repositories import motoristas_repo, usuarios_repo

        agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
        titulo = (f"{'⭐ ' if m['prioridade'] else ''}🔧 Manutenção {'alterada' if editado else 'programada'}: "
                  f"{m['placa']} em {dt.date.fromisoformat(m['data']):%d/%m}")
        texto = f"{m['tipo']}{' · ' + m['descricao'] if m.get('descricao') else ''} · por {usuario}. " \
                "Depois de descarregar, a placa vai para a manutenção."
        for u in usuarios_repo.listar(apenas_ativos=True):
            if u["perfil"] == PERFIL_MOTORISTA or u["nome"] == usuario:
                continue
            sessao = usuarios_repo.carregar_sessao(u["id"])
            if operacao_id not in (sessao.get("operacoes") or [operacao_id]):
                continue
            if pode_acessar_aba(sessao, "armazem", "patio"):
                motoristas_repo.criar_notificacao(u["id"], "manutencao", f"manut:{m['placa']}:{agora}", titulo, texto,
                                                  "armazem", agora)
    except Exception:
        pass
