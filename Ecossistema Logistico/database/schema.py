"""Estrutura do banco de dados.

`init_db()` é chamado na abertura do app: cria as tabelas que faltam
e o usuário admin no primeiro acesso. É seguro rodar várias vezes.

Para evoluir o banco, adicione um item em MIGRACOES (nunca altere um
item antigo) — ele será aplicado uma única vez.
"""
import re

from config.settings import (ADMIN_EMAIL_PADRAO, ADMIN_LOGIN, ADMIN_SENHA_INICIAL, OPERACOES_CONSOLIDADAS, OPERACOES_PADRAO,
                             PERFIL_MASTER)
from core.segredos import segredo
from database.connection import get_conn

TABELAS = """
-- ============ ESTRUTURA / ACESSO ============
CREATE TABLE IF NOT EXISTS operacoes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT UNIQUE NOT NULL,
    cnpj    TEXT,
    cidade  TEXT,
    uf      TEXT,
    ativo   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    login       TEXT UNIQUE NOT NULL,
    nome        TEXT NOT NULL,
    senha_hash  TEXT NOT NULL,
    email       TEXT,
    cargo       TEXT,
    perfil      TEXT NOT NULL DEFAULT 'Operacional',
    e_aprovador INTEGER NOT NULL DEFAULT 0,
    alcada      REAL NOT NULL DEFAULT 0,
    ativo       INTEGER NOT NULL DEFAULT 1,
    criado_em   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS usuario_modulos (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    modulo     TEXT NOT NULL,
    PRIMARY KEY (usuario_id, modulo)
);

CREATE TABLE IF NOT EXISTS usuario_operacoes (
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id) ON DELETE CASCADE,
    PRIMARY KEY (usuario_id, operacao_id)
);

-- ============ CADASTROS GERAIS ============
CREATE TABLE IF NOT EXISTS produtos (               -- antiga base_01_11 + base_linear
    cod        INTEGER PRIMARY KEY,
    descricao  TEXT,
    fator_hl   REAL DEFAULT 0,
    cx_pallet  REAL DEFAULT 0,
    tipo       TEXT,
    categoria  TEXT
);

CREATE TABLE IF NOT EXISTS transportadoras (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT UNIQUE NOT NULL,
    cnpj    TEXT,
    contato TEXT
);

CREATE TABLE IF NOT EXISTS centros_custo (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE NOT NULL
);

-- ============ PUXADA ============
CREATE TABLE IF NOT EXISTS origens_destinos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    nome        TEXT NOT NULL,
    cidade      TEXT,
    uf          TEXT,
    tipo        TEXT,
    UNIQUE (operacao_id, nome)
);

CREATE TABLE IF NOT EXISTS trechos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id      INTEGER NOT NULL REFERENCES operacoes(id),
    origem_id        INTEGER NOT NULL REFERENCES origens_destinos(id),
    destino_id       INTEGER NOT NULL REFERENCES origens_destinos(id),
    distancia_km     REAL DEFAULT 0,
    pedagio          REAL DEFAULT 0,
    valor_remunerado REAL DEFAULT 0,
    valor_frete      REAL DEFAULT 0,
    UNIQUE (operacao_id, origem_id, destino_id)
);

CREATE TABLE IF NOT EXISTS cotacoes_frete (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id       INTEGER NOT NULL REFERENCES operacoes(id),
    origem_id         INTEGER REFERENCES origens_destinos(id),
    destino_id        INTEGER REFERENCES origens_destinos(id),
    transportadora_id INTEGER REFERENCES transportadoras(id),
    centro_custo_id   INTEGER REFERENCES centros_custo(id),
    data_requisicao   TEXT,
    data_frete        TEXT,
    motivo            TEXT,
    valor_negociado   REAL DEFAULT 0,
    valor_tabela      REAL,
    solicitante_id    INTEGER REFERENCES usuarios(id),
    aprovador_id      INTEGER REFERENCES usuarios(id),
    observacao        TEXT,
    status            TEXT NOT NULL DEFAULT 'Pendente Aprovação',
    decidido_em       TEXT,
    motivo_rejeicao   TEXT,
    nf_arquivo        TEXT,
    cte_arquivo       TEXT,
    numero_cte        TEXT,
    finalizado_em     TEXT
);

CREATE TABLE IF NOT EXISTS metas_obz (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    mes_ano     TEXT NOT NULL,          -- AAAA-MM
    meta_valor  REAL DEFAULT 0,
    UNIQUE (operacao_id, mes_ano)
);

CREATE TABLE IF NOT EXISTS pedidos_marcados (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL REFERENCES operacoes(id),
    data_puxada   TEXT,
    cod           INTEGER,
    descricao     TEXT,
    cx_solicitadas REAL DEFAULT 0,
    cx_marcadas   REAL DEFAULT 0,
    hl_marcado    REAL DEFAULT 0,
    status_item   TEXT,
    numero_pedido TEXT,
    dt_atualizacao TEXT
);

-- ============ RESSUPRIMENTO ============
CREATE TABLE IF NOT EXISTS ressuprimento_diario (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id      INTEGER NOT NULL REFERENCES operacoes(id),
    data             TEXT NOT NULL,     -- AAAA-MM-DD
    cesta            TEXT NOT NULL,
    volume_sellin_hl REAL DEFAULT 0,
    volume_real_hl   REAL DEFAULT 0,
    dt_atualizacao   TEXT,
    UNIQUE (operacao_id, data, cesta)
);

CREATE TABLE IF NOT EXISTS metas_ressuprimento (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    mes_ano        TEXT NOT NULL,       -- AAAA-MM
    cesta          TEXT NOT NULL,
    meta_volume_hl REAL DEFAULT 0,
    UNIQUE (operacao_id, mes_ano, cesta)
);

-- Dias em que a filial não puxa (recalcula metas semanais/diárias e a tendência)
CREATE TABLE IF NOT EXISTS ressup_sem_puxada (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    data        TEXT NOT NULL,
    UNIQUE (operacao_id, data)
);

-- Ajuste do gestor sobre a meta semanal (percentual a mais/a menos, por semana do mês)
CREATE TABLE IF NOT EXISTS ressup_ajuste_semana (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL REFERENCES operacoes(id),
    mes_ano       TEXT NOT NULL,
    semana_ini    TEXT NOT NULL,
    ajuste_pct    REAL DEFAULT 0,
    observacao    TEXT,
    atualizado_por TEXT,
    atualizado_em TEXT,
    UNIQUE (operacao_id, mes_ano, semana_ini)
);

-- Links públicos (somente leitura) por revenda — ex.: Portal Comercial. O Master gera/desativa.
CREATE TABLE IF NOT EXISTS links_publicos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    tipo         TEXT NOT NULL,
    token        TEXT UNIQUE NOT NULL,
    ativo        INTEGER DEFAULT 1,
    atualizado_por TEXT,
    atualizado_em  TEXT,
    UNIQUE (operacao_id, tipo)
);

-- ============ ARMAZÉM / ESTOQUE ============
CREATE TABLE IF NOT EXISTS armazens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    nome        TEXT NOT NULL,
    cap_hl      REAL DEFAULT 0,
    cap_paletes REAL DEFAULT 0,
    UNIQUE (operacao_id, nome)
);

CREATE TABLE IF NOT EXISTS armazem_areas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    armazem_id  INTEGER NOT NULL REFERENCES armazens(id) ON DELETE CASCADE,
    nome        TEXT NOT NULL,
    cap_paletes REAL DEFAULT 0,
    cap_hl      REAL DEFAULT 0,
    UNIQUE (armazem_id, nome)
);

CREATE TABLE IF NOT EXISTS estoque (                -- antiga base_estoque_02
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    cod            INTEGER NOT NULL,
    descricao      TEXT,
    inicial        REAL DEFAULT 0,
    entrada        REAL DEFAULT 0,
    saida          REAL DEFAULT 0,
    disponivel     REAL DEFAULT 0,
    saldo_dia      REAL DEFAULT 0,
    dt_atualizacao TEXT,
    PRIMARY KEY (operacao_id, cod)
);

CREATE TABLE IF NOT EXISTS linear_vendas (          -- média de caixas/dia por SKU
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    cod            INTEGER NOT NULL,
    linear_cx_dia  REAL DEFAULT 0,
    dt_atualizacao TEXT,
    PRIMARY KEY (operacao_id, cod)
);

CREATE TABLE IF NOT EXISTS metas_doi (
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    cod         INTEGER NOT NULL,
    doi_meta    REAL DEFAULT 7.0,
    PRIMARY KEY (operacao_id, cod)
);

CREATE TABLE IF NOT EXISTS curva_abc (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    mes_ano        TEXT NOT NULL,       -- AAAA-MM
    cod            INTEGER NOT NULL,
    descricao      TEXT,
    total_qtde     REAL DEFAULT 0,
    pct_acumulado  REAL DEFAULT 0,
    classe         TEXT,
    dt_atualizacao TEXT,
    UNIQUE (operacao_id, mes_ano, cod)
);

-- ============ DEMAIS ÁREAS (registros operacionais) ============
CREATE TABLE IF NOT EXISTS distribuicao_rotas (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id      INTEGER NOT NULL REFERENCES operacoes(id),
    data             TEXT,
    rota             TEXT,
    motorista        TEXT,
    placa            TEXT,
    otif_percent     REAL DEFAULT 0,
    devolucao_caixas INTEGER DEFAULT 0,
    status           TEXT DEFAULT 'Concluída'
);

CREATE TABLE IF NOT EXISTS frota_manutencao (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    data         TEXT,
    placa        TEXT,
    tipo_servico TEXT,
    valor        REAL DEFAULT 0,
    km_atual     INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'Finalizado'
);

CREATE TABLE IF NOT EXISTS gente_ssma (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id         INTEGER NOT NULL REFERENCES operacoes(id),
    data                TEXT,
    dds_tema            TEXT,
    incidentes_qtd      INTEGER DEFAULT 0,
    absenteismo_percent REAL DEFAULT 0,
    turnover_percent    REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS financeiro_obz (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    mes_ano     TEXT,
    pacote      TEXT,
    orcado      REAL DEFAULT 0,
    realizado   REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS compras_pedidos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    data           TEXT,
    item           TEXT,
    quantidade     REAL DEFAULT 0,
    valor_unitario REAL DEFAULT 0,
    fornecedor     TEXT,
    solicitante    TEXT,
    status         TEXT DEFAULT 'Pendente'
);

-- ============ ANEXOS (NF/CT-e guardados no próprio banco) ============
CREATE TABLE IF NOT EXISTS anexos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cotacao_id  INTEGER NOT NULL REFERENCES cotacoes_frete(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL,          -- NF | CTE
    nome        TEXT NOT NULL,
    conteudo    BLOB NOT NULL,
    criado_em   TEXT DEFAULT (datetime('now','localtime'))
);

-- ============ HISTÓRICO DE ATUALIZAÇÃO DAS BASES ============
CREATE TABLE IF NOT EXISTS bases_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER,
    base        TEXT NOT NULL,
    linhas      INTEGER DEFAULT 0,
    arquivo     TEXT,
    usuario     TEXT,
    dt          TEXT
);

-- ============ PUXADA: LOGÍSTICA DE PÁTIO E VIAGENS ============
CREATE TABLE IF NOT EXISTS carretas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    placa        TEXT NOT NULL,
    modelo       TEXT,
    capacidade_hl REAL DEFAULT 0,
    status       TEXT DEFAULT 'Disponível',
    UNIQUE (operacao_id, placa)
);

CREATE TABLE IF NOT EXISTS fabricas (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome   TEXT UNIQUE NOT NULL,
    cidade TEXT,
    uf     TEXT
);

CREATE TABLE IF NOT EXISTS motoristas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    nome        TEXT NOT NULL,
    cnh         TEXT,
    telefone    TEXT
);

-- ============ FROTA ============
CREATE TABLE IF NOT EXISTS locadoras (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nome     TEXT UNIQUE NOT NULL,
    cnpj     TEXT,
    contato  TEXT,
    telefone TEXT
);

-- Cadastro único de placas do Grupo Lima (todas as áreas e revendas)
CREATE TABLE IF NOT EXISTS frota_placas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    placa           TEXT UNIQUE NOT NULL,
    operacao_id     INTEGER REFERENCES operacoes(id),
    tipo            TEXT,
    marca_modelo    TEXT,
    ano             INTEGER,
    proprietario_id INTEGER REFERENCES transportadoras(id),
    aluguel         INTEGER DEFAULT 0,
    locadora_id     INTEGER REFERENCES locadoras(id),
    area            TEXT,
    motorista_id    INTEGER REFERENCES motoristas(id),
    status          TEXT DEFAULT 'Ativo',
    observacao      TEXT,
    atualizado_por  TEXT,
    atualizado_em   TEXT
);

CREATE TABLE IF NOT EXISTS entregas_mapas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL REFERENCES operacoes(id),
    data          TEXT NOT NULL,
    mapa          TEXT NOT NULL,
    roadshow      TEXT,
    placa         TEXT,
    veiculo       TEXT,
    transportadora TEXT,
    motorista     TEXT,
    carga         TEXT,
    classificacao TEXT,
    km_prev       REAL,
    tempo_prev    TEXT,
    entregas      INTEGER,
    caixas        REAL,
    ocup_cx       REAL,
    peso          REAL,
    ocup_peso     REAL,
    pct_tempo     REAL,
    eficiencia    REAL,
    roteirizado   TEXT,
    carga_atual   TEXT,
    cidades       TEXT,
    regiao        TEXT,
    importado_em  TEXT,
    UNIQUE (operacao_id, data, mapa)
);

CREATE TABLE IF NOT EXISTS entregas_notas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL REFERENCES operacoes(id),
    data          TEXT NOT NULL,
    mapa          TEXT NOT NULL,
    operacao_cod  TEXT,
    tipo_movto    TEXT,
    status        TEXT,
    hl            REAL,
    qtde          REAL,
    notas         INTEGER,
    clientes      INTEGER,
    valor         REAL,
    importado_em  TEXT
);

CREATE TABLE IF NOT EXISTS operacoes_fiscais (
    codigo     TEXT PRIMARY KEY,
    tipo_movto TEXT,
    nome       TEXT
);

CREATE TABLE IF NOT EXISTS setor_operacoes (
    setor  TEXT NOT NULL,
    codigo TEXT NOT NULL,
    PRIMARY KEY (setor, codigo)
);

CREATE TABLE IF NOT EXISTS notas_dia (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    origem       TEXT NOT NULL,
    data         TEXT NOT NULL,
    operacao_cod TEXT,
    tipo_movto   TEXT,
    status       TEXT,
    valor        REAL,
    valor_bruto  REAL,
    desconto     REAL,
    hl           REAL,
    qtde         REAL,
    notas        INTEGER,
    clientes     INTEGER,
    itens        INTEGER,
    importado_em TEXT
);

CREATE TABLE IF NOT EXISTS notas_produto_mes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    origem       TEXT NOT NULL,
    mes          TEXT NOT NULL,
    operacao_cod TEXT,
    status       TEXT,
    produto      TEXT,
    descricao    TEXT,
    valor        REAL,
    hl           REAL,
    qtde         REAL,
    clientes     INTEGER,
    importado_em TEXT
);

CREATE TABLE IF NOT EXISTS notas_cliente_mes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    origem       TEXT NOT NULL,
    mes          TEXT NOT NULL,
    operacao_cod TEXT,
    status       TEXT,
    cliente      TEXT,
    nome         TEXT,
    valor        REAL,
    hl           REAL,
    notas        INTEGER,
    importado_em TEXT
);

CREATE TABLE IF NOT EXISTS metas_vendas_cestas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    mes_ano        TEXT NOT NULL,
    cesta          TEXT NOT NULL,
    meta_volume_hl REAL DEFAULT 0,
    UNIQUE (operacao_id, mes_ano, cesta)
);

CREATE TABLE IF NOT EXISTS estoque_saldos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    mes          TEXT NOT NULL,
    tipo_saldo   TEXT NOT NULL,
    armazem      TEXT,
    deposito     TEXT,
    produto      TEXT,
    descricao    TEXT,
    unidade      TEXT,
    tipo         TEXT,
    fator        REAL,
    qtd_unid     REAL,
    qtd_venda    REAL,
    custo_medio  REAL,
    valor        REAL,
    valor_ur     REAL,
    hl           REAL,
    importado_em TEXT
);

CREATE TABLE IF NOT EXISTS depositos_nomes (
    armazem  TEXT NOT NULL,
    deposito TEXT NOT NULL,
    nome     TEXT,
    PRIMARY KEY (armazem, deposito)
);

CREATE TABLE IF NOT EXISTS obz_departamentos (
    codigo TEXT PRIMARY KEY,
    nome   TEXT,
    ativo  INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS obz_contas (
    codigo     TEXT PRIMARY KEY,
    nome       TEXT,
    pacote     TEXT,
    natureza   TEXT DEFAULT 'despesa',
    no_obz     INTEGER DEFAULT 1,
    limite_pct REAL,
    dono_id    INTEGER
);

CREATE TABLE IF NOT EXISTS obz_subdonos (
    conta      TEXT NOT NULL,
    depto      TEXT NOT NULL,
    usuario_id INTEGER NOT NULL,
    PRIMARY KEY (conta, depto)
);

CREATE TABLE IF NOT EXISTS obz_papeis (
    usuario_id INTEGER NOT NULL,
    papel      TEXT NOT NULL,
    PRIMARY KEY (usuario_id, papel)
);

CREATE TABLE IF NOT EXISTS obz_real (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    mes          TEXT NOT NULL,
    conta        TEXT NOT NULL,
    depto        TEXT NOT NULL,
    debito       REAL,
    credito      REAL,
    valor        REAL,
    lancamentos  INTEGER,
    importado_em TEXT
);

CREATE TABLE IF NOT EXISTS obz_real_lanc (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    mes         TEXT NOT NULL,
    data        TEXT,
    conta       TEXT,
    depto       TEXT,
    historico   TEXT,
    debito      REAL,
    credito     REAL
);

CREATE TABLE IF NOT EXISTS obz_plan (
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    mes         TEXT NOT NULL,
    conta       TEXT NOT NULL,
    depto       TEXT NOT NULL,
    valor       REAL DEFAULT 0,
    PRIMARY KEY (operacao_id, mes, conta, depto)
);

CREATE TABLE IF NOT EXISTS obz_tend (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id      INTEGER NOT NULL REFERENCES operacoes(id),
    mes              TEXT NOT NULL,
    conta            TEXT NOT NULL,
    depto            TEXT NOT NULL,
    valor            REAL,
    sugerido         REAL,
    lancado_por      TEXT,
    lancado_em       TEXT,
    justificativa    TEXT,
    criticado_por    TEXT,
    criticado_em     TEXT,
    status           TEXT DEFAULT 'lancada',
    aprovador        TEXT,
    aprovado_em      TEXT,
    comentario_aprov TEXT,
    UNIQUE (operacao_id, mes, conta, depto)
);

CREATE TABLE IF NOT EXISTS obz_acoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    mes         TEXT NOT NULL,
    conta       TEXT,
    depto       TEXT,
    acao        TEXT,
    responsavel TEXT,
    prazo       TEXT,
    status      TEXT DEFAULT 'Aberta',
    criado_por  TEXT,
    criado_em   TEXT
);

CREATE TABLE IF NOT EXISTS obz_reunioes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL REFERENCES operacoes(id),
    mes           TEXT NOT NULL,
    data          TEXT,
    participantes TEXT,
    ata           TEXT,
    criado_por    TEXT
);

CREATE TABLE IF NOT EXISTS gestores (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         TEXT NOT NULL,
    cargo        TEXT,
    email        TEXT,
    telefone     TEXT,
    departamento TEXT,
    usuario_id   INTEGER,
    ativo        INTEGER DEFAULT 1,
    criado_em    TEXT
);

CREATE TABLE IF NOT EXISTS obz_areas (
    nome           TEXT PRIMARY KEY,
    dono_gestor_id INTEGER,
    ordem          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS obz_mapa (
    conta TEXT NOT NULL,
    depto TEXT NOT NULL,
    area  TEXT,
    vbz   TEXT,
    PRIMARY KEY (conta, depto)
);

CREATE TABLE IF NOT EXISTS obz_resp (
    area      TEXT NOT NULL,
    conta     TEXT NOT NULL,
    gestor_id INTEGER NOT NULL,
    PRIMARY KEY (area, conta)
);

CREATE TABLE IF NOT EXISTS portal_rn (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf           TEXT UNIQUE NOT NULL,
    nome          TEXT,
    operacoes     TEXT,
    senha_hash    TEXT,
    ativo         INTEGER DEFAULT 1,
    criado_por    TEXT,
    criado_em     TEXT,
    ultimo_acesso TEXT
);

CREATE TABLE IF NOT EXISTS dre_editado (
    operacao_id  INTEGER NOT NULL,
    mes          TEXT NOT NULL,
    chave        TEXT NOT NULL,
    valor        REAL,
    editado_por  TEXT,
    editado_em   TEXT,
    PRIMARY KEY (operacao_id, mes, chave)
);

CREATE TABLE IF NOT EXISTS dre_editado_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL,
    mes          TEXT NOT NULL,
    chave        TEXT,
    rotulo       TEXT,
    de           REAL,
    para         REAL,
    usuario      TEXT,
    em           TEXT
);

CREATE TABLE IF NOT EXISTS obz_sim (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL,
    ano           TEXT NOT NULL,
    nome          TEXT,
    status        TEXT DEFAULT 'rascunho',
    premissas     TEXT,
    criado_por    TEXT,
    criado_em     TEXT,
    atualizado_em TEXT,
    publicado_em  TEXT
);

CREATE TABLE IF NOT EXISTS obz_sim_volume (
    sim_id   INTEGER NOT NULL,
    mes      TEXT NOT NULL,
    hl_base  REAL,
    hl_plan  REAL,
    PRIMARY KEY (sim_id, mes)
);

CREATE TABLE IF NOT EXISTS obz_sim_equipe (
    sim_id        INTEGER NOT NULL,
    area          TEXT NOT NULL,
    equipe_atual  REAL,
    produtividade REAL,
    acompanha     INTEGER DEFAULT 1,
    PRIMARY KEY (sim_id, area)
);

CREATE TABLE IF NOT EXISTS obz_sim_linha (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id      INTEGER NOT NULL,
    conta       TEXT NOT NULL,
    depto       TEXT NOT NULL,
    area        TEXT,
    driver      TEXT,
    base_ano    REAL,
    calc_ano    REAL,
    prop_conta  REAL,
    just_conta  TEXT,
    por_conta   TEXT,
    em_conta    TEXT,
    prop_depto  REAL,
    just_depto  TEXT,
    por_depto   TEXT,
    em_depto    TEXT,
    decisao     TEXT,
    just_fin    TEXT,
    por_fin     TEXT,
    em_fin      TEXT,
    final_ano   REAL
);

CREATE TABLE IF NOT EXISTS obz_sim_valor (
    sim_id  INTEGER NOT NULL,
    conta   TEXT NOT NULL,
    depto   TEXT NOT NULL,
    mes     TEXT NOT NULL,
    valor   REAL,
    PRIMARY KEY (sim_id, conta, depto, mes)
);

CREATE TABLE IF NOT EXISTS vendas_calendario (
    operacao_id  INTEGER NOT NULL,
    mes          TEXT NOT NULL,
    data         TEXT NOT NULL,
    PRIMARY KEY (operacao_id, data)
);

CREATE TABLE IF NOT EXISTS grade_checks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL,
    data         TEXT NOT NULL,
    fonte        TEXT,
    limite_pct   REAL,
    itens        INTEGER,
    divergentes  INTEGER,
    obs          TEXT,
    criado_por   TEXT,
    criado_em    TEXT
);

CREATE TABLE IF NOT EXISTS grade_check_itens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id   INTEGER NOT NULL,
    cod        TEXT,
    descricao  TEXT,
    sistema    REAL,
    grade      REAL,
    dif        REAL,
    dif_pct    REAL,
    divergente INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS grade_controle (
    operacao_id INTEGER NOT NULL,
    usuario_id  INTEGER NOT NULL,
    PRIMARY KEY (operacao_id, usuario_id)
);

CREATE TABLE IF NOT EXISTS grade_config (
    operacao_id INTEGER PRIMARY KEY,
    limite_pct  REAL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS obz_just (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL,
    mes          TEXT NOT NULL,
    conta        TEXT NOT NULL,
    depto        TEXT NOT NULL,
    plan         REAL,
    fechamento   REAL,
    disp         REAL,
    disp_pct     REAL,
    texto        TEXT,
    acao         TEXT,
    status       TEXT DEFAULT 'aguardando',
    por          TEXT,
    por_id       INTEGER,
    em           TEXT,
    aprovador    TEXT,
    aprovado_em  TEXT,
    comentario   TEXT,
    UNIQUE (operacao_id, mes, conta, depto)
);

CREATE TABLE IF NOT EXISTS obz_just_mes (
    operacao_id  INTEGER NOT NULL,
    mes          TEXT NOT NULL,
    prazo        TEXT,
    limite_pct   REAL DEFAULT 5,
    definido_por TEXT,
    definido_em  TEXT,
    PRIMARY KEY (operacao_id, mes)
);

CREATE TABLE IF NOT EXISTS notas_prod_dia (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL,
    origem       TEXT NOT NULL,
    data         TEXT NOT NULL,
    operacao_cod TEXT,
    status       TEXT,
    cliente      TEXT,
    produto      TEXT,
    descricao    TEXT,
    qtde         REAL,
    hl           REAL
);

CREATE TABLE IF NOT EXISTS notas_mapa_prod (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL,
    data         TEXT NOT NULL,
    mapa         TEXT NOT NULL,
    operacao_cod TEXT,
    status       TEXT,
    produto      TEXT,
    descricao    TEXT,
    qtde         REAL,
    hl           REAL,
    importado_em TEXT
);

CREATE TABLE IF NOT EXISTS remun_tabela (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL,
    unidade_cod   TEXT NOT NULL,
    unidade_nome  TEXT,
    produto       TEXT NOT NULL,
    descricao     TEXT,
    ini           TEXT NOT NULL,
    fim           TEXT,
    carreto       REAL,
    frete         REAL,
    arquivo       TEXT,
    importado_por TEXT,
    importado_em  TEXT
);

CREATE TABLE IF NOT EXISTS remun_fabrica_map (
    operacao_id INTEGER NOT NULL,
    unidade_cod TEXT NOT NULL,
    fornecedor  TEXT,
    PRIMARY KEY (operacao_id, unidade_cod)
);

CREATE TABLE IF NOT EXISTS remun_config (
    operacao_id INTEGER NOT NULL,
    chave       TEXT NOT NULL,
    valor       TEXT,
    PRIMARY KEY (operacao_id, chave)
);

CREATE TABLE IF NOT EXISTS inv_armazens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL,
    nome        TEXT NOT NULL,
    ativo       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS inv_areas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL,
    codigo      TEXT NOT NULL,
    nome        TEXT,
    armazem_id  INTEGER,
    ativo       INTEGER DEFAULT 1,
    ordem       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inv_inventarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL,
    mes          TEXT NOT NULL,
    nome         TEXT,
    status       TEXT DEFAULT 'aberto',
    depositos    TEXT,
    base_arquivo TEXT,
    base_em      TEXT,
    criado_por   TEXT,
    criado_em    TEXT
);

CREATE TABLE IF NOT EXISTS inv_base (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    inv_id     INTEGER NOT NULL,
    deposito   TEXT,
    produto    TEXT NOT NULL,
    descricao  TEXT,
    unidade    TEXT,
    fator      REAL,
    disp_un    REAL
);

CREATE TABLE IF NOT EXISTS inv_contagens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    inv_id       INTEGER NOT NULL,
    area         TEXT NOT NULL,
    endereco     TEXT,
    usuario      TEXT,
    inicio       TEXT,
    finalizacao  TEXT,
    produto      TEXT,
    descricao    TEXT,
    qtd          REAL,
    unidade      TEXT,
    validade     TEXT,
    arquivo      TEXT,
    importado_em TEXT
);

CREATE TABLE IF NOT EXISTS inv_recontagem (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    inv_id        INTEGER NOT NULL,
    operacao_id   INTEGER NOT NULL,
    area          TEXT NOT NULL,
    endereco      TEXT,
    produto       TEXT NOT NULL,
    descricao     TEXT,
    c1_un         REAL,
    c2_un         REAL,
    fator         REAL,
    status        TEXT DEFAULT 'pendente',
    qtd_un        REAL,
    contado_por   TEXT,
    contado_em    TEXT,
    descarga_em   TEXT,
    escolha       TEXT,
    final_un      REAL,
    conciliado_por TEXT,
    conciliado_em TEXT,
    enviado_por   TEXT,
    enviado_em    TEXT
);

CREATE TABLE IF NOT EXISTS inv_conversao (
    produto     TEXT PRIMARY KEY,
    un_cx       REAL,
    cx_pallet   REAL,
    cx_lastro   REAL,
    atualizado_por TEXT,
    atualizado_em  TEXT
);

CREATE TABLE IF NOT EXISTS inv_conferentes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL,
    nome          TEXT NOT NULL,
    login         TEXT NOT NULL,
    senha_hash    TEXT,
    ativo         INTEGER DEFAULT 1,
    criado_por    TEXT,
    criado_em     TEXT,
    ultimo_acesso TEXT
);

CREATE TABLE IF NOT EXISTS inv_diario_final (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    inv_id      INTEGER NOT NULL,
    produto     TEXT,
    descricao   TEXT,
    fator       REAL,
    sistema_un  REAL,
    contado_un  REAL,
    final_un    REAL,
    dif_un      REAL,
    status      TEXT,
    rodadas     INTEGER,
    enderecos   TEXT
);

CREATE TABLE IF NOT EXISTS inv_config (
    operacao_id INTEGER NOT NULL,
    chave       TEXT NOT NULL,
    valor       TEXT,
    PRIMARY KEY (operacao_id, chave)
);

CREATE TABLE IF NOT EXISTS obz_tend_abertura (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL,
    mes           TEXT NOT NULL,
    ate           TEXT NOT NULL,
    justificativa TEXT,
    aberto_por    TEXT,
    em            TEXT
);

CREATE TABLE IF NOT EXISTS obz_capex (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id     INTEGER NOT NULL,
    ano             TEXT NOT NULL,
    codigo          TEXT,
    nome            TEXT NOT NULL,
    area            TEXT,
    conta           TEXT,
    conta_juros     TEXT,
    categoria       TEXT,
    tipo            TEXT,
    prioridade      TEXT,
    justificativa   TEXT,
    valor           REAL DEFAULT 0,
    mes_ini         INTEGER DEFAULT 1,
    forma           TEXT DEFAULT 'avista',
    parcelas        INTEGER DEFAULT 1,
    taxa_aa         REAL DEFAULT 0,
    vida_util       REAL DEFAULT 5,
    opex_mensal     REAL DEFAULT 0,
    economia_mensal REAL DEFAULT 0,
    responsavel     TEXT,
    status          TEXT DEFAULT 'proposto',
    valor_realizado REAL,
    comentario      TEXT,
    criado_por      TEXT,
    criado_em       TEXT,
    atualizado_por  TEXT,
    atualizado_em   TEXT
);

CREATE TABLE IF NOT EXISTS obz_capex_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    capex_id    INTEGER NOT NULL,
    status      TEXT,
    usuario     TEXT,
    em          TEXT,
    comentario  TEXT
);

CREATE TABLE IF NOT EXISTS obz_sim_inic (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id      INTEGER NOT NULL,
    tipo        TEXT,
    descricao   TEXT,
    area        TEXT,
    conta       TEXT,
    mes_ini     INTEGER,
    valor       REAL,
    recorrente  INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS obz_sim_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id      INTEGER NOT NULL,
    etapa       TEXT,
    acao        TEXT,
    usuario     TEXT,
    em          TEXT,
    comentario  TEXT
);

CREATE TABLE IF NOT EXISTS obz_sim_reuniao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id        INTEGER NOT NULL,
    etapa         TEXT,
    data          TEXT,
    participantes TEXT,
    pauta         TEXT,
    ata           TEXT,
    decisoes      TEXT,
    criado_por    TEXT,
    criado_em     TEXT
);

CREATE TABLE IF NOT EXISTS robo_execucoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER,
    relatorio   TEXT,
    inicio      TEXT,
    fim         TEXT,
    status      TEXT,
    mensagem    TEXT,
    arquivo     TEXT,
    maquina     TEXT
);

CREATE TABLE IF NOT EXISTS seg_tentativas (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chave   TEXT NOT NULL,
    tipo    TEXT,
    sucesso INTEGER,
    quando  TEXT
);

CREATE TABLE IF NOT EXISTS seg_acessos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    nome       TEXT,
    login      TEXT,
    evento     TEXT,
    detalhe    TEXT,
    quando     TEXT
);

CREATE TABLE IF NOT EXISTS frota_tipos (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome   TEXT NOT NULL,
    ativo  INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS frota_modelos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    modelo      TEXT NOT NULL,
    tipo        TEXT,
    observacao  TEXT,
    ativo       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS idade_contagens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL,
    data        TEXT NOT NULL,
    nome        TEXT,
    arquivo     TEXT,
    linhas      INTEGER,
    criado_por  TEXT,
    criado_em   TEXT
);

CREATE TABLE IF NOT EXISTS idade_itens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contagem_id INTEGER NOT NULL,
    area        TEXT,
    endereco    TEXT,
    produto     TEXT,
    descricao   TEXT,
    qtd         REAL,
    unidade     TEXT,
    qtd_un      REAL,
    un_cx       REAL,
    validade    TEXT,
    usuario     TEXT
);

CREATE TABLE IF NOT EXISTS idade_areas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL,
    area        TEXT NOT NULL,
    tipo        TEXT
);

CREATE TABLE IF NOT EXISTS idade_limites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL,
    produto     TEXT NOT NULL,
    dias        INTEGER
);

CREATE TABLE IF NOT EXISTS fin_contab (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL,
    mes           TEXT NOT NULL,
    codigo        TEXT,
    classificacao TEXT,
    nome          TEXT,
    departamento  TEXT,
    subpacote     TEXT,
    valor         REAL,
    arquivo       TEXT,
    criado_por    TEXT,
    criado_em     TEXT
);

CREATE TABLE IF NOT EXISTS fin_contab_outras (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL,
    mes           TEXT NOT NULL,
    departamento  TEXT,
    conta         TEXT,
    despesa       REAL,
    obs           TEXT,
    criado_por    TEXT,
    criado_em     TEXT
);

CREATE TABLE IF NOT EXISTS dre_manual (
    operacao_id     INTEGER NOT NULL,
    mes             TEXT NOT NULL,
    conta_corrente  REAL DEFAULT 0,
    pis_cofins      REAL DEFAULT 0,
    icms            REAL DEFAULT 0,
    atualizado_por  TEXT,
    atualizado_em   TEXT,
    PRIMARY KEY (operacao_id, mes)
);

CREATE TABLE IF NOT EXISTS notas_cli_prod_mes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    mes          TEXT NOT NULL,
    operacao_cod TEXT,
    status       TEXT,
    cliente      TEXT,
    produto      TEXT,
    valor        REAL,
    hl           REAL
);

CREATE TABLE IF NOT EXISTS agendamentos_descarga (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    data        TEXT NOT NULL,
    hora        TEXT,
    placa       TEXT NOT NULL,
    slot        TEXT,
    tipo_carga  TEXT,
    status      TEXT DEFAULT 'Agendado',
    observacao  TEXT,
    criado_por  TEXT,
    dt_atualizacao TEXT
);

-- Janelas de descarga da revenda: em cada intervalo cabem N carretas (slots).
-- dias = dias da semana em que a janela vale (0=seg … 6=dom, separados por vírgula).
CREATE TABLE IF NOT EXISTS janelas_descarga (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    hora_inicio TEXT NOT NULL,
    hora_fim    TEXT NOT NULL,
    slots       INTEGER NOT NULL DEFAULT 1,
    dias        TEXT NOT NULL DEFAULT '0,1,2,3,4,5',
    produto     TEXT,
    ativo       INTEGER DEFAULT 1
);

-- Pedidos do dia (D0) e do dia seguinte (D+1) montados pela Puxada para cada placa.
-- Retornável: paletes por embalagem, Descartável: paletes no total. O armazém finaliza.
CREATE TABLE IF NOT EXISTS pedidos_puxada (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    data           TEXT NOT NULL,
    placa          TEXT NOT NULL,
    numero_pedido  TEXT NOT NULL,
    tipo           TEXT NOT NULL,
    p600_ambar     REAL DEFAULT 0,
    p600_verde     REAL DEFAULT 0,
    p1l            REAL DEFAULT 0,
    p300           REAL DEFAULT 0,
    paletes        REAL DEFAULT 0,
    status         TEXT DEFAULT 'Aberto',
    observacao     TEXT,
    criado_por     TEXT,
    criado_em      TEXT,
    atualizado_em  TEXT,
    finalizado_por TEXT,
    finalizado_em  TEXT
);

-- Tempo de deslocamento de cada revenda (filial) até cada fábrica, em horas
CREATE TABLE IF NOT EXISTS fabrica_deslocamento (
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    fabrica_id  INTEGER NOT NULL REFERENCES fabricas(id),
    horas       REAL DEFAULT 0,
    PRIMARY KEY (operacao_id, fabrica_id)
);

-- Férias dos motoristas (período fechado: início e fim inclusos)
CREATE TABLE IF NOT EXISTS ferias_motoristas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    motorista_id INTEGER NOT NULL REFERENCES motoristas(id),
    inicio       TEXT NOT NULL,
    fim          TEXT NOT NULL,
    observacao   TEXT,
    criado_por   TEXT,
    criado_em    TEXT
);

-- Motorista "em serviço" fora de viagem (manobra, oficina, abastecimento...) — marcado no App Carreteiro
CREATE TABLE IF NOT EXISTS servicos_motorista (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    motorista_id INTEGER NOT NULL REFERENCES motoristas(id),
    tipo         TEXT,
    observacao   TEXT,
    inicio       TEXT NOT NULL,
    fim          TEXT
);

-- Paradas na viagem registradas pelo motorista no App Carreteiro (ex.: manutenção): início e fim
CREATE TABLE IF NOT EXISTS paradas_viagem (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    viagem_id    INTEGER NOT NULL,
    motorista_id INTEGER,
    tipo         TEXT DEFAULT 'Manutenção',
    observacao   TEXT,
    inicio       TEXT NOT NULL,
    fim          TEXT,
    lat          REAL,
    lon          REAL
);

-- Interjornada marcada pelo motorista no app (11 h a partir do toque)
CREATE TABLE IF NOT EXISTS interjornadas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    motorista_id INTEGER NOT NULL REFERENCES motoristas(id),
    viagem_id    INTEGER,
    inicio       TEXT NOT NULL,
    fim_previsto TEXT NOT NULL,
    avisado_fim  INTEGER DEFAULT 0
);

-- Manutenção programada pela Puxada para uma placa (o armazém vê no pátio: depois de descarregar, vai p/ oficina)
CREATE TABLE IF NOT EXISTS manutencoes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    placa        TEXT NOT NULL,
    data         TEXT NOT NULL,
    hora         TEXT,
    tipo         TEXT,
    descricao    TEXT,
    oficina      TEXT,
    previsao_fim TEXT,
    prioridade   INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'Programada',
    criado_por   TEXT,
    criado_em    TEXT,
    iniciado_em  TEXT,
    concluido_em TEXT
);

CREATE TABLE IF NOT EXISTS vinculos_pedidos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id       INTEGER NOT NULL REFERENCES operacoes(id),
    numero_pedido     TEXT NOT NULL,
    data_puxada       TEXT,
    placa             TEXT,
    fabrica           TEXT,
    transportadora    TEXT,
    motorista         TEXT,
    notas_fiscais     TEXT,
    hl_carregado      REAL DEFAULT 0,
    dt_atualizacao    TEXT
);

-- ============ RESSUPRIMENTO: POLÍTICA DE ESTOQUE ============
CREATE TABLE IF NOT EXISTS politica_estoque (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id   INTEGER NOT NULL REFERENCES operacoes(id),
    data_registro TEXT NOT NULL,
    cod           INTEGER NOT NULL,
    sku_original  TEXT,
    tipo          TEXT,
    categoria     TEXT,
    estoque       REAL DEFAULT 0,
    demanda       REAL DEFAULT 0,
    doi_atual     REAL DEFAULT 0,
    pe_min_dias   REAL DEFAULT 0,
    pe_obj_dias   REAL DEFAULT 0,
    pe_max_dias   REAL DEFAULT 0,
    pe_min_hl     REAL DEFAULT 0,
    pe_obj_hl     REAL DEFAULT 0,
    pe_max_hl     REAL DEFAULT 0,
    dt_atualizacao TEXT
);

-- ============ BOOK DPO (padrões por pilar) E LAYOUTS ============
CREATE TABLE IF NOT EXISTS padroes_dpo (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    modulo         TEXT NOT NULL,
    subbloco       TEXT NOT NULL,
    titulo         TEXT,
    conteudo       TEXT,
    responsavel    TEXT,
    status         TEXT DEFAULT 'Em elaboração',
    atualizado_por TEXT,
    dt_atualizacao TEXT,
    UNIQUE (operacao_id, modulo, subbloco)
);

CREATE TABLE IF NOT EXISTS layouts_armazem (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id INTEGER NOT NULL REFERENCES operacoes(id),
    area        TEXT NOT NULL,
    nome_arquivo TEXT,
    tipo        TEXT,
    conteudo    BLOB,
    dt_atualizacao TEXT
);

-- ============ FINANCEIRO: CONTAS A PAGAR E FLUXO DE CAIXA ============
CREATE TABLE IF NOT EXISTS contas_pagar (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id     INTEGER NOT NULL REFERENCES operacoes(id),
    pacote          TEXT,
    departamento    TEXT,
    data_vencimento TEXT,
    documento       TEXT,
    fornecedor      TEXT,
    historico       TEXT,
    conta_gerencial TEXT,
    valor           REAL DEFAULT 0,
    realizado       REAL DEFAULT 0,
    dt_atualizacao  TEXT
);

CREATE TABLE IF NOT EXISTS fluxo_caixa (
    operacao_id          INTEGER NOT NULL REFERENCES operacoes(id),
    data                 TEXT NOT NULL,
    saldo_banco          REAL,
    compra_ambev         REAL DEFAULT 0,
    previsao_recebimento REAL DEFAULT 0,
    PRIMARY KEY (operacao_id, data)
);

-- ============ VENDAS: METAS ============
CREATE TABLE IF NOT EXISTS metas_vendas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    mes_ano      TEXT NOT NULL,
    categoria    TEXT NOT NULL,
    meta_hl      REAL DEFAULT 0,
    realizado_hl REAL DEFAULT 0,
    UNIQUE (operacao_id, mes_ano, categoria)
);

-- ============ REDEFINIÇÃO DE SENHA POR E-MAIL ============
CREATE TABLE IF NOT EXISTS senha_codigos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    codigo_hash TEXT NOT NULL,
    criado_em   TEXT NOT NULL,
    expira_em   TEXT NOT NULL,
    tentativas  INTEGER NOT NULL DEFAULT 0,
    usado       INTEGER NOT NULL DEFAULT 0
);

-- ============ APP CARRETEIRO ============
CREATE TABLE IF NOT EXISTS viagens_carreteiro (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id         INTEGER NOT NULL REFERENCES operacoes(id),
    motorista_id        INTEGER NOT NULL REFERENCES motoristas(id),
    usuario_id          INTEGER REFERENCES usuarios(id),
    numero_pedido       TEXT NOT NULL,
    agendamento         TEXT,
    destino_id          INTEGER REFERENCES fabricas(id),
    destino             TEXT,
    placa               TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'Em viagem',
    ts_inicio           TEXT,
    ts_apresentado      TEXT,
    apresentou_no_prazo INTEGER,
    atraso_min          INTEGER,
    ts_chamado          TEXT,
    ts_carregado        TEXT,
    ts_saida_cervejaria TEXT,
    ts_chegada_revenda  TEXT,
    ts_fim              TEXT,
    observacao          TEXT,
    criado_em           TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS viagem_eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    viagem_id   INTEGER NOT NULL REFERENCES viagens_carreteiro(id) ON DELETE CASCADE,
    etapa       TEXT NOT NULL,
    ts          TEXT NOT NULL,
    lat         REAL,
    lon         REAL,
    precisao_m  REAL,
    distancia_m REAL,
    dentro_raio INTEGER
);

CREATE TABLE IF NOT EXISTS viagem_notas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    viagem_id  INTEGER NOT NULL REFERENCES viagens_carreteiro(id) ON DELETE CASCADE,
    numero_nf  TEXT NOT NULL,
    criado_em  TEXT
);

CREATE TABLE IF NOT EXISTS viagem_fotos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    viagem_id  INTEGER NOT NULL REFERENCES viagens_carreteiro(id) ON DELETE CASCADE,
    nota_id    INTEGER REFERENCES viagem_notas(id) ON DELETE CASCADE,
    nome       TEXT,
    tipo       TEXT,
    conteudo   BLOB NOT NULL,
    criado_em  TEXT
);

-- ============ MOTORISTAS: REMUNERAÇÃO E NOTIFICAÇÕES ============
CREATE TABLE IF NOT EXISTS remuneracao_fabrica (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id  INTEGER NOT NULL REFERENCES operacoes(id),
    fabrica_id   INTEGER NOT NULL REFERENCES fabricas(id) ON DELETE CASCADE,
    valor_viagem REAL DEFAULT 0,
    UNIQUE (operacao_id, fabrica_id)
);

CREATE TABLE IF NOT EXISTS notificacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL,
    chave       TEXT,
    titulo      TEXT NOT NULL,
    texto       TEXT,
    pagina      TEXT,
    criado_em   TEXT NOT NULL,
    lida_em     TEXT
);

CREATE TABLE IF NOT EXISTS metas_centro_custo (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id     INTEGER NOT NULL REFERENCES operacoes(id),
    centro_custo_id INTEGER NOT NULL REFERENCES centros_custo(id) ON DELETE CASCADE,
    mes_ano         TEXT NOT NULL,
    valor_meta      REAL DEFAULT 0,
    UNIQUE (operacao_id, centro_custo_id, mes_ano)
);

CREATE TABLE IF NOT EXISTS disponibilidade_placas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id    INTEGER NOT NULL REFERENCES operacoes(id),
    placa          TEXT NOT NULL,
    data           TEXT NOT NULL,
    status         TEXT NOT NULL,
    observacao     TEXT,
    atualizado_por TEXT,
    dt_atualizacao TEXT,
    UNIQUE (operacao_id, placa, data)
);

-- ============ CONTROLE ============
CREATE TABLE IF NOT EXISTS _migracoes (
    id          TEXT PRIMARY KEY,
    aplicada_em TEXT DEFAULT (datetime('now','localtime'))
);
"""

