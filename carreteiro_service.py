"""Regras do App Carreteiro.

Fluxo do motorista (cada passo grava data e hora, e o GPS quando o celular permite):
  Iniciar viagem → Apresentado → Chamado para carregar → Pedido carregado (NFs + fotos)
  → Saída da cervejaria → Chegada na revenda → Finalizar viagem

Indicadores (aba TMV/TMA da Puxada):
  • TMV — tempo médio de viagem: do "Iniciar viagem" ao "Finalizar viagem".
  • TMA — tempo da placa parada na revenda: da "Chegada na revenda" até o "Iniciar viagem"
    seguinte da mesma placa. Com o ponto da revenda cadastrado, cada chegada/saída é
    conferida pelo GPS (dentro ou fora do raio).
"""
import io
import math
import re
import datetime as dt

import pandas as pd

from config.settings import (DESFAZER_ETAPA_MIN, ETAPAS_VIAGEM, PERFIL_MOTORISTA, RAIO_REVENDA_PADRAO_M,
                             TOLERANCIA_APRESENTACAO_MIN)
from core import tempo
from repositories import carreteiro_repo as repo
from repositories import usuarios_repo
from services.erros import RegraNegocioError

ETAPAS = {e[0]: {"botao": e[1], "coluna": e[2], "icone": e[3], "nome": e[4], "ordem": i}
          for i, e in enumerate(ETAPAS_VIAGEM)}
ORDEM = [e[0] for e in ETAPAS_VIAGEM]
# etapas em que a placa está na revenda — o GPS confere se estava dentro do raio
ETAPAS_NA_REVENDA = {"inicio", "chegada", "fim"}
MAX_FOTO_BYTES = 12 * 1024 * 1024


def agora_seg() -> str:
    return tempo.agora().strftime("%Y-%m-%d %H:%M:%S")


# --- Utilidades -------------------------------------------------------------
def distancia_m(lat1, lon1, lat2, lon2) -> float:
    """Distância em metros entre dois pontos (fórmula de Haversine)."""
    r = 6_371_000
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def formatar_duracao(horas) -> str:
    if horas is None or (isinstance(horas, float) and math.isnan(horas)):
        return "—"
    minutos = int(round(float(horas) * 60))
    sinal = "-" if minutos < 0 else ""
    minutos = abs(minutos)
    d, resto = divmod(minutos, 1440)
    h, m = divmod(resto, 60)
    if d:
        return f"{sinal}{d}d {h}h"
    return f"{sinal}{h}h {m:02d}min" if h else f"{sinal}{m}min"


def proxima_etapa(v: dict) -> str | None:
    for chave in ORDEM:
        if not v.get(ETAPAS[chave]["coluna"]):
            return chave
    return None


def ultima_etapa(v: dict) -> str | None:
    feitas = [c for c in ORDEM if v.get(ETAPAS[c]["coluna"])]
    return feitas[-1] if feitas else None


def _geo_com_raio(operacao_id: int, etapa: str, geo: dict | None) -> dict | None:
    if not geo or geo.get("lat") is None or geo.get("lon") is None:
        return None
    g = {"lat": float(geo["lat"]), "lon": float(geo["lon"]), "precisao": geo.get("precisao")}
    rev = repo.revenda(operacao_id)
    if rev.get("lat") is not None and rev.get("lon") is not None:
        d = distancia_m(g["lat"], g["lon"], float(rev["lat"]), float(rev["lon"]))
        g["distancia_m"] = round(d)
        if etapa in ETAPAS_NA_REVENDA:
            raio = float(rev.get("raio_m") or RAIO_REVENDA_PADRAO_M)
            g["dentro_raio"] = int(d <= raio + min(float(g.get("precisao") or 0), 150))
    return g


