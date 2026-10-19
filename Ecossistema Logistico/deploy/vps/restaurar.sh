#!/usr/bin/env bash
# Restaura o banco de uma empresa a partir de um backup:
#   ./restaurar.sh <slug> backups/2026-10-19/<slug>.dump.age /caminho/da/chave_privada.txt
# CUIDADO: substitui os dados atuais da empresa pelos do backup.
set -euo pipefail
cd /opt/eco
SLUG=${1:?slug}; ARQ=${2:?arquivo .dump.age}; CHAVE=${3:?arquivo da chave privada}
URL=$(grep -E "^DATABASE_URL=" "empresas/$SLUG/.env" | cut -d= -f2-)
read -rp "Substituir os dados de $SLUG pelos do backup $ARQ? Digite SIM: " ok
[[ "$ok" == "SIM" ]] || exit 1
age -d -i "$CHAVE" "$ARQ" | docker run --rm -i --network eco postgres:17 pg_restore --clean --if-exists --no-owner -d "$URL"
SLUG=$SLUG docker compose -p "eco-$SLUG" -f app.yml restart
echo "Restaurado."
