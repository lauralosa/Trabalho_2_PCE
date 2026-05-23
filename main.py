from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel, Field 
from typing import List, Optional 
import psycopg2
import json
import requests
from psycopg2.extras import RealDictCursor
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt
from datetime import datetime, timedelta
from typing import List, Optional, Literal
import os
import requests
HAPI_URL = os.getenv("FHIR_SERVER_URL", "http://localhost:9090/fhir")

# Configurações EHRbase
EHRBASE_URL = os.getenv("EHRBASE_URL", "http://localhost:8085/ehrbase/rest/openehr/v1")
EHRBASE_USER = "admin-user"
EHRBASE_PASS = "RequirementPassword"
# Autenticação básica para o EHRbase
EHR_AUTH = (EHRBASE_USER, EHRBASE_PASS)


# ==========================================
# --- CONFIGURAÇÕES JWT ---
# ==========================================

SECRET_KEY = "pce_uminho_secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ================================================
# --- INICIALIZAÇÃO DA API E CONEXÕES EXTERNAS ---
# ===============================================

app = FastAPI(title="Middleware FHIR R4 - Universidade do Minho")

def get_db_connection():
    return psycopg2.connect(host="localhost", port="5432", database="clinica_db", user="user", password="password")


# ==========================================
# --- SCHEMAS DE VALIDAÇÃO ---
# ==========================================

class TelecomSchema(BaseModel):
    tipo: Literal["telemóvel", "telefone", "email"]
    valor: str = Field(..., pattern=r".+@.+\..+|[0-9]{7,15}")

class EnderecoSchema(BaseModel):
    tipo: str
    valor: str

class ContactoSchema(BaseModel):
    nome: str = Field(..., min_length=3)
    telecom: Optional[List[TelecomSchema]] = None
    endereco: Optional[List[EnderecoSchema]] = None

class PatientSchema(BaseModel):
    numero_sns: str = Field(..., description="Número de Utente do SNS") # NOVO CAMPO
    nome: str = Field(..., min_length=3)
    genero: Literal["m", "f", "masculino", "feminino", "male", "female"]
    telecom: List[TelecomSchema]
    contacto: List[ContactoSchema]

class PractitionerSchema(BaseModel):
    cedula: str = Field(..., description="Número de Cédula Profissional") # NOVO CAMPO
    nome: str = Field(..., min_length=3)
    especialidade: str = Field(..., min_length=2)

class EncounterSchema(BaseModel):
    paciente_id: int = Field(..., gt=0)
    practitioner_id: int = Field(..., gt=0)
    status: Literal["planned", "arrived", "triaged", "in-progress", "onleave", "finished", "cancelled"]
    classe_code: Literal["AMB", "EMER", "INT", "VR", "TLC"] 

class ObsMedicao(BaseModel):
    valor: float
    unidade: str
    sistema: str = "http://unitsofmeasure.org"
    code: str

class ObservationSchema(BaseModel):
    estado: Literal["registered", "preliminary", "final", "amended", "corrected"]
    codigo: dict
    referencia: str = Field(..., pattern=r"^Patient/pat-\d+$")
    dataExecucao: str
    medicao: ObsMedicao

# ==========================================
# --- FUNÇÕES DE MAPEAMENTO ---
# ==========================================

def to_fhir_patient(db_id, data):
    return {
        "resourceType": "Patient",
        "id": f"pat-{db_id}",
        "identifier": [{ # NOVO BLOCO
            "system": "https://www.sns.gov.pt/utente",
            "value": data.numero_sns
        }],
        "active": True,
        "name": [{"text": data.nome}],
        "gender": "male" if data.genero.lower() == "m" else "female",
        "telecom": [{"system": "phone" if t.tipo == "telemóvel" else "email", "value": t.valor} for t in data.telecom],
        "contact": [{"name": {"text": c.nome}} for c in data.contacto]
    }

def to_fhir_practitioner(db_id, data):
    return {
        "resourceType": "Practitioner",
        "id": f"prac-{db_id}",
        "identifier": [{ # NOVO BLOCO
            "system": "https://www.ordemdosmedicos.pt",
            "value": data.cedula
        }],
        "active": True,
        "name": [{"text": data.nome}],
        "qualification": [{"code": {"text": data.especialidade}}]
    }

