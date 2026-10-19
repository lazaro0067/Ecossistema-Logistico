# Implantação — uma instância por empresa

Cada empresa cliente roda a sua própria cópia do sistema: **o mesmo código** (este repositório) com **o seu banco**
(um projeto Supabase) e **os seus Secrets** (empresa, plano, e-mail). Os dados de uma empresa nunca se misturam com
os de outra.

## Planos

Configurados nos Secrets da instância (`config/plano.py`):

| Plano | Módulos | Usuários | Revendas |
| --- | --- | --- | --- |
| Essencial | Puxada, Ressuprimento, Armazém | 10 | 1 |
| Profissional | + Vendas, Distribuição, Frota, Compras, Gente | 30 | 3 |
| Completo | Todos (inclui Financeiro e Gestão Corporativa) | sem limite | sem limite |

Relatórios & Bases fazem parte de todo plano. `MODULOS_EXTRAS`, `MAX_USUARIOS` e `MAX_REVENDAS` ajustam um cliente
sem mudar o plano. Módulo fora do plano não aparece para ninguém, nem para o Master.

## Servidor (Fly.io, São Paulo)

O banco (Supabase) está em São Paulo; o servidor também fica em São Paulo (`gru`) — cada consulta ao banco fica
bem mais rápida do que no Streamlit Cloud (que roda nos EUA).

1. Instale o `flyctl` e entre: `fly auth login`.
2. Na pasta do app (onde está o `fly.toml`), crie a instância da empresa:
   `fly apps create eco-grupolima`
3. Cadastre os Secrets (os mesmos do Streamlit Cloud + empresa/plano):
   `fly secrets set -a eco-grupolima DATABASE_URL="..." ADMIN_EMAIL="..." SMTP_HOST="..." SMTP_PORT="587" SMTP_USUARIO="..." SMTP_SENHA="..." SMTP_REMETENTE="..." APP_URL="https://eco-grupolima.fly.dev" EMPRESA_NOME="Grupo Lima" PLANO="completo"`
4. Publique: `fly deploy -a eco-grupolima`
5. Abra `https://eco-grupolima.fly.dev`, confira o login e os relatórios.
6. Só depois de conferir, avise os usuários do novo endereço e desligue o app do Streamlit Cloud.

Máquina: 2 GB de memória e 2 CPUs compartilhadas (`fly.toml`), sempre ligada.

## Nova empresa cliente

1. Novo projeto no Supabase (região São Paulo) → copie o `DATABASE_URL` (Session pooler).
2. `fly apps create eco-<empresa>` e `fly secrets set -a eco-<empresa> ...` com `EMPRESA_NOME` e `PLANO` dela.
3. `fly deploy -a eco-<empresa>` — as tabelas são criadas sozinhas na primeira abertura.
4. Entre com o `ADMIN_EMAIL` dela, cadastre revendas e usuários.

## Atualizar o sistema

Mesmo código para todas: a cada versão, `fly deploy -a <app>` em cada empresa (ou automático pelo GitHub, na
etapa de homologação).

## Arquivos anexados

O banco fica no Supabase. Imagens anexadas (plantas, fotos) ficam na pasta `/data` da máquina, que é apagada
quando a máquina é recriada — como hoje no Streamlit Cloud. Para guardá-las de vez:
`fly volumes create dados -a eco-grupolima --region gru --size 1` e, no `fly.toml`, `[mounts] source = "dados"`,
`destination = "/data"`.
