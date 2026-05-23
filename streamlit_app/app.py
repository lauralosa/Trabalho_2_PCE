"""
app.py — Ponto de entrada principal da aplicação Streamlit.
Mostra a página de boas-vindas e a sidebar de autenticação.
"""
import streamlit as st
from utils.auth import show_login_sidebar

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="PCE — Processo Clínico Eletrónico",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS personalizado para uma estética premium
st.markdown(
    """
    <style>
    /* Importar fonte moderna */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Gradiente no fundo da página principal */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Sidebar estilizada */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a0e1a 0%, #111827 100%);
        border-right: 1px solid #1e293b;
    }

    /* Botões primários */
    .stButton > button {
        background: linear-gradient(135deg, #0d7377 0%, #14a085 100%);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(13, 115, 119, 0.4);
    }

    /* Cards métricos */
    [data-testid="metric-container"] {
        background: rgba(13, 115, 119, 0.1);
        border: 1px solid rgba(13, 115, 119, 0.3);
        border-radius: 12px;
        padding: 1rem;
        backdrop-filter: blur(10px);
    }

    /* Inputs */
    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stNumberInput > div > div > input {
        border-radius: 8px;
        border: 1px solid #1e293b;
        background: #111827;
    }

    /* Separador estilizado */
    hr {
        border-color: #1e293b;
    }

    /* Alertas personalizados */
    .stAlert {
        border-radius: 10px;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #111827;
        border-radius: 10px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #94a3b8;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #0d7377, #14a085) !important;
        color: white !important;
    }

    /* Hero section */
    .hero-container {
        background: linear-gradient(135deg, rgba(13,115,119,0.15) 0%, rgba(20,160,133,0.08) 100%);
        border: 1px solid rgba(13,115,119,0.25);
        border-radius: 16px;
        padding: 2.5rem 3rem;
        text-align: center;
        backdrop-filter: blur(10px);
        margin-bottom: 2rem;
    }
    .hero-title {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #0d7377, #14a085, #38bdf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0 0 0.5rem 0;
    }
    .hero-subtitle {
        font-size: 1.1rem;
        color: #94a3b8;
        margin: 0;
    }

    /* Feature cards */
    .feature-card {
        background: rgba(17, 24, 39, 0.8);
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        transition: all 0.3s ease;
        height: 100%;
    }
    .feature-card:hover {
        border-color: #0d7377;
        box-shadow: 0 4px 20px rgba(13,115,119,0.2);
        transform: translateY(-2px);
    }
    .feature-emoji { font-size: 2rem; }
    .feature-title { font-weight: 600; color: #e2e8f0; font-size: 1rem; margin: 0.5rem 0 0.25rem 0; }
    .feature-desc { color: #64748b; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Sidebar ─────────────────────────────────────────────────────────────────
is_auth = show_login_sidebar()

# ─── Conteúdo principal ───────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero-container">
        <p class="hero-title">🏥 PCE Dashboard</p>
        <p class="hero-subtitle">
            Processo Clínico Eletrónico — Integração FHIR R4 + openEHR<br>
            <span style="color:#0d7377; font-size:0.9rem;">Universidade do Minho · 2025/2026</span>
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Cards de funcionalidades
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        """
        <div class="feature-card">
            <div class="feature-emoji">📊</div>
            <div class="feature-title">Dashboard</div>
            <div class="feature-desc">Visualiza os sinais vitais históricos de um utente a partir do EHRbase</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div class="feature-card">
            <div class="feature-emoji">👤</div>
            <div class="feature-title">Pacientes</div>
            <div class="feature-desc">Regista e pesquisa utentes com N.º SNS e dados de contacto</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        """
        <div class="feature-card">
            <div class="feature-emoji">👨‍⚕️</div>
            <div class="feature-title">Profissionais</div>
            <div class="feature-desc">Gere médicos e enfermeiros com cédula profissional</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        """
        <div class="feature-card">
            <div class="feature-emoji">🩺</div>
            <div class="feature-title">Observações</div>
            <div class="feature-desc">Regista sinais vitais (temperatura, peso, PA...) via formulário</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# Estado do sistema
st.markdown("### 🔌 Estado do Sistema")
col_s1, col_s2, col_s3 = st.columns(3)

import requests
import os

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:5000")
EHRBASE_LOCAL = os.getenv("EHRBASE_URL_LOCAL", "http://localhost:8081/ehrbase/rest/openehr/v1")
HAPI_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:9090/fhir")

def check_service(url, name):
    try:
        r = requests.get(url, timeout=3)
        return r.status_code < 500
    except Exception:
        return False

with col_s1:
    ok = check_service(f"{FASTAPI_URL}/docs", "FastAPI")
    st.metric("⚡ FastAPI", "Online ✅" if ok else "Offline ❌")

with col_s2:
    ok = check_service(f"{HAPI_URL}/metadata", "HAPI FHIR")
    st.metric("🔵 HAPI FHIR", "Online ✅" if ok else "Offline ❌")

with col_s3:
    ok = check_service(f"{EHRBASE_LOCAL}/definition/template/adl1.4", "EHRbase")
    st.metric("🟢 EHRbase", "Online ✅" if ok else "Offline ❌")

# Instrução de login
if not is_auth:
    st.markdown("<br>", unsafe_allow_html=True)
    st.info("👈 **Faz login na barra lateral** para aceder às funcionalidades. (admin / 1234)")
else:
    st.markdown("<br>", unsafe_allow_html=True)
    st.success("✅ Sessão iniciada! Usa o menu lateral para navegar entre as páginas.")
