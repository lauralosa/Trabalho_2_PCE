"""

 Arquitetura do sistema:

   [Dispositivo / Postman]
         │ POST Observation
         ▼
   [HAPI FHIR Server :9090]   — armazena recursos FHIR (Patient, Observation, etc.)
         │
         │ FHIR Subscription REST-hook (Seta 4):
         │   O HAPI FHIR envia automaticamente um POST HTTP a este serviço
         │   sempre que uma nova Observation é registada.
         │   A Subscription é criada no arranque deste serviço.
         ▼
   [Integration Server :5000]  — este ficheiro
   POST /webhook/fhir-observation
         │ Converte Observation FHIR → Composição openEHR (Seta 4.1)
         ▼
   [EHRbase Server :8085]      — armazena composições openEHR (EHRs, Compositions)

 Mecanismo de Gatilho — Justificação da escolha:
   Implementa-se a Opção A (FHIR Subscription R4, REST-hook) por ser a abordagem
   orientada a eventos recomendada para integrações em tempo real. Em comparação
   com o polling periódico (Opção B), o webhook assegura processamento imediato
   das observações sem latência associada a intervalos de verificação e sem
   consumo de recursos em pedidos periódicos quando não existem dados novos.
   A Subscription é criada automaticamente no arranque do serviço, não requerendo
   qualquer configuração manual.

=============================================================================
"""

# --- Importações Standard ---
import os           # leitura de variáveis de ambiente
import json         # serialização/deserialização JSON (para a BD local)
import logging      # logs estruturados para debugging
import time         # pausa entre tentativas de ligação (startup com resiliência)
import asyncio      # chamadas assíncronas no startup

# --- Importações de Datas ---
from datetime import datetime, timedelta, timezone

# --- Framework Web (FastAPI) ---
from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
# FastAPI        → framework web principal
# HTTPException  → retornar erros HTTP com código e mensagem descritiva
# Query          → parâmetros de query string nos endpoints GET
# Depends        → injeção de dependências (usado para JWT)
# BackgroundTasks→ executa tarefas após retornar a resposta HTTP (não bloqueia o webhook)

# --- Validação de Dados (Pydantic) ---
from pydantic import BaseModel, Field
# BaseModel → classe base para os schemas de validação dos pedidos
# Field     → metadados e validações extra nos campos (min_length, pattern, etc.)

# --- Tipos de Dados ---
from typing import List, Optional, Literal

# --- Base de Dados (PostgreSQL) ---
import psycopg2
from psycopg2.extras import RealDictCursor
# psycopg2        → driver para ligar ao PostgreSQL
# RealDictCursor  → retorna linhas da BD como dicionários {coluna: valor}

# --- Chamadas HTTP Externas ---
import requests
# Usado para comunicar com HAPI FHIR e EHRbase via REST API

# --- Autenticação JWT ---
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt
# python-jose → criação e verificação de tokens JWT (JSON Web Tokens)


# =============================================================================
# SECÇÃO 1: CONFIGURAÇÕES GLOBAIS
# =============================================================================
#
# As URLs são lidas de variáveis de ambiente (os.getenv).
# Isto é essencial para o Docker funcionar corretamente:
#
#   Dentro do Docker: os containers comunicam pelo NOME do serviço definido
#   no docker-compose.yml (ex: "hapi-fhir", "ehrbase"), não por "localhost".
#   O docker-compose passa estes valores via secção "environment".
#
#   Em execução local (fora do Docker): na ausência de variáveis de ambiente
#   definidas, os.getenv utiliza os valores padrão (localhost + porta exposta).
#
#   Mapeamento de portas (docker-compose.yml):
#     HAPI FHIR:   porta interna 8080 → porta local 9090
#     EHRbase:     porta interna 8080 → porta local 8085
#     Integration: porta interna 5000 → porta local 5000
# =============================================================================

HAPI_URL = os.getenv("FHIR_SERVER_URL", "http://localhost:9090/fhir")
EHRBASE_URL = os.getenv("EHRBASE_URL", "http://localhost:8085/ehrbase/rest/openehr/v1")

# URL interno do serviço de integração, acessível pelos restantes containers Docker.
# O HAPI FHIR utiliza este endereço para enviar as notificações de webhook.
# O nome do serviço "integration-service" é resolvido pela rede interna do Docker
# e corresponde ao valor de container_name definido no docker-compose.yml.
WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    "http://integration-service:5000/webhook/fhir-observation"
)

# O EHRbase está configurado com SECURITY_AUTHTYPE=none no docker-compose.yml,
# o que significa que não requer autenticação HTTP Basic.
# Quando auth=None é passado ao requests, nenhum cabeçalho Authorization é enviado.
EHR_AUTH = None

# Configuração do sistema de logging estruturado.
# Formato: "2026-05-24 01:00:00 [INFO] integration-service: mensagem"
# Visível em tempo real com: docker logs integration-service -f
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("integration-service")


# =============================================================================
# SECÇÃO 2: AUTENTICAÇÃO JWT (JSON Web Token)
# =============================================================================
#
# O JWT (JSON Web Token) é o mecanismo de autenticação que protege os endpoints
# da API. O fluxo de autenticação é o seguinte:
#
#   1. O cliente envia as credenciais via POST /token (username e password)
#   2. O servidor valida as credenciais e devolve um token JWT assinado
#   3. O cliente inclui o token em todos os pedidos subsequentes:
#      Cabeçalho HTTP: "Authorization: Bearer <token>"
#   4. O FastAPI verifica automaticamente o token em cada endpoint protegido
#      através da função de dependência get_current_user()
#
# O token tem validade definida por ACCESS_TOKEN_EXPIRE_MINUTES.
# Pedidos com token inválido ou expirado recebem a resposta HTTP 401 Unauthorized.
# =============================================================================

SECRET_KEY = "pce_uminho_secret"       # Chave secreta para assinar os tokens (em produção seria uma env var)
ALGORITHM = "HS256"                     # Algoritmo HMAC-SHA256 (seguro e amplamente suportado)
ACCESS_TOKEN_EXPIRE_MINUTES = 30        # Validade do token: 30 minutos

# OAuth2PasswordBearer instrui o FastAPI sobre como extrair o token
# dos pedidos HTTP (procura o cabeçalho "Authorization: Bearer <token>")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# =============================================================================
# SECÇÃO 3: INICIALIZAÇÃO DA APLICAÇÃO FASTAPI
# =============================================================================

app = FastAPI(
    title="Middleware FHIR R4 → EHRbase — Universidade do Minho",
    description=(
        "Serviço de integração — Trabalho Prático 2, Processo Clínico Eletrónico.\n\n"
        "**Mecanismo de Gatilho (Fase 3):**\n"
        "FHIR Subscription R4 (Opção A — REST-hook). O servidor HAPI FHIR notifica "
        "este serviço automaticamente via `POST /webhook/fhir-observation` sempre que "
        "uma nova Observation é registada. A Subscription é criada no arranque do serviço.\n\n"
        "**Autenticação:** JWT Bearer Token. Utilize `POST /token` para obter um token de acesso."
    ),
    version="2.0.0"
)


# =============================================================================
# SECÇÃO 4: LIGAÇÃO À BASE DE DADOS LOCAL (PostgreSQL)
# =============================================================================

