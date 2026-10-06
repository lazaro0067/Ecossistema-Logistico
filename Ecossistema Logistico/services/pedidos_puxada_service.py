"""Pedidos D0 (hoje) e D+1 (amanhã) da Puxada.

Fluxo:
  1. Puxada › 🗓️ Disponibilidade: o gestor marca cada placa do dia (Disponível / Indisponível Frota /
     Indisponível Viagem) e, se disponível, a sugestão de pedido (Retornável ou Descartável).
  2. Puxada › 📋 Pedidos D0 / D+1: escolhe a placa, informa o número do pedido e o tipo.
     Retornável → paletes de 600 ml Âmbar, 600 ml Verde, 1 Litro e 300 ml. Descartável → paletes no total.
  3. O pedido aparece para o Ressuprimento e para o Armazém (Gestão de Pedidos).
     Quando o armazém termina, clica em ✅ Finalizado — o status muda em todas as telas.
"""
import datetime as dt
import re

import pandas as pd

from config.settings import EMBALAGENS_RETORNAVEL, SUGESTAO_PEDIDO
from core import tempo
from repositories import pedidos_puxada_repo as repo
from services.erros import RegraNegocioError

STATUS_ICONE = {"Aberto": "🟡", "Finalizado": "✅", "Cancelado": "⛔", "Reprogramado": "🔁"}


DIAS_A_FRENTE = 3  # D0, D+1, D+2 e D+3


def dias_pedido() -> list[dt.date]:
    """D0 = hoje, D+1 = amanhã, D+2 e D+3."""
    hoje = tempo.hoje()
    return [hoje + dt.timedelta(days=i) for i in range(DIAS_A_FRENTE + 1)]


def rotulo_dia(d: dt.date) -> str:
    n = (d - tempo.hoje()).days
    nome = {0: "D0 · hoje", 1: "D+1 · amanhã"}.get(n, "Anterior" if n < 0 else f"D+{n}")
    return f"{nome} {d:%d/%m}"


# --- Prazo de saída da carreta (prioridade do armazém) ---------------------------------
def agendamento_dt(r: dict) -> dt.datetime | None:
    hora = r.get("hora_agendamento")
    if not isinstance(hora, str) or not hora:
        return None
    try:
        return dt.datetime.combine(dt.date.fromisoformat(str(r["data"])[:10]), dt.datetime.strptime(hora, "%H:%M").time())
    except ValueError:
        return None


def prazo_saida(r: dict) -> dt.datetime | None:
    """Hora máxima para a carreta sair da revenda = agendamento na fábrica − deslocamento até a fábrica."""
    ag = agendamento_dt(r)
    if not ag:
        return None
    try:
        h = float(r.get("deslocamento_h") or 0)
    except (TypeError, ValueError):
        h = 0.0
    return ag - dt.timedelta(hours=h if h == h else 0)


def prioridade(r: dict) -> tuple[int, str, str]:
    """(ordem, rótulo, cor) — quanto menor a ordem, mais urgente para o armazém."""
    if r.get("status") == "Finalizado":
        return 9, "✅ Finalizado", "#146c43"
    if r.get("status") == "Cancelado":
        return 10, "⛔ Cancelado", "#77766f"
    if r.get("status") == "Reprogramado":
        return 11, "🔁 Reprogramado", "#77766f"
    pz = prazo_saida(r)
    if not pz:
        return 6, "⚪ Sem agendamento", "#77766f"
    falta_h = (pz - tempo.agora()).total_seconds() / 3600
    if falta_h < 0:
        return 0, f"⛔ Atrasado {_dur(-falta_h)}", "#a32025"
    if falta_h <= 2:
        return 1, f"🔴 Sai em {_dur(falta_h)}", "#d03b3b"
    if falta_h <= 6:
        return 2, f"🟠 Sai em {_dur(falta_h)}", "#c2571a"
    if falta_h <= 24:
        return 3, f"🟡 Sai em {_dur(falta_h)}", "#b7791f"
    return 4, f"🟢 Sai em {_dur(falta_h)}", "#146c43"