# Lista de (id, sql). Adicione novas no final; nunca edite as antigas.
MIGRACOES: list[tuple[str, str]] = [
    ("001_indices", """
        CREATE INDEX IF NOT EXISTS ix_cot_status ON cotacoes_frete(operacao_id, status);
        CREATE INDEX IF NOT EXISTS ix_pedmarc_op ON pedidos_marcados(operacao_id, data_puxada);
        CREATE INDEX IF NOT EXISTS ix_ress_op ON ressuprimento_diario(operacao_id, data);
    """),
    ("002_trocar_senha", "ALTER TABLE usuarios ADD COLUMN trocar_senha INTEGER NOT NULL DEFAULT 0;"),
    ("003_ultimo_acesso", "ALTER TABLE usuarios ADD COLUMN ultimo_acesso TEXT;"),
    ("004_idx_bases_log", "CREATE INDEX IF NOT EXISTS ix_bases_log ON bases_log(base, operacao_id, dt);"),
    ("005_op_membros", "ALTER TABLE operacoes ADD COLUMN membros TEXT;"),
    ("006_trecho_transp", "ALTER TABLE trechos ADD COLUMN transportadora_id INTEGER;"),
    ("007_trecho_aprov", "ALTER TABLE trechos ADD COLUMN aprovador_id INTEGER;"),
    ("008_cot_nfs", "ALTER TABLE cotacoes_frete ADD COLUMN notas_fiscais TEXT;"),
    ("010_idx_email", "CREATE INDEX IF NOT EXISTS ix_usuarios_email ON usuarios(email);"),
    ("009_idx_novos", """
        CREATE INDEX IF NOT EXISTS ix_desc_op ON agendamentos_descarga(operacao_id, data);
        CREATE INDEX IF NOT EXISTS ix_vinc_op ON vinculos_pedidos(operacao_id, data_puxada);
        CREATE INDEX IF NOT EXISTS ix_pol_op ON politica_estoque(operacao_id, data_registro);
        CREATE INDEX IF NOT EXISTS ix_cp_op ON contas_pagar(operacao_id, data_vencimento);
    """),
    ("012_carreteiro", """
        ALTER TABLE motoristas ADD COLUMN usuario_id INTEGER;
        ALTER TABLE operacoes ADD COLUMN lat REAL;
        ALTER TABLE operacoes ADD COLUMN lon REAL;
        ALTER TABLE operacoes ADD COLUMN raio_m REAL;
        CREATE INDEX IF NOT EXISTS ix_vc_op ON viagens_carreteiro(operacao_id, ts_inicio);
        CREATE INDEX IF NOT EXISTS ix_vc_mot ON viagens_carreteiro(motorista_id, status);
        CREATE INDEX IF NOT EXISTS ix_vc_placa ON viagens_carreteiro(operacao_id, placa, ts_inicio);
        CREATE INDEX IF NOT EXISTS ix_vev_viagem ON viagem_eventos(viagem_id);
        CREATE INDEX IF NOT EXISTS ix_vnf_viagem ON viagem_notas(viagem_id);
        CREATE INDEX IF NOT EXISTS ix_vft_viagem ON viagem_fotos(viagem_id, nota_id);
    """),
    ("013_integracao_viagem", """
        ALTER TABLE agendamentos_descarga ADD COLUMN viagem_id INTEGER;
        ALTER TABLE vinculos_pedidos ADD COLUMN viagem_id INTEGER;
        CREATE INDEX IF NOT EXISTS ix_desc_viagem ON agendamentos_descarga(viagem_id);
        CREATE INDEX IF NOT EXISTS ix_vinc_viagem ON vinculos_pedidos(viagem_id);
        CREATE INDEX IF NOT EXISTS ix_pedmarc_num ON pedidos_marcados(operacao_id, numero_pedido);
    """),
    ("014_motoristas_cnh", """
        ALTER TABLE motoristas ADD COLUMN cpf TEXT;
        ALTER TABLE motoristas ADD COLUMN cnh_validade TEXT;
        ALTER TABLE motoristas ADD COLUMN gestor_id INTEGER;
        ALTER TABLE motoristas ADD COLUMN salario_fixo REAL DEFAULT 0;
        CREATE INDEX IF NOT EXISTS ix_notif_usuario ON notificacoes(usuario_id, lida_em);
        CREATE INDEX IF NOT EXISTS ix_notif_chave ON notificacoes(usuario_id, chave, criado_em);
    """),
    # Remove o ressuprimento diário trazido do sistema antigo (volumes sem a vírgula e iguais nas 3 filiais).
    # Esses registros têm a data de atualização no formato antigo DD/MM/AAAA. Basta reimportar o relatório.
    ("015_limpa_ressup_antigo", "DELETE FROM ressuprimento_diario WHERE dt_atualizacao LIKE '__/__/____%';"),
    # Trechos da frota própria (fábrica → revenda): valor da viagem do motorista, km e tempo padrão
    ("016_trecho_proprio", """
        ALTER TABLE remuneracao_fabrica ADD COLUMN km REAL DEFAULT 0;
        ALTER TABLE remuneracao_fabrica ADD COLUMN tempo_padrao_h REAL DEFAULT 0;
    """),
    # App Carreteiro: o motorista agenda a descarga (dia, hora e produto) entre carregar e sair da cervejaria
    ("017_agenda_descarga_app", """
        ALTER TABLE viagens_carreteiro ADD COLUMN ts_agendado TEXT;
        ALTER TABLE viagens_carreteiro ADD COLUMN desc_data TEXT;
        ALTER TABLE viagens_carreteiro ADD COLUMN desc_hora TEXT;
        ALTER TABLE viagens_carreteiro ADD COLUMN desc_tipo TEXT;
        CREATE INDEX IF NOT EXISTS ix_disp_placa ON disponibilidade_placas(operacao_id, data);
    """),
    # Janelas de descarga com slots: o motorista escolhe a janela e a vaga é consumida
    ("018_janelas_descarga", """
        ALTER TABLE agendamentos_descarga ADD COLUMN janela_id INTEGER;
        ALTER TABLE viagens_carreteiro ADD COLUMN desc_janela_id INTEGER;
        CREATE INDEX IF NOT EXISTS ix_janela_op ON janelas_descarga(operacao_id);
    """),
    # Disponibilidade com sugestão de produto e pedidos D0/D+1 da Puxada
    ("019_pedidos_puxada", """
        ALTER TABLE disponibilidade_placas ADD COLUMN sugestao TEXT;
        CREATE INDEX IF NOT EXISTS ix_pedpux_op ON pedidos_puxada(operacao_id, data);
    """),
    ("020_pedidos_puxada_fabrica", """
        ALTER TABLE pedidos_puxada ADD COLUMN fabrica_id INTEGER;
    """),
    # Pedido com motorista e hora do agendamento na fábrica (prazo de saída = agendamento − deslocamento),
    # ligado à viagem do App Carreteiro. Ressuprimento guarda o número como veio no relatório.
    ("021_pedido_agendamento", """
        ALTER TABLE pedidos_puxada ADD COLUMN motorista_id INTEGER;
        ALTER TABLE pedidos_puxada ADD COLUMN hora_agendamento TEXT;
        ALTER TABLE pedidos_puxada ADD COLUMN viagem_id INTEGER;
        ALTER TABLE ressuprimento_diario ADD COLUMN volume_txt TEXT;
        CREATE INDEX IF NOT EXISTS ix_pedpux_num ON pedidos_puxada(operacao_id, numero_pedido);
    """),
    # Trecho spot por fábrica + transportadora + tipo (Retornável/Descartável): tira a trava de 1 trecho
    # por origem/destino. Cotação guarda o tipo e a justificativa de aprovar valor diferente do cadastrado.
    # Pedido da Puxada registra quem editou e quando.
    ("022_trecho_tipo", lambda conn: _mig_022(conn)),
    ("023_ferias_motoristas", """
        CREATE INDEX IF NOT EXISTS ix_ferias_mot ON ferias_motoristas(motorista_id, inicio, fim);
        CREATE INDEX IF NOT EXISTS ix_vc_mot_fim ON viagens_carreteiro(motorista_id, ts_fim);
    """),
    # Vasilhames Corona 600 e Outros, janela do agendamento (início–fim), reprogramação (substitui o pedido),
    # perfil do veículo (9 eixos 42 paletes / LS 28) e motorista em serviço no app
    ("024_pedido_janela_reprog", """
        ALTER TABLE pedidos_puxada ADD COLUMN p_corona600 REAL DEFAULT 0;
        ALTER TABLE pedidos_puxada ADD COLUMN p_outros REAL DEFAULT 0;
        ALTER TABLE pedidos_puxada ADD COLUMN outros_desc TEXT;
        ALTER TABLE pedidos_puxada ADD COLUMN hora_agendamento_fim TEXT;
        ALTER TABLE pedidos_puxada ADD COLUMN substitui_id INTEGER;
        ALTER TABLE pedidos_puxada ADD COLUMN substituido_por INTEGER;
        ALTER TABLE pedidos_puxada ADD COLUMN reprogramado_motivo TEXT;
        ALTER TABLE carretas ADD COLUMN perfil TEXT;
        CREATE INDEX IF NOT EXISTS ix_serv_mot ON servicos_motorista(motorista_id, inicio);
    """),
    # Slots por tempo de doca (descartável/retornável por período) + parada de manutenção na viagem
    ("025_slots_tempo_doca", lambda conn: _mig_025(conn)),
    # Interjornada no app, manutenção programada, prioridade do pedido para o armazém
    ("026_interjornada_manutencao", """
        ALTER TABLE pedidos_puxada ADD COLUMN prioridade INTEGER DEFAULT 0;
        CREATE INDEX IF NOT EXISTS ix_interj_mot ON interjornadas(motorista_id, inicio);
        CREATE INDEX IF NOT EXISTS ix_manut_op ON manutencoes(operacao_id, data);
    """),
    ("027_relato_bloqueio_acesso", """
        ALTER TABLE operacoes ADD COLUMN link_relato TEXT;
        ALTER TABLE motoristas ADD COLUMN acesso_liberado_em TEXT;
    """),
    ("028_paletes_puxada_marcada", """
        ALTER TABLE pedidos_marcados ADD COLUMN paletes REAL DEFAULT 0;
    """),
    ("029_frota_cadastros", """
        ALTER TABLE motoristas ADD COLUMN categoria_cnh TEXT;
        ALTER TABLE transportadoras ADD COLUMN telefone TEXT;
        CREATE INDEX IF NOT EXISTS ix_frota_placas_op ON frota_placas(operacao_id);
    """),
    ("030_terceiro_app", """
        ALTER TABLE cotacoes_frete ADD COLUMN numeros_pedido TEXT;
        ALTER TABLE cotacoes_frete ADD COLUMN placa TEXT;
        ALTER TABLE cotacoes_frete ADD COLUMN alerta_destino TEXT;
        ALTER TABLE viagens_carreteiro ADD COLUMN terceiro INTEGER DEFAULT 0;
        ALTER TABLE viagens_carreteiro ADD COLUMN cotacao_id INTEGER;
        ALTER TABLE viagens_carreteiro ADD COLUMN terceiro_codigo TEXT;
        ALTER TABLE motoristas ADD COLUMN terceiro INTEGER DEFAULT 0;
    """),
    ("031_produtividade_entrega", """
        CREATE INDEX IF NOT EXISTS ix_ent_mapas ON entregas_mapas(operacao_id, data);
        CREATE INDEX IF NOT EXISTS ix_ent_notas ON entregas_notas(operacao_id, data);
        CREATE INDEX IF NOT EXISTS ix_ent_notas_mapa ON entregas_notas(operacao_id, mapa);
    """),
    ("032_faturamento", """
        CREATE INDEX IF NOT EXISTS ix_notas_dia ON notas_dia(operacao_id, origem, data);
        CREATE INDEX IF NOT EXISTS ix_notas_prod ON notas_produto_mes(operacao_id, origem, mes);
        CREATE INDEX IF NOT EXISTS ix_notas_cli ON notas_cliente_mes(operacao_id, origem, mes);
        ALTER TABLE ressuprimento_diario ADD COLUMN volume_venda_hl REAL;
    """),
    ("033_estoque_saldos", "CREATE INDEX IF NOT EXISTS ix_est_saldos ON estoque_saldos(operacao_id, mes, tipo_saldo);"),
    ("034_obz", """
        CREATE INDEX IF NOT EXISTS ix_obz_real ON obz_real(operacao_id, mes);
        CREATE INDEX IF NOT EXISTS ix_obz_lanc ON obz_real_lanc(operacao_id, mes, conta);
        CREATE INDEX IF NOT EXISTS ix_obz_tend ON obz_tend(operacao_id, mes);
    """),
    ("035_obz_areas", "ALTER TABLE obz_departamentos ADD COLUMN area TEXT;"),
    ("036_cli_prod", "CREATE INDEX IF NOT EXISTS ix_cli_prod ON notas_cli_prod_mes(operacao_id, mes);"),
    ("037_obz_bonif", """
        UPDATE obz_contas SET no_obz = 0, pacote = 'Bonificações'
         WHERE LOWER(nome) LIKE '%bonif%' OR LOWER(nome) LIKE '%amostra%';
    """),
    ("038_obz_sim", """
        CREATE INDEX IF NOT EXISTS ix_sim_linha ON obz_sim_linha(sim_id);
        CREATE INDEX IF NOT EXISTS ix_sim_log ON obz_sim_log(sim_id);
    """),
    ("039_sim_qlp", """
        ALTER TABLE obz_sim_equipe ADD COLUMN qlp_plan REAL;
        ALTER TABLE obz_sim_volume ADD COLUMN fonte TEXT;
        CREATE INDEX IF NOT EXISTS ix_capex ON obz_capex(operacao_id, ano);
    """),
    ("040_grade_calendario", """
        CREATE INDEX IF NOT EXISTS ix_grade_itens ON grade_check_itens(check_id);
        CREATE INDEX IF NOT EXISTS ix_grade_checks ON grade_checks(operacao_id, data);
        CREATE INDEX IF NOT EXISTS ix_vend_cal ON vendas_calendario(operacao_id, mes);
    """),
    ("041_obz_just", """
        CREATE INDEX IF NOT EXISTS ix_obz_just ON obz_just(operacao_id, mes);
        CREATE INDEX IF NOT EXISTS ix_obz_tend_ab ON obz_tend_abertura(operacao_id, mes);
    """),
    ("042_remun_ambev", """
        CREATE INDEX IF NOT EXISTS ix_notas_prod_dia ON notas_prod_dia(operacao_id, origem, data);
        CREATE INDEX IF NOT EXISTS ix_remun_tab ON remun_tabela(operacao_id, unidade_cod, produto, ini);
    """),
    ("043_remun_mes", """
        ALTER TABLE remun_tabela ADD COLUMN mes TEXT;
        UPDATE remun_tabela SET mes = substr(ini, 1, 7) WHERE mes IS NULL;
        CREATE INDEX IF NOT EXISTS ix_remun_mes ON remun_tabela(operacao_id, unidade_cod, mes);
    """),
    ("044_mapa_prod", """
        CREATE INDEX IF NOT EXISTS ix_mapa_prod ON notas_mapa_prod(operacao_id, data);
        CREATE INDEX IF NOT EXISTS ix_mapa_prod_m ON notas_mapa_prod(operacao_id, mapa);
    """),    ("045_inventario", """
        ALTER TABLE produtos ADD COLUMN cx_lastro REAL;
        ALTER TABLE produtos ADD COLUMN un_cx REAL;
        CREATE INDEX IF NOT EXISTS ix_inv_cont ON inv_contagens(inv_id, area);
        CREATE INDEX IF NOT EXISTS ix_inv_base ON inv_base(inv_id);
        CREATE INDEX IF NOT EXISTS ix_inv_rec ON inv_recontagem(inv_id, status);
        CREATE INDEX IF NOT EXISTS ix_inv_areas ON inv_areas(operacao_id, codigo);
    """),
    ("046_inv_conferentes", """
        CREATE INDEX IF NOT EXISTS ix_inv_conf ON inv_conferentes(operacao_id, login);
    """),
    ("047_inv_rodadas", """
        ALTER TABLE inv_recontagem ADD COLUMN rodada INTEGER DEFAULT 1;
        ALTER TABLE inv_recontagem ADD COLUMN pl REAL;
        ALTER TABLE inv_recontagem ADD COLUMN cx REAL;
        ALTER TABLE inv_recontagem ADD COLUMN un_s REAL;
        ALTER TABLE inv_inventarios ADD COLUMN finalizado_em TEXT;
        ALTER TABLE inv_inventarios ADD COLUMN finalizado_por TEXT;
        UPDATE inv_recontagem SET rodada = 1 WHERE rodada IS NULL;
    """),
    ("048_inv_diario", """
        ALTER TABLE inv_inventarios ADD COLUMN tipo TEXT DEFAULT 'mensal';
        ALTER TABLE inv_inventarios ADD COLUMN data TEXT;
        UPDATE inv_inventarios SET tipo = 'mensal' WHERE tipo IS NULL;
    """),
    ("049_inv_diario_final", """
        CREATE INDEX IF NOT EXISTS ix_inv_dfinal ON inv_diario_final(inv_id);
    """),    ("050_inv_transito", """
        ALTER TABLE inv_base ADD COLUMN transito_un REAL;
        ALTER TABLE inv_inventarios ADD COLUMN contab_transito INTEGER DEFAULT 0;
    """),    ("051_fin_contab", """
        CREATE INDEX IF NOT EXISTS ix_fin_contab ON fin_contab(operacao_id, mes);
        CREATE INDEX IF NOT EXISTS ix_fin_contab_out ON fin_contab_outras(operacao_id, mes);
    """),    ("052_idade", """
        CREATE INDEX IF NOT EXISTS ix_idade_itens ON idade_itens(contagem_id);
        CREATE INDEX IF NOT EXISTS ix_idade_cont ON idade_contagens(operacao_id, data);
    """),    ("053_seguranca", """
        CREATE INDEX IF NOT EXISTS ix_seg_tent ON seg_tentativas(chave, tipo, quando);
        CREATE INDEX IF NOT EXISTS ix_seg_acessos ON seg_acessos(quando);
    """),    ("054_robo", """
        CREATE INDEX IF NOT EXISTS ix_robo_exec ON robo_execucoes(relatorio, inicio);
    """),    ("055_frota_capacidade", """
        ALTER TABLE frota_tipos ADD COLUMN cap_cx REAL;
        ALTER TABLE frota_tipos ADD COLUMN cap_kg REAL;
    """),    ("056_frota_peso_placa", """
        ALTER TABLE frota_placas ADD COLUMN peso_kg REAL;
        ALTER TABLE frota_tipos ADD COLUMN cap_baias REAL;
        UPDATE frota_placas SET peso_kg = (SELECT t.cap_kg FROM frota_tipos t WHERE t.nome = frota_placas.tipo)
         WHERE peso_kg IS NULL;
    """),    ("057_usuario_distribui", """
        CREATE TABLE IF NOT EXISTS usuario_distribui (
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            modulo     TEXT NOT NULL,
            PRIMARY KEY (usuario_id, modulo)
        );
    """),
]


