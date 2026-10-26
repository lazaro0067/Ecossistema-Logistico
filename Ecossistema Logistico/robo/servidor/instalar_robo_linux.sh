#!/usr/bin/env bash
# Instala o ROBÔ de relatórios num servidor Linux (Ubuntu/Debian) da empresa — só o robô, sem o sistema.
#   1) No seu PC: rode robo\servidor\empacotar_para_servidor.bat (gera robo_servidor.zip)
#   2) Copie para o servidor:  scp robo_servidor.zip instalar_robo_linux.sh USUARIO@IP:/tmp/
#   3) No servidor, como root:  cd /tmp && bash instalar_robo_linux.sh /srv/relatorios
# Não mexe em firewall, SSH nem atualiza o sistema inteiro. Cria o usuário "ecorobo" e roda tudo com ele.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Rode como root:  sudo -i  e depois  bash instalar_robo_linux.sh"; exit 1; }
PASTA=${1:-/srv/relatorios}
BASE=/opt/eco-robo
ZIP=${ZIP:-/tmp/robo_servidor.zip}
[[ -f "$ZIP" ]] || { echo "Não achei $ZIP — copie o robo_servidor.zip para /tmp"; exit 1; }

echo "==> 1/6 Pacotes (Python, tela virtual)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq python3 python3-venv python3-pip unzip xvfb xauth ca-certificates curl

echo "==> 2/6 Usuário e pastas"
id ecorobo >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/ecorobo --shell /bin/bash ecorobo
mkdir -p "$BASE" "$PASTA"
unzip -oq "$ZIP" -d "$BASE"
mkdir -p "$BASE/robo/logs" "$BASE/robo/segredos"
chown -R ecorobo:ecorobo "$BASE" "$PASTA"
chmod 700 "$BASE/robo/segredos"

echo "==> 3/6 Python do robô + navegadores (Edge e Chromium)"
export PLAYWRIGHT_BROWSERS_PATH="$BASE/navegadores"   # pasta fixa (instalado como root, depois vai p/ ecorobo)
[[ -x "$BASE/.venv/bin/python" ]] || python3 -m venv "$BASE/.venv"
"$BASE/.venv/bin/pip" install -q --upgrade pip
"$BASE/.venv/bin/pip" install -q playwright tomli
"$BASE/.venv/bin/python" -m playwright install-deps chromium
"$BASE/.venv/bin/python" -m playwright install chromium
"$BASE/.venv/bin/python" -m playwright install msedge || echo "    (Edge não instalou — o robô usa o Chromium; ajuste navegador no config)"
chown -R ecorobo:ecorobo "$BASE"

echo "==> 4/6 Configuração"
CFG="$BASE/robo/config.toml"
[[ -f "$CFG" ]] || cp "$BASE/robo/config.exemplo.toml" "$CFG"
sed -i "s#^pasta *=.*#pasta = '$PASTA'#" "$CFG"
chown ecorobo:ecorobo "$CFG"
cat > "$BASE/rodar.sh" <<RODAR
#!/usr/bin/env bash
# Roda o robô na tela virtual (xvfb). Ex.: rodar.sh  |  rodar.sh --grupo grade  |  rodar.sh --so ressuprimento
cd "$BASE/robo"
export ECO_ROBO_SERVIDOR=1 PYTHONUTF8=1 TZ=America/Sao_Paulo PLAYWRIGHT_BROWSERS_PATH="$BASE/navegadores"
exec 9>"$BASE/robo/logs/.trava"; flock -n 9 || { echo "\$(date '+%F %T') já está rodando — pulei" >> logs/agendador.log; exit 0; }
echo "==== \$(date '+%d/%m/%Y %T') inicio \$*" >> logs/agendador.log
xvfb-run -a --server-args="-screen 0 1440x900x24" "$BASE/.venv/bin/python" robo.py "\$@" >> logs/agendador.log 2>&1
echo "==== \$(date '+%d/%m/%Y %T') fim (codigo \$?)" >> logs/agendador.log
RODAR
cat > "$BASE/robo.sh" <<ROBO
#!/usr/bin/env bash
# Comandos do robô como o usuário dele. Ex.: robo.sh --senha powerbi  |  robo.sh --senha github
cd "$BASE/robo" && exec sudo -u ecorobo env ECO_ROBO_SERVIDOR=1 PYTHONUTF8=1 PLAYWRIGHT_BROWSERS_PATH="$BASE/navegadores" "$BASE/.venv/bin/python" robo.py "\$@"
ROBO
chmod 755 "$BASE/rodar.sh" "$BASE/robo.sh"

echo "==> 5/6 Agenda (fuso de São Paulo, sem mudar o fuso do servidor): 07:00 e 09:00 · Grade Cora 06h–22h de 2 em 2 h"
for NOME in relatorios grade; do
  ARGS=""; [[ "$NOME" == "grade" ]] && ARGS="--grupo grade"
  cat > /etc/systemd/system/eco-robo-$NOME.service <<UNIT
[Unit]
Description=Robo de relatorios ($NOME)
After=network-online.target
[Service]
Type=oneshot
User=ecorobo
ExecStart=$BASE/rodar.sh $ARGS
TimeoutStartSec=100min
UNIT
done
cat > /etc/systemd/system/eco-robo-relatorios.timer <<UNIT
[Unit]
Description=Robo - relatorios 07:00 e 09:00 (Sao Paulo)
[Timer]
OnCalendar=*-*-* 07,09:00:00 America/Sao_Paulo
Persistent=true
[Install]
WantedBy=timers.target
UNIT
cat > /etc/systemd/system/eco-robo-grade.timer <<UNIT
[Unit]
Description=Robo - Grade Cora de 2 em 2 horas, 06h-22h (Sao Paulo)
[Timer]
OnCalendar=*-*-* 06..22/2:00:00 America/Sao_Paulo
Persistent=true
[Install]
WantedBy=timers.target
UNIT
rm -f /etc/cron.d/eco-robo
systemctl daemon-reload
systemctl enable --now eco-robo-relatorios.timer eco-robo-grade.timer
systemctl list-timers 'eco-robo-*' --no-pager | head -5

echo "==> 6/6 Pronto"
echo
echo "Agora guarde as senhas (cada uma pede o valor; colar funciona):"
echo "  $BASE/robo.sh --senha github     # chave do repositório de ENTRADA do robô"
echo "  $BASE/robo.sh --senha powerbi    # senha do e-mail Microsoft do Power BI"
echo "  $BASE/robo.sh --senha promax     # (quando tiver a receita do Promax)"
echo "Testar agora:  sudo -u ecorobo $BASE/rodar.sh --so ressuprimento   ·   log: tail -f $BASE/robo/logs/agendador.log"
echo "Próximas rodadas: systemctl list-timers 'eco-robo-*'   ·   rodar agora: systemctl start eco-robo-relatorios"
echo "Relatórios salvos em: $PASTA/<data>/"
