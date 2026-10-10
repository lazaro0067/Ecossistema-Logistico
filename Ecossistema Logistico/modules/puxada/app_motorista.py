"""App Carreteiro — tela do motorista (celular).

O motorista entra com o próprio acesso e vê só esta tela: abre a viagem
(pedido, agendamento, destino e placa), aperta o botão verde e vai marcando
cada passo. Cada clique grava data, hora e — se o celular permitir — o GPS.
"""
import datetime as dt

import streamlit as st

from core import session, tema, tempo, ui
from modules.componentes.geolocalizacao import localizacao, ponto
from repositories import carreteiro_repo as repo
from services import carreteiro_service as svc
from services import usuarios_service
from services.erros import RegraNegocioError

VERDE, AZUL, LARANJA = "#22a06b", "#2f6fe0", "#f4845f"
# azul da marca Lima (cor da carreta): TEAL = destaque, TEAL_ESC = escuro, TINTA = fundo mais escuro
TEAL, TEAL_ESC, TINTA = "#2f6fe0", "#1d47a6", "#0b2563"

_CSS = f"""
<style>
.block-container {{ max-width: 640px; padding-top: 1.2rem; padding-left: 1rem; padding-right: 1rem; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
.car-topo {{ background: linear-gradient(135deg, #0B1F3A 0%, #1f4a8a 100%); color: #fff; border-radius: 18px;
    padding: 1rem 1.2rem; margin-bottom: .8rem; }}
.car-topo b {{ font-size: 1.25rem; display: block; }}
.car-topo span {{ opacity: .8; font-size: .88rem; }}
.car-viagem {{ background: #fff; border: 1px solid #e1e0d9; border-radius: 16px; padding: .9rem 1.1rem; margin: .4rem 0 .8rem; }}
.car-viagem .lin {{ display: flex; justify-content: space-between; gap: .6rem; padding: .2rem 0; font-size: .95rem; }}
.car-viagem .lin span {{ color: #898781; }}
.car-viagem .lin b {{ text-align: right; }}
.car-passos {{ margin: .4rem 0 1rem; }}
.car-passo {{ display: flex; align-items: center; gap: .75rem; padding: .55rem .2rem; border-left: 3px solid #e1e0d9;
    margin-left: .9rem; padding-left: 1rem; position: relative; }}
.car-passo .ic {{ position: absolute; left: -1.05rem; width: 1.8rem; height: 1.8rem; border-radius: 50%;
    display: grid; place-items: center; font-size: .95rem; background: #f0efec; border: 2px solid #e1e0d9; }}
.car-passo.feito {{ border-left-color: {VERDE}; }}
.car-passo.feito .ic {{ background: #e8f6e8; border-color: {VERDE}; }}
.car-passo.atual .ic {{ background: #eaf2fc; border-color: {AZUL}; box-shadow: 0 0 0 4px rgba(42,120,214,.15); }}
.car-passo.atual {{ font-weight: 700; }}
.car-passo .nm {{ flex: 1; }}
.car-passo .hr {{ color: #52514e; font-size: .88rem; font-variant-numeric: tabular-nums; }}
.car-passo.pend .nm {{ color: #898781; }}
.car-jans {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap:.45rem; margin:.3rem 0 .7rem; }}
.car-jan {{ border-radius:12px; padding:.5rem .6rem; border:1.5px solid; display:flex; flex-direction:column; gap:.1rem; }}
.car-jan b {{ font-size:1rem; }} .car-jan span {{ font-size:.82rem; font-weight:700; }} .car-jan i {{ font-size:.72rem; font-style:normal; opacity:.8; }}
.car-jan.ok {{ background:#ecfdf3; border-color:#34c27a; color:#0f5132; }}
.car-jan.cheia {{ background:#fdecec; border-color:#e5484d; color:#8a1c1f; }}
.car-jan.fim {{ background:#f2f2f0; border-color:#d0cfc8; color:#77766f; }}
.car-nf {{ background: #f7f7f5; border-radius: 12px; padding: .55rem .8rem; margin: .3rem 0; font-size: .92rem; }}
.st-key-car_verde button {{ background: {VERDE} !important; border-color: {VERDE} !important; min-height: 3.6rem;
    border-radius: 14px !important; box-shadow: 0 8px 18px -8px rgba(12,163,12,.7); }}
.st-key-car_verde button p {{ color: #fff !important; font-size: 1.2rem !important; font-weight: 800; }}
.st-key-car_etapa button {{ background: {AZUL} !important; border-color: {AZUL} !important; min-height: 3.6rem;
    border-radius: 14px !important; }}
.st-key-car_etapa button p {{ color: #fff !important; font-size: 1.15rem !important; font-weight: 800; }}
.st-key-car_fim button {{ background: {VERDE} !important; border-color: {VERDE} !important; min-height: 3.6rem;
    border-radius: 14px !important; }}
.st-key-car_fim button p {{ color: #fff !important; font-size: 1.15rem !important; font-weight: 800; }}
.st-key-car_form input {{ height: 2.9rem; font-size: 1rem; }}
/* --- visual do app (cartões coloridos e botões grandes) --- */
.stApp {{ background: linear-gradient(180deg, #eef4ff 0%, #f7f9fc 260px, #f7f9fc 100%); }}
.car-topo {{ position: relative; overflow: hidden; box-shadow: 0 14px 30px -18px rgba(11,31,58,.75); }}
.car-topo:after {{ content: "🚛"; position: absolute; right: -.4rem; bottom: -1.1rem; font-size: 4.6rem; opacity: .13; }}
.car-topo .chip {{ display: inline-block; margin-top: .45rem; padding: .18rem .65rem; border-radius: 999px;
    font-size: .78rem; font-weight: 800; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28); }}
.car-viagem {{ box-shadow: 0 6px 16px -12px rgba(11,31,58,.35); border-radius: 18px; }}
.car-card {{ border-radius: 18px; padding: .9rem 1.05rem; margin: .5rem 0 .7rem; color: #fff;
    box-shadow: 0 12px 24px -16px rgba(11,31,58,.7); }}
.car-card b {{ display: block; font-size: 1.05rem; }}
.car-card span {{ display: block; font-size: .85rem; opacity: .92; margin-top: .15rem; }}
.car-card .car-big {{ font-size: 1.45rem; font-weight: 900; margin-top: .2rem; letter-spacing: -.01em; }}
.car-card.azul {{ background: linear-gradient(135deg, #2a78d6, #1b4fa0); }}
.car-card.verde {{ background: linear-gradient(135deg, #12a150, #0b7a3b); }}
.car-card.laranja {{ background: linear-gradient(135deg, #f08a3c, #d4622a); }}
.car-card.roxo {{ background: linear-gradient(135deg, #7a4fc9, #5a34a3); }}
.car-step {{ display: flex; align-items: center; gap: .6rem; margin: .8rem 0 .35rem; }}
.car-step span {{ width: 1.7rem; height: 1.7rem; flex: none; border-radius: 50%; background: {AZUL}; color: #fff;
    display: grid; place-items: center; font-weight: 900; font-size: .9rem; box-shadow: 0 0 0 4px rgba(42,120,214,.15); }}
.car-step b {{ color: #0B1F3A; font-size: .98rem; display: block; }}
.car-step i {{ color: #6b6a65; font-size: .78rem; font-style: normal; display: block; }}
.car-vazio {{ background: #fff4e5; border: 1.5px dashed #f0a94f; color: #8a4b08; border-radius: 14px;
    padding: .8rem; text-align: center; font-weight: 700; font-size: .9rem; }}
.car-prog {{ height: 10px; background: #e3e9f3; border-radius: 99px; overflow: hidden; margin: .1rem 0 .2rem; }}
.car-prog i {{ display: block; height: 100%; background: linear-gradient(90deg, {VERDE}, #4cc94c); border-radius: 99px; }}
.car-prog-tx {{ font-size: .8rem; color: #52514e; font-weight: 700; margin-bottom: .3rem; }}
/* pills: produto, dia e horários viram quadrados para tocar */
.st-key-car_prod [data-testid="stButtonGroup"] button {{ min-height: 3.4rem; min-width: 9rem; border-radius: 16px;
    font-size: 1.05rem; font-weight: 800; border: 2px solid #c9d6ea; background: #fff; }}
.st-key-car_prod [data-testid="stButtonGroup"] button[kind="pillsActive"] {{ background: {AZUL}; border-color: {AZUL}; color: #fff; }}
.st-key-car_prod [data-testid="stButtonGroup"] button[kind="pillsActive"] p {{ color: #fff; }}
.st-key-car_dias [data-testid="stButtonGroup"] button {{ min-height: 2.9rem; border-radius: 14px; font-weight: 700;
    border: 2px solid #d9e2ef; background: #fff; }}
.st-key-car_dias [data-testid="stButtonGroup"] button[kind="pillsActive"] {{ background: #0B1F3A; border-color: #0B1F3A; }}
.st-key-car_dias [data-testid="stButtonGroup"] button[kind="pillsActive"] p {{ color: #fff; }}
.st-key-car_horas [data-testid="stButtonGroup"] {{ gap: .5rem; }}
.st-key-car_horas [data-testid="stButtonGroup"] button {{ width: 6.6rem; min-height: 4.1rem; border-radius: 16px;
    background: #ecfdf3; border: 2px solid #34c27a; white-space: normal; line-height: 1.2;
    box-shadow: 0 6px 12px -10px rgba(15,81,50,.8); transition: transform .08s ease; }}
.st-key-car_horas [data-testid="stButtonGroup"] button p {{ color: #0f5132; font-weight: 800; font-size: .95rem; }}
.st-key-car_horas [data-testid="stButtonGroup"] button:hover {{ background: #34c27a; transform: translateY(-2px); }}
.st-key-car_horas [data-testid="stButtonGroup"] button:hover p {{ color: #fff; }}
.st-key-car_horas [data-testid="stButtonGroup"] button[kind="pillsActive"] {{ background: {VERDE}; border-color: {VERDE}; }}
.st-key-car_horas [data-testid="stButtonGroup"] button[kind="pillsActive"] p {{ color: #fff; }}
.st-key-nav_mod_motorista [data-testid="stButtonGroup"] button {{ border-radius: 999px; font-weight: 700; }}
.st-key-nav_mod_motorista [data-testid="stButtonGroup"] button[kind="segmented_controlActive"] {{ background: #0B1F3A; color: #fff; }}
.st-key-nav_mod_motorista [data-testid="stButtonGroup"] button[kind="segmented_controlActive"] p {{ color: #fff; }}
/* --- visual de app profissional: verde-água, branco e cartões limpos; abas fixas embaixo --- */
.stApp {{ background: linear-gradient(180deg, {TINTA} 0%, #163d91 45%, #1f55c4 100%) fixed !important; color: #fff; }}
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stWidgetLabel"] *, .stApp .eco-secao h3, .stApp .eco-secao p, .stApp h1, .stApp h2, .stApp h3 {{
    color: #fff !important; }}
.stApp [data-testid="stCaptionContainer"] {{ opacity: .85; }}
/* tudo que tem fundo branco (botões, expansores, formulários) fica com a letra azul */
.stApp [data-testid="stExpander"] details, .stApp [data-testid="stForm"] {{ background: #fff !important;
    border: none !important; border-radius: 16px !important; }}
.stApp [data-testid="stExpander"] [data-testid="stMarkdownContainer"],
.stApp [data-testid="stExpander"] [data-testid="stCaptionContainer"],
.stApp [data-testid="stExpander"] [data-testid="stWidgetLabel"] *,
.stApp [data-testid="stExpander"] summary *,
.stApp [data-testid="stForm"] [data-testid="stMarkdownContainer"],
.stApp [data-testid="stForm"] [data-testid="stCaptionContainer"],
.stApp [data-testid="stForm"] [data-testid="stWidgetLabel"] * {{ color: {TEAL_ESC} !important; }}
.stApp [data-testid="stExpander"] summary svg {{ fill: {TEAL_ESC} !important; color: {TEAL_ESC} !important; }}
.stApp button [data-testid="stMarkdownContainer"], .stApp button p {{ color: {TEAL_ESC} !important; font-weight: 700; }}
.stApp [data-testid="stPopover"] button svg {{ color: {TEAL_ESC} !important; fill: {TEAL_ESC} !important; }}
.stApp [data-testid="stButtonGroup"] button[kind="pillsActive"] p,
.stApp [data-testid="stButtonGroup"] button[kind="pillsActive"] [data-testid="stMarkdownContainer"],
.stApp .st-key-car_horas [data-testid="stButtonGroup"] button:hover p {{ color: #fff !important; }}
.stApp button[kind="primary"] [data-testid="stMarkdownContainer"], .stApp button[kind="primary"] p,
.stApp button[kind="primaryFormSubmit"] [data-testid="stMarkdownContainer"],
.stApp button[kind="primaryFormSubmit"] p {{ color: #fff !important; }}
[data-testid="stPopoverBody"] {{ background: #163d91 !important; color: #fff !important; }}
[data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"] {{ color: #fff !important; }}
.stApp [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {{ color: inherit !important; }}
.car-viagem, .car-nf, .car-vazio, .car-jan {{ color: #1f2937 !important; }}
.car-viagem b, .car-nf b {{ color: #0b2563; }}
.car-nf {{ background: #fff !important; }}
.car-step b {{ color: #fff !important; }} .car-step i {{ color: rgba(255,255,255,.8) !important; }}
.car-prog-tx {{ color: #fff !important; }}
.car-passos {{ background: #fff; border-radius: 18px; padding: .6rem .8rem .6rem .4rem; color: #1f2937; }}
/* tela inicial do app: atalhos grandes em 2 colunas (também no celular) */
.st-key-car_home [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: .7rem; }}
.st-key-car_home [data-testid="stColumn"] {{ min-width: 0 !important; width: 50% !important; flex: 1 1 0 !important; }}
.st-key-car_home button {{ min-height: 7.2rem; border-radius: 20px !important; background: #fff !important; border: none !important;
    box-shadow: 0 14px 26px -18px rgba(0,0,0,.7); }}
.st-key-car_home button p {{ font-size: 1.12rem !important; font-weight: 800 !important; color: #0b2563 !important;
    white-space: pre-line; line-height: 1.5; }}
.st-key-car_home button:active {{ transform: scale(.98); }}
.car-home-tit {{ color: #fff; font-weight: 800; font-size: 1.05rem; margin: .4rem 0 .5rem; }}
.st-key-car_voltar button {{ background: rgba(255,255,255,.14) !important; border: 1px solid rgba(255,255,255,.35) !important;
    border-radius: 999px !important; min-height: 2.4rem; }}
.stApp .st-key-car_voltar button p, .stApp .st-key-car_voltar button [data-testid="stMarkdownContainer"] {{
    color: #fff !important; font-weight: 700; }}
.block-container {{ padding-bottom: 6.5rem !important; }}
.car-topo {{ background: linear-gradient(160deg, {TINTA} 0%, {TEAL_ESC} 70%, {TEAL} 100%) !important; border-radius: 22px !important;
    padding: 1.1rem 1.2rem !important; box-shadow: 0 16px 30px -20px rgba(11,37,99,.9) !important; }}
.car-topo:after {{ opacity: .10 !important; }}
.car-topo .av {{ float: left; width: 3rem; height: 3rem; border-radius: 50%; background: rgba(255,255,255,.16);
    display: grid; place-items: center; font-weight: 800; font-size: 1.1rem; margin-right: .75rem;
    border: 2px solid rgba(255,255,255,.45); }}
.car-topo .chip {{ background: rgba(255,255,255,.14) !important; }}
.car-viagem {{ border: 1px solid #e6ece9 !important; border-radius: 18px !important; background: #fff;
    box-shadow: 0 8px 20px -18px rgba(11,37,99,.6) !important; }}
.car-viagem .lin span {{ color: #6b7a76 !important; }}
.car-passo .ic {{ box-shadow: 0 3px 8px -6px rgba(0,0,0,.4); }}
.car-passo.feito {{ border-left-color: {TEAL} !important; }}
.car-passo.feito .ic {{ background: #e6eeff !important; border-color: {TEAL} !important; }}
.car-passo.atual .ic {{ background: {TEAL} !important; border-color: {TEAL_ESC} !important; color: #fff;
    animation: carpulse 1.6s ease-in-out infinite; }}
@keyframes carpulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(47,111,224,.55); }} 50% {{ box-shadow: 0 0 0 9px rgba(47,111,224,0); }} }}
.car-prog {{ background: #dde6f7 !important; }}
.car-prog i {{ background: {TEAL} !important; }}
.car-step span {{ background: {TEAL} !important; box-shadow: 0 0 0 4px rgba(47,111,224,.2) !important; }}
.car-card.azul {{ background: linear-gradient(160deg, {TINTA}, {TEAL_ESC}) !important; }}
.car-card.verde {{ background: linear-gradient(160deg, {TEAL_ESC}, {TEAL}) !important; }}
.st-key-car_verde button, .st-key-car_etapa button, .st-key-car_fim button {{ background: {TEAL} !important;
    border: none !important; border-radius: 12px !important; min-height: 3.6rem !important;
    box-shadow: 0 6px 14px -8px rgba(29,71,166,.9) !important; }}
.stApp .st-key-car_verde button p, .stApp .st-key-car_etapa button p, .stApp .st-key-car_fim button p,
.stApp .st-key-car_verde button [data-testid="stMarkdownContainer"], .stApp .st-key-car_etapa button [data-testid="stMarkdownContainer"],
.stApp .st-key-car_fim button [data-testid="stMarkdownContainer"] {{ color: #fff !important; font-weight: 700 !important;
    letter-spacing: .01em; }}
.st-key-car_verde button:active, .st-key-car_etapa button:active, .st-key-car_fim button:active {{ background: {TEAL_ESC} !important; }}
.st-key-car_prod [data-testid="stButtonGroup"] button[kind="pillsActive"],
.st-key-car_dias [data-testid="stButtonGroup"] button[kind="pillsActive"] {{ background: {TEAL_ESC} !important; border-color: {TEAL_ESC} !important; }}
.st-key-car_horas [data-testid="stButtonGroup"] button {{ background: #fff !important; border: 2px solid {TEAL} !important; }}
.st-key-car_horas [data-testid="stButtonGroup"] button p {{ color: {TEAL_ESC} !important; }}
.st-key-car_horas [data-testid="stButtonGroup"] button:hover {{ background: {TEAL} !important; }}
.st-key-car_horas [data-testid="stButtonGroup"] button:hover p {{ color: #fff !important; }}
[data-testid="stExpander"], [data-testid="stPopover"] button {{ border-radius: 12px !important; }}
.st-key-car_relato a {{ background: linear-gradient(135deg, #f08a3c, #d4622a) !important; border: none !important;
    border-radius: 16px !important; min-height: 3.1rem; box-shadow: 0 10px 20px -14px rgba(212,98,42,.9); }}
.stApp .st-key-car_relato a p, .stApp .st-key-car_relato a span,
.stApp .st-key-car_relato a [data-testid="stMarkdownContainer"] {{ color: #fff !important; font-weight: 800; font-size: 1.02rem; }}
</style>
"""