def to_fhir_encounter(db_id, data):
    return {
        "resourceType": "Encounter",
        "id": f"enc-{db_id}",
        "status": data.status, # planned, finished, etc.
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": data.classe_code # AMB, EMER, etc.
        },
        "subject": {"reference": f"Patient/pat-{data.paciente_id}"},
        "participant": [{
            "individual": {"reference": f"Practitioner/prac-{data.practitioner_id}"}
        }]
    }

def to_fhir_observation(db_id, data):
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


# ==========================================
# --- TOKENS ---
# ==========================================


# Função para criar o Token
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Endpoint para o utilizador fazer login e receber o Token
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "admin" and form_data.password == "1234":
        access_token = create_access_token(data={"sub": form_data.username})
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

# Função que verifica se o token é válido
async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

# ==========================================
# --- ENDPOINTS: PATIENT ---
# ==========================================

@app.post("/Patient") 
async def post_paciente(data: PatientSchema, user: str = Depends(get_current_user)): 
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO pacientes (numero_sns, nome, genero, telecom, contacto) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (data.numero_sns, data.nome, data.genero, json.dumps([t.dict() for t in data.telecom]), json.dumps([c.dict() for c in data.contacto]))
        )
        new_id = cur.fetchone()[0]
        
        fhir_p = to_fhir_patient(new_id, data)
        response = requests.put(f"{HAPI_URL}/Patient/pat-{new_id}", json=fhir_p, timeout=5)
        response.raise_for_status()

        conn.commit()
        return fhir_p
    
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no servidor FHIR ao criar paciente: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na base de dados: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.get("/Patient")
async def search_patient(name: str = Query(None, description="Procurar por parte do nome (ex: Helena)"), user: str = Depends(get_current_user)):
    try:
        params = {}
        if name:
            params["name"] = name
            
        response = requests.get(f"{HAPI_URL}/Patient", params=params, timeout=5)
        response.raise_for_status()
        
        bundle = response.json()
        if bundle.get("total") == 0:
            return {"message": f"Nenhum paciente encontrado com o nome '{name}'.", "bundle": bundle}
            
        return bundle
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Servidor HAPI FHIR inacessível: {str(e)}")

@app.get("/Patient/{id}")
async def get_patient(id: str, user: str = Depends(get_current_user)):
    try:
        response = requests.get(f"{HAPI_URL}/Patient/pat-{id}", timeout=5)
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"O paciente com o ID {id} não existe no servidor FHIR.")
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Servidor HAPI FHIR inacessível: {str(e)}")


# ==========================================
# --- ENDPOINTS: PRACTITIONER ---
# ==========================================

@app.post("/Practitioner")
async def post_practitioner(data: PractitionerSchema, user: str = Depends(get_current_user)): 
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO profissionais (cedula, nome, especialidade) VALUES (%s, %s, %s) RETURNING id", 
                    (data.cedula, data.nome, data.especialidade))
        new_id = cur.fetchone()[0]

        fhir_prac = {
            "resourceType": "Practitioner",
            "id": f"prac-{new_id}", 
            "name": [{"text": data.nome}],
            "qualification": [{"code": {"text": data.especialidade}}]
        }
        response = requests.put(f"{HAPI_URL}/Practitioner/prac-{new_id}", json=fhir_prac, timeout=5)
        response.raise_for_status() 

        conn.commit()
        return fhir_prac
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no servidor FHIR ao criar Practitioner: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na base de dados: {str(e)}")
    finally:
        cur.close()
        conn.close()

        
