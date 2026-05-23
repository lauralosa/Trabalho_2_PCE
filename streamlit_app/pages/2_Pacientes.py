"""
2_Pacientes.py — Formulário de criação e pesquisa de Pacientes.
Substitui o Postman para o endpoint POST /Patient.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import require_auth, get_auth_headers
from utils.api_client import criar_paciente, pesquisar_pacientes

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Pacientes — PCE", page_icon="👤", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .page-header {
        background: linear-gradient(135deg, rgba(13,115,119,0.15), rgba(56,189,248,0.08));
        border: 1px solid rgba(13,115,119,0.3);
        border-radius: 14px; padding: 1.2rem 2rem; margin-bottom: 1.5rem;
    }
    .page-header h1 { margin:0; font-size:1.6rem; font-weight:700; }
    .page-header p  { margin:0.3rem 0 0; color:#64748b; font-size:0.85rem; }

    .form-section {
        background: rgba(17,24,39,0.8);
        border: 1px solid #1e293b;
        border-radius: 12px; padding: 1.5rem 2rem; margin-bottom: 1rem;
    }
    .form-section h3 { margin:0 0 1rem; font-size:1rem; color:#94a3b8; }

    .stButton > button {
        background: linear-gradient(135deg, #0d7377, #14a085);
        color:white; border:none; border-radius:8px; font-weight:600;
    }
    .stButton > button:hover { transform:translateY(-1px); }

    .result-card {
        background: rgba(13,115,119,0.08);
        border: 1px solid rgba(13,115,119,0.2);
        border-radius: 10px; padding: 1rem 1.3rem; margin: 0.5rem 0;
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
        <h1>👤 Gestão de Pacientes</h1>
        <p>Regista novos utentes ou pesquisa utentes existentes no sistema FHIR R4</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_criar, tab_pesquisar = st.tabs(["➕ Registar Paciente", "🔍 Pesquisar Pacientes"])

# ══════════════════════════════════════════════════════════════
# TAB 1 — CRIAR PACIENTE
# ══════════════════════════════════════════════════════════════
with tab_criar:
    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("form_paciente", clear_on_submit=True):
        # ── Identificação ───────────────────────────────────────
        st.markdown("#### 🪪 Identificação")
        col1, col2 = st.columns(2)
        with col1:
            numero_sns = st.text_input(
                "N.º de Utente SNS *",
                placeholder="Ex: 123456789",
                help="Identificador único do utente no SNS (obrigatório)",
            )
        with col2:
            nome = st.text_input(
                "Nome Completo *",
                placeholder="Ex: Helena Oliveira",
                help="Mínimo 3 caracteres",
            )

        genero = st.radio(
            "Género *",
            options=["feminino", "masculino"],
            horizontal=True,
            format_func=lambda x: ("♀ Feminino" if x == "feminino" else "♂ Masculino"),
        )

        st.markdown("---")
        # ── Contactos ──────────────────────────────────────────
        st.markdown("#### 📞 Contactos do Utente")
        col3, col4 = st.columns(2)
        with col3:
            telemovel = st.text_input(
                "Telemóvel *",
                placeholder="Ex: 912345678",
                help="Número de telemóvel (9 dígitos)",
            )
        with col4:
            email = st.text_input(
                "Email",
                placeholder="Ex: helena@email.com",
                help="Endereço de email (opcional)",
            )

        st.markdown("---")
        # ── Contacto de Emergência ─────────────────────────────
        st.markdown("#### 🆘 Contacto de Emergência")
        col5, col6 = st.columns(2)
        with col5:
            contacto_nome = st.text_input(
                "Nome do Contacto *",
                placeholder="Ex: Maria Oliveira",
                help="Nome do familiar ou cuidador",
            )
        with col6:
            contacto_tel = st.text_input(
                "Telemóvel do Contacto",
                placeholder="Ex: 927895461",
            )

        contacto_morada = st.text_input(
            "Morada do Contacto",
            placeholder="Ex: Rua da Universidade, 25, Braga",
        )

        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "✅ Registar Paciente",
            use_container_width=True,
            type="primary",
        )

    # ── Processar submissão ────────────────────────────────────────────────────
    if submitted:
        # Validações básicas
        erros = []
        if not numero_sns.strip():
            erros.append("N.º de Utente SNS é obrigatório.")
        if not nome.strip() or len(nome.strip()) < 3:
            erros.append("Nome deve ter pelo menos 3 caracteres.")
        if not telemovel.strip() or not telemovel.strip().isdigit():
            erros.append("Telemóvel inválido (apenas dígitos).")
        if not contacto_nome.strip() or len(contacto_nome.strip()) < 3:
            erros.append("Nome do contacto de emergência deve ter pelo menos 3 caracteres.")

        if erros:
            for erro in erros:
                st.error(f"❌ {erro}")
        else:
            # Construir o payload para a API
            telecom_list = [{"tipo": "telemóvel", "valor": telemovel.strip()}]
            if email.strip():
                telecom_list.append({"tipo": "email", "valor": email.strip()})

            contacto_payload = {"nome": contacto_nome.strip()}
            if contacto_tel.strip():
                contacto_payload["telecom"] = [{"tipo": "telemóvel", "valor": contacto_tel.strip()}]
            if contacto_morada.strip():
                contacto_payload["endereco"] = [{"tipo": "casa", "valor": contacto_morada.strip()}]

            payload = {
                "numero_sns": numero_sns.strip(),
                "nome": nome.strip(),
                "genero": genero,
                "telecom": telecom_list,
                "contacto": [contacto_payload],
            }

            try:
                with st.spinner("A registar paciente no FHIR..."):
                    resultado = criar_paciente(payload, headers)

                st.success(
                    f"✅ Paciente **{nome}** registado com sucesso! "
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
                st.error(f"❌ Erro ao registar paciente: {detalhe}")

# ══════════════════════════════════════════════════════════════
# TAB 2 — PESQUISAR PACIENTES
# ══════════════════════════════════════════════════════════════
with tab_pesquisar:
    st.markdown("<br>", unsafe_allow_html=True)

    col_q, col_btn = st.columns([4, 1])
    with col_q:
        nome_pesquisa = st.text_input(
            "Pesquisar por nome",
            placeholder="Ex: Helena (deixa em branco para ver todos)",
            label_visibility="collapsed",
            key="pesq_paciente_nome",
        )
    with col_btn:
        btn_pesquisar = st.button("Pesquisar", use_container_width=True, key="btn_pesq_paciente")

    if btn_pesquisar:
        try:
            with st.spinner("A consultar o servidor FHIR..."):
                entries = pesquisar_pacientes(
                    nome_pesquisa.strip() if nome_pesquisa.strip() else None,
                    headers,
                )

            if not entries:
                st.info("📭 Nenhum paciente encontrado.")
            else:
                st.success(f"✅ {len(entries)} paciente(s) encontrado(s).")
                for entry in entries:
                    resource = entry.get("resource", entry)
                    pid = resource.get("id", "—")
                    pnome = resource.get("name", [{}])[0].get("text", "—")
                    pgenero = resource.get("gender", "—").capitalize()
                    identifiers = resource.get("identifier", [])
                    sns = next(
                        (i["value"] for i in identifiers if "sns" in i.get("system", "").lower()),
                        "—"
                    )
                    telecoms = resource.get("telecom", [])
                    tel = next((t["value"] for t in telecoms if t.get("system") == "phone"), "—")

                    st.markdown(
                        f"""
                        <div class="result-card">
                            <strong style="color:#e2e8f0;">{pnome}</strong> &nbsp;
                            <span style="color:#64748b;">({pid})</span><br>
                            <span style="font-size:0.85rem; color:#94a3b8;">
                                SNS: <strong style="color:#0d7377;">{sns}</strong> &nbsp;|&nbsp;
                                Género: {pgenero} &nbsp;|&nbsp;
                                ☎ {tel}
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"❌ Erro ao pesquisar: {e}")
