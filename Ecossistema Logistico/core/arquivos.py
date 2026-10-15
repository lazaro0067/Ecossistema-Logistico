"""Uploads em vários formatos: CSV (; , ou tab), TXT, ZIP e Excel (.xlsx, .xlsm, .xls).

Os leitores do sistema trabalham com o CSV do Promax (separador ";", decimal com vírgula, datas dd/mm/aaaa).
`preparar()` converte qualquer formato aceito para esse CSV antes de ler — assim todo relatório sobe igual,
seja exportado em CSV, salvo no Excel ou compactado em .zip.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from services.erros import RegraNegocioError

FORMATOS = ["csv", "txt", "zip", "xlsx", "xlsm", "xls"]
FORMATOS_TXT = "CSV, TXT, Excel (.xlsx/.xls) ou .zip"
_EXCEL = (".xlsx", ".xlsm", ".xls")
_LIMITE_RECONVERTER = 300 * 1024 ** 2  # CSV com outro separador: reescreve só até este tamanho


class _Arquivo(io.BytesIO):
    """Arquivo em memória com nome (imita o arquivo enviado pelo Streamlit)."""

    def __init__(self, dados: bytes, nome: str):
        super().__init__(dados)
        self.name = nome
        self.size = len(dados)

    def getvalue(self) -> bytes:  # noqa: D401
        return super().getvalue()


def _celula(v) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "strftime"):
        t = pd.Timestamp(v)
        return t.strftime("%d/%m/%Y") if (t.hour, t.minute, t.second) == (0, 0, 0) else t.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        return f"{v:.10f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(v).replace("\r", " ").replace("\n", " ")


def _excel_para_csv(dados: bytes, nome: str) -> bytes:
    motor = "xlrd" if nome.lower().endswith(".xls") else "openpyxl"
    try:
        abas = pd.read_excel(io.BytesIO(dados), sheet_name=None, header=None, dtype=object, engine=motor)
    except ImportError as e:
        raise RegraNegocioError("Este formato de Excel não é suportado no servidor — salve como .xlsx ou CSV.") from e
    except Exception as e:
        raise RegraNegocioError(f"Não consegui abrir a planilha ({e}). Salve como .xlsx ou CSV e suba de novo.") from e
    # usa a aba com mais dados
    df = max(abas.values(), key=lambda d: d.shape[0] * max(d.shape[1], 1)) if abas else pd.DataFrame()
    if df.empty:
        raise RegraNegocioError("A planilha está vazia.")
    df = df.dropna(how="all").dropna(axis=1, how="all")
    linhas = [";".join(_celula(v).replace(";", ",") for v in r) for r in df.itertuples(index=False)]
    return ("\n".join(linhas) + "\n").encode("utf-8-sig")


def _separador(amostra: str) -> str:
    linhas = [ln for ln in amostra.splitlines()[:30] if ln.strip()]
    if not linhas:
        return ";"
    conta = {s: sum(ln.count(s) for ln in linhas) for s in (";", "\t", ",", "|")}
    if conta[";"] >= max(len(linhas) // 2, 1):
        return ";"
    return max(conta, key=conta.get) if max(conta.values()) else ";"


def _texto_para_csv(dados: bytes, nome: str) -> bytes:
    """CSV/TXT com outro separador (tab, vírgula, |) vira ';' — o CSV do Promax passa direto."""
    amostra = dados[:200_000]
    try:
        txt = amostra.decode("utf-8-sig")
        enc = "utf-8-sig"
    except UnicodeDecodeError:
        txt, enc = amostra.decode("latin1"), "latin1"
    sep = _separador(txt)
    if sep == ";" or len(dados) > _LIMITE_RECONVERTER:
        return dados
    df = pd.read_csv(io.BytesIO(dados), sep=sep, header=None, dtype=str, encoding=enc, keep_default_na=False,
                     on_bad_lines="skip", engine="python")
    if sep == ",":  # CSV americano: 1234.56 → 1234,56 (só onde é número)
        num = df.apply(lambda c: c.str.fullmatch(r"-?\d+\.\d+"))
        df = df.where(~num.fillna(False), df.apply(lambda c: c.str.replace(".", ",", regex=False)))
    out = io.StringIO()
    df.to_csv(out, sep=";", header=False, index=False)
    return out.getvalue().encode("utf-8-sig")


def converter(dados: bytes, nome: str) -> tuple[bytes, str]:
    """Devolve (bytes do CSV ';', nome .csv). ZIP: pega o CSV/TXT/Excel de dentro. CSV ';' passa sem cópia."""
    n = str(nome or "arquivo").lower()
    if n.endswith(".zip") or dados[:2] == b"PK" and not n.endswith(_EXCEL):
        try:
            z = zipfile.ZipFile(io.BytesIO(dados))
        except zipfile.BadZipFile as e:
            raise RegraNegocioError("O .zip está corrompido ou incompleto — compacte de novo e suba outra vez.") from e
        dentro = [x for x in z.namelist() if not x.endswith("/") and not x.startswith("__MACOSX")]
        txt = [x for x in dentro if x.lower().endswith((".csv", ".txt"))]
        xls = [x for x in dentro if x.lower().endswith(_EXCEL)]
        if txt:
            sep_ok = _separador(z.open(txt[0]).read(200_000).decode("latin1")) == ";"
            if sep_ok:
                return dados, nome  # o leitor lê o .zip em fluxo (arquivo grande)
            return _texto_para_csv(z.read(txt[0]), txt[0]), txt[0].rsplit("/", 1)[-1].rsplit(".", 1)[0] + ".csv"
        if xls:
            return _excel_para_csv(z.read(xls[0]), xls[0]), xls[0].rsplit("/", 1)[-1].rsplit(".", 1)[0] + ".csv"
        raise RegraNegocioError("O .zip não tem nenhum CSV, TXT ou Excel dentro.")
    if n.endswith(_EXCEL):
        return _excel_para_csv(dados, nome), nome.rsplit(".", 1)[0] + ".csv"
    return _texto_para_csv(dados, nome), (nome if n.endswith((".csv", ".txt")) else nome + ".csv")


def preparar(arq):
    """Recebe o arquivo enviado (st.file_uploader) e devolve um arquivo com .name/.getvalue() no formato CSV ';'.
    CSV com ';' e .zip de CSV voltam como vieram (sem copiar — o arquivo grande continua sendo lido em fluxo)."""
    if arq is None:
        return None
    n = str(getattr(arq, "name", "")).lower()
    if n.endswith((".csv", ".txt")):
        arq.seek(0)
        amostra = arq.read(200_000)
        arq.seek(0)
        if _separador(amostra.decode("latin1")) == ";":
            return arq
    elif n.endswith(".zip"):
        try:
            z = zipfile.ZipFile(arq)
            txt = [x for x in z.namelist() if x.lower().endswith((".csv", ".txt"))]
            if txt and _separador(z.open(txt[0]).read(200_000).decode("latin1")) == ";":
                arq.seek(0)
                return arq
        except zipfile.BadZipFile:
            pass
        arq.seek(0)
    dados, nome = converter(arq.getvalue(), getattr(arq, "name", "arquivo"))
    return _Arquivo(dados, nome)
