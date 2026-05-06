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
HAPI_URL = "http://localhost:9090/fhir"
EHRBASE_URL = "http://localhost:8082/ehrbase/rest/openehr/v1"


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

HAPI_URL = "http://localhost:9090/fhir"

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
    
    if not os.path.exists(nome_ficheiro):
        print(f" Ficheiro '{nome_ficheiro}' não encontrado.")
        return

    try:
        # Ler o conteúdo do ficheiro XML
        with open(nome_ficheiro, "r", encoding="utf-8") as file:
            template_xml = file.read()

        # Preparar os cabeçalhos (Postman)
        headers = {
            "Accept": "application/xml",
            "Content-Type": "application/xml"
        }
        
        # Fazer o pedido POST ao EHRbase
        url = f"{EHRBASE_URL}/definition/template/adl1.4"
        print(f"A comunicar com EHRbase para carregar template...")
        
        response = requests.post(url, data=template_xml.encode('utf-8'), headers=headers)
        
        # Resposta
        if response.status_code == 201:
            print(" SUCESSO: Template openEHR carregado automaticamente no EHRbase!")
        elif response.status_code == 409:
            # 409 Conflict significa que o template já lá está 
            print("INFO: O template já existe no EHRbase. Pronto a usar.")
        else:
            print(f"ERRO ao carregar template: {response.status_code} - {response.text}")

    except requests.exceptions.ConnectionError:
        print(" ERRO: Não foi possível conectar ao EHRbase na porta 8080.")
    except Exception as e:
        print(f" ERRO ao processar o template: {str(e)}")