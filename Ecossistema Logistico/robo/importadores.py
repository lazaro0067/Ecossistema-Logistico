"""Importa no sistema o arquivo que o robô baixou — usando as MESMAS funções do upload manual (mesmos números)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from core import arquivos, tempo

USUARIO = "🤖 Robô"
LAYOUTS = {"estoque", "pedidos_marcados", "ressuprimento", "linear", "produtos", "politica"}


def _arq(caminho: Path):
    """Arquivo em memória com .name/.getvalue(), já convertido para o CSV ';' que os leitores esperam."""
    dados = caminho.read_bytes()
    a = arquivos._Arquivo(dados, caminho.name)
    return arquivos.preparar(a)


def _layout(chave: str, caminho: Path, op: int) -> str:
    from services import importacao_service as imp
    from services.erros import RegraNegocioError

    df = imp.ler_arquivo(caminho.name, caminho.read_bytes(), chave)
    mapa = imp.sugerir_mapeamento(chave, list(df.columns))
    falta = imp.faltando(chave, mapa)
    if falta:
        raise RegraNegocioError(f"Colunas não reconhecidas ({', '.join(falta)}) — suba uma vez pela tela para "
                                "conferir o de/para.")
    dados = imp.preparar(chave, df, mapa, remover_digito=bool(imp.LAYOUTS[chave].get("digito_verificador")))
    mes = tempo.hoje().strftime("%Y-%m") if imp.LAYOUTS[chave].get("pede_mes") else None
    n = imp.gravar(chave, dados, op, mes_ano=mes, usuario=USUARIO, arquivo=caminho.name)
    return f"{n} linhas gravadas"


def importar(tipo: str, caminho: Path, op: int) -> str:
    """Devolve a mensagem do que foi gravado. Erro de regra = RegraNegocioError (vai para o registro)."""
    if tipo == "so_baixar":
        return "arquivo salvo na pasta (sem importar)"
    if tipo in LAYOUTS:
        return _layout(tipo, caminho, op)
    if tipo == "vendas":
        from services import produtividade_entrega_service as pe

        a = _arq(caminho)
        r = pe.importar_notas(a, a.name, op, USUARIO)
        return f"{r['itens']} itens · {r['meses']} mês(es) · {r['mapas']} mapas"
    if tipo == "compra":
        from services import faturamento_service as fs

        a = _arq(caminho)
        r = fs.importar_compra(a, a.name, op, USUARIO)
        return f"{r['itens']} itens · {r['meses']} mês(es)"
    if tipo == "pcd":
        from services import produtividade_entrega_service as pe

        a = _arq(caminho)
        r = pe.importar_pcd(a.getvalue(), a.name, op, USUARIO)
        return f"{r['linhas']} mapas"
    if tipo == "contagem_validade":
        from services import idade_service as ids

        a = _arq(caminho)
        r = ids.importar(op, a.getvalue(), a.name, USUARIO)
        return f"contagem de {r['data']}: {r['linhas']} linhas · {r['produtos']} produtos"
    if tipo == "saldo_estoque":
        # 02.05.02 do dia = saldo final do mês corrente (vai sendo substituído até o último dia).
        # No dia 1º ele também fecha o mês anterior e abre o mês novo.
        from services import estoque_valor_service as ev

        a = _arq(caminho)
        hoje = tempo.hoje()
        mes = hoje.strftime("%Y-%m")
        msgs = []
        if hoje.day == 1:
            ant = (hoje - dt.timedelta(days=1)).strftime("%Y-%m")
            ev.importar(a.getvalue(), a.name, op, ant, "final", USUARIO)
            ev.importar(a.getvalue(), a.name, op, mes, "inicial", USUARIO)
            msgs.append(f"final de {ant} e inicial de {mes}")
        else:
            r = ev.importar(a.getvalue(), a.name, op, mes, "final", USUARIO)
            msgs.append(f"saldo final de {mes}: {r['itens']} itens")
        return " · ".join(msgs)
    raise ValueError(f"tipo de importação desconhecido: {tipo}")