def get_db_connection():
    """
    Cria e retorna uma nova ligação à base de dados PostgreSQL local.

    As credenciais são lidas de variáveis de ambiente para funcionar
    corretamente tanto dentro do Docker como em desenvolvimento local.
    A ligação é sempre fechada no bloco 'finally' do endpoint que a chama.
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "clinica_db"),
        user=os.getenv("DB_USER", "user"),
        password=os.getenv("DB_PASS", "password")
    )


# =============================================================================
# SECÇÃO 5: SCHEMAS DE VALIDAÇÃO (PYDANTIC)
# =============================================================================
#
# Os schemas Pydantic definem e validam a estrutura dos dados recebidos nos
# pedidos POST. O Pydantic retorna automaticamente HTTP 422 (Unprocessable Entity)
# se algum campo obrigatório estiver em falta ou com tipo inválido.
#
# No âmbito do TP02 (Fase 2), foram adicionados identificadores nacionais:
#   PatientSchema      → campo 'numero_sns' (Nº de Utente do SNS)
#   PractitionerSchema → campo 'cedula'     (Nº de Cédula Profissional)
# Estes identificadores estabelecem a ligação unívoca entre os recursos FHIR
# e os registos correspondentes no EHRbase.
# =============================================================================

class TelecomSchema(BaseModel):
    """Contacto de telecomunicações: número de telemóvel, telefone fixo ou email."""
    tipo: Literal["telemóvel", "telefone", "email"]
    valor: str = Field(..., pattern=r".+@.+\..+|[0-9]{7,15}")

class EnderecoSchema(BaseModel):
    """Endereço postal do paciente ou do seu contacto de emergência."""
    tipo: str
    valor: str

class ContactoSchema(BaseModel):
    """Pessoa de contacto de emergência associada ao paciente."""
    nome: str = Field(..., min_length=3)
    telecom: Optional[List[TelecomSchema]] = None
    endereco: Optional[List[EnderecoSchema]] = None

class PatientSchema(BaseModel):
    """
    Dados de um novo paciente a registar no sistema.

    O 'numero_sns' é o Número de Utente do SNS — identificador único nacional
    que permite ligar o recurso FHIR Patient ao EHR no EHRbase (TP02, Fase 2).
    """
    numero_sns: str = Field(..., description="Número de Utente do SNS (ex: '123456789')")
    nome: str = Field(..., min_length=3)
    genero: Literal["m", "f", "masculino", "feminino", "male", "female"]
    telecom: List[TelecomSchema]
    contacto: List[ContactoSchema]

class PractitionerSchema(BaseModel):
    """
    Dados de um novo profissional de saúde a registar no sistema.

    A 'cedula' é o Número de Cédula Profissional — identificador da Ordem dos
    Médicos que identifica unicamente o profissional no EHRbase (TP02, Fase 2).
    """
    cedula: str = Field(..., description="Número de Cédula Profissional (ex: 'C-12345')")
    nome: str = Field(..., min_length=3)
    especialidade: str = Field(..., min_length=2)

class EncounterSchema(BaseModel):
    """Dados de uma consulta/encontro clínico entre um paciente e um profissional."""
    paciente_id: int = Field(..., gt=0, description="ID local do paciente (da BD PostgreSQL)")
    practitioner_id: int = Field(..., gt=0, description="ID local do profissional (da BD PostgreSQL)")
    status: Literal["planned", "arrived", "triaged", "in-progress", "onleave", "finished", "cancelled"]
    classe_code: Literal["AMB", "EMER", "INT", "VR", "TLC"]

class ObsMedicao(BaseModel):
    """Valor numérico de uma medição clínica com unidade de medida UCUM."""
    valor: float
    unidade: str
    sistema: str = "http://unitsofmeasure.org"  # sistema UCUM — padrão internacional para unidades clínicas
    code: str

class ObservationSchema(BaseModel):
    """
    Dados de uma Observation FHIR (sinal vital ou medição clínica).

    O campo 'referencia' liga esta observação ao paciente usando o formato
    FHIR: "Patient/pat-{id_bd}".
    O campo 'codigo' deve conter o código LOINC da medição.
    """
    estado: Literal["registered", "preliminary", "final", "amended", "corrected"]
    codigo: dict   # ex: {"coding": [{"system": "http://loinc.org", "code": "8310-5"}]}
    referencia: str = Field(..., pattern=r"^Patient/pat-\d+$")
    dataExecucao: str
    medicao: ObsMedicao


# =============================================================================
# SECÇÃO 6: FUNÇÕES DE MAPEAMENTO FHIR
# =============================================================================
#
# Convertem os schemas Pydantic para o formato JSON do standard FHIR R4.
# O campo 'identifier' foi adicionado no TP02 para incluir os identificadores
# nacionais (SNS e cédula) necessários para a ligação entre sistemas.
# =============================================================================

def to_fhir_patient(db_id: int, data: PatientSchema) -> dict:
    """
    Converte PatientSchema para recurso FHIR Patient (R4).

    O 'identifier' com sistema 'https://www.sns.gov.pt/utente' contém o
    Nº de Utente SNS — permite ao EHRbase e a outros sistemas identificar
    este paciente de forma única, independente do ID interno da BD.
    """
    return {
        "resourceType": "Patient",
        "id": f"pat-{db_id}",
        "identifier": [{
            "system": "https://www.sns.gov.pt/utente",
            "value": data.numero_sns
        }],
        "active": True,
        "name": [{"text": data.nome}],
        "gender": "male" if data.genero.lower() in ["m", "masculino", "male"] else "female",
        "telecom": [
            {"system": "phone" if t.tipo == "telemóvel" else "email", "value": t.valor}
            for t in data.telecom
        ],
        "contact": [{"name": {"text": c.nome}} for c in data.contacto]
    }

def to_fhir_practitioner(db_id: int, data: PractitionerSchema) -> dict:
    """
    Converte PractitionerSchema para recurso FHIR Practitioner (R4).

    O 'identifier' com sistema 'https://www.ordemdosmedicos.pt' contém a
    cédula profissional — permite ao EHRbase associar o profissional como
    'composer' (autor) das Composições openEHR que submete.
    """
    return {
        "resourceType": "Practitioner",
        "id": f"prac-{db_id}",
        "identifier": [{
            "system": "https://www.ordemdosmedicos.pt",
            "value": data.cedula
        }],
        "active": True,
        "name": [{"text": data.nome}],
        "qualification": [{"code": {"text": data.especialidade}}]
    }

def to_fhir_encounter(db_id: int, data: EncounterSchema) -> dict:
    """
    Converte EncounterSchema para recurso FHIR Encounter (R4).

    O Encounter representa uma consulta clínica e liga o paciente ao
    profissional de saúde responsável pelo atendimento.
    """
    return {
        "resourceType": "Encounter",
        "id": f"enc-{db_id}",
        "status": data.status,
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": data.classe_code   # AMB=ambulatório, EMER=urgência, INT=internamento, etc.
        },
        "subject": {"reference": f"Patient/pat-{data.paciente_id}"},
        "participant": [{"individual": {"reference": f"Practitioner/prac-{data.practitioner_id}"}}]
    }

def to_fhir_observation(db_id: int, data: ObservationSchema) -> dict:
    """
    Converte ObservationSchema para recurso FHIR Observation (R4).

    O 'code' contém o código LOINC da medição. O 'valueQuantity' segue
    o sistema UCUM de unidades (standard internacional para saúde).
    """
    return {
        "resourceType": "Observation",
        "id": f"obs-{db_id}",
        "status": data.estado,
        "code": data.codigo,
        "subject": {"reference": data.referencia},
        "effectiveDateTime": data.dataExecucao,
        "valueQuantity": {
            "value": data.medicao.valor,
            "unit": data.medicao.unidade,
            "system": data.medicao.sistema,
            "code": data.medicao.code
        }
    }


# =============================================================================
# SECÇÃO 7: MAPA DE SINAIS VITAIS (CÓDIGOS LOINC → ARQUÉTIPOS OPENEHR)
# =============================================================================
#
# LOINC (Logical Observation Identifiers Names and Codes) é o sistema
# internacional de codificação de observações clínicas e laboratoriais,
# obrigatório em FHIR para identificar o tipo de medição numa Observation.
#
# Este dicionário mapeia cada código LOINC ao arquétipo openEHR correspondente,
# permitindo ao serviço:
#   1. Reconhecer que tipo de sinal vital chegou (pelo código LOINC)
#   2. Saber em que arquétipo openEHR deve guardar o valor no EHRbase
#   3. Saber qual o nó ('node') dentro do arquétipo onde o valor é colocado
# =============================================================================

MAPA_SINAIS_VITAIS = {
    "8480-6": {
        "nome": "Systolic",
        "archetype": "openEHR-EHR-OBSERVATION.blood_pressure.v2",
        "history_node": "at0001",
        "event_node": "at0006",
        "data_node": "at0003",
        "item_node": "at0004",
        "unidade": "mm[Hg]",
    },
    "8462-4": {
        "nome": "Diastolic",
        "archetype": "openEHR-EHR-OBSERVATION.blood_pressure.v2",
        "history_node": "at0001",
        "event_node": "at0006",
        "data_node": "at0003",
        "item_node": "at0005",
        "unidade": "mm[Hg]",
    },
    "8867-4": {
        "nome": "Rate",
        "archetype": "openEHR-EHR-OBSERVATION.pulse.v2",
        "history_node": "at0002",
        "event_node": "at0003",
        "data_node": "at0001",
        "item_node": "at0004",
        "unidade": "/min",
    },
    "8310-5": {
        "nome": "Temperature",
        "archetype": "openEHR-EHR-OBSERVATION.body_temperature.v2",
        "history_node": "at0002",
        "event_node": "at0003",
        "data_node": "at0001",
        "item_node": "at0004",
        "unidade": "Cel",
    },
    "59408-5": {
        "nome": "SpO₂",
        "archetype": "openEHR-EHR-OBSERVATION.pulse_oximetry.v1",
        "history_node": "at0001",
        "event_node": "at0002",
        "data_node": "at0003",
        "item_node": "at0006",
        "unidade": "%",
    },
    "29463-7": {
        "nome": "Weight",
        "archetype": "openEHR-EHR-OBSERVATION.body_weight.v2",
        "history_node": "at0002",
        "event_node": "at0003",
        "data_node": "at0001",
        "item_node": "at0004",
        "unidade": "kg",
    },
    "9279-1": {
        "nome": "Rate",
        "archetype": "openEHR-EHR-OBSERVATION.respiration.v2",
        "history_node": "at0001",
        "event_node": "at0002",
        "data_node": "at0003",
        "item_node": "at0004",
        "unidade": "/min",
    },
}


# =============================================================================
# SECÇÃO 8: FUNÇÕES DE INTEGRAÇÃO FHIR → EHRBASE
# =============================================================================
#
# Funções auxiliares que encapsulam a lógica de comunicação com o EHRbase
# e a conversão de formatos entre FHIR R4 e openEHR Canonical JSON.
# São invocadas pelo processo de integração (Secção 9) e pelo mecanismo
# de gatilho (Secção 10).
# =============================================================================

def garantir_ehr(numero_utente: str, patient_fhir_id: str) -> str:
    """
    Garante que existe um EHR (Electronic Health Record) no EHRbase para o utente.

    Implementa a lógica de gestão do registo do paciente no EHRbase:
      1. Pesquisa no EHRbase se já existe um EHR para este Nº de Utente SNS
         → GET /ehr?subject_id={patient_fhir_id}&subject_namespace=pt_sns_utente
      2. Se existir → retorna o ehr_id (UUID) diretamente
      3. Se não existir → cria novo EHR com o Patient.id do FHIR como externalId
         → POST /ehr (com EHR_STATUS contendo a referência bidirecional)

    A ligação bidirecional entre sistemas é garantida pelo externalId:
      FHIR sabe o SNS do paciente (campo 'identifier')
      EHRbase sabe o ID FHIR do paciente (campo 'subject.external_ref.id')

    Args:
        numero_utente: Número de Utente do SNS (ex: "123456789")
        patient_fhir_id: ID do recurso Patient no FHIR (ex: "pat-1")

    Returns:
        ehr_id: UUID do EHR no EHRbase (ex: "a1b2c3d4-e5f6-...")
    """
    search_url = f"{EHRBASE_URL}/ehr?subject_id={patient_fhir_id}&subject_namespace=pt_sns_utente"
    try:
        res = requests.get(search_url, auth=EHR_AUTH, timeout=10)
        if res.status_code == 200:
            ehr_id = res.json()['ehr_id']['value']
            logger.info(f"EHR já existe para utente SNS {numero_utente}: {ehr_id}")
            return ehr_id
    except Exception as e:
        logger.warning(f"Erro ao pesquisar EHR para utente {numero_utente}: {e}")

    # EHR não encontrado → criar novo com ligação bidirecional ao recurso FHIR
    logger.info(f"A criar novo EHR para utente SNS {numero_utente}...")
    payload = {
        "_type": "EHR_STATUS",
        "archetype_node_id": "openEHR-EHR-EHR_STATUS.generic.v1",
        "name": {"_type": "DV_TEXT", "value": "EHR Status"},
        "subject": {
            "external_ref": {
                # externalId: guarda o Patient.id do FHIR → garante ligação bidirecional
                "id": {"_type": "GENERIC_ID", "value": patient_fhir_id, "scheme": "fhir"},
                "namespace": "pt_sns_utente",
                "type": "PERSON"
            }
        },
        "is_queryable": True,
        "is_modifiable": True
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": f"subject_id={patient_fhir_id}"
    }
    create_res = requests.post(
        f"{EHRBASE_URL}/ehr", json=payload,
        auth=EHR_AUTH, headers=headers, timeout=10
    )
    
    #  Prevenir crash 409
    if create_res.status_code == 409:
        logger.warning(f"[WEBHOOK] Conflito 409 para utente {numero_utente}. A tentar recuperar EHR existente...")
        retry = requests.get(search_url, auth=EHR_AUTH)
        if retry.status_code == 200:
            return retry.json()['ehr_id']['value']

    create_res.raise_for_status()
    # O EHRbase retorna o ehr_id no header 'EHR-Id' (201 Created)
    # O corpo pode vir vazio ou com o EHR completo dependendo da versão
    ehr_id = create_res.headers.get("EHR-Id")
    if not ehr_id:
        # Fallback: tentar extrair do corpo JSON
        try:
            ehr_id = create_res.json()['ehr_id']['value']
        except Exception:
            raise Exception(f"Não foi possível obter ehr_id da resposta do EHRbase. Status: {create_res.status_code}, Body: {create_res.text[:200]}")
    logger.info(f"Novo EHR criado para utente SNS {numero_utente}: {ehr_id}")
    return ehr_id


def build_openehr_composition(fhir_obs: dict, practitioner_info: dict) -> Optional[dict]:
    """
    Converte uma Observation FHIR para o formato Canonical JSON de uma
    Composição openEHR, compatível com o template 'Sinais vitais'.

    O formato Canonical JSON é o formato padrão do EHRbase para receber
    composições via REST API (POST /ehr/{ehr_id}/composition).

    Hierarquia openEHR construída:
      COMPOSITION → OBSERVATION → HISTORY → POINT_EVENT → ITEM_TREE → ELEMENT → DV_QUANTITY

    Args:
        fhir_obs: Dicionário com o recurso FHIR Observation completo
        practitioner_info: Dicionário com os dados do médico

    Returns:
        Dicionário no formato Canonical JSON, ou None se o código LOINC não for suportado.
    """
    try:
        valor_medicao = fhir_obs.get('valueQuantity', {}).get('value')
        data_execucao = fhir_obs.get('effectiveDateTime')

        # Extrai o código LOINC do campo 'code.coding[0].code' da Observation FHIR
        loinc = fhir_obs.get('code', {}).get('coding', [{}])[0].get('code')
        if not loinc:
            logger.warning("Observation FHIR sem código LOINC válido — não é possível mapear.")
            return None

        info = MAPA_SINAIS_VITAIS.get(loinc)
        if not info:
            logger.warning(f"Código LOINC '{loinc}' não está no mapa de sinais vitais suportados.")
            return None

        # Remover 'Z' da data para o Java do EHRbase não falhar
        if data_execucao and data_execucao.endswith('Z'):
            data_execucao = data_execucao.replace('Z', '')

        # Regra especial para Saturação (Proportion vs Quantity)
        if loinc == "59408-5":
            value_block = {
                "_type": "DV_PROPORTION",
                "numerator": float(valor_medicao) if valor_medicao else 0.0,
                "denominator": 100.0,
                "type": 3
            }
        else:
            value_block = {
                "_type": "DV_QUANTITY",
                "magnitude": float(valor_medicao) if valor_medicao else 0.0,
                "units": fhir_obs.get('valueQuantity', {}).get('unit', info['unidade'])
            }

        nome_medico = practitioner_info.get("nome", "Desconhecido")
        fhir_medico_id = practitioner_info.get("cedula", "Desconhecido")

        composer_block = {
            "_type": "PARTY_IDENTIFIED",
            "name": nome_medico,
            "external_ref": {
                "_type": "PARTY_REF",
                "id": {"_type": "GENERIC_ID", "value": str(fhir_medico_id), "scheme": "fhir"},
                "namespace": "pt-cedula-profissional",
                "type": "ORGANISATION"
            }
        }

        # Construção final da Composição
        return {
            "_type": "COMPOSITION",
            "archetype_node_id": "openEHR-EHR-COMPOSITION.encounter.v1",
            "name": {"_type": "DV_TEXT", "value": "Sinais vitais"},
            "archetype_details": {
                "_type": "ARCHETYPED",
                "archetype_id": {"_type": "ARCHETYPE_ID", "value": "openEHR-EHR-COMPOSITION.encounter.v1"},
                "template_id": {"_type": "TEMPLATE_ID", "value": "Sinais vitais"},
                "rm_version": "1.0.4"
            },
            "language": {"_type": "CODE_PHRASE", "terminology_id": {"_type": "TERMINOLOGY_ID", "value": "ISO_639-1"}, "code_string": "en"},
            "territory": {"_type": "CODE_PHRASE", "terminology_id": {"_type": "TERMINOLOGY_ID", "value": "ISO_3166-1"}, "code_string": "PT"},
            "category": {
                "_type": "DV_CODED_TEXT", "value": "event",
                "defining_code": {"_type": "CODE_PHRASE", "terminology_id": {"_type": "TERMINOLOGY_ID", "value": "openehr"}, "code_string": "433"}
            },
            "composer": composer_block,
            "context": {
                "_type": "EVENT_CONTEXT",
                "start_time": {"_type": "DV_DATE_TIME", "value": data_execucao},
                "setting": {
                    "_type": "DV_CODED_TEXT", "value": "secondary medical care",
                    "defining_code": {"_type": "CODE_PHRASE", "terminology_id": {"_type": "TERMINOLOGY_ID", "value": "openehr"}, "code_string": "232"}
                }
            },
            "content": [
                {
                    "_type": "OBSERVATION",
                    "archetype_node_id": info["archetype"],
                    "name": {"_type": "DV_TEXT", "value": info["nome"]},
                    "archetype_details": {
                        "_type": "ARCHETYPED",
                        "archetype_id": {"_type": "ARCHETYPE_ID", "value": info["archetype"]},
                        "rm_version": "1.0.4"
                    },
                    "language": {"_type": "CODE_PHRASE", "terminology_id": {"_type": "TERMINOLOGY_ID", "value": "ISO_639-1"}, "code_string": "en"},
                    "encoding": {"_type": "CODE_PHRASE", "terminology_id": {"_type": "TERMINOLOGY_ID", "value": "IANA_character-sets"}, "code_string": "UTF-8"},
                    "subject": {"_type": "PARTY_SELF"},
                    "data": {
                        "_type": "HISTORY",
                        "archetype_node_id": info["history_node"],  
                        "name": {"_type": "DV_TEXT", "value": "History"},
                        "origin": {"_type": "DV_DATE_TIME", "value": data_execucao},
                        "events": [
                            {
                                "_type": "POINT_EVENT",
                                "archetype_node_id": info["event_node"],  
                                "name": {"_type": "DV_TEXT", "value": "Any event"},
                                "time": {"_type": "DV_DATE_TIME", "value": data_execucao},
                                "data": {
                                    "_type": "ITEM_TREE",
                                    "archetype_node_id": info["data_node"],
                                    "name": {"_type": "DV_TEXT", "value": "Tree"},
                                    "items": [
                                        {
                                            "_type": "ELEMENT",
                                            "archetype_node_id": info["item_node"],
                                            "name": {"_type": "DV_TEXT", "value": info["nome"]},
                                            "value": value_block
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            ]
        }
    except Exception as e:
        logger.error(f"❌ Erro crítico ao construir composição openEHR: {e}")
        return None


def obter_dados_medico_fhir(ref: str) -> dict:
    """
    Obtém o recurso Practitioner do HAPI FHIR
    para extrair o nome e a cédula (identifier).
    """
    if not ref:
        return {"nome": "Profissional Desconhecido", "cedula": None, "sistema": None}
    try:
        response = requests.get(f"{HAPI_URL}/{ref}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            nome = data.get('name', [{}])[0].get('text', "Médico s/ Nome")
            cedula = None
            sistema = None
            for ident in data.get("identifier", []):
                if "ordem" in ident.get("system", ""):
                    cedula = ident.get("value")
                    sistema = ident.get("system")
                    break
            return {"nome": nome, "cedula": cedula, "sistema": sistema}
    except Exception as e:
        logger.warning(f"Erro ao consultar Practitioner '{ref}': {e}")
    return {"nome": "Profissional Desconhecido", "cedula": None, "sistema": None}


def validar_composicao_openehr(ehr_id: str, composition: dict) -> tuple:
    """
    (Extra) Valida uma Composição openEHR contra o Template no EHRbase
    antes de a guardar definitivamente.

    O endpoint de validação verifica conformidade com o template .opt sem
    persistir a composição — útil para detetar erros de mapeamento.

    Returns:
        (True, "ok") se válida ou endpoint não suportado,
        (False, "mensagem de erro") se explicitamente inválida (HTTP 4xx != 405).
    """
    validate_url = f"{EHRBASE_URL}/ehr/{ehr_id}/composition/validate"
    try:
        res = requests.post(validate_url, json=composition, auth=EHR_AUTH, timeout=10)
        if res.status_code == 200:
            return True, "Composição válida conforme o Template."
        if res.status_code == 405:
            # O EHRbase não suporta este endpoint nesta versão — tratar como válido
            logger.info("[VALIDAÇÃO] Endpoint /composition/validate não suportado (405). A continuar sem validação prévia.")
            return True, "Validação não suportada nesta versão do EHRbase."
        return False, res.text
    except Exception as e:
        return False, f"Erro na ligação ao validador EHRbase: {str(e)}"


# =============================================================================
# SECÇÃO 9: LÓGICA DE INTEGRAÇÃO (Fase 4)
# =============================================================================
#
# Esta secção implementa a função central de integração entre o HAPI FHIR e o
# EHRbase. A função processar_observation() é invocada automaticamente pelo
# endpoint de webhook (Secção 10) sempre que o HAPI FHIR notifica o serviço
# sobre uma nova Observation.
#
# Funções auxiliares disponíveis (implementadas na Secção 8):
#   garantir_ehr(numero_utente, patient_fhir_id)  → ehr_id (str)
#   build_openehr_composition(fhir_obs, nome)     → dict | None
#   obter_nome_medico_fhir(ref)                   → str
#   validar_composicao_openehr(ehr_id, comp)      → (bool, str)
#
# Variáveis globais de configuração disponíveis:
#   EHRBASE_URL, HAPI_URL, EHR_AUTH, MAPA_SINAIS_VITAIS
# =============================================================================

def processar_observation(fhir_obs: dict) -> dict:
    """
    Processa uma Observation FHIR e persiste os dados no EHRbase.

    É chamado automaticamente pelo webhook (Secção 10) sempre que o HAPI FHIR notifica o serviço sobre
    uma nova Observation.

    Fluxo:
      1. Extrai a referência ao Patient e ao Practitioner da Observation
      2. Obtém o Nº de Utente SNS consultando o Patient no HAPI FHIR
      3. Garante/cria o EHR no EHRbase para este utente
      4. Obtém o nome do profissional de saúde no HAPI FHIR
      5. Constrói a Composição openEHR a partir da Observation
      6. Submete a Composição ao EHRbase

    Args:
        fhir_obs: Dicionário completo do recurso FHIR Observation

    Returns:
        dict com {"status": "ok"/"ignorado"/"erro", ...} e detalhes do processamento
    """
    obs_id = fhir_obs.get("id", "desconhecido")
    logger.info(f"[INTEGRAÇÃO] A processar Observation/{obs_id}...")

    # ------------------------------------------------------------------
    # Passo 1 — Extrair referências da Observation
    # A Observation FHIR tem dois campos de referência relevantes:
    #   subject   → o paciente a quem pertencem os dados (Patient/pat-X)
    #   performer → o profissional que fez a medição (Practitioner/prac-X)
    # ------------------------------------------------------------------
    subject_ref = fhir_obs.get("subject", {}).get("reference", "")
    performer_refs = fhir_obs.get("performer", [])
    performer_ref = performer_refs[0].get("reference", "") if performer_refs else ""

    if not subject_ref:
        logger.error(f"[INTEGRAÇÃO] Observation/{obs_id} não tem 'subject.reference'. A ignorar.")
        return {
            "status": "erro",
            "observation_id": obs_id,
            "mensagem": "Campo 'subject.reference' em falta na Observation FHIR."
        }

    # ------------------------------------------------------------------
    # Passo 2 — Obter o Nº de Utente SNS a partir do Patient no HAPI FHIR
    # O Patient tem o SNS no campo 'identifier' com sistema sns.gov.pt
    # (adicionado no TP02, Fase 2). Precisamos deste número para criar/
    # encontrar o EHR correspondente no EHRbase.
    # ------------------------------------------------------------------
    try:
        patient_response = requests.get(f"{HAPI_URL}/{subject_ref}", timeout=5)
        patient_response.raise_for_status()
        patient_data = patient_response.json()

        # Percorrer os identifiers do Patient para encontrar o SNS
        numero_utente = None
        for identifier in patient_data.get("identifier", []):
            if "sns.gov.pt" in identifier.get("system", ""):
                numero_utente = identifier.get("value")
                break

        if not numero_utente:
            logger.error(
                f"[INTEGRAÇÃO] Patient '{subject_ref}' não tem identificador SNS. "
                f"Não é possível criar EHR sem Nº de Utente."
            )
            return {
                "status": "erro",
                "observation_id": obs_id,
                "mensagem": "Nº de Utente SNS não encontrado no campo 'identifier' do Patient FHIR."
            }

        # ID do Patient no FHIR (ex: "pat-1") — guardado como externalId no EHR
        patient_fhir_id = patient_data.get("id", subject_ref.split("/")[-1])
        logger.info(
            f"[INTEGRAÇÃO] Paciente identificado: SNS={numero_utente}, "
            f"FHIR Patient ID={patient_fhir_id}"
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"[INTEGRAÇÃO] Erro ao obter Patient '{subject_ref}' do HAPI FHIR: {e}")
        return {
            "status": "erro",
            "observation_id": obs_id,
            "mensagem": f"Erro ao consultar Patient no HAPI FHIR: {e}"
        }

    # ------------------------------------------------------------------
    # Passo 3 — Garantir/criar EHR no EHRbase
    # garantir_ehr() verifica se já existe um EHR para este utente.
    # Se não existir, cria-o com o patient_fhir_id como externalId,
    # garantindo a ligação bidirecional FHIR ↔ EHRbase.
    # ------------------------------------------------------------------
    try:
        ehr_id = garantir_ehr(numero_utente, patient_fhir_id)
        logger.info(f"[INTEGRAÇÃO] EHR garantido para SNS {numero_utente}: {ehr_id}")
    except Exception as e:
        logger.error(f"[INTEGRAÇÃO] Erro ao garantir EHR para SNS {numero_utente}: {e}")
        return {
            "status": "erro",
            "observation_id": obs_id,
            "mensagem": f"Erro ao gerir EHR no EHRbase: {e}"
        }

    # ------------------------------------------------------------------
    # Passo 4 — Obter o nome do profissional de saúde
    # O nome é usado como 'composer' (autor) na Composição openEHR.
    # Se não houver performer na Observation, usa um valor padrão.
    # ------------------------------------------------------------------
    if performer_ref:
        practitioner_info = obter_dados_medico_fhir(performer_ref)
        logger.info(f"[INTEGRAÇÃO] Profissional de saúde: {practitioner_info.get('nome')}")
    else:
        practitioner_info = {"nome": "Profissional Desconhecido", "cedula": None, "sistema": None}
        logger.warning(
            f"[INTEGRAÇÃO] Observation/{obs_id} não tem 'performer'. "
            f"A usar 'Profissional Desconhecido' como composer da Composição."
        )

    # ------------------------------------------------------------------
    # Passo 5 — Construir a Composição openEHR
    # build_openehr_composition() mapeia a Observation FHIR para o formato
    # Canonical JSON compatível com o template 'Sinais vitais' no EHRbase.
    # Retorna None se o código LOINC não for um sinal vital suportado.
    # ------------------------------------------------------------------
    composition = build_openehr_composition(fhir_obs, practitioner_info)
    if composition is None:
        loinc = fhir_obs.get('code', {}).get('coding', [{}])[0].get('code', 'desconhecido')
        logger.warning(
            f"[INTEGRAÇÃO] Observation/{obs_id} tem código LOINC '{loinc}' "
            f"que não está no mapa de sinais vitais. A ignorar."
        )
        return {
            "status": "ignorado",
            "observation_id": obs_id,
            "loinc": loinc,
            "mensagem": f"Código LOINC '{loinc}' não é um sinal vital suportado.",
            "sinais_suportados": list(MAPA_SINAIS_VITAIS.keys())
        }

    # ------------------------------------------------------------------
    # Desafio Extra — Validar a Composição openEHR contra o Template
    # A validação é não bloqueante: se o endpoint não existir (405) ou
    # se a ligação falhar, regista um aviso e continua para a submissão.
    # Só bloqueia se o EHRbase confirmar explicitamente que a composição
    # é inválida (HTTP 4xx com corpo de erro detalhado).
    # ------------------------------------------------------------------
    is_valid, validation_msg = validar_composicao_openehr(ehr_id, composition)
    if not is_valid:
        logger.warning(
            f"[INTEGRAÇÃO] Aviso de validação para Observation/{obs_id}: {validation_msg}. "
            f"A continuar para submissão — o EHRbase fará a validação final."
        )

    # ------------------------------------------------------------------
    # Passo 6 — Submeter a Composição ao EHRbase
    # POST /ehr/{ehr_id}/composition com o Canonical JSON.
    # O EHRbase valida contra o template .opt e persiste se válida.
    # O header 'Prefer: return=representation' pede ao EHRbase que retorne
    # a composição criada com o seu UID atribuído.
    # ------------------------------------------------------------------
    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation"
        }
        response = requests.post(
            f"{EHRBASE_URL}/ehr/{ehr_id}/composition",
            json=composition,
            headers=headers,
            auth=EHR_AUTH,
            timeout=15
        )

        if response.status_code in [200, 201]:
            # UID único atribuído pelo EHRbase à composição persistida
            comp_uid = response.json().get("uid", {}).get("value", "desconhecido")
            logger.info(
                f"[INTEGRAÇÃO] ✅ Composição submetida com sucesso! "
                f"UID: {comp_uid} | EHR: {ehr_id} | Utente SNS: {numero_utente}"
            )
            return {
                "status": "ok",
                "observation_id": obs_id,
                "ehr_id": ehr_id,
                "composition_uid": comp_uid,
                "numero_utente_sns": numero_utente,
                "profissional": nome_medico
            }
        else:
            # EHRbase retorna detalhes do erro no corpo da resposta
            logger.error(
                f"[INTEGRAÇÃO] EHRbase respondeu HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            return {
                "status": "erro",
                "observation_id": obs_id,
                "http_status": response.status_code,
                "mensagem": f"EHRbase rejeitou a composição: {response.text[:200]}"
            }

    except requests.exceptions.RequestException as e:
        logger.error(f"[INTEGRAÇÃO] Erro de rede ao submeter composição ao EHRbase: {e}")
        return {
            "status": "erro",
            "observation_id": obs_id,
            "mensagem": f"Erro de ligação ao EHRbase: {e}"
        }



# =============================================================================
# SECÇÃO 10: MECANISMO DE GATILHO — FHIR Subscription (Fase 3)
# =============================================================================
#
# Implementação da Opção A do enunciado: FHIR Subscription R4 (REST-hook).
#
# Fluxo de funcionamento:
#   1. No arranque do serviço, é criada automaticamente uma FHIR Subscription
#      no HAPI FHIR (ver função registar_subscription_fhir, Secção 17).
#   2. A Subscription configura o HAPI FHIR para enviar um POST HTTP ao
#      endpoint /webhook/fhir-observation sempre que uma nova Observation é criada.
#   3. O endpoint recebe a notificação, delega o processamento para background
#      e responde imediatamente com HTTP 200 ao HAPI FHIR.
#
# Justificação da escolha (Opção A sobre Opção B):
#   A abordagem orientada a eventos (webhook) processa cada Observation de forma
#   imediata, sem latência associada a intervalos de polling. Adicionalmente,
#   não realiza pedidos periódicos ao servidor FHIR na ausência de dados novos,
#   resultando numa utilização mais eficiente dos recursos do sistema.
# =============================================================================

@app.post(
    "/webhook/fhir-observation",
    summary="Webhook FHIR Subscription — Receção de Observations (Opção A, REST-hook)",
    tags=["Fase 3 — Mecanismo de Gatilho"]
)
async def webhook_fhir_observation(payload: dict, background_tasks: BackgroundTasks):
    """
    Endpoint de Webhook que recebe notificações automáticas do HAPI FHIR.

    O HAPI FHIR envia um POST a este endpoint sempre que uma nova Observation
    é criada, graças à FHIR Subscription criada automaticamente no startup
    (ver função `registar_subscription_fhir`).

    O processamento é feito em background (BackgroundTasks) para que o serviço
    responda imediatamente com HTTP 200 ao HAPI FHIR. Se o processamento
    bloqueasse a resposta, o HAPI FHIR poderia considerar o webhook como falhado
    e tentar novamente, gerando processamento duplicado.

    O payload recebido pode ser:
      - Uma Observation FHIR direta (resourceType: "Observation")
      - Um Bundle de notificação com a Observation dentro (resourceType: "Bundle")
    """
    resource_type = payload.get("resourceType", "desconhecido")
    logger.info(f"[WEBHOOK] Notificação recebida do HAPI FHIR. resourceType: '{resource_type}'")

    if resource_type == "Observation":
        # O HAPI FHIR enviou uma Observation diretamente → processa em background
        background_tasks.add_task(processar_observation, payload)
        return {
            "status": "aceite",
            "mensagem": "Observation recebida e enviada para processamento em background."
        }

    elif resource_type == "Bundle":
        # O HAPI FHIR pode enviar um Bundle de notificação contendo a Observation
        entries = payload.get("entry", [])
        count = 0
        for entry in entries:
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Observation":
                background_tasks.add_task(processar_observation, resource)
                count += 1
        logger.info(f"[WEBHOOK] {count} Observation(ões) extraídas do Bundle e enviadas para processamento.")
        return {
            "status": "aceite",
            "mensagem": f"{count} Observation(ões) recebidas no Bundle e enviadas para processamento."
        }

    else:
        # Tipo de recurso não tratado por este webhook
        logger.warning(f"[WEBHOOK] Tipo de recurso não suportado: '{resource_type}'")
        return {
            "status": "ignorado",
            "mensagem": f"O tipo de recurso '{resource_type}' não é processado por este webhook."
        }


# =============================================================================
# SECÇÃO 11: SUPORTE A FHIR BUNDLE
# =============================================================================
#
# Um FHIR Bundle permite enviar múltiplos recursos numa única mensagem HTTP.
# O caso de uso típico é o envio simultâneo de vários sinais vitais recolhidos
# numa mesma consulta (ex: temperatura, SpO2 e frequência cardíaca num único
# pedido, em vez de N pedidos individuais).
#
# O endpoint valida o código LOINC de cada Observation contida no Bundle,
# processa as válidas em background e retorna um relatório de execução.
# =============================================================================

def _get_current_user_sync(token: str) -> str:
    """
    Versão síncrona da verificação do token JWT.
    Necessária para usar Depends em contextos lambda (ex: endpoint /Bundle).
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Token JWT inválido ou expirado.")