def situacao_apresentacao(agendamento: str | None, ts: str) -> tuple[int | None, int | None]:
    """(no_prazo 1/0, atraso em minutos; negativo = adiantado)."""
    ag = tempo.parse_dt(agendamento)
    if not ag:
        return None, None
    diff = (tempo.parse_dt(ts) - ag).total_seconds() / 60
    return int(diff <= TOLERANCIA_APRESENTACAO_MIN), int(round(diff))


def mensagem_apresentacao(v: dict) -> tuple[str, str] | None:
    """(tipo, texto) para avisar o motorista se a apresentação ficou dentro ou fora do agendamento."""
    if not v.get("ts_apresentado"):
        return None
    if v.get("apresentou_no_prazo") is None:
        return "info", "Apresentação registrada (viagem sem horário de agendamento)."
    atraso = int(v.get("atraso_min") or 0)
    if v["apresentou_no_prazo"]:
        folga = f" — {formatar_duracao(-atraso / 60)} antes do horário" if atraso < 0 else ""
        return "success", f"✅ Você se apresentou DENTRO do agendamento{folga}."
    return "error", f"⚠️ Apresentação FORA do agendamento — atraso de {formatar_duracao(atraso / 60)}."


# --- Viagem -----------------------------------------------------------------
def iniciar_viagem(usuario: dict, numero_pedido: str, data_ag: dt.date | None, hora_ag: dt.time | None,
                   destino_id: int | None, placa: str | None, geo: dict | None = None) -> int:
    mot = repo.motorista_do_usuario(usuario["id"])
    if not mot:
        raise RegraNegocioError("Seu acesso não está ligado a um motorista. Fale com a Puxada.")
    if repo.viagem_ativa_motorista(mot["id"]):
        raise RegraNegocioError("Você já tem uma viagem em andamento.")
    numero_pedido = (numero_pedido or "").strip()
    if not numero_pedido:
        raise RegraNegocioError("Informe o número do pedido.")
    if not destino_id:
        raise RegraNegocioError("Escolha o destino.")
    if not placa:
        raise RegraNegocioError("Escolha a placa do cavalo.")
    if repo.pedido_em_viagem(mot["operacao_id"], numero_pedido):
        raise RegraNegocioError(f"O pedido {numero_pedido} já tem uma viagem lançada. Confira o número.")
    outra = repo.viagem_ativa_placa(mot["operacao_id"], placa)
    if outra:
        raise RegraNegocioError(f"A placa {placa} já está em viagem com {outra['motorista']}.")
    if hora_ag and not data_ag:
        raise RegraNegocioError("Informe a data do agendamento.")
    agendamento = None
    if data_ag:
        agendamento = f"{data_ag:%Y-%m-%d} {(hora_ag or dt.time(0, 0)):%H:%M}"
    destino = next((d for d in repo.destinos() if d["id"] == destino_id), None)
    ts = agora_seg()
    vid = repo.criar_viagem({
        "operacao_id": mot["operacao_id"], "motorista_id": mot["id"], "usuario_id": usuario["id"],
        "numero_pedido": numero_pedido, "agendamento": agendamento, "destino_id": destino_id,
        "destino": destino["nome"] if destino else None, "placa": placa.upper(), "status": repo.EM_VIAGEM,
        "ts_inicio": ts,
    })
    repo.registrar_evento(vid, "inicio", ts, _geo_com_raio(mot["operacao_id"], "inicio", geo))
    return vid


def _viagem_do_usuario(usuario: dict, viagem_id: int) -> dict:
    v = repo.viagem(viagem_id)
    mot = repo.motorista_do_usuario(usuario["id"])
    if not v or not mot or v["motorista_id"] != mot["id"]:
        raise RegraNegocioError("Viagem não encontrada.")
    if v["status"] != repo.EM_VIAGEM:
        raise RegraNegocioError("Esta viagem já foi encerrada.")
    return v


