# 🤖 Robô de relatórios

Baixa os relatórios dos sites (Promax, WMS…), guarda na pasta e **importa no sistema sozinho** — com as mesmas
funções do upload manual (os números saem iguais). Roda num computador da empresa, agendado no Windows. O que ele
fez aparece no sistema em **📥 Atualizar relatórios › 🤖 Robô de relatórios** (e o Master recebe aviso se der erro).

## Instalar (uma vez, no computador que vai rodar o robô)
1. Instale o **Python 3.12** (python.org — marque *Add python.exe to PATH*).
2. Na pasta `robo`, dê dois cliques em **`instalar_robo.bat`**.
3. Abra o **`config.toml`** (criado pelo instalador) e preencha: pasta onde salvar, revenda, endereço e usuário de
   cada site e a lista de relatórios.
4. Guarde as senhas no **cofre do Windows** (não ficam em nenhum arquivo). Abra o Prompt na pasta `robo`:
   ```
   robo.bat --senha promax
   robo.bat --senha wms
   robo.bat --senha banco      (o DATABASE_URL do sistema — o mesmo dos Secrets)
   ```

## Sites com login da Microsoft (Power BI) ou com código no celular
O robô tem um navegador próprio (Edge) que **guarda o login**. Entre uma vez você mesmo:
```
robo.bat --entrar powerbi
```
Faça o login (marque "Manter conectado"), espere abrir o relatório e feche o navegador. A partir daí o robô entra
sozinho enquanto a Microsoft mantiver o login (normalmente semanas). Se um dia ele pedir login de novo, repita.

## Ensinar cada relatório (uma vez por relatório)
```
robo.bat --gravar vendas
```
Abre o navegador gravando. Faça o caminho normal: **entrar → abrir o relatório → filtros → exportar**. Use as datas
de **hoje**, **ontem** ou **1º do mês** — o robô troca sozinho pelas datas do dia em que rodar. Quando terminar de
baixar, feche o navegador. A receita fica em `receitas\vendas.py` (sem a sua senha).

Para o WMS: `robo.bat --gravar contagem --site wms`.

Teste vendo o navegador: `robo.bat --testar vendas`. Se o site tiver algo diferente (janela que abre, espera longa),
mande a receita e o erro de `logs\` para ajustar.

## Agendar
```
agendar_robo.bat 06:30
```
Roda todo dia nesse horário (com o seu usuário do Windows logado). Para mais horários, rode de novo com outro nome
de tarefa no Agendador de Tarefas.

## Como cada relatório entra no sistema (`importar` no config.toml)
| importar | O que faz |
| --- | --- |
| vendas | 03.02.37 vendas (Faturamento, Produtividade Entrega) |
| compra | 03.02.37 compra (Compras, DRE, remuneração) |
| pcd | Relatório de mapas (Produtividade Entrega) |
| saldo_estoque | 02.05.02 → saldo final do mês (no dia 1º fecha o mês anterior e abre o novo) |
| contagem_validade | Contagem do WMS com validade (Gestão de Idade / FEFO) |
| estoque, pedidos_marcados, ressuprimento, linear, produtos, politica | Bases do Ressuprimento/Armazém |
| so_baixar | Só guarda o arquivo na pasta |

## Segurança
- Senhas e o endereço do banco ficam no cofre do Windows do usuário que roda o robô.
- A gravação crua (que pode conter a senha) é apagada; a receita usa `ctx.senha`.
- Use um computador da empresa, com senha no Windows.