@app.get("/Practitioner")
async def search_practitioner(
    especialidade: str = Query(None, description="Pesquisar por especialidade (ex: Medicina Geral)"),
    nome: str = Query(None, description="Pesquisar por parte do nome (ex: Rui)"), user: str = Depends(get_current_user)
):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor) 
    try:
        query = "SELECT id, nome, especialidade FROM profissionais WHERE 1=1"
        params = []
        
        if especialidade:
            query += " AND especialidade ILIKE %s"
            params.append(f"%{especialidade}%")
        if nome:
            query += " AND nome ILIKE %s"
            params.append(f"%{nome}%")
            
        cur.execute(query, tuple(params))
        resultados = cur.fetchall()
        
        if not resultados:
            return {"message": "Nenhum médico encontrado com esses critérios.", "resultados": []}
        
        return {
            "total": len(resultados), 
            "nota": "Pesquisa otimizada via Base de Dados Local",
            "resultados": resultados
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno na base de dados: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.get("/Practitioner/{id}")
async def get_practitioner(id: str, user: str = Depends(get_current_user)):
    try:
        response = requests.get(f"{HAPI_URL}/Practitioner/prac-{id}", timeout=5)
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"O médico com o ID {id} não existe no servidor FHIR.")
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Servidor HAPI FHIR inacessível: {str(e)}")

# ==========================================
# --- ENDPOINTS: ENCOUNTER ---
# ==========================================


@app.post("/Encounter")
async def post_encounter(data: EncounterSchema, user: str = Depends(get_current_user)): 

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO encontros (paciente_id, practitioner_id, status, classe) VALUES (%s, %s, %s, %s) RETURNING id",
                    (data.paciente_id, data.practitioner_id, data.status, data.classe_code))
        new_id = cur.fetchone()[0]

        fhir_enc = to_fhir_encounter(new_id, data)

        response = requests.put(f"{HAPI_URL}/Encounter/enc-{new_id}", json=fhir_enc, timeout=5)
        response.raise_for_status() 

        conn.commit()
        return fhir_enc
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no servidor FHIR ao criar Encounter: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na base de dados: {str(e)}")
    finally:
        cur.close(); 
        conn.close()

@app.get("/Encounter")
async def search_encounters(
    patient: str = Query(None, description="ID local do paciente (ex: 1)"),
    status: str = Query(None, description="Estado da consulta (ex: planned, finished)"), user: str = Depends(get_current_user)
):
    try:
        params = {}
        if patient:
            params["patient"] = f"pat-{patient}"
        if status:
            params["status"] = status
            
        response = requests.get(f"{HAPI_URL}/Encounter", params=params, timeout=5)
        response.raise_for_status()
        
        bundle = response.json()
        if bundle.get("total") == 0:
            return {"message": "Nenhum encontro encontrado com esses critérios.", "bundle": bundle}
            
        return bundle
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Servidor HAPI FHIR inacessível: {str(e)}")

@app.get("/Encounter/{id}")
async def get_encounter(id: str, user: str = Depends(get_current_user)):
    try:
        response = requests.get(f"{HAPI_URL}/Encounter/enc-{id}", timeout=5)
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"A consulta com o ID {id} não existe no servidor FHIR.")
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Servidor HAPI FHIR inacessível: {str(e)}")

# ==========================================
# --- ENDPOINTS: OBSERVATION ---
# ==========================================

@app.post("/Observation") 
async def post_observation(data: ObservationSchema, user: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO observacoes (estado, codigo, referencia, dataExecucao, medicao) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (data.estado, json.dumps(data.codigo), data.referencia, data.dataExecucao, json.dumps(data.medicao.dict()))
        )
        new_id = cur.fetchone()[0] 
        
        fhir_obs = to_fhir_observation(new_id, data)
        response = requests.put(f"{HAPI_URL}/Observation/obs-{new_id}", json=fhir_obs, timeout=5)
        response.raise_for_status() 

        conn.commit()
        return fhir_obs
    except requests.exceptions.RequestException as e:
        conn.rollback()
        detail = response.text if 'response' in locals() else str(e)
        raise HTTPException(status_code=502, detail=f"Erro no servidor FHIR ao criar Observation: {detail}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno na base de dados: {str(e)}")
    finally:
        cur.close(); 
        conn.close()

@app.get("/Observation")
async def get_obs(patient: str = Query(..., description="ID do paciente na BD local, ex: 1"), user: str = Depends(get_current_user)):
    try:
        params = {"patient": f"pat-{patient}"}
        response = requests.get(f"{HAPI_URL}/Observation", params=params, timeout=5)
        response.raise_for_status()
        
        bundle = response.json()
        if bundle.get("total") == 0:
            return {"message": "Nenhuma observação encontrada para este paciente no FHIR", "bundle": bundle}
            
        return bundle
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Servidor HAPI FHIR inacessível: {str(e)}")

