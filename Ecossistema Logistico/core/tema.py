"""Identidade visual: CSS global, cabeçalho de página, cards de indicador e selos de status.

Cores de status são reservadas (nunca usadas como "série 4" de gráfico) e
sempre aparecem com ícone + texto, nunca só pela cor.
"""
import html

import streamlit as st

# --- Paleta ---------------------------------------------------------------
NAVY = "#0B1F3A"
NAVY_2 = "#16305A"
AZUL = "#2a78d6"
FUNDO = "#F4F6FA"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#898781"
BORDA = "rgba(11,11,11,0.08)"

# status: (cor do traço, fundo do selo, texto do selo, ícone, rótulo padrão)
STATUS = {
    "bom":     ("#0ca30c", "#e7f6e7", "#006300", "✓", "No alvo"),
    "atencao": ("#fab219", "#fff4dc", "#7a5200", "!", "Atenção"),
    "serio":   ("#ec835a", "#fdece5", "#9a3d17", "▲", "Fora do alvo"),
    "critico": ("#d03b3b", "#fbe7e7", "#a12626", "✕", "Crítico"),
    "info":    (AZUL,      "#e6f0fb", "#1c5cab", "•", "Informativo"),
    "neutro":  ("#c3c2b7", "#f0efec", TINTA_2,   "–", "Sem meta"),
}

