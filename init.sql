-- Tabela de Pacientes (Resource: Patient)
CREATE TABLE IF NOT EXISTS pacientes (
    id SERIAL PRIMARY KEY,
    numero_sns VARCHAR(20) UNIQUE, 
    nome VARCHAR(255),
    genero VARCHAR(10),
    telecom JSONB,
    contacto JSONB
);

-- Tabela de Profissionais de Saúde (Resource: Practitioner)
CREATE TABLE IF NOT EXISTS profissionais (
    id SERIAL PRIMARY KEY,
    cedula VARCHAR(20) UNIQUE, 
    nome VARCHAR(255),
    especialidade VARCHAR(100)
);

-- Tabela de Encontros/Consultas (Resource: Encounter)
CREATE TABLE IF NOT EXISTS encontros (
    id SERIAL PRIMARY KEY,
    paciente_id INT,
    practitioner_id INT,
    status VARCHAR(50),
    classe VARCHAR(10), 
    data_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT fk_paciente FOREIGN KEY(paciente_id) REFERENCES pacientes(id),
    CONSTRAINT fk_profissional FOREIGN KEY(practitioner_id) REFERENCES profissionais(id)
);

-- Tabela de Observações (Resource: Observation)
CREATE TABLE IF NOT EXISTS observacoes (
    id SERIAL PRIMARY KEY,
    estado VARCHAR(50),
    codigo JSONB,
    referencia VARCHAR(50), 
    dataExecucao TIMESTAMPTZ, 
    medicao JSONB
);