def registrar_etapa(usuario: dict, viagem_id: int, etapa: str, geo: dict | None = None) -> dict:
    v = _viagem_do_usuario(usuario, viagem_id)
    esperada = proxima_etapa(v)
    if etapa not in ETAPAS or etapa == "inicio":
        raise RegraNegocioError("Etapa inválida.")
    if etapa != esperada:
        if v.get(ETAPAS[etapa]["coluna"]):
            raise RegraNegocioError(f"“{ETAPAS[etapa]['nome']}” já foi registrado.")
        raise RegraNegocioError(f"Antes, registre “{ETAPAS[esperada]['nome']}”.")
    if etapa == "carregado" and not repo.notas(viagem_id):
        raise RegraNegocioError("Adicione pelo menos uma nota fiscal com foto antes de confirmar o carregamento.")
    if etapa == "carregado" and any(n["fotos"] == 0 for n in repo.notas(viagem_id)):
        raise RegraNegocioError("Há nota fiscal sem foto. Tire a foto de todas as notas.")
    ts = agora_seg()
    extra = {}
    if etapa == "apresentado":
        extra["apresentou_no_prazo"], extra["atraso_min"] = situacao_apresentacao(v.get("agendamento"), ts)
    if etapa == "fim":
        extra["status"] = repo.FINALIZADA
    if not repo.marcar_etapa(viagem_id, ETAPAS[etapa]["coluna"], ts, extra):
        raise RegraNegocioError(f"“{ETAPAS[etapa]['nome']}” já foi registrado.")
    repo.registrar_evento(viagem_id, etapa, ts, _geo_com_raio(v["operacao_id"], etapa, geo))
    integrar(viagem_id)
    return repo.viagem(viagem_id)


def desfazer_ultima(usuario: dict, viagem_id: int) -> str:
    """O motorista pode desfazer um clique errado até DESFAZER_ETAPA_MIN minutos depois."""
    v = _viagem_do_usuario(usuario, viagem_id)
    ultima = ultima_etapa(v)
    if not ultima:
        raise RegraNegocioError("Nada para desfazer.")
    quando = tempo.parse_dt(v[ETAPAS[ultima]["coluna"]])
    if quando and (tempo.agora() - quando).total_seconds() > DESFAZER_ETAPA_MIN * 60:
        raise RegraNegocioError(f"Só é possível desfazer até {DESFAZER_ETAPA_MIN} minutos depois. "
                                "Peça a correção para a Puxada.")
    if ultima == "inicio":
        repo.atualizar(viagem_id, status=repo.CANCELADA, observacao="Cancelada pelo motorista ao desfazer o início")
    else:
        campos = {ETAPAS[ultima]["coluna"]: None}
        if ultima == "apresentado":
            campos.update(apresentou_no_prazo=None, atraso_min=None)
        repo.atualizar(viagem_id, **campos)
    repo.apagar_evento(viagem_id, ultima)
    integrar(viagem_id)
    return ETAPAS[ultima]["nome"]


# --- Notas fiscais e fotos ---------------------------------------------------
def _comprimir(conteudo: bytes, tipo: str) -> tuple[bytes, str]:
    """Reduz fotos grandes do celular (máx. 1600 px, JPEG 75%). Se não conseguir, guarda o original."""
    if not (tipo or "").startswith("image/"):
        return conteudo, tipo
    try:
        from PIL import Image, ImageOps

        img = ImageOps.exif_transpose(Image.open(io.BytesIO(conteudo)))
        img = img.convert("RGB")
        img.thumbnail((1600, 1600))
        saida = io.BytesIO()
        img.save(saida, "JPEG", quality=75, optimize=True)
        menor = saida.getvalue()
        return (menor, "image/jpeg") if len(menor) < len(conteudo) else (conteudo, tipo)
    except Exception:
        return conteudo, tipo


