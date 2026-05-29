"""
5_Consultas.py — Formulário de criação e pesquisa de Consultas (Encounters).
Substitui o Postman para o endpoint POST /Encounter.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import require_auth, get_auth_headers
from utils.api_client import criar_consulta, pesquisar_consultas
from utils.style import apply_custom_style

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Consultas — SyncHealth", page_icon="🏥", layout="wide")

# Aplicar estilo premium global
apply_custom_style()

# ─── Auth ─────────────────────────────────────────────────────────────────────
token = require_auth()
headers = get_auth_headers()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="premium-card">
        <h1 style="font-size: 1.8rem; font-weight: 700; color: #1c2b3e; margin:0;">Gestão de Consultas</h1>
        <p style="margin: 0.3rem 0 0 0; color: #5c6e84; font-size: 0.9rem;">Registo de Encounters (Consultas) associando Pacientes e Profissionais de Saúde no FHIR R4</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_criar, tab_pesquisar = st.tabs(["Registar Consulta", "Pesquisar Consultas"])

# ══════════════════════════════════════════════════════════════
# TAB 1 — CRIAR CONSULTA
# ══════════════════════════════════════════════════════════════
with tab_criar:
    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("form_consulta", clear_on_submit=True):
        st.markdown("#### Detalhes da Consulta")
        col1, col2 = st.columns(2)
        
        with col1:
            paciente_id = st.text_input(
                "ID Local do Paciente *",
                placeholder="Ex: 1",
                help="ID interno do paciente na base de dados (ex: 1 para o primeiro paciente criado)",
            )
            classe_code = st.selectbox(
                "Classe da Consulta *",
                options=["AMB", "EMER", "INT", "VR", "TLC"],
                format_func=lambda x: {
                    "AMB": "AMB — Ambulatório",
                    "EMER": "EMER — Urgência",
                    "INT": "INT — Internamento",
                    "VR": "VR — Virtual",
                    "TLC": "TLC — Teleconsulta",
                }.get(x, x),
                help="Classificação do encontro clínico (AMB, EMER, INT, VR, TLC)"
            )
            
        with col2:
            practitioner_id = st.text_input(
                "ID Local do Profissional *",
                placeholder="Ex: 1",
                help="ID interno do médico/enfermeiro na base de dados",
            )
            status = st.selectbox(
                "Estado da Consulta *",
                options=["planned", "arrived", "in-progress", "finished", "cancelled"],
                index=3,
                help="O FHIR R4 requer que as consultas documentadas estejam num destes estados."
            )

        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "Registar Consulta",
            use_container_width=True,
            type="primary",
        )

    # ── Processar submissão ────────────────────────────────────────────────────
    if submitted:
        erros = []
        if not paciente_id.strip():
            erros.append("O ID do Paciente é obrigatório.")
        if not practitioner_id.strip():
            erros.append("O ID do Profissional é obrigatório.")

        if erros:
            for erro in erros:
                st.error(erro)
        else:
            payload = {
                "paciente_id": paciente_id.strip(),
                "practitioner_id": practitioner_id.strip(),
                "status": status,
                "classe_code": classe_code
            }

            try:
                with st.spinner("A registar consulta no FHIR..."):
                    resultado = criar_consulta(payload, headers)

                st.success(
                    f"Consulta registada com sucesso! "
                    f"FHIR ID: {resultado.get('id_fhir', resultado.get('id', '—'))}"
                )
                with st.expander("Ver recurso FHIR criado"):
                    st.json(resultado)

            except Exception as e:
                detalhe = str(e)
                if hasattr(e, "response") and e.response is not None:
                    try:
                        detalhe = e.response.json().get("detail", e.response.text)
                    except Exception:
                        detalhe = e.response.text
                st.error(f"Erro ao registar consulta: {detalhe}")

# ══════════════════════════════════════════════════════════════
# TAB 2 — PESQUISAR CONSULTAS
# ══════════════════════════════════════════════════════════════
with tab_pesquisar:
    st.markdown("<br>", unsafe_allow_html=True)

    col_p, col_s, col_btn = st.columns([3, 3, 1])
    with col_p:
        paciente_pesquisa = st.text_input(
            "ID do Paciente",
            placeholder="Ex: 1",
            label_visibility="visible",
            key="pesq_enc_pac",
        )
    with col_s:
        status_pesquisa = st.selectbox(
            "Estado",
            options=["", "planned", "arrived", "in-progress", "finished", "cancelled"],
            format_func=lambda x: "Todos" if x == "" else x,
            key="pesq_enc_stat",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_pesq_consulta = st.button("Pesquisar", use_container_width=True, key="btn_pesq_enc")

    if btn_pesq_consulta:
        try:
            with st.spinner("A consultar consultas (Encounters)..."):
                resultados = pesquisar_consultas(
                    paciente_pesquisa.strip() or None,
                    status_pesquisa.strip() or None,
                    headers,
                )

            if not resultados:
                st.info("Nenhuma consulta encontrada.")
            else:
                st.success(f"{len(resultados)} consulta(s) encontrada(s).")
                for entry in resultados:
                    res = entry.get("resource", entry)
                    eid = res.get("id", "—")
                    estatus = res.get("status", "—")
                    eclasse = res.get("class", {}).get("code", "—")
                    
                    # Extrair referência do paciente (ex: "Patient/pat-1")
                    esubject = res.get("subject", {}).get("reference", "—")
                    
                    st.markdown(
                        f"""
                        <div class="premium-card" style="padding: 1.2rem !important; margin-bottom: 0.5rem !important;">
                            <strong style="font-size:1.1rem; font-family:'Outfit';">Consulta {eclasse}</strong> &nbsp;
                            <span style="font-size:0.85rem;">(FHIR ID: {eid})</span><br>
                            <span style="font-size:0.88rem; line-height:1.6;">
                                Paciente: <strong>{esubject}</strong> &nbsp;·&nbsp;
                                Estado: <span class="tag-badge" style="margin-top: 0; padding: 0.1rem 0.4rem;">{estatus}</span>
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"Erro ao pesquisar: {e}")