def _dur(h: float) -> str:
    m = int(round(h * 60))
    if m < 60:
        return f"{m} min"
    if m < 48 * 60:
        return f"{m // 60}h{m % 60:02d}"
    return f"{m // 1440} dias"


def _num(v) -> float:
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        raise RegraNegocioError("Quantidade de paletes inválida.")
    if f < 0:
        raise RegraNegocioError("A quantidade de paletes não pode ser negativa.")
    return f


def janela_txt(r: dict) -> str:
    ini, fim = r.get("hora_agendamento"), r.get("hora_agendamento_fim")
    ini = ini if isinstance(ini, str) and ini else ""
    fim = fim if isinstance(fim, str) and fim else ""
    return f"{ini}–{fim}" if ini and fim else ini or "—"


def _hora(v, nome: str) -> str | None:
    if v in (None, ""):
        return None
    h = v.strftime("%H:%M") if isinstance(v, dt.time) else str(v)[:5]
    if not re.fullmatch(r"\d{2}:\d{2}", h):
        raise RegraNegocioError(f"{nome} inválida (use HH:MM).")
    return h


def salvar_pedido(operacao_id: int, pid: int | None, data: dt.date, placa: str, numero: str, tipo: str,
                  qtds: dict | None, paletes, observacao: str, usuario: str, fabrica_id: int | None = None,
                  motorista_id: int | None = None, hora_agendamento=None, hora_agendamento_fim=None,
                  outros_desc: str | None = None, _reprogramando: bool = False) -> int:
    from repositories import operacoes_repo

    if operacoes_repo.e_consolidada(operacao_id):
        raise RegraNegocioError("Escolha uma filial no menu para lançar pedidos.")
    atual = repo.pedido(pid) if pid else None
    if atual and atual["status"] in ("Cancelado", "Reprogramado"):
        raise RegraNegocioError(f"Este pedido está {atual['status'].lower()} — não pode mais ser alterado.")
    if not atual and data not in dias_pedido():
        raise RegraNegocioError("Lance pedidos para D0 (hoje) até D+3.")
    placa = (placa or "").strip().upper()
    if not placa:
        raise RegraNegocioError("Escolha a placa.")
    lista = repo.numeros(numero)
    if not lista:
        raise RegraNegocioError("Informe o número do pedido.")
    if len(set(lista)) != len(lista):
        raise RegraNegocioError("Há número de pedido repetido no agendamento.")
    numero = ", ".join(lista)  # mais de um pedido no mesmo agendamento
    repetido = repo.numero_existe(operacao_id, numero, pid)
    if repetido:
        raise RegraNegocioError(f"O pedido {repetido} já está em outro agendamento.")
    from repositories import logistica_repo

    fabricas = set(logistica_repo.fabricas_df()["id"].astype(int))
    if not fabricas:
        raise RegraNegocioError("Cadastre as fábricas em Puxada › ⚙️ Cadastros › 🏭 Fábricas.")
    if not fabrica_id or int(fabrica_id) not in fabricas:
        raise RegraNegocioError("Escolha a fábrica do pedido.")
    motoristas = set(logistica_repo.motoristas_df(operacao_id)["id"].astype(int))
    if not motorista_id or int(motorista_id) not in motoristas:
        raise RegraNegocioError("Escolha o motorista do pedido.")
    hora = _hora(hora_agendamento, "Hora de início do agendamento")
    hora_fim = _hora(hora_agendamento_fim, "Hora de fim do agendamento")
    if not hora:
        raise RegraNegocioError("Informe o slot do agendamento na fábrica (início).")
    if hora_fim and hora_fim <= hora:
        raise RegraNegocioError("O fim do slot de agendamento precisa ser depois do início.")
    if tipo not in SUGESTAO_PEDIDO:
        raise RegraNegocioError("Escolha Retornável ou Descartável.")
    dados = {"data": data.isoformat(), "placa": placa, "numero_pedido": numero, "fabrica_id": int(fabrica_id),
             "motorista_id": int(motorista_id), "hora_agendamento": hora, "hora_agendamento_fim": hora_fim,
             "tipo": tipo, "outros_desc": None,
             "observacao": (observacao or "").strip() or None, **{k: 0.0 for k in EMBALAGENS_RETORNAVEL}, "paletes": 0.0}
    if tipo == "Retornável":
        for k in EMBALAGENS_RETORNAVEL:
            dados[k] = _num((qtds or {}).get(k))
        dados["paletes"] = sum(dados[k] for k in EMBALAGENS_RETORNAVEL)
        if dados["paletes"] <= 0:
            raise RegraNegocioError("Informe a quantidade de paletes de pelo menos uma embalagem retornável.")
        if dados.get("p_outros"):
            if not (outros_desc or "").strip():
                raise RegraNegocioError("Descreva o vasilhame em “Outros”.")
            dados["outros_desc"] = outros_desc.strip()
    else:
        dados["paletes"] = _num(paletes)
        if dados["paletes"] <= 0:
            raise RegraNegocioError("Informe a quantidade de paletes do pedido descartável.")
    if not atual or _reprogramando:
        return repo.salvar(operacao_id, None, dados, usuario)
    resumo = _resumo_edicao(atual, dados)
    if not resumo:
        raise RegraNegocioError("Nada foi alterado no pedido.")
    reabrir = atual["status"] == "Finalizado"
    if reabrir:
        resumo += " · reaberto (estava finalizado pelo armazém)"
    repo.salvar(operacao_id, pid, dados, usuario, resumo, reabrir)
    _avisar_edicao(operacao_id, {**atual, **dados}, usuario, resumo)
    return pid