@app.post(
    "/Bundle",
    summary="Processar FHIR Bundle com múltiplas Observations",
    tags=["FHIR — Bundle"]
)
async def processar_bundle(
    bundle: dict,
    background_tasks: BackgroundTasks,
    user: str = Depends(lambda token=Depends(oauth2_scheme): _get_current_user_sync(token))
):
    """
    Processa um FHIR Bundle contendo múltiplas Observations de uma só vez.

    Para cada Observation dentro do Bundle:
      1. Verifica se o código LOINC está nos sinais vitais suportados (MAPA_SINAIS_VITAIS)
      2. Se válido → envia para processamento em background via processar_observation()
      3. Se inválido → marca como 'ignorado' e continua

    Retorna um relatório detalhado de cada entry processada.
    Requer autenticação JWT (Bearer Token).

    Exemplo de Bundle com 2 observações:
    ```json
    {
      "resourceType": "Bundle",
      "type": "transaction",
      "entry": [
        {"resource": {"resourceType": "Observation", "code": {"coding": [{"code": "8310-5"}]}, ...}},
        {"resource": {"resourceType": "Observation", "code": {"coding": [{"code": "59408-5"}]}, ...}}
      ]
    }
    ```
    """
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(
            status_code=400,
            detail="O corpo do pedido deve ser um recurso FHIR do tipo 'Bundle'."
        )

    entries = bundle.get("entry", [])
    if not entries:
        raise HTTPException(status_code=400, detail="O Bundle está vazio (sem entries).")

    processadas = 0
    ignoradas = 0
    resultados = []

    for i, entry in enumerate(entries):
        resource = entry.get("resource", {})
        rt = resource.get("resourceType")

        if rt != "Observation":
            # Ignorar recursos que não sejam Observations (ex: Patient, Encounter no mesmo Bundle)
            ignoradas += 1
            resultados.append({
                "entry_index": i,
                "status": "ignorado",
                "motivo": f"Tipo '{rt}' não é Observation."
            })
            continue

        # Verificar se o código LOINC corresponde a um sinal vital suportado
        try:
            loinc = resource.get('code', {}).get('coding', [{}])[0].get('code')
        except (IndexError, KeyError):
            loinc = None

        if not loinc or loinc not in MAPA_SINAIS_VITAIS:
            ignoradas += 1
            resultados.append({
                "entry_index": i,
                "status": "ignorado",
                "motivo": f"Código LOINC '{loinc}' não é um sinal vital suportado.",
                "sinais_suportados": list(MAPA_SINAIS_VITAIS.keys())
            })
            continue

        # Observation válida → processa em background
        background_tasks.add_task(processar_observation, resource)
        processadas += 1
        resultados.append({
            "entry_index": i,
            "status": "aceite",
            "observation_id": resource.get("id", "sem-id"),
            "loinc": loinc,
            "sinal_vital": MAPA_SINAIS_VITAIS[loinc]["nome"]
        })

    logger.info(
        f"[BUNDLE] {processadas} aceites, {ignoradas} ignoradas de {len(entries)} entries."
    )
    return {
        "status": "ok",
        "total_entries": len(entries),
        "processadas": processadas,
        "ignoradas": ignoradas,
        "detalhes": resultados
    }


