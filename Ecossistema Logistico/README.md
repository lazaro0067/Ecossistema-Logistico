# 🌐 Ecossistema Logístico — Revenda Ambev

Sistema web (Streamlit + SQLite) para gestão logística de revenda Ambev,
com várias operações (filiais/CDDs), controle de acesso por módulo e
fluxo completo de frete da Puxada.

## Como rodar (Windows)

```bat
cd "C:\Sistema Revenda\Ecossistema Logistico"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Ou dê dois cliques em **iniciar.bat**.

Primeiro acesso: usuário **admin**, senha **admin123** — troque em *⚙️ Minha conta*.

## Trazer os dados do sistema antigo

```bat
venv\Scripts\activate
python scripts\migrar_banco_antigo.py --antigo "..\puxada_ambev.db" --puxada "..\Sistema Puxada\puxada_ambev.db" --operacao-puxada "Lima Rio Verde"
```

Os bancos antigos não são alterados. O novo banco fica em `data\ecossistema.db`.

## Estrutura de pastas

```
Ecossistema Logistico/
├── app.py                  # entrada: login, menu lateral e roteamento
├── config/settings.py      # constantes: caminhos, módulos, status, listas
├── database/
│   ├── connection.py       # conexão SQLite + atalhos de consulta
│   └── schema.py           # tabelas, migrações versionadas, admin inicial
├── core/
│   ├── auth.py             # senha com hash, login, regras de permissão
│   ├── session.py          # usuário / operação / página da sessão
│   └── ui.py               # formatação (R$, %), tabelas, avisos
├── repositories/           # SÓ acesso a dados (SQL)
├── services/               # SÓ regras de negócio (validações, cálculos)
├── modules/                # SÓ telas — uma pasta por área
│   ├── puxada/             # uma aba = um arquivo
│   ├── ressuprimento/  armazem/  vendas/
│   ├── distribuicao/  frota/  gente/  financeiro/  compras/
│   ├── admin/  conta/  inicio/
│   └── componentes/        # importador de planilhas, tela de registros
├── scripts/migrar_banco_antigo.py
└── data/                   # banco e anexos (NF/CT-e) — criada sozinha
```

Regra de ouro: **tela → serviço → repositório → banco**. A tela nunca
escreve SQL; o repositório nunca decide regra de negócio.

## Módulos

| Módulo | O que faz |
|---|---|
| 🚚 Puxada | Cotação de frete com valor de tabela do trecho, aprovação respeitando alçada, painel, encerramento com NF/CT-e salvos em disco, OBZ real x meta, pedidos marcados |
| 🔄 Ressuprimento | Volume real x sell-in x meta por cesta, evolução diária |
| 📦 Armazém | Posição de estoque, DOI por SKU com situação (ruptura/crítico/excesso), sugestão de compra, ocupação HL/paletes, armazéns e áreas |
| 📈 Vendas | Curva ABC calculada automaticamente a partir das vendas do mês |
| 🚛 🛡️ 👥 💰 🛒 | Distribuição, Frota, Gente, Financeiro (OBZ por pacote) e Compras: lançamentos + indicadores |
| 🔑 Gestão de Acessos | Usuários (perfil, módulos, operações, alçada) e operações |

Importações de planilha (Excel/CSV) ficam na aba **📥 Importar** de cada
módulo: o sistema sugere o de/para das colunas e você confirma.

## Como criar um módulo novo

1. Crie `modules/<nome>/page.py` com `def render(usuario, operacao_id)`.
2. Adicione `"<nome>": ("Rótulo", "ícone")` em `MODULOS` (`config/settings.py`).
3. Registre em `modules/__init__.py`.
4. Tabelas novas: adicione em `database/schema.py` (`TABELAS` ou um item novo em `MIGRACOES`).
