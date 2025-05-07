-- Tabela cadastro_usuario (base para as outras)
CREATE TABLE IF NOT EXISTS cadastro_usuario (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    senha VARCHAR(100) NOT NULL
);

-- Tabela empresas (deve ser criada antes das que referenciam ela)
CREATE TABLE IF NOT EXISTS empresas (
    id SERIAL PRIMARY KEY,
    nome_empresa VARCHAR(100) NOT NULL,
    razao_social VARCHAR(100) NOT NULL,
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    centro_trabalho VARCHAR(10) NOT NULL,
    segmento VARCHAR(50) NOT NULL,
    email_coorporativo VARCHAR(100) NOT NULL,
    contato VARCHAR(50) NOT NULL,
    responsavel_tecnico TEXT,
    responsavel_legal TEXT,
    tipo_empresa VARCHAR(50) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    criado_por INTEGER,
    usuario_master_id INTEGER DEFAULT 0,
    FOREIGN KEY (criado_por) REFERENCES cadastro_usuario(id)
);

-- Tabela dados_usuario
CREATE TABLE IF NOT EXISTS dados_usuario (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    centro_trabalho VARCHAR(50),
    contato VARCHAR(50),
    empresa VARCHAR(100),
    vinculo VARCHAR(50),
    segmento VARCHAR(50),
    empresa_id INTEGER,
    treinamentos VARCHAR(255),
    certificados JSONB,
    FOREIGN KEY (user_id) REFERENCES cadastro_usuario(id),
    FOREIGN KEY (empresa_id) REFERENCES empresas(id)
);

-- Tabela empresa_usuarios
CREATE TABLE IF NOT EXISTS empresa_usuarios (
    id SERIAL PRIMARY KEY,
    empresa_id INTEGER NOT NULL,
    usuario_id INTEGER,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    vinculo VARCHAR(100) NOT NULL DEFAULT 'Funcionário',
    importado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (empresa_id, email),
    FOREIGN KEY (empresa_id) REFERENCES empresas(id),
    FOREIGN KEY (usuario_id) REFERENCES cadastro_usuario(id)
);

-- Tabela password_reset_tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES cadastro_usuario(id)
);

-- Tabela user_sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    device_info TEXT,
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP,
    access_hash VARCHAR(255) UNIQUE,
    expires_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES cadastro_usuario(id)
);

-- Índices adicionais (alguns já são criados automaticamente pelas constraints)
CREATE INDEX IF NOT EXISTS idx_empresas_criado_por ON empresas(criado_por);
CREATE INDEX IF NOT EXISTS idx_dados_usuario_empresa_id ON dados_usuario(empresa_id);
CREATE INDEX IF NOT EXISTS idx_empresa_usuarios_usuario_id ON empresa_usuarios(usuario_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);