@app.get("/Observation/{id}")
async def get_observation_by_id(id: str, user: str = Depends(get_current_user)):
    try:
        response = requests.get(f"{HAPI_URL}/Observation/obs-{id}", timeout=5)
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"A observação com o ID {id} não existe no servidor FHIR.")
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Servidor HAPI FHIR inacessível: {str(e)}")


MAPA_SINAIS_VITAIS = {
    "8480-6": {"nome": "Pressão arterial sistólica", "archetype": "openEHR-EHR-OBSERVATION.blood_pressure.v1", "node": "at0004"},
    "8462-4": {"nome": "Pressão arterial diastólica", "archetype": "openEHR-EHR-OBSERVATION.blood_pressure.v1", "node": "at0005"},
    "8867-4": {"nome": "Frequência cardíaca", "archetype": "openEHR-EHR-OBSERVATION.pulse.v1", "node": "at0004"},
    "8310-5": {"nome": "Temperatura corporal", "archetype": "openEHR-EHR-OBSERVATION.body_temperature.v1", "node": "at0004"},
    "59408-5": {"nome": "Saturação de oxigénio", "archetype": "openEHR-EHR-OBSERVATION.pulse_oximetry.v1", "node": "at0004"},
    "29463-7": {"nome": "Peso corporal", "archetype": "openEHR-EHR-OBSERVATION.body_weight.v1", "node": "at0004"},
    "9279-1": {"nome": "Frequência respiratória", "archetype": "openEHR-EHR-OBSERVATION.respiration.v1", "node": "at0004"}
}




def garantir_ehr(numero_utente: str, patient_fhir_id: str):
    """
    Verifica se existe EHR para o utente. Se não, cria-o com ligação bidirecional[cite: 54, 56].
    """
    # Consulta se já existe EHR para este subject_id [cite: 54]
    search_url = f"{EHRBASE_URL}/ehr?subject_id={numero_utente}&subject_namespace=pt.sns.utente"
    res = requests.get(search_url, auth=EHR_AUTH)
   
    if res.status_code == 200:
        return res.json()['ehr_id']['value']
   
    # Caso não exista, cria o EHR registando o Patient.id como externalId [cite: 55, 56]
    payload = {
        "_type": "EHR_STATUS",
        "subject": {
            "external_ref": {
                "id": {"_type": "GENERIC_ID", "value": patient_fhir_id, "scheme": "fhir"},
                "namespace": "pt.sns.utente",
                "type": "PERSON"
            }
        },
        "is_queryable": True,
        "is_modifiable": True
    }
    create_res = requests.post(f"{EHRBASE_URL}/ehr", json=payload, auth=EHR_AUTH)
    create_res.raise_for_status()
    return create_res.json()['ehr_id']['value']


