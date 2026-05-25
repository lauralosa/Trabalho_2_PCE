"""
4_Observacoes.py — Formulário de registo de Sinais Vitais (Observations FHIR).
Substitui o Postman para o endpoint POST /Observation.
"""
import streamlit as st
from datetime import datetime, timezone
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import require_auth, get_auth_headers
from utils.api_client import criar_observacao, pesquisar_observacoes
from utils.style import apply_custom_style
import requests as req

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Observações — SyncHealth", page_icon="🩺", layout="wide")

HAPI_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:9090/fhir")
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:5000")

# Aplicar estilo premium global
apply_custom_style()

# CSS local para a caixa LOINC
st.markdown(
    """
    <style>
    .loinc-info {
        background: rgba(255, 255, 255, 0.7) !important;
        border: 1px solid rgba(28, 43, 62, 0.08) !important;
        border-radius: 14px !important;
        padding: 0.8rem 1.2rem !important;
        font-size: 0.82rem !important;
        color: #5c6e84 !important;
        margin-top: 0.5rem !important;
    }
    .loinc-code {
        background: rgba(28, 43, 62, 0.05) !important;
        border: 1px solid rgba(28, 43, 62, 0.1) !important;
        border-radius: 6px !important;
        padding: 2px 8px !important;
        font-family: monospace !important;
        color: #1c2b3e !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Mapa de sinais vitais ────────────────────────────────────────────────────
SINAIS_VITAIS = {
    "Temperatura Corporal":           {"loinc": "8310-5",  "display": "Body temperature",        "unidade": "Cel",  "sistema_unit": "http://unitsofmeasure.org", "min": 30.0, "max": 45.0, "step": 0.1},
    "Peso Corporal":                  {"loinc": "29463-7", "display": "Body weight",             "unidade": "kg",   "sistema_unit": "http://unitsofmeasure.org", "min": 0.5,  "max": 300.0,"step": 0.1},
    "Frequência Cardíaca":            {"loinc": "8867-4",  "display": "Heart rate",              "unidade": "/min", "sistema_unit": "http://unitsofmeasure.org", "min": 20.0, "max": 300.0,"step": 1.0},
    "Pressão Arterial Sistólica":      {"loinc": "8480-6",  "display": "Systolic blood pressure", "unidade": "mm[Hg]","sistema_unit": "http://unitsofmeasure.org","min": 50.0, "max": 280.0,"step": 1.0},
    "Pressão Arterial Diastólica":     {"loinc": "8462-4",  "display": "Diastolic blood pressure","unidade": "mm[Hg]","sistema_unit": "http://unitsofmeasure.org","min": 20.0, "max": 180.0,"step": 1.0},
    "Saturação de Oxigénio (SpO2)":    {"loinc": "59408-5", "display": "Oxygen saturation",      "unidade": "%",    "sistema_unit": "http://unitsofmeasure.org", "min": 50.0, "max": 100.0,"step": 0.1},
    "Frequência Respiratória":         {"loinc": "9279-1",  "display": "Respiratory rate",       "unidade": "/min", "sistema_unit": "http://unitsofmeasure.org", "min": 4.0,  "max": 80.0, "step": 1.0},
}

# ─── Auth ─────────────────────────────────────────────────────────────────────
token = require_auth()
headers = get_auth_headers()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="premium-card">
        <h1 style="font-size: 1.8rem; font-weight: 700; margin:0;">Registo de Sinais Vitais</h1>
        <p style="margin: 0.3rem 0 0 0; font-size: 0.9rem;">Submissão de observações clínicas diretamente para o servidor interoperável FHIR R4</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_criar, tab_consultar = st.tabs(["Registar Observação", "Consultar Observações"])

# ══════════════════════════════════════════════════════════════
# TAB 1 — CRIAR OBSERVAÇÃO
# ══════════════════════════════════════════════════════════════
with tab_criar:
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Passo 1: Selecionar Paciente ──────────────────────────────────────────
    st.markdown("#### Passo 1 — Identificar Utente")
    col_sns, col_btn_sns = st.columns([4, 1])
    with col_sns:
        sns_input = st.text_input(
            "N.º de Utente SNS",
            placeholder="Ex: 123456789",
            key="obs_sns",
            label_visibility="collapsed",
        )
    with col_btn_sns:
        btn_buscar = st.button("Verificar", key="btn_buscar_sns")

    patient_fhir_id = None
    patient_nome = None

    if btn_buscar and sns_input.strip():
        try:
            r = req.get(
                f"{HAPI_URL}/Patient",
                params={"identifier": f"https://www.sns.gov.pt/utente|{sns_input.strip()}"},
                timeout=8,
            )
            if r.status_code == 200:
                entries = r.json().get("entry", [])
                if entries:
                    resource = entries[0]["resource"]
                    patient_fhir_id = resource.get("id", "")
                    patient_nome = resource.get("name", [{}])[0].get("text", "Desconhecido")
                    st.session_state["obs_patient_id"] = patient_fhir_id
                    st.session_state["obs_patient_nome"] = patient_nome
                    st.session_state["obs_sns_confirmed"] = sns_input.strip()
                    st.success(f"Utente encontrado: {patient_nome} (FHIR ID: {patient_fhir_id})")
                else:
                    st.warning("Nenhum paciente encontrado com este N.º de Utente. Registe-o primeiro na página Pacientes.")
        except Exception as e:
            st.error(f"Erro ao consultar FHIR: {e}")

    # Recuperar da sessão (caso o utilizador já tenha verificado antes)
    if "obs_patient_id" in st.session_state and not btn_buscar:
        patient_fhir_id = st.session_state["obs_patient_id"]
        patient_nome = st.session_state.get("obs_patient_nome", "")
        st.info(
            f"Utente selecionado: {patient_nome} "
            f"(SNS: {st.session_state.get('obs_sns_confirmed', '—')}, FHIR ID: {patient_fhir_id})"
        )

    st.markdown("---")

    # ── Seleção do tipo de sinal vital FORA do form ──────────────────────────
    # O selectbox tem de estar fora do st.form para que mudar o tipo de sinal
    # vital acione um re-render imediato, atualizando os limites e unidade.
    st.markdown("#### Passo 2 — Detalhes da Observação")

    col_tipo, col_status_outer = st.columns(2)
    with col_tipo:
        tipo_sinal = st.selectbox(
            "Tipo de Sinal Vital *",
            options=list(SINAIS_VITAIS.keys()),
            help="Seleciona o tipo de medição",
            key="obs_tipo_sinal",
        )
    with col_status_outer:
        estado = st.selectbox(
            "Estado *",
            options=["final", "preliminary", "registered", "amended", "corrected"],
            help="Estado da observação clínica",
            key="obs_estado",
        )

    # Info do código LOINC — atualiza imediatamente ao mudar o tipo
    info_sv = SINAIS_VITAIS[tipo_sinal]
    st.markdown(
        f"""
        <div class="loinc-info">
            Código LOINC: <span class="loinc-code">{info_sv['loinc']}</span>
            &nbsp;·&nbsp; Display: <em>{info_sv['display']}</em>
            &nbsp;·&nbsp; Unidade padrão: <strong>{info_sv['unidade']}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Formulário de medição (apenas os campos de valor/data/hora) ───────────
    with st.form("form_observacao", clear_on_submit=False):
        st.markdown("#### Passo 3 — Medição")

        col_val, col_unit, col_data = st.columns(3)
        with col_val:
            valor = st.number_input(
                f"Valor ({info_sv['unidade']}) *",
                min_value=float(info_sv["min"]),
                max_value=float(info_sv["max"]),
                value=float((info_sv["min"] + info_sv["max"]) / 2),
                step=float(info_sv["step"]),
                format="%.1f",
                help=f"Intervalo esperado: {info_sv['min']} – {info_sv['max']}",
            )
        with col_unit:
            unidade = st.text_input(
                "Unidade *",
                value=info_sv["unidade"],
                help="Unidade de medida (UCUM)",
            )
        with col_data:
            data_exec = st.date_input(
                "Data da observação *",
                value=datetime.now().date(),
            )

        hora_exec = st.time_input(
            "Hora da observação *",
            value=datetime.now().time(),
        )

        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "Registar Observação",
            use_container_width=True,
            type="primary",
        )

    # ── Processar submissão ────────────────────────────────────────────────────
    if submitted:
        if not patient_fhir_id:
            st.error("Verifique o N.º de Utente SNS antes de registar (Passo 1).")
        else:
            # Extrair ID numérico do FHIR ID (ex: "pat-1" → "1")
            id_numerico = patient_fhir_id.replace("pat-", "")

            # Combinar data + hora em ISO 8601
            dt_combined = datetime.combine(data_exec, hora_exec)
            data_iso = dt_combined.strftime("%Y-%m-%dT%H:%M:%SZ")

            payload = {
                "estado": estado,
                "codigo": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": info_sv["loinc"],
                        "display": info_sv["display"],
                    }],
                    "text": info_sv["display"],
                },
                "referencia": f"Patient/pat-{id_numerico}",
                "dataExecucao": data_iso,
                "medicao": {
                    "valor": float(valor),
                    "unidade": unidade.strip(),
                    "sistema": info_sv["sistema_unit"],
                    "code": unidade.strip(),
                },
            }

            try:
                with st.spinner("A registar observação no servidor FHIR..."):
                    resultado = criar_observacao(payload, headers)

                st.success(
                    f"Observação registada com sucesso! "
                    f"FHIR ID: {resultado.get('id', '—')} "
                    f"· Tipo: **{tipo_sinal}** · Valor: **{valor} {unidade}**"
                )

                with st.expander("Ver recurso FHIR criado"):
                    st.json(resultado)

                st.info("Aceda ao Dashboard para consultar os gráficos de sinais vitais deste utente.")

            except Exception as e:
                detalhe = str(e)
                if hasattr(e, "response") and e.response is not None:
                    try:
                        detalhe = e.response.json().get("detail", e.response.text)
                    except Exception:
                        detalhe = e.response.text
                st.error(f"Erro ao registar observação: {detalhe}")