_ROTULOS = {"data": "dia", "placa": "placa", "numero_pedido": "nº do pedido", "fabrica_id": "fábrica",
            "motorista_id": "motorista", "hora_agendamento": "agendamento", "hora_agendamento_fim": "fim do slot",
            "tipo": "tipo", **EMBALAGENS_RETORNAVEL, "outros_desc": "descrição outros",
            "paletes": "paletes", "observacao": "observação"}


def _resumo_edicao(atual: dict, novo: dict) -> str:
    """Ex.: 'placa PRH4F57 → ABC1D23 · 600 ml Âmbar 20 → 18'."""
    from repositories import logistica_repo

    fabs = {int(r["id"]): r["nome"] for r in logistica_repo.fabricas_df().to_dict("records")}
    mots = {int(r["id"]): r["nome"] for r in logistica_repo.motoristas_df(atual["operacao_id"]).to_dict("records")}

    def fmt(k, v):
        if v is None or v == "" or (isinstance(v, float) and v != v):
            return "—"
        if k == "fabrica_id":
            return fabs.get(int(v), str(v))
        if k == "motorista_id":
            return mots.get(int(v), str(v))
        if k == "data":
            return dt.date.fromisoformat(str(v)[:10]).strftime("%d/%m")
        if isinstance(v, float):
            return _fmt(v)
        return str(v)

    partes = []
    for k, rot in _ROTULOS.items():
        a, b = fmt(k, atual.get(k)), fmt(k, novo.get(k))
        if k in EMBALAGENS_RETORNAVEL or k == "paletes":
            try:
                if float(atual.get(k) or 0) == float(novo.get(k) or 0):
                    continue
            except (TypeError, ValueError):
                pass
        if a != b:
            partes.append(f"{rot} {a} → {b}")
    return " · ".join(partes)


