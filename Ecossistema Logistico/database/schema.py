"""Estrutura do banco de dados.

`init_db()` é chamado na abertura do app: cria as tabelas que faltam
e o usuário admin no primeiro acesso. É seguro rodar várias vezes.

Para evoluir o banco, adicione um item em MIGRACOES (nunca altere um
item antigo) — ele será aplicado uma única vez.
"""
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
]


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


def init_db(db_path=None) -> None:
    from core.auth import hash_senha  # import tardio evita ciclo

    with get_conn(db_path) as conn:
        conn.executescript(TABELAS)

        aplicadas = {r[0] for r in conn.execute("SELECT id FROM _migracoes")}
        for mig_id, sql in MIGRACOES:
            if mig_id not in aplicadas:
                sql(conn) if callable(sql) else conn.executescript(sql)
                conn.execute("INSERT INTO _migracoes (id) VALUES (?)", (mig_id,))

        # Usuário master no primeiro acesso (e-mail vem do segredo ADMIN_EMAIL)
        admin_email = (segredo("ADMIN_EMAIL") or ADMIN_EMAIL_PADRAO).strip().lower()
        if not conn.execute("SELECT 1 FROM usuarios WHERE perfil = ?", (PERFIL_MASTER,)).fetchone():
            conn.execute(
                """INSERT INTO usuarios (login, nome, senha_hash, email, cargo, perfil, e_aprovador, alcada, trocar_senha)
                   VALUES (?, 'Administrador', ?, ?, 'Administrador Master', ?, 1, 9999999, 1)""",
                (admin_email, hash_senha(ADMIN_SENHA_INICIAL), admin_email, PERFIL_MASTER),
            )
        # O admin antigo (login "admin", sem e-mail) passa a entrar com o e-mail
        conn.execute("UPDATE usuarios SET email = ? WHERE login = ? AND (email IS NULL OR email = '')",
                     (admin_email, ADMIN_LOGIN))
        _master_inicial(conn, admin_email)
        _recuperar_master(conn, admin_email, hash_senha)

        # Operações padrão do Grupo Lima (só no primeiro acesso)
        if not conn.execute("SELECT 1 FROM operacoes").fetchone():
            for nome, cnpj, cidade, uf in OPERACOES_PADRAO:
                conn.execute("INSERT INTO operacoes (nome, cnpj, cidade, uf) VALUES (?, ?, ?, ?)",
                             (nome, cnpj, cidade, uf))
        _garantir_consolidadas(conn)


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