# =============================================================================
# SECÇÃO 12: AUTENTICAÇÃO JWT — Endpoints de Autenticação
# =============================================================================
#
# Todos os endpoints FHIR (/Patient, /Practitioner, /Encounter, /Observation, /Bundle)
# requerem um Bearer Token JWT válido no cabeçalho Authorization.
# O endpoint /webhook/fhir-observation está isento de autenticação, dado que é
# invocado pelo servidor HAPI FHIR através da rede interna do Docker.
# =============================================================================

def create_access_token(data: dict) -> str:
    """
    Cria um token JWT assinado com os dados fornecidos e uma data de expiração.
    O token é assinado com SECRET_KEY usando o algoritmo HS256 (HMAC-SHA256).
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/token", summary="Obter Token JWT de Autenticação", tags=["Autenticação"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Endpoint de login. Valida as credenciais e retorna um Bearer Token JWT.

    Credenciais de acesso: username='admin', password='1234'

    O token deve ser incluído em todos os pedidos protegidos:
      Header: Authorization: Bearer <access_token>
    """
    if form_data.username == "admin" and form_data.password == "1234":
        access_token = create_access_token(data={"sub": form_data.username})
        logger.info(f"Login bem-sucedido para o utilizador '{form_data.username}'.")
        return {"access_token": access_token, "token_type": "bearer"}
    logger.warning(f"Tentativa de login falhada para '{form_data.username}'.")
    raise HTTPException(status_code=401, detail="Credenciais inválidas.")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependência FastAPI: verifica e descodifica o token JWT em cada pedido protegido.
    Retorna HTTP 401 automaticamente se o token for inválido ou expirado.
    """
    return _get_current_user_sync(token)


# =============================================================================
# SECÇÃO 13: ENDPOINTS FHIR — PATIENT
# =============================================================================

@app.post("/Patient", summary="Criar Paciente", tags=["FHIR — Recursos"])
async def post_paciente(data: PatientSchema, user: str = Depends(get_current_user)):
    """
    Regista um novo paciente na BD local (PostgreSQL) e no servidor HAPI FHIR.

    O recurso FHIR Patient é criado com o Nº de Utente SNS no campo 'identifier',
    permitindo a ligação ao EHRbase. Requer autenticação JWT.

    Usa upsert (ON CONFLICT DO UPDATE): se o Nº de Utente SNS já existir na BD
    (situação típica após reinício do Docker quando o HAPI FHIR perde os dados),
    o registo é atualizado e re-sincronizado com o HAPI FHIR em vez de devolver erro.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # UPSERT: INSERT ou UPDATE se o numero_sns já existir (evita erro de chave duplicada
        # após reinício do Docker em que o HAPI FHIR perde dados mas o PostgreSQL os mantém)
        cur.execute(
            "INSERT INTO pacientes (numero_sns, nome, genero, telecom, contacto) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (numero_sns) DO UPDATE SET "
            "  nome=EXCLUDED.nome, genero=EXCLUDED.genero, "
            "  telecom=EXCLUDED.telecom, contacto=EXCLUDED.contacto "
            "RETURNING id",
            (data.numero_sns, data.nome, data.genero,
             json.dumps([t.dict() for t in data.telecom]),
             json.dumps([c.dict() for c in data.contacto]))
        )
        new_id = cur.fetchone()[0]
        fhir_p = to_fhir_patient(new_id, data)
        # PUT em vez de POST: usamos o ID já conhecido (pat-{new_id}) em vez de deixar o FHIR gerar um
        response = requests.put(f"{HAPI_URL}/Patient/pat-{new_id}", json=fhir_p, timeout=5)
        response.raise_for_status()
        conn.commit()
        logger.info(f"Paciente registado/atualizado: pat-{new_id} (SNS: {data.numero_sns})")
        return fhir_p
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no FHIR ao criar paciente: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na BD: {str(e)}")
    finally:
        cur.close(); conn.close()