def _avisar_edicao(operacao_id: int, p: dict, usuario: str, resumo: str) -> None:
    """🔔 para quem acompanha os pedidos (Armazém e Ressuprimento) da filial."""
    try:
        from config.settings import PERFIL_MOTORISTA
        from core.auth import pode_acessar_aba
        from repositories import motoristas_repo, usuarios_repo

        agora = tempo.agora().strftime("%Y-%m-%d %H:%M:%S")
        titulo = f"Pedido {p['numero_pedido']} editado por {usuario}"
        for u in usuarios_repo.listar(apenas_ativos=True):
            if u["perfil"] == PERFIL_MOTORISTA or u["nome"] == usuario:
                continue
            sessao = usuarios_repo.carregar_sessao(u["id"])
            if operacao_id not in (sessao.get("operacoes") or [operacao_id]):
                continue
            pagina = ("armazem" if pode_acessar_aba(sessao, "armazem", "pedidos") else
                      "ressuprimento" if pode_acessar_aba(sessao, "ressuprimento", "puxada_pedidos") else None)
            if pagina:
                motoristas_repo.criar_notificacao(u["id"], "pedido", f"pedido:{p.get('id')}:{agora}", titulo,
                                                  f"Placa {p['placa']} · {resumo}", pagina, agora)
    except Exception:
        pass


def reprogramar(operacao_id: int, pid: int, data: dt.date, motivo: str, usuario: str, **novos) -> int:
    """Cria o pedido novo (nova data/slot/placa...) e marca o antigo como 🔁 Reprogramado (substituído)."""
    atual = repo.pedido(pid)
    if not atual or atual["status"] in ("Cancelado", "Reprogramado"):
        raise RegraNegocioError("Este pedido não pode ser reprogramado.")
    if atual["status"] == "Finalizado":
        raise RegraNegocioError("O armazém já finalizou este pedido — reabra antes de reprogramar.")
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise RegraNegocioError("Informe o motivo da reprogramação.")
    base = {k: atual.get(k) for k in ("placa", "numero_pedido", "tipo", "fabrica_id", "motorista_id",
                                      "hora_agendamento", "hora_agendamento_fim", "paletes", "observacao",
                                      "outros_desc")}
    base.update({k: v for k, v in novos.items() if v is not None})
    qtds = {k: (novos.get("qtds") or {}).get(k, _v(atual.get(k))) for k in EMBALAGENS_RETORNAVEL}
    novos.pop("qtds", None)
    # o número continua o mesmo: libera o antigo antes de validar o novo
    repo.mudar_status(pid, "Reprogramado", usuario)
    try:
        novo = salvar_pedido(operacao_id, None, data, base["placa"], base["numero_pedido"], base["tipo"], qtds,
                             base["paletes"], base.get("observacao") or "", usuario, fabrica_id=base["fabrica_id"],
                             motorista_id=base["motorista_id"], hora_agendamento=base["hora_agendamento"],
                             hora_agendamento_fim=base.get("hora_agendamento_fim"),
                             outros_desc=base.get("outros_desc"))
    except Exception:
        repo.mudar_status(pid, atual["status"], None)
        raise
    repo.marcar_reprogramado(pid, novo, motivo, usuario)
    _avisar_edicao(operacao_id, {**atual, "id": novo}, usuario,
                   f"🔁 reprogramado para {data:%d/%m} {base['hora_agendamento'] or ''} — {motivo}")
    return novo


def capacidade_paletes(operacao_id: int, placa: str) -> int | None:
    from config.settings import PERFIS_VEICULO
    from repositories import logistica_repo

    c = logistica_repo.carretas_df(operacao_id)
    linha = c[c["placa"].str.upper() == str(placa or "").upper()] if not c.empty else c
    if linha.empty or not isinstance(linha.iloc[0].get("perfil"), str):
        return None
    return PERFIS_VEICULO.get(linha.iloc[0]["perfil"])


def finalizar(pid: int, usuario: str) -> None:
    p = repo.pedido(pid)
    if not p:
        raise RegraNegocioError("Pedido não encontrado.")
    if p["status"] in ("Cancelado", "Reprogramado"):
        raise RegraNegocioError(f"Pedido {p['status'].lower()} não pode ser finalizado.")
    repo.mudar_status(pid, "Finalizado", usuario)


def reabrir(pid: int) -> None:
    repo.mudar_status(pid, "Aberto", None)


