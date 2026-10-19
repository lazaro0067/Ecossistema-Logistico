#!/usr/bin/env bash
# Backup diário de cada empresa (banco + arquivos), criptografado: só abre com a chave que você guardou.
# Fica 14 dias aqui e, se existir o remoto "eco-backup" no rclone (rclone config), vai também para fora.
set -euo pipefail
cd /opt/eco
DIA=$(date +%Y-%m-%d)
PUB=$(cat segredos/backup.pub)
mkdir -p "backups/$DIA"
FALHOU=0
for d in empresas/*/; do
  s=$(basename "$d")
  URL=$(grep -E "^DATABASE_URL=" "$d/.env" | cut -d= -f2-)
  if docker run --rm --network eco postgres:17 pg_dump -Fc --no-owner "$URL" | age -r "$PUB" > "backups/$DIA/$s.dump.age" \
     && tar -C "$d" -czf - . | age -r "$PUB" > "backups/$DIA/$s.arquivos.tgz.age"; then
    echo "$(date '+%F %T') $s ok"
  else
    echo "$(date '+%F %T') ERRO no backup de $s"; FALHOU=1
  fi
done
find backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
if rclone listremotes 2>/dev/null | grep -q "^eco-backup:"; then
  rclone copy "backups/$DIA" "eco-backup:eco/$DIA" && echo "$(date '+%F %T') enviado para fora"
else
  echo "$(date '+%F %T') AVISO: sem remoto 'eco-backup' no rclone — backup só neste servidor"
fi
exit $FALHOU