def _mig_025(conn) -> None:
    from config.settings import OPERACOES_CONSOLIDADAS

    conn.executescript("""
        ALTER TABLE janelas_descarga ADD COLUMN dur_desc_min INTEGER;
        ALTER TABLE janelas_descarga ADD COLUMN dur_ret_min INTEGER;
        CREATE INDEX IF NOT EXISTS ix_parada_viagem ON paradas_viagem(viagem_id);
    """)
    # Sobe o padrão da operação: 20h–02h (descartável 1h30 · retornável 2h30) e 02h–20h (1h · 2h)
    ops = [r[0] for r in conn.execute("SELECT id, nome FROM operacoes").fetchall()
           if r[1] not in OPERACOES_CONSOLIDADAS]
    conn.execute("UPDATE janelas_descarga SET ativo = 0")
    for op in ops:
        for ini, fim, dd, dr in (("20:00", "02:00", 90, 150), ("02:00", "20:00", 60, 120)):
            conn.execute("""INSERT INTO janelas_descarga (operacao_id, hora_inicio, hora_fim, slots, dias, ativo,
                            dur_desc_min, dur_ret_min) VALUES (?, ?, ?, 1, '0,1,2,3,4,5,6', 1, ?, ?)""",
                         (op, ini, fim, dd, dr))