@app.get("/Patient", summary="Pesquisar Pacientes", tags=["FHIR — Recursos"])
async def search_patient(
    name: str = Query(None, description="Pesquisar por parte do nome"),
    user: str = Depends(get_current_user)
):
    """Pesquisa pacientes no HAPI FHIR por nome. Requer autenticação JWT."""
    try:
        params = {"name": name} if name else {}
        response = requests.get(f"{HAPI_URL}/Patient", params=params, timeout=5)
        response.raise_for_status()
        bundle = response.json()
        if bundle.get("total") == 0:
            return {"message": f"Nenhum paciente encontrado com o nome '{name}'.", "bundle": bundle}
        return bundle
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HAPI FHIR inacessível: {str(e)}")


@app.get("/Patient/{id}", summary="Obter Paciente por ID", tags=["FHIR — Recursos"])
async def get_patient(id: str, user: str = Depends(get_current_user)):
    """Obtém um paciente pelo ID local (ex: '1' para buscar 'pat-1'). Requer autenticação JWT."""
    try:
        response = requests.get(f"{HAPI_URL}/Patient/pat-{id}", timeout=5)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Paciente com ID '{id}' não encontrado no FHIR.")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HAPI FHIR inacessível: {str(e)}")


# =============================================================================
# SECÇÃO 14: ENDPOINTS FHIR — PRACTITIONER
# =============================================================================

