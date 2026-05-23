from __future__ import annotations
"""
api_client.py — Encapsula todas as chamadas HTTP ao FastAPI middleware.
Todas as funções recebem os headers de autenticação como parâmetro.
"""
import requests
import streamlit as st
import os

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:5000")


# ─────────────────────────────────────────────
#  PACIENTES
# ─────────────────────────────────────────────

def criar_paciente(data: dict, headers: dict) -> dict:
    """POST /Patient — Cria um novo paciente."""
    r = requests.post(f"{FASTAPI_URL}/Patient", json=data, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def pesquisar_pacientes(nome: str | None, headers: dict) -> list:
    """GET /Patient?name=... — Pesquisa pacientes por nome."""
    params = {}
    if nome:
        params["name"] = nome
    r = requests.get(f"{FASTAPI_URL}/Patient", params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("entry", [])


def get_paciente_por_id(patient_id: str, headers: dict) -> dict | None:
    """GET /Patient/{id} — Obtém um paciente por ID numérico."""
    try:
        r = requests.get(f"{FASTAPI_URL}/Patient/{patient_id}", headers=headers, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ─────────────────────────────────────────────
#  PROFISSIONAIS
# ─────────────────────────────────────────────

def criar_profissional(data: dict, headers: dict) -> dict:
    """POST /Practitioner — Cria um novo profissional."""
    r = requests.post(f"{FASTAPI_URL}/Practitioner", json=data, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def pesquisar_profissionais(nome: str | None, especialidade: str | None, headers: dict) -> list:
    """GET /Practitioner — Pesquisa profissionais."""
    params = {}
    if nome:
        params["nome"] = nome
    if especialidade:
        params["especialidade"] = especialidade
    r = requests.get(f"{FASTAPI_URL}/Practitioner", params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    # A API retorna {"total":..., "resultados": [...]}
    return data.get("resultados", [])


# ─────────────────────────────────────────────
#  OBSERVAÇÕES
# ─────────────────────────────────────────────

def criar_observacao(data: dict, headers: dict) -> dict:
    """POST /Observation — Regista uma nova observação (sinal vital)."""
    r = requests.post(f"{FASTAPI_URL}/Observation", json=data, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def pesquisar_observacoes(patient_id: str, headers: dict) -> list:
    """GET /Observation?patient=... — Lista observações de um paciente."""
    r = requests.get(
        f"{FASTAPI_URL}/Observation",
        params={"patient": patient_id},
        headers=headers,
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("entry", [])