def build_openehr_composition(fhir_obs: dict, practitioner_info: dict):
    """
    Mapeia Observation FHIR para Composição openEHR[cite: 36, 63].
    """
    # Extração do código LOINC [cite: 44]
    try:
        loinc = fhir_obs.get('code', {}).get('coding', [{}])[0].get('code')
    except (IndexError, KeyError):
        return None


    info = MAPA_SINAIS_VITAIS.get(loinc)
    if not info:
        return None


    composer = {
        "_type": "PARTY_IDENTIFIED", 
        "name": practitioner_info.get("nome", "Desconhecido")
    }
    if practitioner_info.get("cedula"):
        composer["external_ref"] = {
            "id": {"_type": "GENERIC_ID", "value": practitioner_info["cedula"], "scheme": practitioner_info.get("sistema", "fhir")},
            "namespace": "pt.ordem",
            "type": "PERSON"
        }

    # Estrutura Canonical JSON
    return {
        "_type": "COMPOSITION",
        "name": {"_type": "DV_TEXT", "value": "Sinais Vitais"},
        "archetype_details": {
            "archetype_id": "openEHR-EHR-COMPOSITION.encounter.v1",
            "template_id": "Sinais vitais", # Deve coincidir com o teu .opt
            "rm_version": "1.0.4"
        },
        "language": {"code_string": "pt", "terminology_id": {"value": "ISO_639-1"}},
        "territory": {"code_string": "PT", "terminology_id": {"value": "ISO_3166-1"}},
        "category": {"value": "event", "defining_code": {"terminology_id": {"value": "openehr"}, "code_string": "433"}},
        "composer": composer, # Requisito 4.3 [cite: 61]
        "content": [{
            "_type": "OBSERVATION",
            "name": {"_type": "DV_TEXT", "value": info["nome"]},
            "archetype_node_id": info["archetype"],
            "data": {
                "_type": "HISTORY",
                "name": {"_type": "DV_TEXT", "value": "history"},
                "origin": {"_type": "DV_DATE_TIME", "value": fhir_obs.get('effectiveDateTime')},
                "events": [{
                    "_type": "POINT_EVENT",
                    "name": {"_type": "DV_TEXT", "value": "any event"},
                    "time": {"_type": "DV_DATE_TIME", "value": fhir_obs.get('effectiveDateTime')},
                    "data": {
                        "_type": "ITEM_TREE",
                        "name": {"_type": "DV_TEXT", "value": "tree"},
                        "items": [{
                            "_type": "ELEMENT",
                            "name": {"_type": "DV_TEXT", "value": info["nome"]},
                            "archetype_node_id": info["node"],
                            "value": {
                                "_type": "DV_QUANTITY",
                                "magnitude": fhir_obs.get('valueQuantity', {}).get('value'),
                                "units": fhir_obs.get('valueQuantity', {}).get('unit')
                            }
                        }]
                    }
                }]
            }
        }]
    }


def obter_dados_medico_fhir(ref: str):
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
        print(f"Erro ao consultar Practitioner: {e}")
        pass
    return {"nome": "Erro ao consultar Practitioner", "cedula": None, "sistema": None}



# EXTRA
def validar_composicao_openehr(ehr_id: str, composition: dict):
    """
    Desafio Extra: Valida a Composição contra o Template (.opt) no EHRbase
    antes de a gravar efetivamente.
    """
    # O endpoint de validação segue a mesma estrutura da submissão, mas termina em /validate
    validate_url = f"{EHRBASE_URL}/ehr/{ehr_id}/composition/validate"
   
    try:
        # Enviamos a composição para teste
        res = requests.post(validate_url, json=composition, auth=EHR_AUTH)
       
        if res.status_code == 200:
            return True, "Composição válida conforme o Template."
        else:
            # O EHRbase devolve os erros específicos (ex: campo obrigatório em falta)
            return False, res.text
    except Exception as e:
        return False, f"Erro na ligação ao validador: {str(e)}"