_CSS = f"""
<style>
:root {{ --navy:{NAVY}; --azul:{AZUL}; --borda:{BORDA}; }}
.stApp {{ background:{FUNDO}; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1500px; }}
#MainMenu, footer, [data-testid="stStatusWidget"] {{ visibility: hidden; }}
h1, h2, h3 {{ letter-spacing: -0.01em; color:{TINTA}; }}

/* ---------- Menu lateral ---------- */
[data-testid="stSidebar"] {{ background: linear-gradient(180deg, {NAVY} 0%, {NAVY_2} 100%); }}
[data-testid="stSidebar"] * {{ color: #E6ECF5; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.12); margin: .6rem 0; }}
[data-testid="stSidebar"] .stButton > button {{
    background: transparent; border: 1px solid transparent; color: #E6ECF5 !important;
    justify-content: flex-start; text-align: left; padding: .45rem .8rem; border-radius: 10px;
    font-weight: 500; min-height: 2.4rem; box-shadow: none;
}}
[data-testid="stSidebar"] .stButton > button p {{ color: #E6ECF5 !important; font-size: .95rem; text-align: left; }}
[data-testid="stSidebar"] .stButton > button > div {{ justify-content: flex-start !important; width: 100%; }}
[data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] {{ text-align: left; width: 100%; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.10); }}
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {{
    background: #ffffff; border-color: #ffffff;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] p,
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] p {{ color: {NAVY} !important; font-weight: 700; }}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.18); }}
[data-testid="stSidebar"] [data-baseweb="select"] * {{ color: #ffffff !important; }}
.eco-marca {{ display:flex; align-items:center; gap:.6rem; margin:.2rem 0 .8rem; }}
.eco-marca .logo {{ width:38px; height:38px; border-radius:10px; background:{AZUL}; display:grid; place-items:center; font-size:1.2rem; }}
.eco-marca b {{ font-size:1.05rem; line-height:1.1; display:block; color:#fff; }}
.eco-marca span {{ font-size:.75rem; opacity:.7; }}
.eco-user {{ background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.10); border-radius:12px; padding:.6rem .75rem; margin-bottom:.4rem; font-size:.85rem; }}
.eco-user b {{ display:block; font-size:.95rem; color:#fff; }}
.eco-menu-titulo {{ font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; opacity:.55; margin:.6rem 0 .2rem .2rem; }}

/* ---------- Cabeçalho da página ---------- */
.eco-hero {{ background:#fff; border:1px solid {BORDA}; border-radius:16px; padding:1.1rem 1.4rem;
    display:flex; justify-content:space-between; align-items:center; gap:1rem; margin-bottom:1rem;
    box-shadow: 0 1px 2px rgba(11,31,58,.04); flex-wrap: wrap; }}
.eco-hero h1 {{ font-size:1.65rem; margin:0; padding:0; }}
.eco-hero p {{ margin:.15rem 0 0; color:{TINTA_2}; font-size:.92rem; }}
.eco-pill {{ display:inline-flex; align-items:center; gap:.35rem; padding:.3rem .7rem; border-radius:999px;
    background:#e6f0fb; color:#1c5cab; font-size:.82rem; font-weight:600; white-space:nowrap; }}
.eco-pill.cinza {{ background:#f0efec; color:{TINTA_2}; }}

/* ---------- Cards de indicador ---------- */
.eco-kpis {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:.8rem; margin:.3rem 0 1rem; }}
.eco-kpi {{ background:#fff; border:1px solid {BORDA}; border-radius:14px; padding:.85rem 1rem .8rem;
    position:relative; overflow:hidden; box-shadow: 0 1px 2px rgba(11,31,58,.04); }}
.eco-kpi::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--cor); }}
.eco-kpi .rot {{ font-size:.8rem; color:{TINTA_2}; font-weight:600; display:flex; gap:.4rem; align-items:center; }}
.eco-kpi .val {{ font-size:1.6rem; font-weight:750; color:{TINTA}; margin:.25rem 0 .1rem; line-height:1.15; }}
.eco-kpi .det {{ font-size:.78rem; color:{TINTA_2}; min-height:1.1rem; }}
/* cards clicáveis: o botão invisível cobre o card inteiro */
div[class*="st-key-kpic_"] {{ position:relative; gap:0 !important; height:100%; }}
div[class*="st-key-kpic_"] [data-testid="stElementContainer"]:has(.eco-kpi),
div[class*="st-key-kpic_"] [data-testid="stMarkdown"],
div[class*="st-key-kpic_"] [data-testid="stMarkdownContainer"] {{ height:100%; }}
div[class*="st-key-kpic_"] .eco-kpi {{ height:100%; margin:0; transition: transform .12s ease, box-shadow .12s ease; }}
div[class*="st-key-kpic_"]:hover .eco-kpi {{ transform: translateY(-2px); border-color: var(--cor);
    box-shadow: 0 12px 24px -14px rgba(11,31,58,.45); }}
div[class*="st-key-kpic_"] [data-testid="stElementContainer"]:has(.stButton) {{ position:absolute; inset:0; z-index:3; margin:0; }}
div[class*="st-key-kpic_"] .stButton, div[class*="st-key-kpic_"] .stButton button {{ width:100%; height:100%; }}
div[class*="st-key-kpic_"] .stButton button {{ opacity:0; cursor:pointer; }}
.eco-kpi .ver {{ font-size:.72rem; font-weight:700; color:{TINTA_3}; margin-top:.4rem; letter-spacing:.01em; }}
div[class*="st-key-kpic_"]:hover .eco-kpi .ver {{ color: var(--cor); }}
.eco-kpis-row {{ margin:.3rem 0 1rem; }}
.eco-selo {{ display:inline-flex; align-items:center; gap:.3rem; padding:.12rem .5rem; border-radius:999px;
    font-size:.72rem; font-weight:700; margin-top:.35rem; }}
.eco-selo i {{ font-style:normal; font-weight:800; }}

/* ---------- Seções e cartões genéricos ---------- */
.eco-secao {{ margin: 1.2rem 0 .4rem; }}
.eco-secao h3 {{ font-size:1.1rem; margin:0; }}
.eco-secao p {{ color:{TINTA_2}; font-size:.85rem; margin:.1rem 0 0; }}
.eco-base {{ background:#fff; border:1px solid {BORDA}; border-radius:14px; padding:.9rem 1rem; height:100%; }}
.eco-base h4 {{ font-size:1rem; margin:0 0 .15rem; }}
.eco-base .freq {{ color:{TINTA_3}; font-size:.78rem; }}

/* ---------- Abas e componentes nativos ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap:.25rem; border-bottom:1px solid {BORDA}; flex-wrap: wrap; }}
.stTabs [data-baseweb="tab"] {{ padding:.55rem .9rem; border-radius:10px 10px 0 0; font-weight:600; }}
.stTabs [aria-selected="true"] {{ background:#fff; }}
[data-testid="stForm"], [data-testid="stExpander"] {{ background:#fff; border:1px solid {BORDA} !important; border-radius:14px; }}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border-radius:12px; overflow:hidden; }}
/* ---------- Cor primária fixa (não depende do config.toml) ---------- */
.stApp [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"],
.stApp [data-testid="stBaseButton-primaryFormSubmit"],
.stApp .main .stButton > button[kind="primary"],
.stApp [data-testid="stMain"] [data-testid="stBaseButton-primary"] {{
    background: {AZUL}; border-color: {AZUL}; color: #fff; }}
.stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover,
.stApp [data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover {{ background: #1c5cab; border-color: #1c5cab; }}
.stTabs [aria-selected="true"] p {{ color: {AZUL}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {AZUL}; }}
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: transparent; }}



</style>
"""


