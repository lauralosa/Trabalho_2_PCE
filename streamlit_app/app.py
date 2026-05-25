"""
app.py — Ponto de entrada principal da aplicação Streamlit.
Mostra a página de boas-vindas e a sidebar de autenticação.
"""
import streamlit as st
from utils.auth import show_login_sidebar
from utils.style import apply_custom_style

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="SyncHealth",
    page_icon="⚕️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Aplicar estilo premium global
apply_custom_style()

# ─── Sidebar ─────────────────────────────────────────────────────────────────
is_auth = show_login_sidebar()

# ─── Conteúdo principal ───────────────────────────────────────────────────────
st.markdown(
    """
    <div class="premium-card" style="text-align: center;">
        <h1 style="font-size: 2.4rem; font-weight: 700; margin: 0 0 0.4rem 0;">SyncHealth</h1>
        <p style="font-size: 1.05rem; margin: 0 0 1.2rem 0;">
            Integração interoperável de dados médicos usando FHIR R4 e openEHR
        </p>
        <span class="tag-badge">Universidade do Minho · 2025/2026</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# Cards de funcionalidades
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        """
        <div class="premium-card" style="text-align: center; height: 100%; margin-bottom: 0px !important;">
            <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 0.3rem;">Dashboard</div>
            <div style="font-size: 0.85rem;">Histórico de sinais vitais do utente consultado a partir do EHRbase</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div class="premium-card" style="text-align: center; height: 100%; margin-bottom: 0px !important;">
            <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 0.3rem;">Pacientes</div>
            <div style="font-size: 0.85rem;">Registo e pesquisa de utentes no repositório clínico FHIR R4</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        """
        <div class="premium-card" style="text-align: center; height: 100%; margin-bottom: 0px !important;">
            <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 0.3rem;">Profissionais</div>
            <div style="font-size: 0.85rem;">Gestão de médicos e enfermeiros com cédula de identificação</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        """
        <div class="premium-card" style="text-align: center; height: 100%; margin-bottom: 0px !important;">
            <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 0.3rem;">Observações</div>
            <div style="font-size: 0.85rem;">Registo estruturado de novos sinais vitais por utente</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# Estado do sistema
st.markdown("### Estado do Sistema")
col_s1, col_s2, col_s3 = st.columns(3)

import requests
import os

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:5000")
EHRBASE_LOCAL = os.getenv("EHRBASE_URL_LOCAL", "http://localhost:8085/ehrbase/rest/openehr/v1")
HAPI_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:9090/fhir")

def check_service(url, name):
    try:
        r = requests.get(url, timeout=3)
        return r.status_code < 500
    except Exception:
        return False

with col_s1:
    ok = check_service(f"{FASTAPI_URL}/docs", "FastAPI")
    st.metric("FastAPI", "Online" if ok else "Offline")

with col_s2:
    ok = check_service(f"{HAPI_URL}/metadata", "HAPI FHIR")
    st.metric("HAPI FHIR", "Online" if ok else "Offline")

with col_s3:
    ok = check_service(f"{EHRBASE_LOCAL}/definition/template/adl1.4", "EHRbase")
    st.metric("EHRbase", "Online" if ok else "Offline")

# Instrução de login
if not is_auth:
    st.markdown("<br>", unsafe_allow_html=True)
    st.info("Efetue o login na barra lateral para aceder às funcionalidades da aplicação (admin / 1234).")
else:
    st.markdown("<br>", unsafe_allow_html=True)
    st.success("Sessão iniciada com sucesso. Utilize o menu lateral para navegar entre as páginas.")
