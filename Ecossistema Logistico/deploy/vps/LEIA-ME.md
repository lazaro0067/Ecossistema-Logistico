# Servidor próprio (VPS) — passo a passo

Uma VPS roda várias empresas: cada uma com o seu container, o seu endereço (HTTPS) e o seu banco separado.

## 0. Antes
1. **Repositório privado:** GitHub › Settings › Danger Zone › Change visibility › Private.
2. **VPS:** Ubuntu 24.04, 2 vCPU / 8 GB (ex.: Hostinger KVM 2), região Brasil se houver.
   No painel, cadastre a **sua chave SSH** (para entrar sem senha).
3. **Domínio** (ex.: Registro.br). No DNS, um registro **A** para cada empresa apontando para o IP da VPS
   (ex.: `grupolima.seudominio.com.br → IP`), ou um curinga `*.seudominio.com.br → IP`.

## 1. Instalar (uma vez)
Entre na VPS (`ssh root@IP`), copie o `instalar.sh` para lá e rode:
```
bash instalar.sh seu@email.com git@github.com:USUARIO/Ecossistema-Logistico.git
```
Ele vai pedir duas coisas:
- **Deploy key:** cole a chave que ele mostrar em GitHub › repositório › Settings › Deploy keys (só leitura).
- **Chave dos backups:** ele mostra UMA vez — guarde num cofre de senhas, fora do servidor. Sem ela os backups não
  abrem (nem para quem invadir o servidor).

O que fica configurado: firewall (só SSH, 80 e 443), SSH só com chave, bloqueio de quem erra a senha do SSH
(fail2ban), atualizações de segurança automáticas, banco fechado para a internet, HTTPS automático e backup
criptografado todo dia às 02:30.

## 2. Cada empresa
```
/opt/eco/nova_empresa.sh grupolima grupolima.seudominio.com.br "Grupo Lima" completo admin@grupolima.com.br "postgresql://...supabase..."
/opt/eco/nova_empresa.sh empresa2  empresa2.seudominio.com.br  "Distribuidora X" profissional ti@distx.com.br
```
- O último parâmetro (opcional) é um banco externo — use o do Supabase para o Grupo Lima continuar com os dados de
  hoje. Sem ele, a empresa ganha um banco novo, só dela, dentro da VPS.
- Ele mostra a **senha provisória** do Master (troca obrigatória no 1º login).
- E-mail (SMTP), módulos extras e limites: edite `/opt/eco/empresas/<empresa>/.env` e rode `./atualizar.sh`.

## 3. Atualizar o sistema (todas as empresas)
Depois do Push no GitHub: `ssh root@IP` → `/opt/eco/atualizar.sh`.

## 4. Backup fora do servidor (recomendado)
`rclone config` → crie um remoto chamado **eco-backup** (Google Drive, Backblaze, S3…). A partir daí o backup diário
também vai para lá. Log: `/var/log/eco_backup.log`.
Restaurar: `/opt/eco/restaurar.sh <empresa> backups/AAAA-MM-DD/<empresa>.dump.age /caminho/da/chave.txt`

## Úteis
- Ver empresas no ar: `docker ps`
- Log de uma empresa: `docker logs -f eco_<empresa>`
- Reiniciar uma empresa: `cd /opt/eco && SLUG=<empresa> docker compose -p eco-<empresa> -f app.yml restart`
