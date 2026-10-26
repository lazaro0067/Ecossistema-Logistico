# Grupo Lima no servidor da empresa (Linux, IP fixo, domínio próprio)

Resultado: o sistema roda no servidor da Lima, com banco próprio (não some mais em reinício), HTTPS automático e
endereço próprio, ex.: **https://ecossistema.SEUDOMINIO.com.br**. Os dados de hoje vêm sozinhos do backup do GitHub.

## 1. Domínio (você)
1. Compre o domínio no **Registro.br** (ex.: `grupolimalog.com.br`).
2. No Registro.br › seu domínio › **DNS** › *Editar zona* › **Nova entrada**:
   - Tipo **A** · Nome `ecossistema` · Dados = **IP fixo da empresa** → salvar.
3. Em alguns minutos `ecossistema.SEUDOMINIO.com.br` já aponta para a empresa.

## 2. Roteador / firewall da empresa (TI)
Encaminhar as portas **80** e **443** (TCP) do IP fixo para o **IP interno do servidor** (ex.: 192.168.0.10).
Só essas duas — o banco de dados não fica exposto.

## 3. Instalação no servidor (uma vez, ~15 min)
Copie o instalador do seu PC para o servidor (no CMD do Windows):
```
scp "C:\Sistema Revenda\PARA_GITHUB\Ecossistema-Logistico\Ecossistema Logistico\deploy\vps\instalar.sh" USUARIO@IP-DO-SERVIDOR:/tmp/
```
Entre no servidor (`ssh USUARIO@IP-DO-SERVIDOR`), vire root (`sudo -i`), vá em `cd /tmp` e rode no modo
**servidor existente** (não mexe em SSH, não liga firewall desligado, não atualiza o sistema inteiro e confere se
as portas 80/443 estão livres):
```
EXISTENTE=1 bash instalar.sh seu@email.com git@github.com:lazaro0067/Ecossistema-Logistico.git
```
- Ele mostra uma **deploy key**: GitHub › Ecossistema-Logistico › Settings › Deploy keys › *Add* (sem escrita).
- Ele mostra **a chave dos backups** uma vez: guarde num cofre de senhas, fora do servidor.
- Se ele disser que a porta 80/443 está em uso, mande a tela — tem outro site no servidor e ajustamos juntos.

## 4. Colocar o Grupo Lima no ar com os dados de hoje
Antes, no sistema atual (Streamlit): 🔑 Gestão de Acessos › 💾 Backup › **💾 Salvar backup agora** e
**📚 Salvar as bases de relatório agora**.

No servidor:
```
export BACKUP_GITHUB_TOKEN="(o mesmo dos Secrets do Streamlit)" BACKUP_GITHUB_REPO="lazaro0067/eco-backup"
/opt/eco/nova_empresa.sh grupolima ecossistema.SEUDOMINIO.com.br "Grupo Lima" completo SEU@EMAIL
```
Ao abrir, o banco novo restaura sozinho usuários, cadastros e as bases de relatório. Entre com **o seu e-mail e a
sua senha de sempre** (a senha provisória que o script mostra só vale se não houver backup).
E-mail (SMTP) e a chave do agente (ANTHROPIC_API_KEY): `nano /opt/eco/empresas/grupolima/.env` → `./atualizar.sh`.

## 5. Virada
1. Confira no endereço novo: login, Gestão Corporativa, Ressuprimento.
2. **No Streamlit Cloud, apague os Secrets BACKUP_GITHUB_*** (ou desligue o app). Senão os dois gravam o mesmo
   backup.
3. Avise os usuários do endereço novo (o celular: salvar de novo na tela inicial).
4. O robô continua igual (ele envia para o GitHub e o servidor importa).

## Depois
- **Atualizar o sistema:** Commit/Push no GitHub como hoje → no servidor `/opt/eco/atualizar.sh`.
- **Backup:** diário às 02:30, criptografado (`/var/log/eco_backup.log`) + o do GitHub continua.
- **Ver se está no ar:** `docker ps` · log: `docker logs -f eco_grupolima`.