_CSS_LOGIN = f"""
<style>
.stApp {{ background: #fff !important; }}
.block-container {{ max-width: 480px; padding-top: 0 !important; padding-left: 1rem !important; padding-right: 1rem !important; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.car-hero {{ margin: 0 -1rem; position: relative; height: 46vh; min-height: 300px; overflow: hidden; border-radius: 0 0 4px 4px;
    background: linear-gradient(180deg, #0b2563 0%, #163d91 100%); }}
.car-hero.foto {{ background-size: cover; background-position: 30% 60%; }}
.car-hero svg {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
.car-hero:after {{ content: ""; position: absolute; inset: 0;
    background: linear-gradient(180deg, rgba(0,0,0,0) 45%, rgba(0,0,0,.55) 100%); }}
.car-hero h1 {{ position: absolute; left: 1.6rem; bottom: 1.3rem; z-index: 2; margin: 0; padding: 0; color: #fff !important;
    font-size: 2.3rem; font-weight: 600; letter-spacing: -.02em; line-height: 1.1; }}
.car-hero h1 small {{ display: block; font-size: .95rem; font-weight: 400; opacity: .85; margin-top: .35rem; letter-spacing: 0; }}
.car-login-corpo {{ padding: 1.6rem .6rem .4rem; }}
.car-login-corpo p {{ color: #5b6b67; font-size: .92rem; margin: 0 0 .2rem; }}
.st-key-car_login {{ padding: 0 .6rem; }}
.st-key-car_login [data-testid="stForm"] {{ border: none !important; padding: 0 !important; }}
.st-key-car_login input {{ height: 3.1rem; font-size: 1.05rem; border-radius: 10px !important; }}
.st-key-car_login [data-testid="stFormSubmitButton"] button {{ background: {TEAL} !important; border: none !important;
    min-height: 3.6rem; border-radius: 8px !important; box-shadow: 0 6px 14px -8px rgba(29,71,166,.9); }}
.st-key-car_login [data-testid="stFormSubmitButton"] button p {{ color: #fff !important; font-size: 1.25rem !important;
    font-weight: 500; }}
.st-key-car_login_aj button {{ background: #fff !important; border: 2px solid {TEAL} !important; min-height: 3.6rem;
    border-radius: 8px !important; }}
.st-key-car_login_aj button p {{ color: {TEAL} !important; font-size: 1.15rem !important; font-weight: 500; }}
.st-key-car_login_aj {{ padding: 0 .6rem; }}
.car-login-rod {{ text-align: center; color: #3d4a47; font-size: 1.05rem; padding: 1.4rem 1rem 2rem; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
</style>
"""

