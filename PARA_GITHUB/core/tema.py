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
.eco-login {{ max-width: 420px; margin: 6vh auto 0; }}
.eco-login .eco-hero {{ flex-direction: column; align-items: flex-start; }}
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


def kpis(cards: list[dict]) -> None:
    """cards: [{titulo, valor, detalhe?, status?, selo?, icone?}]"""
    partes = []
    for c in cards:
        status = c.get("status", "info")
        cor = STATUS.get(status, STATUS["neutro"])[0]
        selo_html = selo(status, c.get("selo")) if c.get("selo") or status not in ("info",) else ""
        partes.append(
            f'<div class="eco-kpi" style="--cor:{cor}">'
            f'<div class="rot">{_e(c.get("icone", ""))} {_e(c["titulo"])}</div>'
            f'<div class="val">{_e(c["valor"])}</div>'
            f'<div class="det">{_e(c.get("detalhe", ""))}</div>{selo_html}</div>'
        )
    st.markdown(f'<div class="eco-kpis">{"".join(partes)}</div>', unsafe_allow_html=True)


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
