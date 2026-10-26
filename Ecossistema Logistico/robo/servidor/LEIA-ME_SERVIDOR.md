# Robô no servidor Linux da empresa (Lima)

Só o robô vai para o servidor da Lima (sem o sistema). Ele baixa os relatórios, **guarda na pasta do servidor** e
manda para o Ecossistema por um repositório próprio de entrada. Roda sozinho: 07:00 e 09:00 (relatórios) e a Grade
Cora de 2 em 2 horas (06h–22h), no horário de São Paulo, sem ninguém na tela (tela virtual).

## 1. GitHub — repositório só de entrada do robô (uma vez)
1. GitHub › **New repository** › nome `eco-entrada` › **Private** › Create.
2. GitHub › Settings › Developer settings › **Fine-grained tokens** › Generate new token:
   *Repository access* = **só o `eco-entrada`** · *Permissions › Contents* = **Read and write**. Copie o token.
3. Streamlit › seu app › Settings › **Secrets**, acrescente:
   ```
   ROBO_GITHUB_TOKEN = "github_pat_..."
   ROBO_GITHUB_REPO = "lazaro0067/eco-entrada"
   ```
   (Assim a chave que fica no servidor da Lima só mexe na entrada — nunca no backup do sistema.)

## 2. No seu PC — empacotar o robô
Dois cliques em `robo\servidor\empacotar_para_servidor.bat` → gera `robo_servidor.zip` (robô, receitas e config,
**sem** senhas, logs nem login salvo). Copie para o servidor (no CMD):
```
scp "C:\...\robo\servidor\robo_servidor.zip" "C:\...\robo\servidor\instalar_robo_linux.sh" USUARIO@IP:/tmp/
```

## 3. No servidor (como root: `sudo -i`)
```
cd /tmp && bash instalar_robo_linux.sh /srv/relatorios
```
Não mexe em firewall, SSH nem atualiza o sistema inteiro. Cria o usuário `ecorobo`, a pasta `/srv/relatorios`,
o Edge/Chromium, a tela virtual e a agenda.

Depois:
```
nano /opt/eco-robo/robo/config.toml      # repo_nuvem = "lazaro0067/eco-entrada"  ·  [powerbi] usuario = "seu e-mail"
/opt/eco-robo/robo.sh --senha github     # o token do passo 1
/opt/eco-robo/robo.sh --senha powerbi    # a senha do e-mail Microsoft
systemctl start eco-robo-relatorios      # testa agora · log: tail -f /opt/eco-robo/robo/logs/agendador.log
```

## 4. Código do celular (Power BI)
Quando a Microsoft pedir o código, aparece no topo do Ecossistema (para o Master):
**🔐 O robô precisa do código do celular** → digite o código que chegou → **Enviar ao robô**. Ele espera até 10 min.

## 5. Desligar o robô do seu PC
No PC: `schtasks /Delete /TN EcoRobo_07h00 /F`, `schtasks /Delete /TN EcoRobo_09h00 /F` (e `EcoRobo_Grade`).

## Outros arquivos da empresa
1. No PC, grave a receita: `robo.bat --gravar NOME --site SITE` (o caminho até o download).
2. Copie a receita: `scp robo\receitas\NOME.py USUARIO@IP:/tmp/` → no servidor
   `cp /tmp/NOME.py /opt/eco-robo/robo/receitas/ && chown ecorobo /opt/eco-robo/robo/receitas/NOME.py`.
3. No `config.toml` do servidor, um bloco `[[relatorios]]` com `importar = "so_baixar"` (só guarda na pasta).
Os arquivos ficam em `/srv/relatorios/<data>/` — o TI pode compartilhar essa pasta na rede (Samba) para abrir no
Windows.

## Úteis
- Próximas rodadas: `systemctl list-timers 'eco-robo-*'`
- Rodar a grade agora: `systemctl start eco-robo-grade`
- Erro: `/opt/eco-robo/robo/logs/` (texto e print da tela do momento do erro)