#=========================================================
# Webhook (Subscription) para Observações
#=========================================================
@app.post("/webhook/fhir-observation")
async def receive_observation_webhook(observation: dict):
    print("--- [WEBHOOK] Recebida nova Observation ---")
    # 1. Processar Observation
    if observation.get("resourceType") != "Observation":
        print("[WEBHOOK] Ignorado: Não é uma Observation.")
        return {"status": "ignorado", "motivo": "Não é uma Observation"}
    
    # 2. Obter Patient ID do FHIR
    subject_ref = observation.get("subject", {}).get("reference", "")
    if not subject_ref.startswith("Patient/"):
        print("[WEBHOOK] Erro: Referência de Patient inválida.")
        raise HTTPException(status_code=400, detail="Referência de Patient inválida")
    
    patient_id = subject_ref.split("/")[1]
    
    # Obter os detalhes do Patient no FHIR para buscar o número SNS
    try:
        pat_res = requests.get(f"{HAPI_URL}/Patient/{patient_id}")
        pat_res.raise_for_status()
        patient_data = pat_res.json()
    except Exception as e:
        print(f"[WEBHOOK] Erro ao obter Patient do FHIR: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Falha ao obter Patient do FHIR: {str(e)}")
        
    numero_sns = None
    for ident in patient_data.get("identifier", []):
        if ident.get("system") == "https://www.sns.gov.pt/utente":
            numero_sns = ident.get("value")
            break
            
    if not numero_sns:
        print("[WEBHOOK] Erro: Paciente sem N.º de Utente (SNS).")
        raise HTTPException(status_code=400, detail="Paciente sem N.º de Utente (SNS)")
        
    # 3. Garantir EHR no EHRbase
    try:
        ehr_id = garantir_ehr(numero_sns, patient_id)
        print(f"[WEBHOOK] EHR ID garantido: {ehr_id}")
    except Exception as e:
        print(f"[WEBHOOK] Falha ao gerir EHR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Falha ao gerir EHR no EHRbase: {str(e)}")
        
    # 4. Obter Practitioner (Composer)
    performer_ref = None
    performers = observation.get("performer", [])
    if performers:
        performer_ref = performers[0].get("reference")
        
    practitioner_info = {"nome": "Desconhecido", "cedula": None, "sistema": None}
    if performer_ref:
        practitioner_info = obter_dados_medico_fhir(performer_ref)
        print(f"[WEBHOOK] Dados do Médico obtidos: {practitioner_info}")
        
    # 5. Mapear para Composição
    composition = build_openehr_composition(observation, practitioner_info)
    if not composition:
        print("[WEBHOOK] Ignorado: Código LOINC não suportado ou erro no mapeamento.")
        return {"status": "ignorado", "motivo": "Código LOINC não suportado"}
        
    # Validar (Opcional - Desafio Extra)
    is_valid, msg = validar_composicao_openehr(ehr_id, composition)
    if not is_valid:
        print(f"[WEBHOOK] Aviso de Validação openEHR: {msg}")
        
    # 6. Gravar Composição no EHRbase
    try:
        comp_url = f"{EHRBASE_URL}/ehr/{ehr_id}/composition"
        comp_res = requests.post(comp_url, json=composition, auth=EHR_AUTH)
        comp_res.raise_for_status()
        comp_id = comp_res.json().get('uid', {}).get('value')
        print(f"[WEBHOOK] SUCESSO: Composição gravada no EHRbase com ID: {comp_id}")
        return {"status": "sucesso", "ehr_id": ehr_id, "composition_id": comp_id}
    except Exception as e:
        print(f"[WEBHOOK] Falha ao gravar Composition: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Falha ao gravar Composition: {str(e)}")


#=========================================================
#Carrega o template Sinais vitais automaticamente
#=========================================================

@app.on_event("startup")
async def carregar_template_ehrbase():
    """
    Função que corre automaticamente quando a API liga.
    Lê o ficheiro .opt e faz o upload para o EHRbase.
    """
    nome_ficheiro = "sinais_vitais_tp2.opt"
    url = f"{EHRBASE_URL}/definition/template/adl1.4"
    
    print("--- Inicializando Serviço de Integração ---")

    # 1. TENTATIVA DE UPLOAD COM ESPERA (Resiliência)
    for i in range(20): # Tenta 20 vezes (aprox. 100 segundos)
        try:
            if os.path.exists(nome_ficheiro):
                with open(nome_ficheiro, "r", encoding="utf-8") as file:
                    template_xml = file.read()

                headers = {"Accept": "application/xml", "Content-Type": "application/xml"}
                response = requests.post(url, data=template_xml.encode('utf-8'), headers=headers, auth=EHR_AUTH)

                if response.status_code in [200, 201]:
                    print(" SUCESSO: Template openEHR carregado!")
                    break
                elif response.status_code == 409:
                    print("INFO: Template já existe no EHRbase.")
                    break
            else:
                print(f" Erro: Ficheiro '{nome_ficheiro}' não encontrado.")
                break
        except requests.exceptions.ConnectionError:
            print(f" Aguardando EHRbase... (Tentativa {i+1}/20)")
            import time
            time.sleep(5) # Espera 5 segundos antes de tentar outra vez

    # 2. VERIFICAÇÃO DO HAPI FHIR (Como a tua colega fez)
    print("--- Verificando Servidor FHIR ---")
    try:
        res = requests.get(f"{HAPI_URL}/metadata", timeout=3)
        if res.status_code == 200:
            print("HAPI FHIR: Online e pronto.") 
            
    except Exception:
        print("HAPI FHIR: Servidor offline.")