# Ilustração própria (estrada ao entardecer e carreta) — sem imagens externas
_HERO_SVG = """<svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="ceu" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d2b2a"/>
<stop offset=".6" stop-color="#1f6f62"/><stop offset="1" stop-color="#f2b880"/></linearGradient>
<linearGradient id="chao" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#20403c"/><stop offset="1" stop-color="#0b1c1b"/></linearGradient></defs>
<rect width="400" height="300" fill="url(#ceu)"/><circle cx="300" cy="168" r="34" fill="#f7d39a" opacity=".55"/>
<path d="M0 182 L70 150 L130 172 L200 140 L270 170 L340 148 L400 166 L400 200 L0 200Z" fill="#17423d" opacity=".9"/>
<rect y="196" width="400" height="104" fill="url(#chao)"/>
<path d="M170 196 L230 196 L330 300 L70 300Z" fill="#2c3e3b"/>
<path d="M199 205 L201 205 L203 222 L197 222Z M196 234 L204 234 L207 260 L193 260Z M191 272 L209 272 L213 300 L187 300Z" fill="#e9e3c8" opacity=".8"/>
<g transform="translate(118 150)"><rect x="0" y="6" width="112" height="42" rx="3" fill="#e8efed"/>
<rect x="0" y="6" width="112" height="9" fill="#4dbf9f"/><rect x="114" y="18" width="36" height="30" rx="4" fill="#4dbf9f"/>
<rect x="124" y="22" width="20" height="11" rx="2" fill="#123c3a"/><rect x="0" y="48" width="152" height="5" fill="#123c3a"/>
<circle cx="20" cy="56" r="8" fill="#0b1c1b"/><circle cx="36" cy="56" r="8" fill="#0b1c1b"/><circle cx="96" cy="56" r="8" fill="#0b1c1b"/>
<circle cx="134" cy="56" r="8" fill="#0b1c1b"/><circle cx="20" cy="56" r="3" fill="#9fb3ae"/><circle cx="36" cy="56" r="3" fill="#9fb3ae"/>
<circle cx="96" cy="56" r="3" fill="#9fb3ae"/><circle cx="134" cy="56" r="3" fill="#9fb3ae"/>
<rect x="148" y="38" width="5" height="4" fill="#f7d39a"/></g></svg>"""


_FOTO: dict = {}


def _foto_carreta() -> str:
    """Foto da carreta Lima (assets/carreta_lima.jpg) em data URI — carregada uma vez."""
    if "uri" not in _FOTO:
        import base64
        from pathlib import Path

        arq = Path(__file__).resolve().parents[2] / "assets" / "carreta_lima.jpg"
        try:
            _FOTO["uri"] = "data:image/jpeg;base64," + base64.b64encode(arq.read_bytes()).decode()
        except OSError:
            _FOTO["uri"] = ""
    return _FOTO["uri"]


def _topo_login(sub: str, titulo: str = "Seja bem-vindo") -> None:
    st.markdown(_CSS_LOGIN, unsafe_allow_html=True)
    foto = _foto_carreta()
    fundo = (f'<div class="car-hero foto" style="background-image:url({foto})">' if foto
             else f'<div class="car-hero">{_HERO_SVG}')
    st.markdown(f'{fundo}<h1>{tema._e(titulo)}<small>{tema._e(sub)}</small></h1></div>', unsafe_allow_html=True)