def _preparar_fotos(arquivos) -> list[tuple[str, str, bytes]]:
    fotos = []
    for a in arquivos or []:
        if a is None:
            continue
        dados = a.getvalue()
        if not dados:
            continue
        if len(dados) > MAX_FOTO_BYTES:
            raise RegraNegocioError(f"A foto {a.name} passa de 12 MB.")
        conteudo, tipo = _comprimir(dados, getattr(a, "type", "") or "image/jpeg")
        fotos.append((a.name, tipo, conteudo))
    return fotos


def adicionar_nota(usuario: dict, viagem_id: int, numero: str, arquivos) -> int:
    v = _viagem_do_usuario(usuario, viagem_id)
    if not v.get("ts_inicio"):
        raise RegraNegocioError("Inicie a viagem primeiro.")
    numero = re.sub(r"\s+", "", numero or "")
    if not numero:
        raise RegraNegocioError("Digite o número da nota fiscal.")
    fotos = _preparar_fotos(arquivos)
    if not fotos:
        raise RegraNegocioError("Tire (ou escolha) pelo menos uma foto da nota.")
    if repo.nota_existe(viagem_id, numero):
        raise RegraNegocioError(f"A NF {numero} já foi adicionada. Para mais fotos, use “➕ fotos” nela.")
    nid = repo.adicionar_nota(viagem_id, numero, agora_seg(), fotos)
    integrar(viagem_id)
    return nid


def adicionar_fotos(usuario: dict, viagem_id: int, nota_id: int, arquivos) -> int:
    _viagem_do_usuario(usuario, viagem_id)
    fotos = _preparar_fotos(arquivos)
    if not fotos:
        raise RegraNegocioError("Escolha pelo menos uma foto.")
    repo.adicionar_fotos(viagem_id, nota_id, agora_seg(), fotos)
    return len(fotos)


def remover_nota(usuario: dict, viagem_id: int, nota_id: int) -> None:
    v = _viagem_do_usuario(usuario, viagem_id)
    if v.get("ts_carregado") and len(repo.notas(viagem_id)) <= 1:
        raise RegraNegocioError("O pedido já foi carregado — a viagem precisa de pelo menos uma NF.")
    repo.remover_nota(viagem_id, nota_id)
    integrar(viagem_id)


# --- Integração com o resto da Puxada --------------------------------------------
# A viagem começa no carregamento da fábrica e alimenta, sozinha:
#   • 🔗 Vincular Pedido & NFs  — no "Pedido carregado" (pedido, placa, fábrica, motorista, NFs e o HL
#     dos Pedidos Marcados); acompanha cada NF incluída ou removida.
#   • 🅿️ Descarga (Pátio)       — na "Saída da cervejaria" entra como "A caminho" com previsão de chegada;
#     na "Chegada na revenda" vira "Chegou"; no "Finalizar viagem" vira "Descarregado".
ORIGEM_APP = "App Carreteiro"


def _hora_meia(d: dt.datetime) -> str:
    """Arredonda para o horário de 30 em 30 minutos usado no pátio."""
    total = int(round((d.hour * 60 + d.minute) / 30.0)) * 30
    total = min(total, 23 * 60 + 30)
    return f"{total // 60:02d}:{total % 60:02d}"