# ══════════════════════════════════════════════════════════════
# TAB 2 — CONSULTAR OBSERVAÇÕES
# ══════════════════════════════════════════════════════════════
with tab_consultar:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Pesquisar observações de um paciente")

    col_pid, col_btn2 = st.columns([4, 1])
    with col_pid:
        patient_id_pesq = st.text_input(
            "ID local do paciente (número)",
            placeholder="Introduza o ID do paciente (Ex: 1)",
            key="pesq_obs_id",
            label_visibility="collapsed",
        )
    with col_btn2:
        btn_pesq_obs = st.button("Pesquisar", key="btn_pesq_obs")

    if btn_pesq_obs and patient_id_pesq.strip():
        try:
            with st.spinner("A consultar observações..."):
                entries = pesquisar_observacoes(patient_id_pesq.strip(), headers)

            if not entries:
                st.info("Nenhuma observação encontrada para este paciente.")
            else:
                st.success(f"{len(entries)} observação(ões) encontrada(s).")

                for entry in entries:
                    resource = entry.get("resource", entry)
                    obs_id = resource.get("id", "—")
                    coding = resource.get("code", {}).get("coding", [{}])
                    tipo = coding[0].get("display", "—") if coding else "—"
                    loinc = coding[0].get("code", "—") if coding else "—"
                    vq = resource.get("valueQuantity", {})
                    valor_obs = vq.get("value", "—")
                    unidade_obs = vq.get("unit", "—")
                    data_obs = resource.get("effectiveDateTime", "—")
                    status_obs = resource.get("status", "—")

                    # Formatar data
                    try:
                        data_fmt = datetime.fromisoformat(data_obs.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        data_fmt = data_obs

                    st.markdown(
                        f"""
                        <div class="premium-card" style="padding: 1.2rem !important; margin-bottom: 0.5rem !important;">
                            <strong style="font-size:1.1rem; font-family:'Outfit';">{tipo}</strong> &nbsp;
                            <span class="tag-badge" style="font-family:monospace;">{loinc}</span><br>
                            <span style="font-size:0.88rem; line-height:1.6; margin-top:0.4rem; display:block;">
                                Medição: <strong>{valor_obs} {unidade_obs}</strong> &nbsp;·&nbsp; 
                                Data: {data_fmt} &nbsp;·&nbsp; 
                                Estado: {status_obs} &nbsp;·&nbsp; 
                                ID: {obs_id}
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"Erro ao consultar observações: {e}")
    elif btn_pesq_obs:
        st.warning("Introduza o ID numérico do paciente.")