def _mig_022(conn) -> None:
    if conn.pg:
        cur = conn.raw.cursor()
        cur.execute("""SELECT conname FROM pg_constraint WHERE conrelid = 'trechos'::regclass AND contype = 'u'""")
        for (nome,) in cur.fetchall():
            cur.execute(f'ALTER TABLE trechos DROP CONSTRAINT IF EXISTS "{nome}"')
        conn.executescript("ALTER TABLE trechos ADD COLUMN tipo TEXT")
    else:
        conn.executescript("""
            CREATE TABLE trechos_v2 (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                operacao_id       INTEGER NOT NULL REFERENCES operacoes(id),
                origem_id         INTEGER NOT NULL REFERENCES origens_destinos(id),
                destino_id        INTEGER NOT NULL REFERENCES origens_destinos(id),
                distancia_km      REAL DEFAULT 0,
                pedagio           REAL DEFAULT 0,
                valor_remunerado  REAL DEFAULT 0,
                valor_frete       REAL DEFAULT 0,
                transportadora_id INTEGER,
                aprovador_id      INTEGER,
                tipo              TEXT
            );
            INSERT INTO trechos_v2 (id, operacao_id, origem_id, destino_id, distancia_km, pedagio, valor_remunerado,
                                    valor_frete, transportadora_id, aprovador_id)
                SELECT id, operacao_id, origem_id, destino_id, distancia_km, pedagio, valor_remunerado, valor_frete,
                       transportadora_id, aprovador_id FROM trechos;
            DROP TABLE trechos;
            ALTER TABLE trechos_v2 RENAME TO trechos;
        """)
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS ix_trechos_busca ON trechos(operacao_id, origem_id, destino_id);
        ALTER TABLE cotacoes_frete ADD COLUMN tipo_carga TEXT;
        ALTER TABLE cotacoes_frete ADD COLUMN justificativa_aprovacao TEXT;
        ALTER TABLE pedidos_puxada ADD COLUMN editado_por TEXT;
        ALTER TABLE pedidos_puxada ADD COLUMN editado_em TEXT;
        ALTER TABLE pedidos_puxada ADD COLUMN editado_resumo TEXT;
    """)


_ADD_COLUNA = re.compile(r"^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.I)


def _coluna_existe(conn, tabela: str, coluna: str) -> bool:
    if getattr(conn, "pg", False):
        r = conn.execute("SELECT 1 FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
                         (tabela.lower(), coluna.lower())).fetchone()
        return bool(r)
    return any(str(r[1]).lower() == coluna.lower() for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall())


def _executar_migracao(conn, script: str) -> None:
    """Roda a migração comando a comando. "ADD COLUMN" de coluna que já existe é pulado — assim uma migração
    interrompida no meio (ex.: deploy reiniciado) termina na próxima vez sem erro de coluna duplicada."""
    pendentes = []
    for stmt in script.split(";"):
        linhas = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith("--")]
        if not linhas:
            continue
        m = _ADD_COLUNA.match("\n".join(linhas))
        if m and _coluna_existe(conn, m.group(1), m.group(2)):
            continue
        pendentes.append(stmt.strip())
    if pendentes:
        conn.executescript(";\n".join(pendentes) + ";")


def init_db(db_path=None) -> None:
    from core.auth import hash_senha  # import tardio evita ciclo

    with get_conn(db_path) as conn:
        conn.executescript(TABELAS)

        aplicadas = {r[0] for r in conn.execute("SELECT id FROM _migracoes")}
        for mig_id, sql in MIGRACOES:
            if mig_id not in aplicadas:
                sql(conn) if callable(sql) else _executar_migracao(conn, sql)
                conn.execute("INSERT INTO _migracoes (id) VALUES (?)", (mig_id,))

        # Usuário master no primeiro acesso (e-mail vem do segredo ADMIN_EMAIL)
        admin_email = (segredo("ADMIN_EMAIL") or ADMIN_EMAIL_PADRAO).strip().lower()
        lima = _instancia_grupo_lima()
        if not conn.execute("SELECT 1 FROM usuarios WHERE perfil = ?", (PERFIL_MASTER,)).fetchone():
            import secrets as _s

            # empresa nova: senha aleatória (o nova_empresa.sh entrega a provisória em MASTER_NOVA_SENHA)
            inicial = ADMIN_SENHA_INICIAL if lima else _s.token_urlsafe(18)
            conn.execute(
                """INSERT INTO usuarios (login, nome, senha_hash, email, cargo, perfil, e_aprovador, alcada, trocar_senha)
                   VALUES (?, 'Administrador', ?, ?, 'Administrador Master', ?, 1, 9999999, 1)""",
                (admin_email, hash_senha(inicial), admin_email, PERFIL_MASTER),
            )
        # O admin antigo (login "admin", sem e-mail) passa a entrar com o e-mail
        conn.execute("UPDATE usuarios SET email = ? WHERE login = ? AND (email IS NULL OR email = '')",
                     (admin_email, ADMIN_LOGIN))
        if lima:  # a senha inicial do dono vale só para a instância do Grupo Lima
            _master_inicial(conn, admin_email)
        _recuperar_master(conn, admin_email, hash_senha)

        # Operações padrão do Grupo Lima (só no primeiro acesso e só na instância dele; outra empresa cadastra as suas)
        if lima and not conn.execute("SELECT 1 FROM operacoes").fetchone():
            for nome, cnpj, cidade, uf in OPERACOES_PADRAO:
                conn.execute("INSERT INTO operacoes (nome, cnpj, cidade, uf) VALUES (?, ?, ?, ?)",
                             (nome, cnpj, cidade, uf))
        _garantir_consolidadas(conn)
        _slots_padrao(conn)


def _instancia_grupo_lima() -> bool:
    from config.plano import empresa

    return empresa().strip().lower().startswith("grupo lima")


def _slots_padrao(conn) -> None:
    """Filial que nunca teve período de descarga recebe o padrão (20h–02h: 1h30/2h30 · 02h–20h: 1h/2h)."""
    from config.settings import OPERACOES_CONSOLIDADAS

    for r in conn.execute("SELECT id, nome FROM operacoes").fetchall():
        op, nome = r[0], r[1]
        if nome in OPERACOES_CONSOLIDADAS:
            continue
        if conn.execute("SELECT 1 FROM janelas_descarga WHERE operacao_id = ?", (op,)).fetchone():
            continue
        for ini, fim, dd, dr in (("20:00", "02:00", 90, 150), ("02:00", "20:00", 60, 120)):
            conn.execute("""INSERT INTO janelas_descarga (operacao_id, hora_inicio, hora_fim, slots, dias, ativo,
                            dur_desc_min, dur_ret_min) VALUES (?, ?, ?, 1, '0,1,2,3,4,5,6', 1, ?, ?)""",
                         (op, ini, fim, dd, dr))


# Senha inicial do Master definida pelo dono do sistema (só o hash fica no código).
# Aplicada uma única vez por banco; troque-a em "Minha conta" depois do 1º acesso.
_MASTER_SENHA_HASH = "pbkdf2$200000$e979d8e2ddadf1a2dad6a8056a9741aa$effd15ded34c0d34883ada9fd2d4f8aa696f3a915fbea5f3dd8d1922acc65c15"


def _master_inicial(conn, admin_email: str) -> None:
    marca = "011_master_inicial"
    if conn.execute("SELECT 1 FROM _migracoes WHERE id = ?", (marca,)).fetchone():
        return
    alvo = conn.execute("SELECT id FROM usuarios WHERE lower(email) = ? OR login = ? ORDER BY id LIMIT 1",
                        (admin_email, ADMIN_LOGIN)).fetchone()
    if alvo:
        conn.execute("UPDATE usuarios SET senha_hash = ?, trocar_senha = 0, ativo = 1, perfil = ?, email = ? "
                     "WHERE id = ?", (_MASTER_SENHA_HASH, PERFIL_MASTER, admin_email, alvo[0]))
    else:
        conn.execute(
            """INSERT INTO usuarios (login, nome, senha_hash, email, cargo, perfil, e_aprovador, alcada, trocar_senha)
               VALUES (?, 'Administrador', ?, ?, 'Administrador Master', ?, 1, 9999999, 0)""",
            (admin_email, _MASTER_SENHA_HASH, admin_email, PERFIL_MASTER))
    conn.execute("INSERT INTO _migracoes (id) VALUES (?)", (marca,))


def _recuperar_master(conn, admin_email: str, hash_senha) -> None:
    """Acesso de emergência: se o segredo MASTER_NOVA_SENHA existir, a senha do Master
    (ADMIN_EMAIL) passa a ser essa — uma única vez por valor — e a troca no próximo login
    é obrigatória. Depois de entrar, apague o segredo."""
    import hashlib

    nova = segredo("MASTER_NOVA_SENHA")
    if not nova:
        return
    marca = "reset_master_" + hashlib.sha256(f"{admin_email}|{nova}".encode()).hexdigest()[:16]
    if conn.execute("SELECT 1 FROM _migracoes WHERE id = ?", (marca,)).fetchone():
        return
    alvo = conn.execute("SELECT id FROM usuarios WHERE lower(email) = ? OR login = ? ORDER BY id LIMIT 1",
                        (admin_email, ADMIN_LOGIN)).fetchone()
    if alvo:
        conn.execute("UPDATE usuarios SET senha_hash = ?, trocar_senha = 1, ativo = 1, perfil = ?, email = ? "
                     "WHERE id = ?", (hash_senha(str(nova)), PERFIL_MASTER, admin_email, alvo[0]))
    else:
        conn.execute(
            """INSERT INTO usuarios (login, nome, senha_hash, email, cargo, perfil, e_aprovador, alcada, trocar_senha)
               VALUES (?, 'Administrador', ?, ?, 'Administrador Master', ?, 1, 9999999, 1)""",
            (admin_email, hash_senha(str(nova)), admin_email, PERFIL_MASTER))
    conn.execute("INSERT INTO _migracoes (id) VALUES (?)", (marca,))


def _garantir_consolidadas(conn) -> None:
    """Cria as operações consolidadas (ex.: Bahia = Barreiras + São Félix) se faltarem."""
    ids = {r["nome"]: r["id"] for r in conn.execute("SELECT id, nome FROM operacoes")}
    for nome, membros in OPERACOES_CONSOLIDADAS.items():
        ids_membros = [str(ids[m]) for m in membros if m in ids]
        if nome not in ids and len(ids_membros) == len(membros):
            conn.execute("INSERT INTO operacoes (nome, cidade, uf, membros) VALUES (?, ?, ?, ?)",
                         (nome, "Consolidado", "", ",".join(ids_membros)))