def tela_login() -> None:
    """Login do link exclusivo dos motoristas (CPF, celular ou e-mail)."""
    from core.auth import autenticar

    _topo_login("App Carreteiro · Grupo Lima")
    if not st.session_state.get("car_login_aberto"):
        st.markdown('<div class="car-login-corpo"><p>Registre cada etapa da sua viagem, agende a descarga e '
                    'acompanhe suas variáveis.</p></div>', unsafe_allow_html=True)
        with st.container(key="car_login"):
            with st.form("car_login_ini"):
                if st.form_submit_button("Login", type="primary", **ui.LARGURA):
                    st.session_state["car_login_aberto"] = True
                    st.rerun()
        with st.container(key="car_login_aj"):
            with st.popover("Primeiro acesso / senha", **ui.LARGURA):
                st.markdown("O acesso é criado pela **equipe da Puxada** da sua unidade. Peça o seu login "
                            "(CPF ou celular) e a senha provisória — no primeiro acesso você cria a sua senha.")
        st.markdown('<div class="car-login-rod">Grupo Lima</div>', unsafe_allow_html=True)
        return
    st.markdown('<div class="car-login-corpo"><p>Entre com o seu CPF ou celular e a senha.</p></div>',
                unsafe_allow_html=True)
    with st.container(key="car_login"):
        with st.form("car_login_form"):
            acesso = st.text_input("CPF, celular ou e-mail", placeholder="Só os números do CPF ou celular",
                                   autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            lembrar = st.checkbox("Manter conectado neste celular", value=True,
                                  help="Ao abrir o app de novo, você continua de onde parou sem digitar a senha.")
            if st.form_submit_button("Entrar", type="primary", **ui.LARGURA):
                usuario = autenticar(acesso, senha)
                bloq = bloqueio(usuario) if usuario else None
                if bloq:
                    st.error(f"⛔ Acesso permitido somente a partir de {bloq:%d/%m} às {bloq:%H:%M} "
                             "(interjornada de 11 h depois de finalizar a viagem). Bom descanso! 😴")
                elif usuario:
                    session.logar(usuario)
                    if lembrar:
                        from core.auth import gerar_token

                        token = gerar_token(usuario["id"])
                        if token:
                            st.query_params["k"] = token
                    st.rerun()
                else:
                    st.error("Acesso ou senha inválidos.")
    with st.container(key="car_login_aj"):
        if st.button("Voltar", key="car_login_voltar", **ui.LARGURA):
            st.session_state.pop("car_login_aberto", None)
            st.rerun()
    st.markdown('<div class="car-login-rod">Esqueceu a senha? Fale com a Puxada da sua unidade.</div>',
                unsafe_allow_html=True)


def bloqueio(usuario: dict) -> dt.datetime | None:
    """Motorista que finalizou a viagem só entra de novo depois das 11 h de interjornada."""
    from services import disp_motoristas_service

    try:
        return disp_motoristas_service.bloqueio_do_usuario(usuario)
    except Exception:
        return None


def tela_bloqueado(usuario: dict, livre: dt.datetime) -> None:
    """Tela de descanso: mostra até quando o acesso está bloqueado e encerra a sessão."""
    from config.settings import INTERJORNADA_H

    _topo_login("Interjornada em andamento", "Bom descanso")
    ui.mostrar_avisos()
    falta = max((livre - tempo.agora()).total_seconds() / 3600, 0)
    pct = max(0.0, min(100.0, 100 - falta / INTERJORNADA_H * 100))
    nome = (usuario.get("nome") or "").split()[0] if usuario.get("nome") else ""
    st.markdown(
        f'<div style="background:linear-gradient(160deg,#123c3a,#1f8a70);color:#fff;border-radius:18px;margin:1rem 0 0;'
        f'padding:1.3rem 1.2rem;text-align:center;box-shadow:0 16px 30px -20px rgba(11,37,99,.9)">'
        f'<div style="font-size:2.6rem">😴</div><div style="font-size:1.3rem;font-weight:900">Bom descanso{", " + tema._e(nome) if nome else ""}!</div>'
        f'<div style="opacity:.9;margin:.3rem 0 .8rem">Seu acesso ao app volta em</div>'
        f'<div style="font-size:2rem;font-weight:900;letter-spacing:-.02em">{livre:%H:%M}</div>'
        f'<div style="opacity:.9">{livre:%d/%m/%Y} · faltam {svc.formatar_duracao(falta)}</div>'
        f'<div style="height:10px;background:rgba(255,255,255,.25);border-radius:99px;margin:.9rem 0 .2rem;overflow:hidden">'
        f'<div style="height:100%;width:{pct:.0f}%;background:#fff"></div></div>'
        f'<div style="font-size:.8rem;opacity:.85">Interjornada de {INTERJORNADA_H} h contada do “Finalizar viagem”.</div></div>',
        unsafe_allow_html=True)
    st.caption("Precisa entrar antes? Fale com a equipe da Puxada — ela pode liberar o seu acesso.")
    session.sair()
    if "k" in st.query_params:
        del st.query_params["k"]


def _sair() -> None:
    session.sair()
    if "k" in st.query_params:
        del st.query_params["k"]
    st.rerun()


def tela_criar_senha(usuario: dict) -> None:
    _topo_login("Crie a sua senha para começar.", f"Olá, {usuario['nome'].split()[0].title()}!")
    with st.container(key="car_login"):
        with st.form("car_criar_senha"):
            nova = st.text_input("Nova senha", type="password", autocomplete="new-password")
            conf = st.text_input("Confirme a nova senha", type="password", autocomplete="new-password")
            if st.form_submit_button("Salvar e entrar", type="primary", **ui.LARGURA):
                try:
                    usuarios_service.trocar_propria_senha(usuario["id"], None, nova, conf)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    usuario["trocar_senha"] = 0
                    ui.avisar("Senha criada! Boa viagem. 🚛")
                    st.rerun()
    if st.button("Sair", key="car_sair_senha"):
        _sair()


def tela_nao_motorista(usuario: dict) -> None:
    from core.segredos import segredo

    _topo_login("Link exclusivo dos motoristas", "App Carreteiro")
    st.warning(f"{usuario['nome'].split()[0]}, este endereço é só para motoristas. "
               "A gestão da puxada fica no link principal do sistema.")
    url = (segredo("APP_URL") or "").rstrip("/")
    if url:
        st.link_button("Abrir o sistema principal", url)
    if st.button("Sair", key="car_sair_outro"):
        _sair()


def link_do_app() -> str:
    """Endereço do App Carreteiro para mandar aos motoristas.
    Ordem: Secret CARRETEIRO_URL (app separado) → Secret APP_URL → endereço aberto agora → endereço padrão."""
    from config.settings import APP_URL_PADRAO
    from core.segredos import segredo

    proprio = (segredo("CARRETEIRO_URL") or "").strip()
    if proprio:
        return proprio
    url = (segredo("APP_URL") or "").strip().rstrip("/")
    if not url:
        try:
            host = st.context.headers.get("host") or ""
        except Exception:
            host = ""
        url = f"https://{host}" if host and "localhost" not in host and "127.0.0.1" not in host else APP_URL_PADRAO
    return f"{url}/?app=motorista"


def link_whatsapp(texto: str, telefone: str | None = None) -> str:
    """Link do WhatsApp com a mensagem pronta (para o número do motorista, se houver)."""
    from urllib.parse import quote

    numero = "".join(c for c in str(telefone or "") if c.isdigit())
    if len(numero) in (10, 11):
        numero = "55" + numero
    destino = numero if len(numero) in (12, 13) else ""
    return f"https://wa.me/{destino}?text={quote(texto)}"


def _fmt(ts) -> str:
    d = tempo.parse_dt(ts)
    return d.strftime("%d/%m %H:%M") if d else "—"


def _status_chip(mot: dict) -> str:
    v = repo.viagem_ativa_motorista(mot["id"])
    if v:
        prox = svc.proxima_etapa(v)
        return f"🚛 Em viagem · pedido {v['numero_pedido']}" + (f" · próximo: {svc.ETAPAS[prox]['nome']}" if prox else "")
    from repositories import motoristas_repo

    if motoristas_repo.servico_ativo(mot["id"]):
        return "🔧 Em serviço"
    return "🟢 Disponível para viagem"


def _topo(usuario: dict, mot: dict) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1.2])
    with c1:
        partes = mot["nome"].split()
        iniciais = (partes[0][:1] + (partes[-1][:1] if len(partes) > 1 else "")).upper()
        st.markdown(f'<div class="car-topo"><div class="av">{tema._e(iniciais)}</div>'
                    f'<b>Olá, {tema._e(partes[0].title())}! 👋</b>'
                    f'<span>App Carreteiro · {tema._e(tempo.agora().strftime("%d/%m %H:%M"))}</span><br>'
                    f'<span class="chip">{tema._e(_status_chip(mot))}</span></div>',
                    unsafe_allow_html=True)
    with c2:
        if st.button("🚪 Sair", key="car_sair", **ui.LARGURA):
            _sair()


def _resumo(v: dict) -> None:
    linhas = [("Pedido", v["numero_pedido"]), ("Destino", v.get("destino") or "—"), ("Placa do cavalo", v["placa"]),
              ("Agendamento", _fmt(v.get("agendamento")) if v.get("agendamento") else "sem agendamento")]
    marcado = repo.pedido_marcado(v["operacao_id"], v["numero_pedido"])
    if marcado:
        linhas.append(("Pedido marcado", f"{int(marcado['itens'])} itens · {ui.numero(marcado['cx'])} cx · "
                                         f"{ui.numero(marcado['hl'], 1)} HL"))
    st.markdown('<div class="car-viagem">' + "".join(
        f'<div class="lin"><span>{tema._e(a)}</span><b>{tema._e(b)}</b></div>' for a, b in linhas) + "</div>",
        unsafe_allow_html=True)


def _linha_do_tempo(v: dict) -> None:
    prox = svc.proxima_etapa(v)
    partes = []
    for chave in svc.ORDEM:
        e = svc.ETAPAS[chave]
        ts = v.get(e["coluna"])
        cls = "feito" if ts else ("atual" if chave == prox else "pend")
        extra = ""
        if chave == "apresentado" and ts and v.get("apresentou_no_prazo") is not None:
            extra = " · " + ("<span style='color:#0ca30c'>no prazo</span>" if v["apresentou_no_prazo"]
                             else "<span style='color:#d03b3b'>fora do prazo</span>")
        partes.append(f'<div class="car-passo {cls}"><div class="ic">{e["icone"] if ts or cls == "atual" else "•"}</div>'
                      f'<div class="nm">{tema._e(e["nome"])}{extra}</div>'
                      f'<div class="hr">{_fmt(ts) if ts else ""}</div></div>')
    feitas = sum(1 for c in svc.ORDEM if v.get(svc.ETAPAS[c]["coluna"]))
    pct = feitas / len(svc.ORDEM) * 100
    st.markdown(f'<div class="car-prog-tx">Etapa {min(feitas + 1, len(svc.ORDEM))} de {len(svc.ORDEM)}'
                f'{" · viagem concluída 🎉" if feitas == len(svc.ORDEM) else ""}</div>'
                f'<div class="car-prog"><i style="width:{pct:.0f}%"></i></div>'
                f'<div class="car-passos">{"".join(partes)}</div>', unsafe_allow_html=True)


