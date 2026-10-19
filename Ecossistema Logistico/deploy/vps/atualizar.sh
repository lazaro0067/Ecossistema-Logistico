#!/usr/bin/env bash
# Atualiza o sistema de TODAS as empresas para a versão do GitHub (main). Uso: ./atualizar.sh
set -euo pipefail
cd /opt/eco
PASTA_APP="Ecossistema Logistico"
git -C codigo pull --ff-only
KIT="codigo/$PASTA_APP/deploy/vps"
cp -f "$KIT"/{docker-compose.yml,app.yml,nova_empresa.sh,atualizar.sh,backup.sh,restaurar.sh} .
chmod 700 ./*.sh
docker build -t eco-app:latest "codigo/$PASTA_APP"
docker compose -f docker-compose.yml up -d
for d in empresas/*/; do
  s=$(basename "$d")
  echo "==> $s"
  SLUG=$s docker compose -p "eco-$s" -f app.yml up -d --force-recreate
done
docker image prune -f >/dev/null
echo "Todas as empresas atualizadas."