@app.post("/Practitioner", summary="Criar Profissional de Saúde", tags=["FHIR — Recursos"])
async def post_practitioner(data: PractitionerSchema, user: str = Depends(get_current_user)):
    """
    Regista um profissional de saúde na BD local e no HAPI FHIR.
    A cédula profissional é incluída no campo 'identifier' do recurso FHIR.
    Requer autenticação JWT.

    Usa upsert (ON CONFLICT DO UPDATE): se a cédula já existir na BD local,
    o registo é atualizado e re-sincronizado com o HAPI FHIR em vez de devolver erro.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # UPSERT: INSERT ou UPDATE se a cedula já existir (evita erro de chave duplicada
        # após reinício do Docker em que o HAPI FHIR perde dados mas o PostgreSQL os mantém)
        cur.execute(
            "INSERT INTO profissionais (cedula, nome, especialidade) VALUES (%s, %s, %s) "
            "ON CONFLICT (cedula) DO UPDATE SET "
            "  nome=EXCLUDED.nome, especialidade=EXCLUDED.especialidade "
            "RETURNING id",
            (data.cedula, data.nome, data.especialidade)
        )
        new_id = cur.fetchone()[0]
        fhir_prac = to_fhir_practitioner(new_id, data)
        response = requests.put(f"{HAPI_URL}/Practitioner/prac-{new_id}", json=fhir_prac, timeout=5)
        response.raise_for_status()
        conn.commit()
        logger.info(f"Profissional registado/atualizado: prac-{new_id} (cédula: {data.cedula})")
        return fhir_prac
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no FHIR ao criar Practitioner: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na BD: {str(e)}")
    finally:
        cur.close(); conn.close()


@app.get("/Practitioner", summary="Pesquisar Profissionais", tags=["FHIR — Recursos"])
async def search_practitioner(
    especialidade: str = Query(None, description="Filtrar por especialidade"),
    nome: str = Query(None, description="Filtrar por parte do nome"),
    user: str = Depends(get_current_user)
):
    """
    Pesquisa profissionais na BD local PostgreSQL (mais eficiente que o FHIR).
    Suporta filtros por especialidade e/ou nome. Requer autenticação JWT.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        query = "SELECT id, nome, especialidade FROM profissionais WHERE 1=1"
        params = []
        if especialidade:
            query += " AND especialidade ILIKE %s"; params.append(f"%{especialidade}%")
        if nome:
            query += " AND nome ILIKE %s"; params.append(f"%{nome}%")
        cur.execute(query, tuple(params))
        resultados = cur.fetchall()
        if not resultados:
            return {"message": "Nenhum profissional encontrado.", "resultados": []}
        return {"total": len(resultados), "nota": "Pesquisa via BD local", "resultados": resultados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno na BD: {str(e)}")
    finally:
        cur.close(); conn.close()


@app.get("/Practitioner/{id}", summary="Obter Profissional por ID", tags=["FHIR — Recursos"])
async def get_practitioner(id: str, user: str = Depends(get_current_user)):
    """Obtém um profissional pelo ID local (ex: '1' para buscar 'prac-1'). Requer autenticação JWT."""
    try:
        response = requests.get(f"{HAPI_URL}/Practitioner/prac-{id}", timeout=5)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Profissional com ID '{id}' não encontrado no FHIR.")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HAPI FHIR inacessível: {str(e)}")


