# 🌐 Ecossistema Logístico — Revenda Ambev

Sistema web (Streamlit) para a gestão logística da revenda: Puxada, Ressuprimento,
Armazém, Distribuição, Frota, Gente, Vendas, Financeiro e Compras — com várias
operações (filiais), login individual e permissões por pasta.

---

## 🚀 Publicar no Streamlit Cloud (passo a passo)

> ⚠️ **Por que precisa de um banco na nuvem:** o Streamlit Cloud apaga os arquivos
> do app toda vez que ele reinicia ou "dorme". Com SQLite (arquivo `.db`), metas,
> usuários e lançamentos somem. Por isso, na nuvem o sistema usa **PostgreSQL**
> (gratuito no Supabase). No seu PC continua funcionando com o arquivo local.

### 1. Criar o banco gratuito (Supabase) — 5 minutos
1. Entre em **supabase.com** → *Start your project* → entre com o GitHub.
2. *New project* → nome `ecossistema`, crie uma **senha do banco** (guarde!),
   região **South America (São Paulo)** → *Create*.
3. No projeto, clique em **Connect** (topo) → aba **Session pooler** → copie a
   *connection string* (`postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres`).
4. Troque `[YOUR-PASSWORD]` pela senha do passo 2. Essa é a sua **DATABASE_URL**.

### 2. Levar os dados antigos para o banco da nuvem (no seu PC)
Abra o *Prompt de Comando* na pasta do sistema:

```bat
cd "C:\Sistema Revenda\Ecossistema Logistico"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=postgresql://postgres.xxxx:SUASENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
python scripts\migrar_banco_antigo.py --antigo "..\puxada_ambev.db" --puxada "..\Sistema Puxada\puxada_ambev.db" --operacao-puxada "Lima Rio Verde"
```

Deve aparecer `Destino: PostgreSQL (nuvem)` e a contagem de cada tabela.