def _gps(valor: dict | None) -> dict | None:
    return ponto(valor)


# --- Nova viagem -------------------------------------------------------------
def _nova_viagem(usuario: dict, mot: dict, geo: dict | None) -> None:
    destinos = repo.destinos()
    placas = repo.placas(mot["operacao_id"])
    tema.secao("Nova viagem", "Preencha os dados e toque no botão verde para iniciar.")
    if not destinos or not placas:
        st.warning("Ainda faltam cadastros: peça à Puxada para cadastrar "
                   + " e ".join(x for x, falta in (("os destinos (fábricas)", not destinos),
                                                   ("as placas", not placas)) if falta) + ".")
        return
    with st.container(key="car_form"):
        pedido = st.text_input("Número do pedido *", placeholder="Ex.: 4500123456", key="car_nova_pedido")
        plan = svc.pedido_planejado(mot["operacao_id"], pedido) if (pedido or "").strip() else None
        data_ag = hora_ag = destino = placa = None
        if plan:
            ag = (f"{dt.date.fromisoformat(str(plan['data'])[:10]):%d/%m} às {plan['hora_agendamento']}"
                  if plan.get("hora_agendamento") else "sem horário")
            outro = plan.get("motorista_id") and int(plan["motorista_id"]) != int(mot["id"])
            st.markdown(
                f'<div class="car-viagem"><div class="lin"><span>✅ Pedido da Puxada</span><b>{tema._e(plan["numero_pedido"])}'
                f'</b></div><div class="lin"><span>Placa</span><b>{tema._e(plan["placa"])}</b></div>'
                f'<div class="lin"><span>Fábrica</span><b>{tema._e(plan.get("fabrica") or "—")}</b></div>'
                f'<div class="lin"><span>Agendamento</span><b>{tema._e(ag)}</b></div>'
                f'<div class="lin"><span>Motorista escalado</span><b>{tema._e(plan.get("motorista") or "—")}</b></div>'
                f'<div class="lin"><span>Carga</span><b>{tema._e(plan["tipo"])}</b></div></div>',
                unsafe_allow_html=True)
            if outro:
                st.warning(f"Este pedido está escalado para **{plan.get('motorista')}**. Se você assumiu a viagem, "
                           "pode iniciar — a Puxada verá o seu nome.")
            st.caption("Tudo já vem do pedido lançado pela Puxada — é só iniciar.")
        else:
            if (pedido or "").strip():
                st.info("Pedido não encontrado nos pedidos da Puxada — preencha os dados abaixo.")
            c1, c2 = st.columns(2)
            data_ag = c1.date_input("Data do agendamento", value=None, format="DD/MM/YYYY", key="car_nova_data")
            hora_ag = c2.time_input("Hora do agendamento", value=None, step=dt.timedelta(minutes=15),
                                    key="car_nova_hora")
            destino = st.selectbox("Destino *", [None] + [d["id"] for d in destinos], key="car_nova_dest",
                                   format_func=lambda i: "Selecione..." if i is None else next(
                                       f'{d["nome"]}' + (f' — {d["cidade"]}/{d["uf"]}' if d.get("cidade") else "")
                                       for d in destinos if d["id"] == i))
            placa = st.selectbox("Placa do cavalo *", [None] + [p["placa"] for p in placas], key="car_nova_placa",
                                 format_func=lambda p: "Selecione..." if p is None else p)
        with st.container(key="car_verde"):
            enviar = st.button("🟢  INICIAR VIAGEM", type="primary", key="car_nova_ok", **ui.LARGURA)
    if enviar:
        try:
            vid = svc.iniciar_viagem(usuario, pedido, data_ag, hora_ag, destino, placa, _gps(geo))
            st.session_state[f"car_aberta_{vid}"] = True  # já abre a viagem para registrar as etapas
        except RegraNegocioError as e:
            st.error(str(e))
        else:
            for k in ("car_nova_pedido", "car_nova_data", "car_nova_hora", "car_nova_dest", "car_nova_placa"):
                st.session_state.pop(k, None)
            ui.avisar(f"Viagem iniciada às {tempo.agora().strftime('%H:%M')}. Boa viagem! 🚛")
            st.rerun()


# --- Notas fiscais (etapa "Pedido carregado") --------------------------------
def _notas(usuario: dict, v: dict, obrigatorio: bool) -> None:
    notas = repo.notas(v["id"])
    tema.secao("📄 Notas fiscais", "Digite o número de cada NF e tire foto(s) dela. Pode adicionar várias notas — "
               "elas já vão para a Puxada vinculadas ao seu pedido.")
    for n in notas:
        c1, c2, c3 = st.columns([3, 1.3, .8])
        c1.markdown(f'<div class="car-nf">🧾 <b>NF {tema._e(n["numero_nf"])}</b> · {n["fotos"]} foto(s)</div>',
                    unsafe_allow_html=True)
        with c2.popover("➕ fotos"):
            vk = st.session_state.get(f"car_fv_{n['id']}", 0)
            arqs = st.file_uploader("Fotos", type=["jpg", "jpeg", "png", "webp", "heic", "pdf"],
                                    accept_multiple_files=True, key=f"car_fotos_{n['id']}_{vk}")
            if st.button("Enviar fotos", key=f"car_envf_{n['id']}"):
                try:
                    qtd = svc.adicionar_fotos(usuario, v["id"], n["id"], arqs)
                except RegraNegocioError as e:
                    st.error(str(e))
                else:
                    st.session_state[f"car_fv_{n['id']}"] = vk + 1
                    ui.avisar(f"{qtd} foto(s) adicionada(s) à NF {n['numero_nf']}.")
                    st.rerun()
        if c3.button("🗑️", key=f"car_rm_{n['id']}", help="Remover esta NF"):
            ui.acao(svc.remover_nota, usuario, v["id"], n["id"], sucesso=f"NF {n['numero_nf']} removida.")

    versao = st.session_state.get("car_nf_v", 0)
    with st.expander("➕ Adicionar nota fiscal", expanded=obrigatorio and not notas):
        numero = st.text_input("Número da NF *", key=f"car_nf_num_{versao}", placeholder="Ex.: 123456")
        arqs = st.file_uploader("📷 Fotos da nota * (tire na hora ou escolha da galeria)",
                                type=["jpg", "jpeg", "png", "webp", "heic", "pdf"], accept_multiple_files=True,
                                key=f"car_nf_fotos_{versao}")
        camera = None
        if st.toggle("Usar a câmera aqui na tela", key=f"car_cam_t_{versao}"):
            camera = st.camera_input("Foto da nota", key=f"car_cam_{versao}")
        if st.button("💾 Salvar NF", key=f"car_nf_salvar_{versao}", type="primary", **ui.LARGURA):
            try:
                svc.adicionar_nota(usuario, v["id"], numero, list(arqs or []) + ([camera] if camera else []))
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state["car_nf_v"] = versao + 1
                ui.avisar(f"NF {numero.strip()} salva. Tem outra nota? Adicione abaixo.")
                st.rerun()


# --- Viagem em andamento ------------------------------------------------------
def _viagem(usuario: dict, v: dict, geo: dict | None) -> None:
    _resumo(v)
    aviso = svc.mensagem_apresentacao(v)
    if aviso:
        getattr(st, aviso[0])(aviso[1])
    _linha_do_tempo(v)

    prox = svc.proxima_etapa(v)
    if prox is None:
        return
    if _parada(usuario, v, geo):  # em manutenção: as etapas esperam o fim da parada
        return
    _etapa_atual(usuario, v, geo, prox)
    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    with st.popover("🔧 Parada para manutenção (início)", **ui.LARGURA):
        st.caption("Registre quando a carreta parar para manutenção. Ao voltar, toque em “Fim da manutenção”.")
        obs = st.text_input("O que aconteceu?", key=f"car_par_obs_{v['id']}", placeholder="ex.: pneu furado")
        if st.button("🔧 Iniciar parada", type="primary", key=f"car_par_ini_{v['id']}", **ui.LARGURA):
            ui.acao(svc.iniciar_parada, usuario, v["id"], obs, _gps(geo),
                    sucesso="Parada para manutenção registrada. A Puxada foi avisada.")
    _cancelar(usuario, v)


def _parada(usuario: dict, v: dict, geo) -> bool:
    p = repo.parada_ativa(v["id"])
    if not p:
        return False
    ini = tempo.parse_dt(p["inicio"])
    dur = svc.formatar_duracao((tempo.agora() - ini).total_seconds() / 3600) if ini else ""
    st.markdown(
        f'<div class="car-viagem" style="border-color:#c2571a"><div class="lin"><span>🔧 Parada para manutenção'
        f'</span><b>desde {ini:%d/%m %H:%M}</b></div><div class="lin"><span>Tempo parado</span><b>{tema._e(dur)}</b></div>'
        + (f'<div class="lin"><span>Motivo</span><b>{tema._e(p["observacao"])}</b></div>' if p.get("observacao") else "")
        + "</div>", unsafe_allow_html=True)
    with st.container(key="car_fim"):
        if st.button("✅  FIM DA MANUTENÇÃO", type="primary", key=f"car_par_fim_{v['id']}", **ui.LARGURA):
            ui.acao(svc.encerrar_parada, usuario, v["id"], sucesso="Manutenção encerrada — siga com a viagem.")
    st.caption("As etapas da viagem voltam depois do fim da manutenção.")
    return True