def aplicar() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _e(txt) -> str:
    return html.escape(str(txt if txt is not None else ""))


def selo(status: str, rotulo: str | None = None) -> str:
    cor, fundo, texto, icone, padrao = STATUS.get(status, STATUS["neutro"])
    return (f'<span class="eco-selo" style="background:{fundo};color:{texto}">'
            f'<i>{icone}</i>{_e(rotulo or padrao)}</span>')


def cabecalho(titulo: str, subtitulo: str = "", icone: str = "", pills: list[str] | None = None) -> None:
    pills_html = "".join(f'<span class="eco-pill{" cinza" if i else ""}">{_e(p)}</span> '
                         for i, p in enumerate(pills or []))
    st.markdown(
        f'<div class="eco-hero"><div><h1>{_e(icone)} {_e(titulo)}</h1>'
        f'{f"<p>{_e(subtitulo)}</p>" if subtitulo else ""}</div><div>{pills_html}</div></div>',
        unsafe_allow_html=True,
    )


def secao(titulo: str, descricao: str = "") -> None:
    st.markdown(f'<div class="eco-secao"><h3>{_e(titulo)}</h3>'
                f'{f"<p>{_e(descricao)}</p>" if descricao else ""}</div>', unsafe_allow_html=True)


def _card_html(c: dict, clicavel: bool = False) -> str:
    status = c.get("status", "info")
    cor = STATUS.get(status, STATUS["neutro"])[0]
    selo_html = selo(status, c.get("selo")) if c.get("selo") or status not in ("info",) else ""
    ver = f'<div class="ver">🔎 ver {_e(c.get("ver") or "detalhes")} ›</div>' if clicavel else ""
    return (f'<div class="eco-kpi" style="--cor:{cor}">'
            f'<div class="rot">{_e(c.get("icone", ""))} {_e(c["titulo"])}</div>'
            f'<div class="val">{_e(c["valor"])}</div>'
            f'<div class="det">{_e(c.get("detalhe", ""))}</div>{selo_html}{ver}</div>')


def _tem_detalhe(c: dict) -> bool:
    return c.get("dados") is not None or callable(c.get("ao_clicar"))


def kpis(cards: list[dict], key: str | None = None) -> None:
    """cards: [{titulo, valor, detalhe?, status?, selo?, icone?, dados?, colunas?, ao_clicar?}]

    Card com `dados` (DataFrame) fica clicável e abre o detalhamento com esses registros;
    `colunas` é o column_config da tabela. `ao_clicar` (função) troca o detalhamento por outra ação.
    """
    if not any(_tem_detalhe(c) for c in cards):
        st.markdown(f'<div class="eco-kpis">{"".join(_card_html(c) for c in cards)}</div>', unsafe_allow_html=True)
        return
    import hashlib

    base = key or "k" + hashlib.md5("|".join(str(c["titulo"]) for c in cards).encode()).hexdigest()[:8]
    por_linha = len(cards) if len(cards) <= 6 else 4
    clicado = None
    for ini in range(0, len(cards), por_linha):
        linha = cards[ini:ini + por_linha]
        for i, (col, c) in enumerate(zip(st.columns(por_linha), linha), start=ini):
            with col:
                if not _tem_detalhe(c):
                    st.markdown(_card_html(c), unsafe_allow_html=True)
                    continue
                with st.container(key=f"kpic_{base}_{i}"):
                    st.markdown(_card_html(c, clicavel=True), unsafe_allow_html=True)
                    if st.button(f"Ver {c['titulo']}", key=f"kpib_{base}_{i}", help=f"Ver detalhes: {c['titulo']}"):
                        clicado = c
    st.markdown('<div class="eco-kpis-row"></div>', unsafe_allow_html=True)
    if clicado is not None:
        if callable(clicado.get("ao_clicar")):
            clicado["ao_clicar"]()
        else:
            detalhe(clicado["titulo"], clicado["dados"], clicado.get("colunas"))


