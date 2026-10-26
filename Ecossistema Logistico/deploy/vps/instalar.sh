#!/usr/bin/env bash
# Instala o servidor do Ecossistema Logístico (Ubuntu/Debian). Rode UMA vez, como root:
#   VPS nova ............ bash instalar.sh seu@email.com git@github.com:USUARIO/Ecossistema-Logistico.git
#   servidor que JÁ USA . EXISTENTE=1 bash instalar.sh seu@email.com git@github.com:USUARIO/Ecossistema-Logistico.git
#     (servidor existente: não atualiza o sistema inteiro, não liga firewall desligado, não mexe no SSH)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Rode como root:  sudo -i  e depois  bash instalar.sh ..."; exit 1; }
EMAIL=${1:?"uso: bash instalar.sh seu@email.com git@github.com:USUARIO/REPO.git"}
REPO=${2:?"uso: bash instalar.sh seu@email.com git@github.com:USUARIO/REPO.git"}
BASE=/opt/eco
PASTA_APP="Ecossistema Logistico"
EXISTENTE=${EXISTENTE:-0}

if [[ "$EXISTENTE" == "1" ]]; then
  echo "==> 0/7 Conferindo o servidor (modo servidor existente)"
  for porta in 80 443; do
    if ss -ltnp 2>/dev/null | grep -qE "[:.]$porta\s"; then
      echo "    ❌ A porta $porta já está em uso por outro programa:"
      ss -ltnp | grep -E "[:.]$porta\s" | sed 's/^/       /'
      echo "    O HTTPS do sistema precisa das portas 80 e 443. Fale com o TI (ou mande esta tela) para decidir:"
      echo "    desligar o outro site, ou colocar o sistema atrás do servidor web que já existe."
      exit 1
    fi
  done
  echo "    portas 80 e 443 livres ✅  ·  memória: $(free -h | awk '/Mem:/{print $2}')  ·  disco livre: $(df -h / | awk 'NR==2{print $4}')"
fi

echo "==> 1/7 Atualizando o sistema e instalando o básico"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
if [[ "$EXISTENTE" == "1" ]]; then
  apt-get install -yq ca-certificates curl git age gzip openssl rclone   # só o necessário, sem upgrade geral
else
  apt-get -yq upgrade
  apt-get install -yq ca-certificates curl git ufw fail2ban unattended-upgrades age gzip openssl rclone
  dpkg-reconfigure -f noninteractive unattended-upgrades   # atualizações de segurança automáticas
fi

echo "==> 2/7 Docker"
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh

echo "==> 3/7 Firewall"
if [[ "$EXISTENTE" == "1" ]]; then
  if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp && ufw allow 443/tcp
    echo "    firewall já estava ligado: liberadas só as portas 80 e 443."
  else
    echo "    firewall do servidor não foi alterado (cuide das portas 80/443 no roteador/firewall da empresa)."
  fi
else
  ufw default deny incoming && ufw default allow outgoing
  ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp
  ufw --force enable
  systemctl enable --now fail2ban   # bloqueia quem erra a senha do SSH várias vezes
fi

echo "==> 4/7 SSH só com chave"
if [[ "$EXISTENTE" == "1" ]]; then
  echo "    servidor existente: SSH não alterado."
elif compgen -G "/root/.ssh/authorized_keys" >/dev/null && [[ -s /root/.ssh/authorized_keys ]]; then
  printf "PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n" \
    > /etc/ssh/sshd_config.d/99-eco.conf
  systemctl reload ssh || systemctl reload sshd || true
  echo "    SSH por senha desligado (entrada só com a sua chave)."
else
  echo "    ATENÇÃO: nenhuma chave SSH em /root/.ssh/authorized_keys — o SSH por senha continua ligado."
  echo "    Cadastre a sua chave (painel da VPS) e rode este script de novo para desligar a senha."
fi

echo "==> 5/7 Código (repositório privado, com chave só de leitura)"
mkdir -p "$BASE"/{segredos,empresas,backups}
chmod 700 "$BASE/segredos" "$BASE/empresas" "$BASE/backups"
if [[ ! -f /root/.ssh/eco_deploy ]]; then
  ssh-keygen -t ed25519 -N "" -C "eco-deploy" -f /root/.ssh/eco_deploy >/dev/null
fi
cat > /root/.ssh/config <<CFG
Host github.com
  IdentityFile /root/.ssh/eco_deploy
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
CFG
if [[ ! -d "$BASE/codigo/.git" ]]; then
  echo
  echo "    No GitHub: repositório › Settings › Deploy keys › Add deploy key (SEM marcar escrita). Cole:"
  echo
  cat /root/.ssh/eco_deploy.pub
  echo
  read -rp "    Depois de adicionar, aperte Enter para continuar... "
  git clone "$REPO" "$BASE/codigo"
fi
KIT="$BASE/codigo/$PASTA_APP/deploy/vps"
cp -f "$KIT"/{docker-compose.yml,app.yml,nova_empresa.sh,atualizar.sh,backup.sh,restaurar.sh} "$BASE/"
chmod 700 "$BASE"/*.sh

echo "==> 6/7 Banco (fechado para a internet) e HTTPS"
[[ -f "$BASE/segredos/pg_senha" ]] || openssl rand -hex 24 > "$BASE/segredos/pg_senha"
chmod 600 "$BASE/segredos/pg_senha"
[[ -f "$BASE/Caddyfile" ]] || printf "{\n\temail %s\n}\n" "$EMAIL" > "$BASE/Caddyfile"
cd "$BASE"
docker compose -f docker-compose.yml up -d
until docker compose -f docker-compose.yml exec -T db pg_isready -U postgres >/dev/null 2>&1; do sleep 2; done
docker compose -f docker-compose.yml exec -T db psql -U postgres -qc "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;"
docker build -t eco-app:latest "$BASE/codigo/$PASTA_APP"

echo "==> 7/7 Backup diário criptografado (02:30)"
if [[ ! -f "$BASE/segredos/backup.pub" ]]; then
  age-keygen -o /root/eco_backup_CHAVE_PRIVADA.txt 2>/dev/null
  grep -o "age1[0-9a-z]*" /root/eco_backup_CHAVE_PRIVADA.txt > "$BASE/segredos/backup.pub"
  echo
  echo "    !!! CHAVE PARA ABRIR OS BACKUPS — copie e guarde FORA do servidor (cofre de senhas): !!!"
  echo
  cat /root/eco_backup_CHAVE_PRIVADA.txt
  echo
  read -rp "    Guardou? Aperte Enter para APAGAR a chave deste servidor... "
  shred -u /root/eco_backup_CHAVE_PRIVADA.txt
fi
echo "30 2 * * * root $BASE/backup.sh >> /var/log/eco_backup.log 2>&1" > /etc/cron.d/eco-backup

echo
echo "Pronto. Agora cadastre a primeira empresa:"
echo "  $BASE/nova_empresa.sh grupolima sistema.SEUDOMINIO.com.br \"Grupo Lima\" completo admin@empresa.com.br"