def _etapa_atual(usuario: dict, v: dict, geo: dict | None, prox: str) -> None:
    e = svc.ETAPAS[prox]
    if prox == "carregado" or v.get("ts_carregado"):
        _notas(usuario, v, obrigatorio=prox == "carregado")
    if v.get("ts_agendado") and not v.get("ts_chegada_revenda"):
        _agenda_resumo(usuario, v, geo)
    if prox == "agendado":
        _agendar(usuario, v, geo)
        _desfazer(usuario, v)
        return

    rotulo = f"{e['icone']}  {e['botao'].upper()}"
    with st.container(key="car_fim" if prox == "fim" else "car_etapa"):
        clicou = st.button(rotulo, key=f"car_btn_{prox}", type="primary", **ui.LARGURA)
    if prox == "apresentado":
        st.caption("Toque assim que se apresentar na cervejaria. O sistema compara com o horário do agendamento.")
    if clicou:
        try:
            nova = svc.registrar_etapa(usuario, v["id"], prox, _gps(geo))
        except RegraNegocioError as err:
            st.error(str(err))
        else:
            if prox == "apresentado":
                tipo, msg = svc.mensagem_apresentacao(nova) or ("success", "Apresentação registrada.")
                ui.avisar(msg, "error" if tipo == "error" else "success")
            elif prox == "fim":
                from config.settings import INTERJORNADA_H

                livre = tempo.parse_dt(nova["ts_fim"]) + dt.timedelta(hours=INTERJORNADA_H)
                ui.avisar(f"✅ Viagem finalizada! TMV: {svc.formatar_duracao(_horas(nova['ts_inicio'], nova['ts_fim']))}. "
                          f"Bom descanso! 😴 Você estará disponível novamente às {livre:%H:%M} de {livre:%d/%m}.")
            else:
                ui.avisar(f"{e['nome']} registrado às {tempo.agora().strftime('%H:%M')}.")
            st.rerun()

    _desfazer(usuario, v)


def _desfazer(usuario: dict, v: dict) -> None:
    ultima = svc.ultima_etapa(v)
    if ultima:
        with st.popover(f"↩️ Desfazer “{svc.ETAPAS[ultima]['nome']}”"):
            st.caption("Use só se tocou por engano. Depois de alguns minutos, peça a correção para a Puxada.")
            if st.button("Confirmar desfazer", key="car_desfazer"):
                ui.acao(svc.desfazer_ultima, usuario, v["id"], sucesso="Etapa desfeita.")


# --- Agendamento da descarga (entre carregar e sair da cervejaria) ------------------
ICONE_PRODUTO = {"Retornável": "♻️", "Descartável": "🥫", "Misto": "🔀"}


def _passo(n: int, titulo: str, sub: str = "") -> None:
    st.markdown(f'<div class="car-step"><span>{n}</span><div><b>{tema._e(titulo)}</b>'
                f'{f"<i>{tema._e(sub)}</i>" if sub else ""}</div></div>', unsafe_allow_html=True)


def _rot_dia(d: dt.date) -> str:
    from services import janelas_service

    n = (d - tempo.hoje()).days
    return "Hoje" if n == 0 else "Amanhã" if n == 1 else janelas_service.DIAS[d.weekday()]


def _agenda_bloco(usuario: dict, v: dict, geo, sucesso: str) -> None:
    """Agendar/trocar a descarga em 3 toques: produto → dia → horário livre (o toque no horário já agenda)."""
    from config.settings import TIPOS_DESCARGA_APP
    from services import janelas_service

    chave = f"car_ag_{v['id']}"
    ver = st.session_state.get(f"{chave}_ver", 0)
    hoje = tempo.hoje()
    _passo(1, "Qual produto você vai descarregar?")
    with st.container(key="car_prod"):
        produto = st.pills("Produto", TIPOS_DESCARGA_APP, key=f"{chave}_p", selection_mode="single",
                           default=v.get("desc_tipo") if v.get("desc_tipo") in TIPOS_DESCARGA_APP else None,
                           format_func=lambda t: f"{ICONE_PRODUTO.get(t, '')} {t}", label_visibility="collapsed")
    if not produto:
        st.caption("👆 Toque no produto para ver os dias e horários livres da doca.")
        return
    com_slots = janelas_service.tem_janelas(v["operacao_id"])
    dias = [hoje + dt.timedelta(days=i) for i in range(7)]
    livres = {d: janelas_service.horarios_livres(v["operacao_id"], d, produto, ignorar_viagem=v["id"])
              for d in dias} if com_slots else {}
    atual_d = dt.date.fromisoformat(v["desc_data"]) if v.get("desc_data") else None
    padrao = atual_d if atual_d in dias else next((d for d in dias if livres.get(d)), dias[0])

    def rot(d):
        base = f"{_rot_dia(d)} {d:%d/%m}"
        if not com_slots:
            return base
        n = len(livres[d])
        return f"{base} · {n} livre{'s' if n != 1 else ''}" if n else f"{base} · lotado"

    _passo(2, "Que dia você chega na revenda?")
    with st.container(key="car_dias"):
        dia = st.pills("Dia", dias, key=f"{chave}_d_{produto}", selection_mode="single", default=padrao,
                       format_func=rot, label_visibility="collapsed") or padrao
    if not com_slots:
        _passo(3, "Que horas você chega?")
        atual_h = dt.datetime.strptime(v["desc_hora"], "%H:%M").time() if v.get("desc_hora") else None
        hora = st.time_input("Hora prevista", value=atual_h, step=dt.timedelta(minutes=30), key=f"{chave}_h",
                             label_visibility="collapsed")
        with st.container(key="car_etapa"):
            if st.button("🗓️  AGENDAR DESCARGA", key=f"{chave}_ok", type="primary", **ui.LARGURA):
                _confirmar_agenda(usuario, v, dia, hora, produto, sucesso, geo, chave)
        return
    hs = livres[dia]
    _passo(3, "Toque no horário livre — já fica agendado",
           f"{_rot_dia(dia)} {dia:%d/%m} · {ICONE_PRODUTO.get(produto, '')} {produto.lower()} · "
           f"atualizado às {tempo.agora():%H:%M}")
    if not hs:
        todos = janelas_service.horarios(v["operacao_id"], dia, produto, ignorar_viagem=v["id"])
        st.markdown(f'<div class="car-vazio">{"🚫 A revenda não recebe descarga neste dia." if not todos else "😕 Todos os horários deste dia já foram ocupados."}'
                    "<br>Escolha outro dia acima.</div>", unsafe_allow_html=True)
        return
    atual_h = v.get("desc_hora") if atual_d == dia and v.get("desc_tipo") == produto else None
    opcoes = [h["hora"] for h in hs]
    fins = {h["hora"]: f"{h['fim']:%H:%M}" + (" +1d" if h["fim"].date() > dia else "") for h in hs}
    with st.container(key="car_horas"):
        esc = st.pills("Horário", opcoes, key=f"{chave}_h_{dia}_{produto}_{ver}", selection_mode="single",
                       format_func=lambda h: f"{'✅' if h == atual_h else '🕒'} {h} até {fins[h]}",
                       label_visibility="collapsed")
    st.caption("Cada quadrado é um horário livre da doca: do início até o fim da sua descarga.")
    if esc and esc != atual_h:
        _confirmar_agenda(usuario, v, dia, esc, produto, sucesso, geo, chave)


def _confirmar_agenda(usuario: dict, v: dict, data, hora, produto, sucesso: str, geo, chave: str) -> None:
    st.session_state[f"{chave}_ver"] = st.session_state.get(f"{chave}_ver", 0) + 1
    st.session_state.pop(f"{chave}_trocar", None)
    try:
        nova = svc.agendar_descarga(usuario, v["id"], data, hora, produto, _gps(geo))
    except RegraNegocioError as e:
        ui.avisar(str(e), "error")
    else:
        ui.avisar(sucesso.format(data=f"{data:%d/%m}", hora=nova.get("desc_hora") or ""))
    st.rerun()


def _agendar(usuario: dict, v: dict, geo) -> None:
    st.markdown('<div class="car-card azul"><b>🗓️ Agende a descarga na revenda</b>'
                '<span>3 toques: produto, dia e horário. O armazém recebe na hora.</span></div>',
                unsafe_allow_html=True)
    with st.container(key="car_form"):
        _agenda_bloco(usuario, v, geo, "✅ Descarga agendada para {data} às {hora}. O armazém já foi avisado.")


