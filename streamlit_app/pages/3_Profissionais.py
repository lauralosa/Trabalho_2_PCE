"""
3_Profissionais.py — Formulário de criação e pesquisa de Profissionais de Saúde.
Substitui o Postman para o endpoint POST /Practitioner.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import require_auth, get_auth_headers
from utils.api_client import criar_profissional, pesquisar_profissionais

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Profissionais — PCE", page_icon="👨‍⚕️", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .page-header {
        background: linear-gradient(135deg, rgba(56,189,248,0.12), rgba(13,115,119,0.08));
        border: 1px solid rgba(56,189,248,0.2);
        border-radius: 14px; padding: 1.2rem 2rem; margin-bottom: 1.5rem;
    }
    .page-header h1 { margin:0; font-size:1.6rem; font-weight:700; }
    .page-header p  { margin:0.3rem 0 0; color:#64748b; font-size:0.85rem; }

    .stButton > button {
        background: linear-gradient(135deg, #0d7377, #14a085);
        color:white; border:none; border-radius:8px; font-weight:600;
    }
    .stButton > button:hover { transform:translateY(-1px); }

    .result-card {
        background: rgba(56,189,248,0.05);
        border: 1px solid rgba(56,189,248,0.15);
        border-radius: 10px; padding: 1rem 1.3rem; margin: 0.5rem 0;
    }

    .specialty-badge {
        display: inline-block;
        background: rgba(13,115,119,0.2);
        border: 1px solid rgba(13,115,119,0.3);
        border-radius: 20px;
        padding: 2px 12px;
        font-size: 0.78rem;
        color: #0d7377;
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Auth ─────────────────────────────────────────────────────────────────────
token = require_auth()
headers = get_auth_headers()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="page-header">
        <h1>👨‍⚕️ Gestão de Profissionais de Saúde</h1>
        <p>Regista médicos e enfermeiros com cédula profissional no sistema FHIR R4</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Especialidades disponíveis ───────────────────────────────────────────────
ESPECIALIDADES = [
    "Medicina Geral e Familiar",
    "Cardiologia",
    "Pneumologia",
    "Ortopedia",
    "Neurologia",
    "Pediatria",
    "Oncologia",
    "Endocrinologia",
    "Dermatologia",
    "Oftalmologia",
    "Enfermagem",
    "Enfermagem de Reabilitação",
    "Enfermagem de Saúde Mental",
    "Outra",
]

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_criar, tab_pesquisar = st.tabs(["➕ Registar Profissional", "🔍 Pesquisar Profissionais"])

# ══════════════════════════════════════════════════════════════
# TAB 1 — CRIAR PROFISSIONAL
# ══════════════════════════════════════════════════════════════
with tab_criar:
    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("form_profissional", clear_on_submit=True):
        st.markdown("#### 🪪 Identificação Profissional")
        col1, col2 = st.columns(2)
        with col1:
            cedula = st.text_input(
                "N.º de Cédula Profissional *",
                placeholder="Ex: OM-12345 ou OE-67890",
                help="Cédula da Ordem dos Médicos (OM-) ou Enfermeiros (OE-)",
            )
        with col2:
            nome = st.text_input(
                "Nome Completo *",
                placeholder="Ex: Dr. Rui Santos",
                help="Nome do profissional (mínimo 3 caracteres)",
            )

        st.markdown("---")
        st.markdown("#### 🏥 Especialidade")

        col3, col4 = st.columns(2)
        with col3:
            especialidade_sel = st.selectbox(
                "Especialidade *",
                options=ESPECIALIDADES,
                help="Seleciona a área de especialização",
            )
        with col4:
            especialidade_custom = st.text_input(
                "Outra especialidade (preenche se selecionou 'Outra')",
                placeholder="Ex: Imunoalergologia",
            )

        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "✅ Registar Profissional",
            use_container_width=True,
            type="primary",
        )

    # ── Processar submissão ────────────────────────────────────────────────────
    if submitted:
        erros = []
        if not cedula.strip():
            erros.append("N.º de Cédula Profissional é obrigatório.")
        if not nome.strip() or len(nome.strip()) < 3:
            erros.append("Nome deve ter pelo menos 3 caracteres.")

        especialidade_final = (
            especialidade_custom.strip()
            if especialidade_sel == "Outra" and especialidade_custom.strip()
            else especialidade_sel
        )
        if len(especialidade_final) < 2:
            erros.append("Especialidade deve ter pelo menos 2 caracteres.")

        if erros:
            for erro in erros:
                st.error(f"❌ {erro}")
        else:
            payload = {
                "cedula": cedula.strip(),
                "nome": nome.strip(),
                "especialidade": especialidade_final,
            }

            try:
                with st.spinner("A registar profissional no FHIR..."):
                    resultado = criar_profissional(payload, headers)

                st.success(
                    f"✅ Profissional **{nome}** registado com sucesso! "
                    f"FHIR ID: `{resultado.get('id', '—')}`"
                )
                st.markdown("**Recurso FHIR criado:**")
                st.json(resultado)

            except Exception as e:
                detalhe = str(e)
                if hasattr(e, "response") and e.response is not None:
                    try:
                        detalhe = e.response.json().get("detail", e.response.text)
                    except Exception:
                        detalhe = e.response.text
                st.error(f"❌ Erro ao registar profissional: {detalhe}")

# ══════════════════════════════════════════════════════════════
# TAB 2 — PESQUISAR PROFISSIONAIS
# ══════════════════════════════════════════════════════════════
with tab_pesquisar:
    st.markdown("<br>", unsafe_allow_html=True)

    col_n, col_e, col_btn = st.columns([3, 3, 1])
    with col_n:
        nome_pesquisa = st.text_input(
            "Nome",
            placeholder="Ex: Rui",
            label_visibility="visible",
            key="pesq_prac_nome",
        )
    with col_e:
        esp_pesquisa = st.text_input(
            "Especialidade",
            placeholder="Ex: Cardiologia",
            label_visibility="visible",
            key="pesq_prac_esp",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_pesquisar = st.button("Pesquisar", use_container_width=True, key="btn_pesq_prac")

    if btn_pesquisar:
        try:
            with st.spinner("A consultar profissionais..."):
                resultados = pesquisar_profissionais(
                    nome_pesquisa.strip() or None,
                    esp_pesquisa.strip() or None,
                    headers,
                )

            if not resultados:
                st.info("📭 Nenhum profissional encontrado.")
            else:
                st.success(f"✅ {len(resultados)} profissional(is) encontrado(s).")
                for prof in resultados:
                    pid = prof.get("id", "—")
                    pnome = prof.get("nome", "—")
                    pesp = prof.get("especialidade", "—")

                    st.markdown(
                        f"""
                        <div class="result-card">
                            <strong style="color:#e2e8f0;">👨‍⚕️ {pnome}</strong>
                            <span style="color:#64748b; font-size:0.85rem;"> &nbsp;(ID: {pid})</span><br>
                            <span class="specialty-badge">{pesp}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"❌ Erro ao pesquisar: {e}")
