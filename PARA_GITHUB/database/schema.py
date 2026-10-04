"""Estrutura do banco de dados.

`init_db()` é chamado na abertura do app: cria as tabelas que faltam
e o usuário admin no primeiro acesso. É seguro rodar várias vezes.

Para evoluir o banco, adicione um item em MIGRACOES (nunca altere um
item antigo) — ele será aplicado uma única vez.
"""
from config.settings import ADMIN_LOGIN, ADMIN_SENHA_INICIAL, PERFIL_MASTER
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
]


def init_db(db_path=None) -> None:
    from core.auth import hash_senha  # import tardio evita ciclo

    with get_conn(db_path) as conn:
        conn.executescript(TABELAS)

        aplicadas = {r[0] for r in conn.execute("SELECT id FROM _migracoes")}
        for mig_id, sql in MIGRACOES:
            if mig_id not in aplicadas:
                conn.executescript(sql)
                conn.execute("INSERT INTO _migracoes (id) VALUES (?)", (mig_id,))

        # Usuário master no primeiro acesso
        if not conn.execute("SELECT 1 FROM usuarios WHERE login = ?", (ADMIN_LOGIN,)).fetchone():
            conn.execute(
                """INSERT INTO usuarios (login, nome, senha_hash, email, cargo, perfil, e_aprovador, alcada, trocar_senha)
                   VALUES (?, 'Administrador', ?, '', 'Administrador Master', ?, 1, 9999999, 1)""",
                (ADMIN_LOGIN, hash_senha(ADMIN_SENHA_INICIAL), PERFIL_MASTER),
            )