def _agenda_resumo(usuario: dict, v: dict, geo) -> None:
    from repositories import logistica_repo
    from services import janelas_service

    d = dt.date.fromisoformat(v["desc_data"])
    jan = janelas_service.janela_de_agendamento(logistica_repo.janelas(v["operacao_id"], False), v["desc_data"],
                                                v.get("desc_hora"), v.get("desc_janela_id"), v.get("desc_tipo"))
    quando = jan.replace("–", " → ") if jan else (v.get("desc_hora") or "--:--")
    prod = v.get("desc_tipo") or ""
    st.markdown(f'<div class="car-card verde"><b>🗓️ Descarga agendada</b><div class="car-big">'
                f'{_rot_dia(d)} {d:%d/%m} · {tema._e(quando)}</div>'
                f'<span>{ICONE_PRODUTO.get(prod, "")} {tema._e(prod)} · o armazém já está sabendo</span></div>',
                unsafe_allow_html=True)
    chave = f"car_ag_{v['id']}"
    if st.toggle("🔁 Trocar dia ou horário", key=f"{chave}_trocar"):
        with st.container(key="car_form"):
            _agenda_bloco(usuario, v, geo, "🔁 Descarga remarcada para {data} às {hora}. O armazém foi avisado.")


def _cancelar(usuario: dict, v: dict) -> None:
    """Cancelar o pedido em qualquer etapa — pede a justificativa."""
    with st.popover("❌ Cancelar este pedido", **ui.LARGURA):
        st.markdown(f"**Cancelar o pedido {tema._e(v['numero_pedido'])}?**")
        st.caption("A Puxada e o armazém recebem o aviso com a sua justificativa, e a vaga da descarga é liberada.")
        just = st.text_area("Justificativa *", key=f"car_cancel_txt_{v['id']}", max_chars=400,
                            placeholder="Ex.: pedido cancelado pela cervejaria, carreta quebrou, ...")
        if st.button("Confirmar cancelamento", key=f"car_cancel_ok_{v['id']}", type="primary", **ui.LARGURA):
            try:
                svc.cancelar_pelo_motorista(usuario, v["id"], just)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                st.session_state.pop(f"car_aberta_{v['id']}", None)
                ui.avisar(f"Pedido {v['numero_pedido']} cancelado. A Puxada foi avisada.", "info")
                st.rerun()


def _horas(a, b) -> float | None:
    da, db = tempo.parse_dt(a), tempo.parse_dt(b)
    return (db - da).total_seconds() / 3600 if da and db else None


AREAS = ["🚛 Viagem", "💵 Variáveis", "🧾 Histórico", "👤 Perfil"]  # atalhos da tela inicial


def _continuar(v: dict) -> bool:
    """Ao abrir o app com viagem em andamento: mostra o pedido para tocar e voltar à etapa em que parou."""
    if st.session_state.get(f"car_aberta_{v['id']}"):
        return True
    prox = svc.proxima_etapa(v)
    ult = svc.ultima_etapa(v)
    etapa = svc.ETAPAS[prox]["nome"] if prox else "concluída"
    st.markdown(
        f'<div class="car-viagem"><div class="lin"><span>Viagem em andamento</span><b>Pedido {tema._e(v["numero_pedido"])}'
        f'</b></div><div class="lin"><span>Placa · destino</span><b>{tema._e(v["placa"])} · {tema._e(v.get("destino") or "")}'
        f'</b></div><div class="lin"><span>Última etapa</span><b>{tema._e(svc.ETAPAS[ult]["nome"]) if ult else "—"} '
        f'{_fmt(v.get(svc.ETAPAS[ult]["coluna"])) if ult else ""}</b></div><div class="lin"><span>Próxima etapa</span>'
        f'<b>{tema._e(etapa)}</b></div></div>', unsafe_allow_html=True)
    with st.container(key="car_verde"):
        if st.button(f"▶️  CONTINUAR · PEDIDO {v['numero_pedido']}", key=f"car_cont_{v['id']}", type="primary",
                     **ui.LARGURA):
            st.session_state[f"car_aberta_{v['id']}"] = True
            st.rerun()
    return False


def _area_viagem(usuario: dict, mot: dict) -> None:
    geo = localizacao(key="geo_motorista")
    if geo and geo.get("erro"):
        st.caption("Sem GPS o app funciona normalmente — mas a Puxada não consegue confirmar a chegada na revenda.")
    _interjornada(mot)
    v = repo.viagem_ativa_motorista(mot["id"])
    if v:
        if _continuar(v):
            _viagem(usuario, v, geo)
    else:
        if _em_servico(mot):
            return
        _nova_viagem(usuario, mot, geo)


def _interjornada(mot: dict) -> None:
    """😴 Interjornada: a qualquer momento o motorista marca o descanso de 11 h (a Puxada é avisada)."""
    from config.settings import INTERJORNADA_H
    from services import disp_motoristas_service as dms

    dms.verificar_interjornadas()
    ij = dms.interjornada_do_motorista(mot["id"])
    if ij and ij["ativa"]:
        falta = (ij["fim"] - tempo.agora()).total_seconds() / 3600
        pct = max(0.0, min(100.0, 100 - falta / INTERJORNADA_H * 100))
        st.markdown(
            f'<div class="car-viagem" style="border-color:#b7791f;background:#fffaf0"><div class="lin"><span>😴 Em '
            f'interjornada</span><b>até {ij["fim"]:%d/%m %H:%M}</b></div><div class="lin"><span>Começou</span>'
            f'<b>{ij["inicio"]:%d/%m %H:%M}</b></div><div class="lin"><span>Falta</span><b>{svc.formatar_duracao(falta)}'
            f'</b></div><div style="height:8px;background:#f1e3c4;border-radius:99px;margin-top:.4rem;overflow:hidden">'
            f'<div style="height:100%;width:{pct:.0f}%;background:#b7791f"></div></div></div>', unsafe_allow_html=True)
        return
    if ij and ij["concluida_ha_h"] is not None and ij["concluida_ha_h"] < 6:
        st.success(f"✅ Interjornada concluída às {ij['fim']:%H:%M} de {ij['fim']:%d/%m} — você está liberado.")
    with st.popover(f"😴 Interjornada (descanso de {INTERJORNADA_H} h)", **ui.LARGURA):
        fim = tempo.agora() + dt.timedelta(hours=INTERJORNADA_H)
        st.markdown(f"Começa **agora** e termina às **{fim:%H:%M} de {fim:%d/%m}**.")
        st.caption("A Puxada recebe o aviso no início e quando terminar.")
        if st.button("😴 Iniciar interjornada", type="primary", key="car_interj_ini", **ui.LARGURA):
            ui.acao(dms.iniciar_interjornada, mot,
                    sucesso=f"Interjornada iniciada — termina às {fim:%H:%M} de {fim:%d/%m}. Bom descanso!")


def _em_servico(mot: dict) -> bool:
    """➕ Em serviço: o motorista registra que está trabalhando fora de viagem. True = está em serviço agora."""
    from config.settings import TIPOS_SERVICO_MOTORISTA
    from repositories import motoristas_repo
    from services import disp_motoristas_service as dms

    ativo = motoristas_repo.servico_ativo(mot["id"])
    if ativo:
        ini = tempo.parse_dt(ativo["inicio"])
        st.markdown(
            f'<div class="car-viagem"><div class="lin"><span>🔧 Em serviço</span><b>{tema._e(ativo.get("tipo") or "")}</b>'
            f'</div><div class="lin"><span>Desde</span><b>{ini:%d/%m %H:%M}</b></div>'
            + (f'<div class="lin"><span>Obs.</span><b>{tema._e(ativo["observacao"])}</b></div>'
               if ativo.get("observacao") else "") + "</div>", unsafe_allow_html=True)
        with st.container(key="car_fim"):
            if st.button("⏹️  ENCERRAR SERVIÇO", type="primary", key="car_serv_fim", **ui.LARGURA):
                ui.acao(dms.encerrar_servico, mot, sucesso="Serviço encerrado.")
        st.caption("Ao iniciar uma viagem, encerre o serviço primeiro.")
        return True
    with st.expander("➕ Em serviço (outra atividade fora de viagem)"):
        tipo = st.selectbox("O que você vai fazer?", TIPOS_SERVICO_MOTORISTA, key="car_serv_tipo")
        obs = st.text_input("Observação", key="car_serv_obs", placeholder="opcional (obrigatório em “Outro”)")
        if st.button("▶️ Começar serviço", type="primary", key="car_serv_ini", **ui.LARGURA):
            ui.acao(dms.iniciar_servico, mot, tipo, obs, sucesso=f"Em serviço: {tipo}.")
    return False


MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
            "Novembro", "Dezembro"]


def _anos(mot: dict) -> list[int]:
    from database.connection import query_one

    r = query_one("""SELECT MIN(a) AS a FROM (
                       SELECT MIN(substr(ts_inicio, 1, 4)) AS a FROM viagens_carreteiro WHERE motorista_id = ?
                       UNION ALL SELECT MIN(substr(data_puxada, 1, 4)) FROM vinculos_pedidos
                       WHERE operacao_id = ? AND lower(trim(motorista)) = lower(trim(?))) x""",
                  (mot["id"], mot["operacao_id"], mot["nome"]))
    atual = tempo.hoje().year
    primeiro = int(r["a"]) if r and r.get("a") and str(r["a"]).isdigit() else atual
    return list(range(atual, min(primeiro, atual) - 1, -1))