@st.dialog("🔎 Detalhamento", width="large")
def _dialogo_detalhe(titulo: str, df, colunas: dict | None) -> None:
    from core.ui import LARGURA

    st.markdown(f"#### {_e(titulo)}")
    if df is None or len(df) == 0:
        st.info("Nenhum registro.")
        return
    st.caption(f"{len(df)} registro(s)")
    st.dataframe(df, hide_index=True, column_config=colunas, **LARGURA)
    csv = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    nome = "".join(ch if ch.isalnum() else "_" for ch in str(titulo).lower())[:40] or "detalhe"
    try:
        st.download_button("⬇️ Baixar (CSV)", csv, file_name=f"{nome}.csv", mime="text/csv", on_click="ignore")
    except TypeError:  # Streamlit sem on_click="ignore"
        st.download_button("⬇️ Baixar (CSV)", csv, file_name=f"{nome}.csv", mime="text/csv")


def detalhe(titulo: str, df, colunas: dict | None = None) -> None:
    """Abre a janela de detalhamento com os registros por trás de um card ou de uma barra."""
    _dialogo_detalhe(titulo, df, colunas)


# --- Regras de cor por desempenho ----------------------------------------
def status_atingimento(pct: float | None, invertido: bool = False) -> str:
    """Atingimento de meta (%). invertido=True para custos (quanto menor, melhor)."""
    if pct is None:
        return "neutro"
    if invertido:
        return "bom" if pct <= 90 else "atencao" if pct <= 100 else "serio" if pct <= 110 else "critico"
    return "bom" if pct >= 100 else "atencao" if pct >= 90 else "serio" if pct >= 75 else "critico"


def status_ocupacao(pct: float) -> str:
    return "bom" if pct < 75 else "atencao" if pct < 85 else "serio" if pct < 95 else "critico"


def status_contagem(n: int, alerta: int = 1, critico: int = 5) -> str:
    return "bom" if n < alerta else "atencao" if n < critico else "critico"