### 3. Subir o código para o GitHub
No repositório que o seu Streamlit Cloud usa, **substitua os arquivos antigos**
por todo o conteúdo desta pasta (menos `venv\` e `data\` — o `.gitignore` já
ignora). O arquivo principal é **`app.py`** na raiz.

### 4. Configurar o app no Streamlit Cloud
1. share.streamlit.io → seu app → **⋮ → Settings → Secrets** e cole:
   ```toml
   DATABASE_URL = "postgresql://postgres.xxxx:SUASENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
   ```
2. Em **Settings → General**, confira *Main file path* = `app.py` e Python **3.12**.
3. **Reboot app**. No rodapé do menu NÃO deve aparecer "Banco local (SQLite)".

### 5. Primeiro acesso (login por e-mail)
- Nos **Secrets**, coloque `ADMIN_EMAIL = "seu.email@..."` — esse é o login do Master.
  (Sem ele, o Master entra com `admin@grupolima.com.br`.)
- Senha inicial **admin123** → o sistema obriga a criar uma senha nova.
- Vá em **🔑 Gestão de Acessos** e crie um acesso para cada pessoa (o e-mail é o login).

### 6. E-mail (redefinir senha e boas-vindas)
Sem isso tudo funciona, mas o “Esqueci minha senha” fica desligado e as senhas
provisórias aparecem na tela para o Master repassar.
1. Crie (ou use) um Gmail do sistema, ative a **Verificação em duas etapas** e gere uma
   **Senha de app** em *Conta Google › Segurança › Senhas de app*.
2. Nos Secrets, preencha `SMTP_HOST`, `SMTP_PORT`, `SMTP_USUARIO`, `SMTP_SENHA` e
   `APP_URL` (modelo em `.streamlit/secrets.toml.exemplo`). Reboot do app.
3. Na tela de login aparece **🔑 Esqueci minha senha**: a pessoa recebe um código de
   6 dígitos (vale 15 min, 5 tentativas, até 3 pedidos por hora) e cria a nova senha.
   Novos usuários criados sem senha recebem os dados de acesso por e-mail.

### 🆘 Master sem acesso
Nos Secrets, adicione `MASTER_NOVA_SENHA = "UmaSenhaTemporaria"` e dê **Reboot**.
A senha do `ADMIN_EMAIL` passa a ser essa (vale uma vez; troca obrigatória ao entrar).
Depois de entrar, **apague a linha** dos Secrets.

---

## 📁 Pastas (departamentos) e abas

| Pasta | Abas |
|---|---|
| 🚚 Puxada | Solicitar frete (por trecho cadastrado) · Aprovações (alçada) · Finalizar (CT-e + NFs + arquivos) · Painel & histórico · OBZ frete · Descarga (pátio, com conflito de slot) · Vincular pedido & NFs · Viagens do mês · Pedidos marcados · Cadastros (trechos, OD, transportadoras, carretas, fábricas, motoristas, centros de custo) |
| 🔄 Ressuprimento | Atualização de bases (01.11, Linear, 02.03.04, Puxada marcada, Ressuprimento diário de todas as filiais, Política, Metas DOI) · Gestão de estoque (D0/D1/D2 e meta DOI editável) · Sugestão & marcação por dia · Acompanhamento por cesta (meta × real × tendência, total Cerveja + Nab) · Carregamento dia a dia · Política de estoque · Metas mensais |
| 📈 Vendas | Estoque do dia (Portal RN) · Metas de vendas · Curva ABC · Importar vendas |
| 📦 Armazém & Estoque | Saúde DPO & ocupação · Book DPO: Fundamentos (com plantas), Manter, Melhorar · Pátio · Capacidade & áreas · Catálogo |
| 🚛 Distribuição | Book DPO de Entrega · Painel · Lançamentos |
| 💰 Financeiro & OBZ | Relatório diário (contas a pagar) · Contas a pagar · Vencimentos · Fluxo de caixa 15 dias · Saúde financeira · OBZ por pacote |
| 🔧 Frota · 🛒 Compras · 👥 Gente | Painel + lançamentos |
| 📁 Relatórios & Bases | Qualquer base em Excel/CSV · Histórico de atualizações |

**Links sem login (somente leitura), como no sistema antigo:**
- Portal comercial: `?modo=comercial&op=<id da filial>`
- Acompanhamento de ressuprimento: `?visualizacao=ressuprimento&op=<id ou nome da filial>`

**Visão consolidada "Bahia (Barreiras + São Félix)":** aparece no seletor de operação e soma as
duas filiais em estoque, ressuprimento, curva ABC e pátio (somente leitura).

**Importar o sistema antigo pelo navegador:** Gestão de Acessos › 📦 Importar sistema antigo —
envie o `puxada_ambev.db` (e, se quiser, o do Sistema Puxada).

## 🔑 Acessos e permissões

- **Login por e-mail e senha individual.** Senhas guardadas com criptografia (nunca em texto).
- **Esqueci minha senha:** código por e-mail (precisa do SMTP configurado).
- **Só o Master** cria usuários, libera pastas, gera senha provisória e cadastra operações.
- **Permissão por pasta:** para cada departamento, marque *pasta inteira* ou só as
  abas (subpastas) que a pessoa pode ver. Ex.: um conferente pode ter só
  *Ressuprimento › Gestão de Estoque*.
- **Operações:** limite quais filiais cada usuário enxerga (vazio = todas).
- **Senha provisória:** em *Resetar senha*, o Master gera uma senha; no próximo
  login o usuário é obrigado a trocar.
- Perfis: **Master** (tudo), **Gestor** (pode definir metas), **Operacional**.

## 💾 Salvamento automático

Tabelas com ✏️ no título gravam **na hora**, sem botão: metas por cesta, meta de
DOI, capacidade dos armazéns, áreas e meta OBZ. Aparece "💾 Salvo automaticamente".
Ao enviar um arquivo de base, o sistema reconhece as colunas e grava sozinho.

## 🎨 Cores

| Cor | Significa |
|---|---|
| 🟢 Verde | No alvo / em dia |
| 🟡 Amarelo | Atenção (perto do limite, base para atualizar) |
| 🟠 Laranja | Fora do alvo |
| 🔴 Vermelho | Crítico (ruptura, meta estourada, base vencida) |
| 🔵 Azul | Informativo |

---

## 💻 Rodar no seu PC

Dois cliques em **iniciar.bat** (cria o ambiente na primeira vez). Sem
`DATABASE_URL`, usa o arquivo local `data\ecossistema.db`. Para o PC usar o mesmo
banco da nuvem, crie `.streamlit\secrets.toml` a partir do `secrets.toml.exemplo`.

## 📁 Estrutura

```
app.py                  # login, menu e roteamento
config/settings.py      # módulos, abas (pastas), status, constantes
database/               # conexão (SQLite ou PostgreSQL) e tabelas
core/                   # login/permissões, tema visual, gráficos, utilidades
repositories/           # SÓ consultas ao banco
services/               # SÓ regras de negócio
modules/<area>/         # SÓ telas — uma pasta por departamento
modules/componentes/    # peças reutilizadas (bases, tabela autosave, registros)
scripts/                # migração dos bancos antigos
```

Regra de ouro: **tela → serviço → repositório → banco**.

**Criar uma aba nova:** adicione a aba em `MODULOS` (`config/settings.py`) e a
função que desenha a tela no `render` do módulo. Ela aparece automaticamente na
árvore de permissões da Gestão de Acessos.
