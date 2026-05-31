"""
2_Pacientes.py — Formulário de criação e pesquisa de Pacientes.
Substitui o Postman para o endpoint POST /Patient.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import require_auth, get_auth_headers
from utils.api_client import criar_paciente, pesquisar_pacientes, get_paciente_por_id
from utils.style import apply_custom_style

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Pacientes — SyncHealth", page_icon="👤", layout="wide")

# Aplicar estilo premium global
apply_custom_style()

# ─── Auth ─────────────────────────────────────────────────────────────────────
token = require_auth()
headers = get_auth_headers()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="premium-card">
        <h1 style="font-size: 1.8rem; font-weight: 700; color: #1c2b3e; margin:0;">Gestão de Pacientes</h1>
        <p style="margin: 0.3rem 0 0 0; color: #5c6e84; font-size: 0.9rem;">Registo de novos utentes e consultas de registos no repositório interoperável FHIR R4</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_criar, tab_pesquisar = st.tabs(["Registar Paciente", "Pesquisar Pacientes"])

# ══════════════════════════════════════════════════════════════
# TAB 1 — CRIAR PACIENTE
# ══════════════════════════════════════════════════════════════
with tab_criar:
    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("form_paciente", clear_on_submit=True):
        # ── Identificação ───────────────────────────────────────
        st.markdown("#### Identificação")
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
            format_func=lambda x: ("Feminino" if x == "feminino" else "Masculino"),
        )

        st.markdown("---")
        # ── Contactos ──────────────────────────────────────────
        st.markdown("#### Contactos do Utente")
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
        st.markdown("#### Contacto de Emergência")
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
            "Registar Paciente",
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
                st.error(erro)
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
                    f"Paciente {nome} registado com sucesso! "
                    f"FHIR ID: {resultado.get('id', '—')}"
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
                st.error(f"Erro ao registar paciente: {detalhe}")

# ══════════════════════════════════════════════════════════════
# TAB 2 — PESQUISAR PACIENTES
# ══════════════════════════════════════════════════════════════
with tab_pesquisar:
    st.markdown("<br>", unsafe_allow_html=True)

    col_q, col_btn = st.columns([4, 1])
    with col_q:
        nome_pesquisa = st.text_input(
            "Pesquisar por nome",
            placeholder="Introduza o nome (deixe em branco para listar todos)",
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
                st.info("Nenhum paciente encontrado.")
            else:
                st.success(f"{len(entries)} paciente(s) encontrado(s).")
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
                        <div class="premium-card" style="padding: 1.2rem !important; margin-bottom: 0.5rem !important;">
                            <strong style="font-size:1.1rem; font-family:'Outfit';">{pnome}</strong> &nbsp;
                            <span style="font-size:0.85rem;">({pid})</span><br>
                            <span style="font-size:0.88rem; line-height:1.6;">
                                SNS: <strong>{sns}</strong> &nbsp;·&nbsp;
                                Género: {pgenero} &nbsp;·&nbsp;
                                Telemóvel: {tel}
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"Erro ao pesquisar: {e}")

    # ── Pesquisa por ID ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Pesquisar Paciente por ID")

    col_id, col_btn_id = st.columns([4, 1])
    with col_id:
        id_pesquisa = st.text_input(
            "ID local do paciente",
            placeholder="Introduza o ID numérico (Ex: 1)",
            label_visibility="collapsed",
            key="pesq_paciente_id",
        )
    with col_btn_id:
        btn_pesq_id = st.button("Pesquisar por ID", use_container_width=True, key="btn_pesq_pac_id")

    if btn_pesq_id and id_pesquisa.strip():
        try:
            with st.spinner("A consultar paciente..."):
                resource = get_paciente_por_id(id_pesquisa.strip(), headers)

            if resource is None:
                st.warning(f"Nenhum paciente encontrado com o ID '{id_pesquisa.strip()}'.")
            else:
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
                email_val = next((t["value"] for t in telecoms if t.get("system") == "email"), "—")

                st.success(f"Paciente encontrado: {pnome}")
                st.markdown(
                    f"""
                    <div class="premium-card" style="padding: 1.2rem !important; margin-bottom: 0.5rem !important;">
                        <strong style="font-size:1.1rem; font-family:'Outfit';">{pnome}</strong> &nbsp;
                        <span style="font-size:0.85rem;">({pid})</span><br>
                        <span style="font-size:0.88rem; line-height:1.6;">
                            SNS: <strong>{sns}</strong> &nbsp;·&nbsp;
                            Género: {pgenero} &nbsp;·&nbsp;
                            Telemóvel: {tel} &nbsp;·&nbsp;
                            Email: {email_val}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                with st.expander("Ver recurso FHIR completo"):
                    st.json(resource)
        except Exception as e:
            st.error(f"Erro ao pesquisar por ID: {e}")
    elif btn_pesq_id:
        st.warning("Introduza o ID numérico do paciente.")