# =============================================================================
# SECÇÃO 15: ENDPOINTS FHIR — ENCOUNTER
# =============================================================================

@app.post("/Encounter", summary="Criar Consulta Clínica", tags=["FHIR — Recursos"])
async def post_encounter(data: EncounterSchema, user: str = Depends(get_current_user)):
    """Regista uma consulta na BD local e no HAPI FHIR. Requer autenticação JWT."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO encontros (paciente_id, practitioner_id, status, classe) VALUES (%s,%s,%s,%s) RETURNING id",
            (data.paciente_id, data.practitioner_id, data.status, data.classe_code)
        )
        new_id = cur.fetchone()[0]
        fhir_enc = to_fhir_encounter(new_id, data)
        response = requests.put(f"{HAPI_URL}/Encounter/enc-{new_id}", json=fhir_enc, timeout=5)
        response.raise_for_status()
        conn.commit()
        return fhir_enc
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no FHIR ao criar Encounter: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na BD: {str(e)}")
    finally:
        cur.close(); conn.close()


@app.get("/Encounter", summary="Pesquisar Consultas", tags=["FHIR — Recursos"])
async def search_encounters(
    patient: str = Query(None, description="ID local do paciente"),
    status: str = Query(None, description="Estado (planned, finished, etc.)"),
    user: str = Depends(get_current_user)
):
    """Pesquisa Encounters no HAPI FHIR por paciente e/ou estado. Requer autenticação JWT."""
    try:
        params = {}
        if patient: params["patient"] = f"pat-{patient}"
        if status:  params["status"] = status
        response = requests.get(f"{HAPI_URL}/Encounter", params=params, timeout=5)
        response.raise_for_status()
        bundle = response.json()
        if bundle.get("total") == 0:
            return {"message": "Nenhuma consulta encontrada.", "bundle": bundle}
        return bundle
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HAPI FHIR inacessível: {str(e)}")


@app.get("/Encounter/{id}", summary="Obter Consulta por ID", tags=["FHIR — Recursos"])
async def get_encounter(id: str, user: str = Depends(get_current_user)):
    """Obtém uma consulta pelo ID local (ex: '1' para buscar 'enc-1'). Requer autenticação JWT."""
    try:
        response = requests.get(f"{HAPI_URL}/Encounter/enc-{id}", timeout=5)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Consulta com ID '{id}' não encontrada no FHIR.")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HAPI FHIR inacessível: {str(e)}")


# =============================================================================
# SECÇÃO 16: ENDPOINTS FHIR — OBSERVATION
# =============================================================================

@app.post("/Observation", summary="Criar Observation (Sinal Vital)", tags=["FHIR — Recursos"])
async def post_observation(data: ObservationSchema, user: str = Depends(get_current_user)):
    """
    Regista uma Observation na BD local e no HAPI FHIR.

    Após o registo no FHIR, o HAPI FHIR notificará automaticamente este serviço
    via Webhook (FHIR Subscription), que chamará processar_observation() para
    converter e guardar a observação no EHRbase. Requer autenticação JWT.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO observacoes (estado, codigo, referencia, dataExecucao, medicao) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (data.estado, json.dumps(data.codigo), data.referencia,
             data.dataExecucao, json.dumps(data.medicao.dict()))
        )
        new_id = cur.fetchone()[0]
        fhir_obs = to_fhir_observation(new_id, data)
        fhir_obs["id"] = f"obs-{new_id}"
        response = requests.post(f"{HAPI_URL}/Observation", json=fhir_obs, timeout=5)
        response.raise_for_status()
        conn.commit()
        logger.info(f"Observation criada: obs-{new_id} — o HAPI FHIR irá notificar o webhook.")
        return fhir_obs
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no FHIR ao criar Observation: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na BD: {str(e)}")
    finally:
        cur.close(); conn.close()


@app.get("/Observation", summary="Pesquisar Observations por Paciente", tags=["FHIR — Recursos"])
async def get_obs(
    patient: str = Query(..., description="ID do paciente na BD local (ex: '1')"),
    user: str = Depends(get_current_user)
):
    """Retorna todas as Observations de um paciente no HAPI FHIR. Requer autenticação JWT."""
    try:
        response = requests.get(f"{HAPI_URL}/Observation", params={"patient": f"pat-{patient}"}, timeout=5)
        response.raise_for_status()
        bundle = response.json()
        if bundle.get("total") == 0:
            return {"message": "Nenhuma observação encontrada para este paciente.", "bundle": bundle}
        return bundle
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HAPI FHIR inacessível: {str(e)}")


@app.get("/Observation/{id}", summary="Obter Observation por ID", tags=["FHIR — Recursos"])
async def get_observation_by_id(id: str, user: str = Depends(get_current_user)):
    """Obtém uma Observation pelo ID local (ex: '1' para buscar 'obs-1'). Requer autenticação JWT."""
    try:
        response = requests.get(f"{HAPI_URL}/Observation/obs-{id}", timeout=5)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Observation com ID '{id}' não encontrada no FHIR.")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HAPI FHIR inacessível: {str(e)}")


# =============================================================================
# SECÇÃO 17: STARTUP — Inicialização Automática do Serviço
# =============================================================================
#
# No arranque, o serviço executa automaticamente 3 tarefas:
#   1. Upload do template openEHR (.opt) para o EHRbase
#   2. Verificação de conectividade com o HAPI FHIR
#   3. Criação automática da FHIR Subscription no HAPI FHIR (Fase 3)
#
# A criação automática da Subscription é o que torna o Webhook "auto-configurável":
# sem ela, seria necessário criar a Subscription manualmente no Postman a cada
# reinício do ambiente Docker.
# =============================================================================

@app.on_event("startup")
async def on_startup():
    """
    Rotina de inicialização executada automaticamente quando a API arranca.
    Coordena o upload do template, verificação do FHIR e registo do webhook.
    """
    await carregar_template_ehrbase()
    await verificar_hapi_fhir()
    await registar_subscription_fhir()