# ---------------------------------------------------------------------------
# Tela de login
# ---------------------------------------------------------------------------
_CSS_LOGIN = f"""
<style>
.stApp {{ background: radial-gradient(1200px 600px at 10% 0%, #dfe9f8 0%, transparent 60%),
                      radial-gradient(900px 500px at 100% 100%, #e3ecf9 0%, transparent 55%), {FUNDO}; }}
.block-container {{ max-width: 1040px; padding-top: 7vh; }}
.st-key-login_card {{ background:#fff; border-radius: 22px; overflow: hidden; gap: 0;
    box-shadow: 0 24px 60px -18px rgba(11,31,58,.28), 0 2px 6px rgba(11,31,58,.06); border:1px solid {BORDA}; }}
.st-key-login_card [data-testid="stHorizontalBlock"] {{ gap: 0; align-items: stretch; }}
.st-key-login_card [data-testid="stColumn"]:first-child {{
    background: linear-gradient(160deg, {NAVY} 0%, {NAVY_2} 55%, #1f4a8a 100%); position: relative; }}
.st-key-login_card [data-testid="stColumn"]:last-child {{ padding: 2.6rem 2.6rem 2.2rem; display:flex;
    flex-direction:column; justify-content:center; }}
.lg-marca {{ padding: 2.6rem 2.4rem; color:#E6ECF5; height:100%; min-height: 460px;
    display:flex; flex-direction:column; justify-content:space-between; }}
.lg-logo {{ display:flex; align-items:center; gap:.75rem; }}
.lg-logo .ic {{ width:46px; height:46px; border-radius:13px; background:{AZUL}; display:grid; place-items:center;
    font-size:1.45rem; box-shadow:0 8px 20px rgba(42,120,214,.45); }}
.lg-logo b {{ display:block; font-size:1.15rem; color:#fff; letter-spacing:-.01em; }}
.lg-logo span {{ font-size:.8rem; opacity:.7; }}
.lg-titulo {{ font-size:2rem; line-height:1.15; font-weight:800; color:#fff; margin:2.2rem 0 .7rem; letter-spacing:-.02em; }}
.lg-sub {{ font-size:.95rem; opacity:.78; max-width: 26rem; }}
.lg-itens {{ display:grid; gap:.65rem; margin-top:1.6rem; }}
.lg-item {{ display:flex; gap:.7rem; align-items:center; background:rgba(255,255,255,.06);
    border:1px solid rgba(255,255,255,.10); border-radius:12px; padding:.6rem .8rem; font-size:.9rem; }}
.lg-item i {{ font-style:normal; font-size:1.1rem; }}
.lg-rodape {{ font-size:.75rem; opacity:.55; margin-top:1.8rem; }}
.lg-form-titulo {{ font-size:1.55rem; font-weight:800; color:{TINTA}; margin:0; letter-spacing:-.01em; }}
.lg-form-sub {{ color:{TINTA_2}; font-size:.92rem; margin:.25rem 0 1.4rem; }}
.st-key-login_card [data-testid="stForm"] {{ border:none !important; padding:0; background:transparent; }}
.st-key-login_card input {{ height: 2.8rem; font-size: .98rem; }}
.st-key-login_card [data-testid="stFormSubmitButton"] button {{ height: 2.9rem; font-weight:700; font-size:1rem;
    border-radius: 11px; }}
.st-key-login_card .stButton > button {{ border:none; background:transparent; color:{AZUL}; font-weight:600; }}
.st-key-login_card .stButton > button:hover {{ background:#eef4fc; color:#1c5cab; }}
@media (max-width: 760px) {{
  .st-key-login_card [data-testid="stColumn"]:first-child {{ display:none; }}
  .st-key-login_card [data-testid="stColumn"]:last-child {{ padding: 1.8rem 1.4rem; }}
  .block-container {{ padding-top: 3vh; }}
}}
</style>
"""


def painel_marca(titulo: str, subtitulo: str, empresa: str, icone: str) -> None:
    st.markdown(_CSS_LOGIN, unsafe_allow_html=True)
    itens = [("🚚", "Puxada, fretes e pátio"), ("🔄", "Ressuprimento, estoque e marcação D0–D2"),
             ("📊", "Indicadores e Book DPO por filial"), ("🔒", "Acesso individual por pasta")]
    st.markdown(
        f'''<div class="lg-marca"><div>
        <div class="lg-logo"><div class="ic">{_e(icone)}</div><div><b>{_e(titulo)}</b><span>{_e(subtitulo)}</span></div></div>
        <div class="lg-titulo">Toda a operação da revenda em um só lugar.</div>
        <div class="lg-sub">Planeje a puxada, acompanhe o estoque e as metas de cada filial com dados atualizados.</div>
        <div class="lg-itens">{"".join(f'<div class="lg-item"><i>{i}</i>{_e(t)}</div>' for i, t in itens)}</div>
        </div><div class="lg-rodape">{_e(empresa)} · uso interno</div></div>''',
        unsafe_allow_html=True)


def titulo_form(titulo: str, subtitulo: str) -> None:
    st.markdown(f'<p class="lg-form-titulo">{_e(titulo)}</p><p class="lg-form-sub">{_e(subtitulo)}</p>',
                unsafe_allow_html=True)