def cancelar(pid: int, usuario: str) -> None:
    p = repo.pedido(pid)
    if p and p["status"] == "Finalizado":
        raise RegraNegocioError("O armazém já finalizou este pedido — peça para reabrir antes de cancelar.")
    repo.mudar_status(pid, "Cancelado", usuario)


def composicao(r: dict) -> str:
    """'Retornável: 600 ml Âmbar 4 · 1 Litro 2' ou 'Descartável: 10 paletes'."""
    if r.get("tipo") == "Retornável":
        partes = [f"{rot if k != 'p_outros' else 'Outros (' + str(r.get('outros_desc') or '') + ')'} {_fmt(r.get(k))}"
                  for k, rot in EMBALAGENS_RETORNAVEL.items() if _v(r.get(k))]
        return " · ".join(partes) or "—"
    return f"{_fmt(r.get('paletes'))} palete(s)"


def _v(v) -> float:
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f


def _fmt(v) -> str:
    f = _v(v)
    return f"{f:.0f}" if f == int(f) else f"{f:.1f}".replace(".", ",")


def tabela(df: pd.DataFrame, com_filial: bool = False) -> pd.DataFrame:
    """Pedidos no formato de leitura (telas, detalhes e download)."""
    if df is None or df.empty:
        return pd.DataFrame()
    linhas = []
    for r in df.to_dict("records"):
        d = {"Dia": rotulo_dia(dt.date.fromisoformat(str(r["data"])[:10]))}
        if com_filial:
            d["Filial"] = r.get("filial")
        fab = r.get("fabrica")
        ag, pz = agendamento_dt(r), prazo_saida(r)
        mot = r.get("motorista")
        d.update({"Prioridade": prioridade(r)[1],
                  "Placa": r["placa"], "Pedido": r["numero_pedido"], "Fábrica": fab if isinstance(fab, str) else "—",
                  "Motorista": mot if isinstance(mot, str) else "—",
                  "Agendamento fábrica": f"{ag:%d/%m} {janela_txt(r)}" if ag else "—",
                  "Sair da revenda até": f"{pz:%d/%m %H:%M}" if pz else "—",
                  "Tipo": r["tipo"],
                  **{rot: _v(r.get(k)) if r["tipo"] == "Retornável" else None
                     for k, rot in EMBALAGENS_RETORNAVEL.items()},
                  "Paletes (total)": float(r.get("paletes") or 0),
                  "Status": f"{STATUS_ICONE.get(r['status'], '')} {r['status']}",
                  "Lançado por": r.get("criado_por") or "",
                  "Editado": (f"{r.get('editado_por')} · {tempo.parse_dt(r['editado_em']):%d/%m %H:%M} · "
                              f"{r.get('editado_resumo') or ''}" if isinstance(r.get("editado_em"), str)
                              and r.get("editado_em") else ""),
                  "Finalizado": (f"{r['finalizado_por']} · {tempo.parse_dt(r['finalizado_em']):%d/%m %H:%M}"
                                 if isinstance(r.get("finalizado_em"), str) and r.get("finalizado_em") else "")})
        linhas.append(d)
    return pd.DataFrame(linhas)


def resumo(df: pd.DataFrame) -> dict:
    """Totais de paletes por embalagem (pedidos não cancelados)."""
    if df is None or df.empty:
        return {"pedidos": 0, "finalizados": 0, "abertos": 0, "ret": 0.0, "desc": 0.0,
                **{k: 0.0 for k in EMBALAGENS_RETORNAVEL}}
    v = df[~df["status"].isin(["Cancelado", "Reprogramado"])]
    ret = v[v["tipo"] == "Retornável"]
    return {"pedidos": len(v), "finalizados": int((v["status"] == "Finalizado").sum()),
            "abertos": int((v["status"] == "Aberto").sum()),
            "ret": float(ret["paletes"].fillna(0).sum()),
            "desc": float(v[v["tipo"] == "Descartável"]["paletes"].fillna(0).sum()),
            **{k: float(pd.to_numeric(ret[k], errors="coerce").fillna(0).sum()) if k in ret else 0.0
               for k in EMBALAGENS_RETORNAVEL}}