def previsao_chegada(v: dict) -> dt.datetime | None:
    """Saída da cervejaria + média dos últimos retornos desse destino (ou de todos)."""
    saida = tempo.parse_dt(v.get("ts_saida_cervejaria"))
    if not saida:
        return None
    for destino in (v.get("destino_id"), None):
        horas = []
        for r in repo.retornos_destino(v["operacao_id"], destino):
            a, b = tempo.parse_dt(r["ts_saida_cervejaria"]), tempo.parse_dt(r["ts_chegada_revenda"])
            if a and b and b > a and r["ts_saida_cervejaria"] != v.get("ts_saida_cervejaria"):
                horas.append((b - a).total_seconds() / 3600)
        if len(horas) >= 2 or (horas and destino is None):
            horas.sort()
            mediana = horas[len(horas) // 2]
            return saida + dt.timedelta(hours=mediana)
    return None


def _obs_descarga(v: dict) -> str:
    partes = [f"📱 Pedido {v['numero_pedido']}", v.get("motorista") or ""]
    nfs = repo.nfs_texto(v["id"])
    if nfs:
        partes.append(f"NFs {nfs}")
    if v.get("ts_chegada_revenda"):
        partes.append(f"chegou {tempo.parse_dt(v['ts_chegada_revenda']):%d/%m %H:%M}")
    elif v.get("ts_saida_cervejaria"):
        partes.append(f"saiu da cervejaria {tempo.parse_dt(v['ts_saida_cervejaria']):%d/%m %H:%M}")
    return " · ".join(p for p in partes if p)


def _sincronizar_vinculo(v: dict) -> None:
    from repositories import logistica_repo

    atual = repo.vinculo_da_viagem(v["id"])
    if v["status"] == repo.CANCELADA or not v.get("ts_carregado"):
        if atual:
            repo.apagar_vinculo_da_viagem(v["id"])
        return
    if not atual:
        atual = repo.vinculo_manual_do_pedido(v["operacao_id"], v["numero_pedido"])
    marcado = repo.pedido_marcado(v["operacao_id"], v["numero_pedido"])
    dados = {
        "numero_pedido": v["numero_pedido"], "data_puxada": str(v["ts_carregado"])[:10], "placa": v["placa"],
        "fabrica": v.get("destino"), "motorista": v.get("motorista"), "notas_fiscais": repo.nfs_texto(v["id"]),
        "viagem_id": v["id"],
    }
    if not atual or not float(atual.get("hl_carregado") or 0):
        dados["hl_carregado"] = float(marcado["hl"]) if marcado else 0.0
    logistica_repo.salvar_vinculo(v["operacao_id"], atual["id"] if atual else None, dados)


def _sincronizar_descarga(v: dict) -> None:
    from repositories import logistica_repo

    ag = repo.agendamento_da_viagem(v["id"])
    if v["status"] == repo.CANCELADA:
        if ag and ag["status"] not in ("Descarregado",):
            logistica_repo.atualizar_agendamento(ag["id"], status="Cancelado")
        return
    if not v.get("ts_saida_cervejaria"):  # ainda não saiu (ou desfez a saída)
        if ag:
            if ag.get("criado_por") == ORIGEM_APP:
                repo.apagar_agendamento(ag["id"])
            else:
                logistica_repo.atualizar_agendamento(ag["id"], status="Agendado", viagem_id=None)
        return
    status = "Descarregado" if v.get("ts_fim") else "Chegou" if v.get("ts_chegada_revenda") else "A caminho"
    obs = _obs_descarga(v)
    if not ag:
        hoje = tempo.hoje()
        ag = repo.agendamento_livre_da_placa(v["operacao_id"], v["placa"], hoje.isoformat(),
                                             (hoje + dt.timedelta(days=2)).isoformat())
        if ag:
            logistica_repo.atualizar_agendamento(ag["id"], viagem_id=v["id"], status=status,
                                                 observacao=((ag.get("observacao") or "") + " | " + obs).strip(" |"))
            return
        prev = previsao_chegada(v) or tempo.parse_dt(v.get("ts_chegada_revenda"))
        data = (prev or tempo.agora()).date().isoformat()
        hora = _hora_meia(prev) if prev else None
        aid = logistica_repo.inserir_agendamento(v["operacao_id"], data, hora, v["placa"], "A definir", None,
                                                 obs, ORIGEM_APP)
        logistica_repo.atualizar_agendamento(aid, viagem_id=v["id"], status=status)
        return
    campos = {"status": status, "placa": v["placa"]}
    if ag.get("criado_por") == ORIGEM_APP:
        campos["observacao"] = obs
    logistica_repo.atualizar_agendamento(ag["id"], **campos)


def integrar(viagem_id: int) -> None:
    """Atualiza vínculo de pedido/NFs e a descarga do pátio a partir da viagem. Nunca derruba o app do motorista."""
    v = repo.viagem(viagem_id)
    if not v:
        return
    for passo in (_sincronizar_vinculo, _sincronizar_descarga):
        try:
            passo(v)
        except Exception as e:  # a viagem já foi gravada; a integração é refeita no próximo passo
            import logging
            logging.getLogger(__name__).warning("Integração da viagem %s falhou em %s: %s", viagem_id,
                                                passo.__name__, e)


# --- Gestão (Puxada) -----------------------------------------------------------
def corrigir_viagem(viagem_id: int, campos: dict, usuario_nome: str = "") -> None:
    """Correção feita pela Puxada (horários, pedido, placa). Valida a ordem das etapas."""
    v = repo.viagem(viagem_id)
    if not v:
        raise RegraNegocioError("Viagem não encontrada.")
    novos = {}
    for k, val in campos.items():
        if k in repo.COLUNAS_TS or k == "agendamento":
            if val in (None, "", "None", "NaT"):
                if k == "ts_inicio":
                    raise RegraNegocioError("O início da viagem não pode ficar vazio.")
                novos[k] = None
                continue
            d = tempo.parse_dt(str(val))
            if not d:
                raise RegraNegocioError(f"Data/hora inválida: {val}. Use DD/MM/AAAA HH:MM.")
            novos[k] = d.strftime("%Y-%m-%d %H:%M:%S" if k != "agendamento" else "%Y-%m-%d %H:%M")
        elif k in ("numero_pedido", "placa", "observacao", "destino"):
            novos[k] = (str(val).strip().upper() if k == "placa" else str(val).strip()) or None
            if k in ("numero_pedido", "placa") and not novos[k]:
                raise RegraNegocioError("Pedido e placa são obrigatórios.")
    final = {**v, **novos}
    # as etapas precisam estar em ordem e sem buracos
    anterior, faltou = None, None
    for chave in ORDEM:
        t = tempo.parse_dt(final.get(ETAPAS[chave]["coluna"]))
        if t is None:
            faltou = faltou or chave
            continue
        if faltou:
            raise RegraNegocioError(f"“{ETAPAS[chave]['nome']}” preenchido sem “{ETAPAS[faltou]['nome']}”.")
        if anterior and t < anterior:
            raise RegraNegocioError(f"“{ETAPAS[chave]['nome']}” ficou antes da etapa anterior.")
        anterior = t
    if "ts_apresentado" in novos or "agendamento" in novos:
        if final.get("ts_apresentado"):
            novos["apresentou_no_prazo"], novos["atraso_min"] = situacao_apresentacao(
                final.get("agendamento"), final["ts_apresentado"])
        else:
            novos["apresentou_no_prazo"] = novos["atraso_min"] = None
    if v["status"] != repo.CANCELADA:
        novos["status"] = repo.FINALIZADA if final.get("ts_fim") else repo.EM_VIAGEM
    if novos:
        obs = (v.get("observacao") or "")
        marca = f"Corrigida por {usuario_nome} em {tempo.agora_str()}" if usuario_nome else ""
        if marca and "observacao" not in novos:
            novos["observacao"] = (obs + " | " if obs else "") + marca
        repo.atualizar(viagem_id, **novos)
        integrar(viagem_id)


def cancelar_viagem(viagem_id: int, motivo: str, usuario_nome: str) -> None:
    if not (motivo or "").strip():
        raise RegraNegocioError("Informe o motivo do cancelamento.")
    repo.atualizar(viagem_id, status=repo.CANCELADA,
                   observacao=f"Cancelada por {usuario_nome} em {tempo.agora_str()}: {motivo.strip()}")
    integrar(viagem_id)


def salvar_revenda(operacao_id: int, lat, lon, raio_m) -> None:
    if (lat in (None, "") or lon in (None, "")) or (float(lat) == 0 and float(lon) == 0):
        repo.salvar_revenda(operacao_id, None, None, None)
        return
    lat, lon, raio_m = float(lat), float(lon), float(raio_m or RAIO_REVENDA_PADRAO_M)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise RegraNegocioError("Latitude/longitude inválidas.")
    if not 30 <= raio_m <= 5000:
        raise RegraNegocioError("O raio deve ficar entre 30 e 5.000 metros.")
    repo.salvar_revenda(operacao_id, lat, lon, raio_m)


def _login_motorista(acesso: str) -> str:
    acesso = (acesso or "").strip().lower()
    if "@" in acesso:
        from services.usuarios_service import validar_email
        return validar_email(acesso)
    digitos = re.sub(r"\D", "", acesso)
    if len(digitos) < 8:
        raise RegraNegocioError("Use o e-mail ou o CPF / celular do motorista (só números).")
    return digitos


def salvar_acesso_motorista(motorista_id: int, acesso: str) -> dict:
    """Cria (ou atualiza o login de) o acesso do motorista. Devolve {"login", "senha"} (senha só se nova)."""
    from core.auth import hash_senha
    from services.usuarios_service import gerar_senha_provisoria

    mot = repo.motorista(motorista_id)
    if not mot:
        raise RegraNegocioError("Motorista não encontrado.")
    login = _login_motorista(acesso)
    dono = usuarios_repo.buscar_por_login(login) or (usuarios_repo.buscar_por_email(login) if "@" in login else None)
    if dono and dono["id"] != mot.get("usuario_id"):
        raise RegraNegocioError("Esse e-mail/CPF já é usado por outro acesso.")
    email = login if "@" in login else None
    dados = {"login": login, "nome": mot["nome"], "email": email, "cargo": "Motorista carreteiro",
             "perfil": PERFIL_MOTORISTA, "e_aprovador": 0, "alcada": 0, "ativo": 1}
    if mot.get("usuario_id") and usuarios_repo.buscar(mot["usuario_id"]):
        atual = usuarios_repo.buscar(mot["usuario_id"])
        dados.update(id=atual["id"], trocar_senha=atual.get("trocar_senha") or 0, ativo=atual["ativo"])
        usuarios_repo.salvar(dados, [], [mot["operacao_id"]])
        return {"login": login, "senha": None}
    senha = gerar_senha_provisoria()
    dados["trocar_senha"] = 1
    uid = usuarios_repo.salvar(dados, [], [mot["operacao_id"]], senha_hash=hash_senha(senha))
    repo.vincular_usuario(motorista_id, uid)
    return {"login": login, "senha": senha}


def nova_senha_motorista(motorista_id: int) -> str:
    from services.usuarios_service import resetar_senha

    mot = repo.motorista(motorista_id)
    if not mot or not mot.get("usuario_id"):
        raise RegraNegocioError("Este motorista ainda não tem acesso.")
    return resetar_senha(mot["usuario_id"])


def bloquear_acesso(motorista_id: int, ativo: bool) -> None:
    mot = repo.motorista(motorista_id)
    if not mot or not mot.get("usuario_id"):
        raise RegraNegocioError("Este motorista ainda não tem acesso.")
    repo.ativar_usuario(mot["usuario_id"], ativo)


# --- Indicadores: TMV / TMA -------------------------------------------------------
def _horas(a: pd.Series, b: pd.Series) -> pd.Series:
    return (b - a).dt.total_seconds() / 3600


def indicadores(operacao_id: int, de: str | None = None, ate: str | None = None) -> pd.DataFrame:
    """Uma linha por viagem com as durações (horas) de cada trecho, o TMV e o TMA."""
    df = repo.viagens_df(operacao_id, de, ate)
    if df.empty:
        return df
    for c in [*repo.COLUNAS_TS, "agendamento"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["tmv_h"] = _horas(df["ts_inicio"], df["ts_fim"])
    df["ida_h"] = _horas(df["ts_inicio"], df["ts_apresentado"])
    df["espera_h"] = _horas(df["ts_apresentado"], df["ts_chamado"])
    df["carregamento_h"] = _horas(df["ts_chamado"], df["ts_carregado"])
    df["liberacao_h"] = _horas(df["ts_carregado"], df["ts_saida_cervejaria"])
    df["volta_h"] = _horas(df["ts_saida_cervejaria"], df["ts_chegada_revenda"])
    df["descarga_h"] = _horas(df["ts_chegada_revenda"], df["ts_fim"])
    df["na_cervejaria_h"] = _horas(df["ts_apresentado"], df["ts_saida_cervejaria"])

    # TMA: chegada na revenda → próximo início de viagem da mesma placa
    chegadas = df.dropna(subset=["ts_chegada_revenda"])
    df["tma_h"] = float("nan")
    df["proxima_viagem_id"] = pd.NA
    if not chegadas.empty:
        inicio_min = chegadas["ts_chegada_revenda"].min().strftime("%Y-%m-%d %H:%M:%S")
        prox = repo.proximas_saidas(operacao_id, sorted(chegadas["placa"].unique().tolist()), inicio_min)
        prox["ts_inicio"] = pd.to_datetime(prox["ts_inicio"], errors="coerce")
        for idx, r in chegadas.iterrows():
            cand = prox[(prox["placa"] == r["placa"]) & (prox["ts_inicio"] >= r["ts_chegada_revenda"])
                        & (prox["id"] != r["id"])]
            if not cand.empty:
                p = cand.iloc[0]
                df.at[idx, "tma_h"] = (p["ts_inicio"] - r["ts_chegada_revenda"]).total_seconds() / 3600
                df.at[idx, "proxima_viagem_id"] = int(p["id"])

    # GPS: chegada e próxima saída dentro do raio da revenda
    geo = repo.geo_viagens([int(i) for i in set(df["id"]).union(
        int(x) for x in df["proxima_viagem_id"].dropna())])
    chegada_ok = set(geo[(geo["etapa"] == "chegada") & (geo["dentro_raio"] == 1)]["viagem_id"])
    saida_ok = set(geo[(geo["etapa"] == "inicio") & (geo["dentro_raio"] == 1)]["viagem_id"])
    com_gps = set(geo[geo["dentro_raio"].notna()]["viagem_id"])
    df["chegada_gps"] = df["id"].map(lambda i: "Dentro do raio" if i in chegada_ok else
                                     ("Fora do raio" if i in com_gps else "Sem GPS"))
    df["tma_confirmado_gps"] = [
        bool(i in chegada_ok and pd.notna(p) and int(p) in saida_ok)
        for i, p in zip(df["id"], df["proxima_viagem_id"])]
    df["data"] = df["ts_inicio"].dt.date
    return df


def placas_na_revenda(operacao_id: int) -> pd.DataFrame:
    """Placas que chegaram na revenda e ainda não saíram de novo (TMA em aberto)."""
    df = repo.viagens_df(operacao_id)
    if df.empty:
        return pd.DataFrame(columns=["placa", "motorista", "chegada", "parada_h"])
    df["ts_inicio"] = pd.to_datetime(df["ts_inicio"], errors="coerce")
    df["ts_chegada_revenda"] = pd.to_datetime(df["ts_chegada_revenda"], errors="coerce")
    ult = df.sort_values("ts_inicio").groupby("placa").tail(1)
    parados = ult[ult["ts_chegada_revenda"].notna()].copy()
    agora = pd.Timestamp(tempo.agora())
    parados["parada_h"] = (agora - parados["ts_chegada_revenda"]).dt.total_seconds() / 3600
    return parados.rename(columns={"ts_chegada_revenda": "chegada"})[
        ["placa", "motorista", "chegada", "parada_h"]].sort_values("parada_h", ascending=False)
