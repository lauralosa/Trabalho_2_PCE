"""
3_Profissionais.py — Formulário de criação e pesquisa de Profissionais de Saúde.
Substitui o Postman para o endpoint POST /Practitioner.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import require_auth, get_auth_headers
from utils.api_client import criar_profissional, pesquisar_profissionais, get_profissional_por_id
from utils.style import apply_custom_style

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Profissionais — SyncHealth", page_icon="👩‍⚕️", layout="wide")

# Aplicar estilo premium global
apply_custom_style()

# ─── Auth ─────────────────────────────────────────────────────────────────────
token = require_auth()
headers = get_auth_headers()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="premium-card">
        <h1 style="font-size: 1.8rem; font-weight: 700; color: #1c2b3e; margin:0;">Gestão de Profissionais de Saúde</h1>
        <p style="margin: 0.3rem 0 0 0; color: #5c6e84; font-size: 0.9rem;">Registo e consulta de credenciais de médicos e enfermeiros no repositório FHIR R4</p>
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
tab_criar, tab_pesquisar = st.tabs(["Registar Profissional", "Pesquisar Profissionais"])

# ══════════════════════════════════════════════════════════════
# TAB 1 — CRIAR PROFISSIONAL
# ══════════════════════════════════════════════════════════════
with tab_criar:
    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("form_profissional", clear_on_submit=True):
        st.markdown("#### Identificação Profissional")
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
        st.markdown("#### Especialidade")

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
            "Registar Profissional",
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
                st.error(erro)
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
                    f"Profissional {nome} registado com sucesso! "
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
                st.error(f"Erro ao registar profissional: {detalhe}")

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
                st.info("Nenhum profissional encontrado.")
            else:
                st.success(f"{len(resultados)} profissional(is) encontrado(s).")
                for prof in resultados:
                    pid = prof.get("id", "—")
                    pnome = prof.get("nome", "—")
                    pesp = prof.get("especialidade", "—")

                    st.markdown(
                        f"""
                        <div class="premium-card" style="padding: 1.2rem !important; margin-bottom: 0.5rem !important;">
                            <strong style="font-size:1.1rem; font-family:'Outfit';">{pnome}</strong> &nbsp;
                            <span style="font-size:0.85rem;">(ID: {pid})</span><br>
                            <span class="tag-badge" style="margin-top: 0.4rem;">{pesp}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"Erro ao pesquisar: {e}")

    # ── Pesquisa por ID ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Pesquisar Profissional por ID")

    col_id, col_btn_id = st.columns([4, 1])
    with col_id:
        id_pesquisa = st.text_input(
            "ID local do profissional",
            placeholder="Introduza o ID numérico (Ex: 1)",
            label_visibility="collapsed",
            key="pesq_prac_id",
        )
    with col_btn_id:
        btn_pesq_id = st.button("Pesquisar por ID", use_container_width=True, key="btn_pesq_prac_id")

    if btn_pesq_id and id_pesquisa.strip():
        try:
            with st.spinner("A consultar profissional..."):
                resource = get_profissional_por_id(id_pesquisa.strip(), headers)

            if resource is None:
                st.warning(f"Nenhum profissional encontrado com o ID '{id_pesquisa.strip()}'.")
            else:
                pid = resource.get("id", "—")
                pnome = resource.get("name", [{}])[0].get("text", "—")
                identifiers = resource.get("identifier", [])
                cedula = next(
                    (i["value"] for i in identifiers if "ordemdosmedicos" in i.get("system", "").lower() or "ordemenfermeiros" in i.get("system", "").lower()),
                    "—"
                )
                qualifications = resource.get("qualification", [])
                especialidade = qualifications[0].get("code", {}).get("text", "—") if qualifications else "—"

                st.success(f"Profissional encontrado: {pnome}")
                st.markdown(
                    f"""
                    <div class="premium-card" style="padding: 1.2rem !important; margin-bottom: 0.5rem !important;">
                        <strong style="font-size:1.1rem; font-family:'Outfit';">{pnome}</strong> &nbsp;
                        <span style="font-size:0.85rem;">(FHIR ID: {pid})</span><br>
                        <span style="font-size:0.88rem; line-height:1.6;">
                            Cédula: <strong>{cedula}</strong> &nbsp;·&nbsp;
                            Especialidade: <span class="tag-badge">{especialidade}</span>
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
        st.warning("Introduza o ID numérico do profissional.")