async def carregar_template_ehrbase():
    """
    Faz o upload automático do template openEHR (.opt) para o EHRbase.

    O template define a estrutura que o EHRbase espera nas Composições.
    Sem ele, o EHRbase rejeita todas as submissões com HTTP 404.

    Mecanismo de resiliência: tenta até 20 vezes com 5s de espera entre tentativas
    (~100s no total). Necessário porque o EHRbase demora 20-60s a inicializar
    após o Docker arrancar.

    Códigos HTTP esperados:
      201 Created  → template carregado com sucesso (primeira vez)
      409 Conflict → template já existe (rearranque) → não é erro
    """
    nome_ficheiro = "sinais_vitais_tp2.opt"
    url = f"{EHRBASE_URL}/definition/template/adl1.4"
    headers = {"Accept": "application/xml", "Content-Type": "application/xml"}

    logger.info("--- [STARTUP] A carregar template openEHR para o EHRbase ---")

    if not os.path.exists(nome_ficheiro):
        logger.error(f"❌ Ficheiro '{nome_ficheiro}' não encontrado. Template NÃO carregado.")
        return

    with open(nome_ficheiro, "r", encoding="utf-8") as f:
        template_xml = f.read()

    for tentativa in range(1, 21):
        try:
            response = requests.post(
                url, data=template_xml.encode('utf-8'),
                headers=headers, auth=EHR_AUTH, timeout=10
            )
            if response.status_code in [200, 201]:
                logger.info("✅ [STARTUP] Template openEHR carregado com sucesso no EHRbase!")
                return
            elif response.status_code == 409:
                logger.info("ℹ️  [STARTUP] Template já existe no EHRbase (rearranque detectado).")
                return
            else:
                logger.warning(f"EHRbase HTTP {response.status_code}: {response.text[:200]}")
                return
        except requests.exceptions.ConnectionError:
            logger.warning(f"⏳ EHRbase ainda não disponível... (tentativa {tentativa}/20)")
            time.sleep(5)

    logger.error("❌ [STARTUP] EHRbase não ficou disponível. Template não foi carregado.")


async def verificar_hapi_fhir():
    """
    Verifica conectividade com o HAPI FHIR ao arrancar, usando o endpoint
    /metadata (CapabilityStatement — health-check padrão de servidores FHIR).
    Um aviso aqui não é crítico; o webhook ficará ativo assim que o FHIR ficar online.
    """
    logger.info("--- [STARTUP] A verificar servidor HAPI FHIR ---")
    try:
        res = requests.get(f"{HAPI_URL}/metadata", timeout=5)
        if res.status_code == 200:
            logger.info(f"✅ [STARTUP] HAPI FHIR online e pronto. ({HAPI_URL})")
        else:
            logger.warning(f"⚠️  HAPI FHIR respondeu HTTP {res.status_code}.")
    except Exception as e:
        logger.warning(f"⚠️  HAPI FHIR não disponível no arranque: {e}")


async def registar_subscription_fhir():
    import asyncio
    """
    Cria automaticamente uma FHIR Subscription R4 no HAPI FHIR (Fase 3).

    A Subscription configura o HAPI FHIR para enviar um POST HTTP ao nosso
    endpoint /webhook/fhir-observation sempre que uma nova Observation é criada.
    Este é o mecanismo central da Opção A (REST-hook) do enunciado.

    Fluxo:
      1. Pesquisa se já existe uma Subscription ativa com o nosso endpoint
         → GET /fhir/Subscription?channel.endpoint={WEBHOOK_URL}
      2. Se já existir → não cria duplicado
      3. Se não existir → cria nova Subscription via POST /fhir/Subscription

    A Subscription usa:
      - criteria: "Observation?" → notifica para qualquer nova Observation
      - channel.type: "rest-hook" → envia HTTP POST (webhook)
      - channel.endpoint: WEBHOOK_URL → o nosso endpoint de webhook
      - channel.payload: "application/fhir+json" → formato JSON FHIR
    """
    logger.info("--- [STARTUP] A registar FHIR Subscription no HAPI FHIR ---")
    # ==========================================================
    # 3. VERIFICAR E CRIAR FHIR SUBSCRIPTION NO HAPI FHIR
    # ==========================================================
    logger.info("--- Verificando Servidor FHIR ---")
    hapi_is_up = False
    for attempt in range(1, 31):
        try:
            check = requests.get(f"{HAPI_URL}/metadata", timeout=5)
            if check.status_code == 200:
                hapi_is_up = True
                logger.info("SUCESSO: HAPI FHIR está online!")
                break
        except requests.exceptions.RequestException:
            pass
        
        logger.warning(f" Aguardando HAPI FHIR... (Tentativa {attempt}/30)")
        await asyncio.sleep(5)
        
    if not hapi_is_up:
        logger.error("❌ HAPI FHIR não ficou online. Webhook não registado.")
        return

    # Verificar se a Subscription já existe (para evitar duplicados em rearranques)
    try:
        check = requests.get(
            f"{HAPI_URL}/Subscription",
            params={"channel.endpoint": WEBHOOK_URL},
            timeout=5
        )
        if check.status_code == 200:
            bundle = check.json()
            if bundle.get("total", 0) > 0:
                logger.info(
                    f"ℹ️  [STARTUP] FHIR Subscription já existe para '{WEBHOOK_URL}'. "
                    f"Nenhuma ação necessária."
                )
                return
    except Exception as e:
        logger.warning(f"⚠️  Não foi possível verificar Subscriptions existentes: {e}")

    # Criar a Subscription no HAPI FHIR
    subscription = {
        "resourceType": "Subscription",
        "status": "active",
        "reason": "Notificação automática de novas Observations para o serviço de integração (TP02)",
        "criteria": "Observation?",   # critério: qualquer nova Observation
        "channel": {
            "type": "rest-hook",           # tipo: webhook HTTP POST
            "endpoint": WEBHOOK_URL,       # URL do nosso endpoint de webhook
            "payload": "application/fhir+json"  # formato do payload enviado
        }
    }

    try:
        response = requests.post(f"{HAPI_URL}/Subscription", json=subscription, timeout=10)
        if response.status_code in [200, 201]:
            sub_id = response.json().get("id", "desconhecido")
            logger.info(
                f"✅ [STARTUP] FHIR Subscription criada com sucesso! "
                f"ID: {sub_id} | Endpoint: {WEBHOOK_URL}"
            )
        else:
            logger.warning(
                f"⚠️  HAPI FHIR respondeu HTTP {response.status_code} ao criar Subscription: "
                f"{response.text[:300]}"
            )
    except requests.exceptions.ConnectionError:
        logger.warning(
            "⚠️  [STARTUP] HAPI FHIR não disponível para criar Subscription. "
            "Cria-la manualmente no Postman se necessário."
        )
    except Exception as e:
        logger.error(f"❌ [STARTUP] Erro ao criar FHIR Subscription: {e}")


# =============================================================================
# SECÇÃO 18: DESAFIO EXTRA — Operação Inversa
# =============================================================================

@app.get("/ehr/{ehr_id}/observations", tags=["Desafios Extra"])
async def recuperar_observacoes_fhir_por_ehr(ehr_id: str):
    """
    Operação Inversa: Dado um ehr_id no EHRbase, recupera as Observations correspondentes no HAPI FHIR.
    """
    # 1. Obter o EHR Status do EHRbase
    url_ehr = f"{EHRBASE_URL}/ehr/{ehr_id}/ehr_status"
    headers = {"Accept": "application/json"}
   
    try:
        ehr_res = requests.get(url_ehr, headers=headers, auth=EHR_AUTH, timeout=5)
        if ehr_res.status_code == 404:
            raise HTTPException(status_code=404, detail="EHR não encontrado no EHRbase.")
        ehr_res.raise_for_status()
        ehr_data = ehr_res.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao comunicar com EHRbase: {str(e)}")

    # 2. Extrair o Patient ID do FHIR guardado no EHRbase
    try:
        # Quando criámos o EHR, guardámos o fhir_patient_id no 'external_ref'
        fhir_patient_id = ehr_data["subject"]["external_ref"]["id"]["value"]
    except KeyError:
        raise HTTPException(status_code=400, detail="EHR encontrado, mas não tem ligação a um doente no FHIR (external_ref ausente).")
       
    # 3. Pesquisar Observations no HAPI FHIR para este doente
    url_fhir = f"{HAPI_URL}/Observation?subject=Patient/{fhir_patient_id}"
    try:
        fhir_res = requests.get(url_fhir, timeout=5)
        fhir_res.raise_for_status()
        fhir_data = fhir_res.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao comunicar com HAPI FHIR: {str(e)}")
       
    observations = [entry.get("resource") for entry in fhir_data.get("entry", []) if entry.get("resource")]
   
    return {
        "status": "sucesso",
        "ehr_id": ehr_id,
        "fhir_patient_id": fhir_patient_id,
        "total_observations": len(observations),
        "observations": observations
    }


@app.on_event("shutdown")
async def on_shutdown():
    """Rotina de encerramento — reservada para limpeza de recursos futura."""
    logger.info("[SHUTDOWN] Serviço de integração encerrado.")
