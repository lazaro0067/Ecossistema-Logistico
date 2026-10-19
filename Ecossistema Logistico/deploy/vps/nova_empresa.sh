#!/usr/bin/env bash
# Coloca uma empresa no ar:  ./nova_empresa.sh <slug> <dominio> "<Nome>" <plano> <email_admin> [DATABASE_URL externa]
#   slug    = nome curto, só letras minúsculas, números e hífen (ex.: grupolima)
#   dominio = endereço dela (o DNS já apontando para o IP desta VPS), ex.: grupolima.seudominio.com.br
#   plano   = essencial | profissional | completo
#   DATABASE_URL externa = opcional (ex.: o Supabase atual do Grupo Lima). Sem ela, cria um banco só dela aqui.
set -euo pipefail
cd /opt/eco
SLUG=${1:?"uso: ./nova_empresa.sh <slug> <dominio> \"<Nome>\" <plano> <email_admin> [DATABASE_URL]"}
DOMINIO=${2:?"informe o domínio"}; NOME=${3:?"informe o nome"}; PLANO=${4:?"informe o plano"}
ADMIN=${5:?"informe o e-mail do administrador"}; URL_EXT=${6:-}
[[ "$SLUG" =~ ^[a-z0-9-]{2,30}$ ]] || { echo "slug inválido: use letras minúsculas, números e hífen"; exit 1; }
[[ "$PLANO" =~ ^(essencial|profissional|completo)$ ]] || { echo "plano inválido"; exit 1; }
[[ -d "empresas/$SLUG" ]] && { echo "a empresa $SLUG já existe (empresas/$SLUG)"; exit 1; }
DBN="eco_${SLUG//-/_}"
mkdir -p "empresas/$SLUG/dados"; chmod 700 "empresas/$SLUG"

if [[ -z "$URL_EXT" ]]; then
  SENHA=$(openssl rand -hex 24)
  docker compose -f docker-compose.yml exec -T db psql -U postgres -v ON_ERROR_STOP=1 -q \
    -c "CREATE ROLE $DBN LOGIN PASSWORD '$SENHA';" \
    -c "CREATE DATABASE $DBN OWNER $DBN;" \
    -c "REVOKE CONNECT ON DATABASE $DBN FROM PUBLIC;"
  URL="postgresql://$DBN:$SENHA@db:5432/$DBN"
else
  URL="$URL_EXT"
fi

PROVISORIA="Eco-$(openssl rand -hex 4)#$(date +%y)"
cat > "empresas/$SLUG/.env" <<ENV
DATABASE_URL=$URL
EMPRESA_NOME=$NOME
PLANO=$PLANO
ADMIN_EMAIL=$ADMIN
APP_URL=https://$DOMINIO
TZ=America/Sao_Paulo
ECO_DATA_DIR=/data
# Senha provisória do Master (vale uma vez; o sistema pede para trocar no 1º login). Pode apagar depois.
MASTER_NOVA_SENHA=$PROVISORIA
# E-mail (redefinição de senha) — preencha e rode ./atualizar.sh
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USUARIO=
# SMTP_SENHA=
# SMTP_REMETENTE=
# MODULOS_EXTRAS=
# MAX_USUARIOS=
# MAX_REVENDAS=
ENV
chmod 600 "empresas/$SLUG/.env"

printf "\n%s {\n\tencode gzip\n\treverse_proxy eco_%s:8501\n}\n" "$DOMINIO" "$SLUG" >> Caddyfile
SLUG=$SLUG docker compose -p "eco-$SLUG" -f app.yml up -d
docker compose -f docker-compose.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile

echo "Pronto: https://$DOMINIO  (o certificado HTTPS sai em até 1 minuto)."
echo "1º acesso: $ADMIN  ·  senha provisória: $PROVISORIA  (o sistema pede para trocar)."