def _meses_do_ano(ano: int) -> list[int]:
    hoje = tempo.hoje()
    ultimo = hoje.month if ano == hoje.year else 12
    return list(range(ultimo, 0, -1))  # mais recente primeiro


def _area_variaveis(mot: dict) -> None:
    from services import motoristas_service

    ano = st.selectbox("Ano", _anos(mot), key="car_var_ano")
    nome = mot["nome"].strip().lower()
    total_ano, linhas = 0.0, []
    for m in _meses_do_ano(ano):
        mes = f"{ano}-{m:02d}"
        r = motoristas_service.remuneracao(mot["operacao_id"], mes)
        res = r["resumo"]
        meu = res[res["motorista"].str.strip().str.lower() == nome] if not res.empty else res
        meu = meu.iloc[0].to_dict() if not meu.empty else {}
        v = r["viagens"]
        minhas = v[v["motorista"].fillna("").str.strip().str.lower() == nome] if not v.empty else v
        variavel = float(meu.get("variavel") or 0)
        total_ano += variavel
        linhas.append((m, meu, minhas, variavel))
    st.markdown(f'<div class="car-viagem"><div class="lin"><span>Variável em {ano}</span>'
                f'<b style="color:#0ca30c">{ui.moeda(total_ano)}</b></div></div>', unsafe_allow_html=True)
    st.caption("Toque no mês para abrir. Valores previstos pelas viagens lançadas — o fechamento oficial é da Puxada/RH.")
    for m, meu, minhas, variavel in linhas:
        fixo = float(meu.get("salario_fixo") or 0)
        with st.expander(f"{MESES_PT[m - 1]} · {len(minhas)} viagem(ns) · variável {ui.moeda(variavel)}",
                         expanded=False):
            st.markdown('<div class="car-viagem">' + "".join(
                f'<div class="lin"><span>{a}</span><b>{b}</b></div>' for a, b in [
                    ("Viagens", str(len(minhas))), ("Km rodados", ui.numero(meu.get("km") or 0)),
                    ("Variável", ui.moeda(variavel)), ("Fixo", ui.moeda(fixo)),
                    ("Total previsto", f"<span style='color:#0ca30c'>{ui.moeda(fixo + variavel)}</span>")]) +
                "</div>", unsafe_allow_html=True)
            if not minhas.empty:
                por_fab = minhas.groupby(minhas["fabrica"].fillna("—")).agg(
                    viagens=("valor", "size"), valor=("valor", "sum")).reset_index()
                for f in por_fab.to_dict("records"):
                    st.markdown(f'<div class="car-nf">🏭 <b>{tema._e(f["fabrica"])}</b> · {f["viagens"]} viagem(ns) · '
                                f'<b>{ui.moeda(f["valor"])}</b></div>', unsafe_allow_html=True)


def _area_viagens(mot: dict) -> None:
    ano = st.selectbox("Ano", _anos(mot), key="car_via_ano")
    df = repo.viagens_df(mot["operacao_id"], f"{ano}-01-01", f"{ano}-12-31", motorista_id=mot["id"])
    if df.empty:
        st.info(f"Nenhuma viagem registrada no app em {ano}.")
        return
    df["mes"] = df["ts_inicio"].str[5:7].astype(int)
    st.caption("Toque no mês para ver as viagens.")
    for m in _meses_do_ano(ano):
        doms = df[df["mes"] == m]
        if doms.empty:
            continue
        fin = doms[doms["status"] == repo.FINALIZADA]
        tmvs = [h for h in (_horas(a, b) for a, b in zip(fin["ts_inicio"], fin["ts_fim"])) if h is not None]
        tmv = svc.formatar_duracao(sum(tmvs) / len(tmvs)) if tmvs else "—"
        with st.expander(f"{MESES_PT[m - 1]} · {len(doms)} viagem(ns) · TMV médio {tmv}"):
            for r in doms.to_dict("records"):
                icone = {"Finalizada": "✅", "Em viagem": "🚛"}.get(r["status"], "⛔")
                tempo_v = svc.formatar_duracao(_horas(r["ts_inicio"], r["ts_fim"])) if r.get("ts_fim") else r["status"]
                st.markdown(f'<div class="car-nf">{icone} <b>{_fmt(r["ts_inicio"])}</b> · Pedido '
                            f'{tema._e(r["numero_pedido"])} · {tema._e(r.get("destino") or "")} · {tema._e(r["placa"])}'
                            f'<br><span style="color:#6b6a65">TMV {tempo_v} · {int(r.get("qtd_nfs") or 0)} NF(s)'
                            f'{" · descarga " + tema._e(r.get("desc_tipo")) if r.get("desc_tipo") else ""}</span></div>',
                            unsafe_allow_html=True)


def _area_dados(usuario: dict, mot: dict) -> None:
    from services.motoristas_service import status_cnh

    _, cnh, _ = status_cnh(mot.get("cnh_validade"))
    st.markdown('<div class="car-viagem">' + "".join(
        f'<div class="lin"><span>{a}</span><b>{tema._e(b)}</b></div>' for a, b in [
            ("Nome", mot["nome"]), ("Login (CPF)", usuario.get("login") or ""), ("Celular", mot.get("telefone") or "—"),
            ("CNH", mot.get("cnh") or "—"), ("Validade da CNH", cnh)]) + "</div>", unsafe_allow_html=True)
    st.caption("Algum dado errado? Fale com a Puxada para atualizar o cadastro.")
    tema.secao("🔑 Trocar minha senha")
    with st.form("car_senha", clear_on_submit=True):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Confirme a nova senha", type="password")
        if st.form_submit_button("Salvar nova senha", type="primary", **ui.LARGURA):
            try:
                usuarios_service.trocar_propria_senha(usuario["id"], atual, nova, conf)
            except RegraNegocioError as e:
                st.error(str(e))
            else:
                if "k" in st.query_params:  # o acesso lembrado antigo deixa de valer; gera um novo
                    from core.auth import gerar_token

                    st.query_params["k"] = gerar_token(usuario["id"])
                ui.avisar("Senha alterada!")
                st.rerun()
    if st.button("🚪 Sair do app", key="car_sair_dados", **ui.LARGURA):
        _sair()


def _relato(mot: dict) -> None:
    """📝 Faça seu relato aqui — abre o formulário cadastrado pela Puxada (Acessos dos motoristas)."""
    link = repo.link_relato(mot["operacao_id"])
    if link:
        with st.container(key="car_relato"):
            st.link_button("📝  Faça seu relato aqui", link, **ui.LARGURA)


_DESC_AREAS = {AREAS[0]: "registrar etapas", AREAS[1]: "quanto vou receber", AREAS[2]: "minhas viagens",
               AREAS[3]: "dados e senha"}


def _home(mot: dict) -> None:
    """Tela inicial: atalhos grandes para cada função do app (toque e abre)."""
    v = repo.viagem_ativa_motorista(mot["id"])
    viagem = f"Pedido {v['numero_pedido']} em andamento" if v else _DESC_AREAS[AREAS[0]]
    desc = {**_DESC_AREAS, AREAS[0]: viagem}
    st.markdown('<div class="car-home-tit">O que você quer fazer?</div>', unsafe_allow_html=True)
    with st.container(key="car_home"):
        for ini in (0, 2):
            for col, a in zip(st.columns(2), AREAS[ini:ini + 2]):
                icone, nome = a.split(" ", 1)
                if col.button(f"{icone}\n{nome}\n{desc[a]}", key=f"car_home_{ini}_{nome}", **ui.LARGURA):
                    st.session_state["car_area_ativa"] = a
                    st.rerun()


def render(usuario: dict) -> None:
    mot = repo.motorista_do_usuario(usuario["id"])
    if not mot:
        st.markdown(_CSS, unsafe_allow_html=True)
        st.warning("Seu acesso ainda não está ligado a um motorista. Fale com a equipe da Puxada.")
        if st.button("🚪 Sair"):
            _sair()
        return
    livre = bloqueio(usuario)
    if livre:
        tela_bloqueado(usuario, livre)
        return
    _topo(usuario, mot)
    ui.mostrar_avisos()
    _relato(mot)
    if mot.get("cnh_validade"):
        from services.motoristas_service import status_cnh

        cor, rotulo, dias = status_cnh(mot["cnh_validade"])
        if dias is not None and dias <= 90:
            (st.error if dias <= 30 else st.warning)(
                f"🪪 Sua CNH {'venceu' if dias < 0 else 'vence em breve'}: {rotulo.split(' ', 1)[-1]}. "
                "Renove e avise a Puxada para atualizar o cadastro.")
    area = st.session_state.get("car_area_ativa")
    if area not in AREAS:
        _home(mot)
        return
    with st.container(key="car_voltar"):
        if st.button("⬅  Início", key="car_voltar_ini"):
            st.session_state.pop("car_area_ativa", None)
            st.rerun()
    st.markdown(f'<div class="car-home-tit">{tema._e(area)}</div>', unsafe_allow_html=True)
    if area == AREAS[1]:
        _area_variaveis(mot)
    elif area == AREAS[2]:
        _area_viagens(mot)
    elif area == AREAS[3]:
        _area_dados(usuario, mot)
    else:
        _area_viagem(usuario, mot)
