from __future__ import annotations
"""
ehrbase_client.py — Comunicação direta com o EHRbase via AQL e REST.
Usado principalmente pelo Dashboard para consultar sinais vitais históricos.
"""
import requests
import os

# Porta 8085: corresponde ao mapeamento do docker-compose.yml (porta interna 8080 → local 8085)
# EHR_AUTH = None: o EHRbase está configurado com SECURITY_AUTHTYPE=none no docker-compose.yml,
# pelo que não requer autenticação HTTP Basic (igual ao que o backend define em main.py)
EHRBASE_URL = os.getenv("EHRBASE_URL_LOCAL", "http://localhost:8085/ehrbase/rest/openehr/v1")
EHR_AUTH = None

# Nomes legíveis para cada código LOINC — coincide com MAPA_SINAIS_VITAIS do main.py
MAPA_SINAIS_VITAIS = {
    "8480-6":  {"nome": "Pressão arterial sistólica",  "unidade": "mmHg", "emoji": "🩺"},
    "8462-4":  {"nome": "Pressão arterial diastólica", "unidade": "mmHg", "emoji": "🩺"},
    "8867-4":  {"nome": "Frequência cardíaca",          "unidade": "bpm",  "emoji": "❤️"},
    "8310-5":  {"nome": "Temperatura corporal",         "unidade": "°C",   "emoji": "🌡️"},
    "59408-5": {"nome": "Saturação de oxigénio",        "unidade": "%",    "emoji": "💨"},
    "29463-7": {"nome": "Peso corporal",                "unidade": "kg",   "emoji": "⚖️"},
    "9279-1":  {"nome": "Frequência respiratória",      "unidade": "rpm",  "emoji": "🌬️"},
}


def get_ehr_by_subject(patient_fhir_id: str) -> dict | None:
    """
    Procura o EHR pelo FHIR Patient ID (ex: 'pat-1').

    O backend (main.py → garantir_ehr) cria o EHR com:
      subject_id        = patient_fhir_id  (ex: "pat-1")
      subject_namespace = "pt.sns.utente"

    Por isso o frontend tem de pesquisar com os mesmos valores.

    Args:
        patient_fhir_id: ID do recurso Patient no FHIR (ex: "pat-1")

    Returns:
        Dicionário com o EHR ou None se não existir / erro de ligação.
    """
    url = f"{EHRBASE_URL}/ehr"
    params = {
        "subject_id": patient_fhir_id,         # ex: "pat-1" — igual ao que o backend gravou
        "subject_namespace": "pt.sns.utente",  # namespace definido em garantir_ehr()
    }
    try:
        r = requests.get(url, params=params, auth=EHR_AUTH, timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except requests.exceptions.ConnectionError:
        return None


def get_composicoes_por_ehr(ehr_id: str) -> list:
    """
    Retorna todas as composições (registos de sinais vitais) de um EHR.
    Usa a API REST do EHRbase para listar composições.
    """
    url = f"{EHRBASE_URL}/ehr/{ehr_id}/composition"
    try:
        r = requests.get(url, auth=EHR_AUTH, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("entries", [])
        return []
    except Exception:
        return []


def query_sinais_vitais_aql(patient_fhir_id: str) -> list:
    """
    Executa uma query AQL no EHRbase para obter todos os sinais vitais
    de um utente identificado pelo FHIR Patient ID (ex: 'pat-1').

    O namespace 'pt.sns.utente' é o que o backend usa em garantir_ehr().

    Retorna uma lista de dicionários com os campos:
    - tipo (nome do sinal vital)
    - valor (float)
    - unidade (str)
    - data (str ISO 8601)
    - ehr_id (str)
    """
    # AQL: seleciona valor, unidade, data e nome do sinal vital.
    # Nota: os nós at0001/at0002/at0003/at0004 são os mais comuns nos arquétipos
    # suportados; o fallback para FHIR cobre os casos em que a AQL não retorne dados.
    aql = f"""
    SELECT
        obs/name/value                                                         AS tipo,
        obs/data[at0001]/events[at0002]/data[at0003]/items[at0004]/value/magnitude AS valor,
        obs/data[at0001]/events[at0002]/data[at0003]/items[at0004]/value/units      AS unidade,
        c/context/start_time/value                                             AS data,
        e/ehr_id/value                                                         AS ehr_id
    FROM EHR e
        CONTAINS COMPOSITION c
        CONTAINS OBSERVATION obs
    WHERE e/ehr_status/subject/external_ref/id/value = '{patient_fhir_id}'
      AND e/ehr_status/subject/external_ref/namespace = 'pt.sns.utente'
    ORDER BY c/context/start_time/value DESC
    LIMIT 200
    """

    url = f"{EHRBASE_URL}/query/aql"
    try:
        r = requests.post(
            url,
            json={"q": aql},
            auth=EHR_AUTH,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            result = r.json()
            rows = result.get("rows", [])
            cols = [col.get("name", f"col_{i}") for i, col in enumerate(result.get("columns", []))]
            # Converte para lista de dicts
            return [dict(zip(cols, row)) for row in rows]
        return []
    except Exception:
        return []


def get_sinais_vitais_fhir_proxy(numero_utente: str, hapi_url: str) -> list:
    """
    Alternativa ao AQL: busca os sinais vitais diretamente no HAPI FHIR
    filtrando por N.º de Utente SNS (via identifier).
    Útil quando o EHRbase ainda não tem dados mas o FHIR já tem.
    """
    try:
        # Primeiro, encontra o Patient pelo identifier SNS
        r = requests.get(
            f"{hapi_url}/Patient",
            params={"identifier": f"https://www.sns.gov.pt/utente|{numero_utente}"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        bundle = r.json()
        entries = bundle.get("entry", [])
        if not entries:
            return []

        patient_id = entries[0]["resource"]["id"]  # ex: "pat-1"

        # Busca Observations para este Patient
        obs_r = requests.get(
            f"{hapi_url}/Observation",
            params={"patient": patient_id},
            timeout=10,
        )
        if obs_r.status_code != 200:
            return []

        obs_bundle = obs_r.json()
        results = []
        for entry in obs_bundle.get("entry", []):
            resource = entry.get("resource", {})
            coding = resource.get("code", {}).get("coding", [{}])
            loinc_code = coding[0].get("code", "") if coding else ""
            info = MAPA_SINAIS_VITAIS.get(loinc_code, {})

            vq = resource.get("valueQuantity", {})
            results.append({
                "tipo": info.get("nome", resource.get("code", {}).get("text", "Desconhecido")),
                "valor": vq.get("value"),
                "unidade": vq.get("unit", info.get("unidade", "")),
                "data": resource.get("effectiveDateTime", ""),
                "loinc": loinc_code,
                "emoji": info.get("emoji", "📊"),
                "fhir_id": resource.get("id", ""),
                "source": "FHIR",
            })
        return results
    except Exception:
        return []
