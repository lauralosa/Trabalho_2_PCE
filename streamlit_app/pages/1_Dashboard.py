"""
1_Dashboard.py — Dashboard de Sinais Vitais
Visualiza o histórico de sinais vitais de um utente a partir do EHRbase e HAPI FHIR.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import require_auth, get_auth_headers
from utils.ehrbase_client import (
    get_ehr_by_subject,
    query_sinais_vitais_aql,
    get_sinais_vitais_fhir_proxy,
    MAPA_SINAIS_VITAIS,
)

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard — PCE",
    page_icon="📊",
    layout="wide",
)

HAPI_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:9090/fhir")

# CSS adicional para o dashboard
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .dashboard-header {
        background: linear-gradient(135deg, rgba(13,115,119,0.2), rgba(20,160,133,0.1));
        border: 1px solid rgba(13,115,119,0.3);
        border-radius: 14px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.5rem;
    }
    .dashboard-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; }
    .dashboard-header p  { margin: 0.3rem 0 0 0; color: #64748b; font-size: 0.9rem; }

    .vital-card {
        background: rgba(17,24,39,0.9);
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        transition: border-color 0.3s;
    }
    .vital-card:hover { border-color: #0d7377; }
    .vital-card .vc-emoji  { font-size: 1.8rem; }
    .vital-card .vc-label  { font-size: 0.78rem; color: #64748b; margin: 0.3rem 0 0.1rem; }
    .vital-card .vc-value  { font-size: 1.7rem; font-weight: 700; color: #e2e8f0; }
    .vital-card .vc-unit   { font-size: 0.8rem; color: #94a3b8; }
    .vital-card .vc-date   { font-size: 0.7rem; color: #475569; margin-top: 0.4rem; }

    .patient-info-card {
        background: rgba(13,115,119,0.08);
        border: 1px solid rgba(13,115,119,0.25);
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1.5rem;
    }

    .stButton > button {
        background: linear-gradient(135deg, #0d7377, #14a085);
        color: white; border: none; border-radius: 8px; font-weight: 600;
    }
    .stButton > button:hover { transform: translateY(-1px); }

    [data-testid="metric-container"] {
        background: rgba(13,115,119,0.1);
        border: 1px solid rgba(13,115,119,0.3);
        border-radius: 12px; padding: 1rem;
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
    <div class="dashboard-header">
        <h1>📊 Dashboard de Sinais Vitais</h1>
        <p>Consulta o histórico clínico de um utente pelo N.º de Utente SNS</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Pesquisa por N.º de Utente ───────────────────────────────────────────────
col_search, col_btn = st.columns([4, 1])
with col_search:
    numero_utente = st.text_input(
        "🔍 N.º de Utente SNS",
        placeholder="Ex: 123456789",
        label_visibility="collapsed",
        key="dashboard_sns_input",
    )
with col_btn:
    pesquisar = st.button("Pesquisar", use_container_width=True, type="primary")

st.markdown("---")

# ─── Resultados ───────────────────────────────────────────────────────────────
if pesquisar and numero_utente.strip():
    numero_utente = numero_utente.strip()

    # 1. Verificar se existe EHR no EHRbase
    with st.spinner("A consultar o EHRbase..."):
        ehr = get_ehr_by_subject(numero_utente)

    # 2. Buscar dados do paciente no FHIR
    import requests as req
    patient_info = None
    try:
        r = req.get(
            f"{HAPI_URL}/Patient",
            params={"identifier": f"https://www.sns.gov.pt/utente|{numero_utente}"},
            timeout=8,
        )
        if r.status_code == 200:
            bundle = r.json()
            entries = bundle.get("entry", [])
            if entries:
                patient_info = entries[0]["resource"]
    except Exception:
        pass

    # ── Informação do Paciente ────────────────────────────────────────────────
    if patient_info:
        nome = patient_info.get("name", [{}])[0].get("text", "Desconhecido")
        genero = patient_info.get("gender", "—").capitalize()
        fhir_id = patient_info.get("id", "—")
        telecoms = patient_info.get("telecom", [])
        contacto_tel = next((t["value"] for t in telecoms if t.get("system") == "phone"), "—")
        contacto_email = next((t["value"] for t in telecoms if t.get("system") == "email"), "—")

        st.markdown(
            f"""
            <div class="patient-info-card">
                <table style="width:100%; border:none;">
                    <tr>
                        <td style="width:60px; vertical-align:middle;">
                            <span style="font-size:2.5rem;">{'👩' if genero.lower() in ['female','feminino','f'] else '👨'}</span>
                        </td>
                        <td style="vertical-align:middle;">
                            <strong style="font-size:1.2rem; color:#e2e8f0;">{nome}</strong><br>
                            <span style="color:#64748b; font-size:0.85rem;">
                                SNS: <strong style="color:#0d7377;">{numero_utente}</strong> &nbsp;|&nbsp;
                                Género: {genero} &nbsp;|&nbsp;
                                FHIR ID: {fhir_id} &nbsp;|&nbsp;
                                ☎ {contacto_tel} &nbsp;|&nbsp;
                                ✉ {contacto_email}
                            </span>
                        </td>
                        <td style="text-align:right; vertical-align:middle;">
                            <span style="background:{'rgba(13,115,119,0.2)' if ehr else 'rgba(239,68,68,0.15)'}; 
                                   border:1px solid {'#0d7377' if ehr else '#ef4444'};
                                   border-radius:20px; padding:4px 12px; font-size:0.8rem;
                                   color:{'#0d7377' if ehr else '#ef4444'};">
                                {'✅ EHR Registado' if ehr else '⚠️ Sem EHR'}
                            </span>
                        </td>
                    </tr>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"⚠️ Nenhum paciente encontrado com o N.º de Utente **{numero_utente}**.")

    # ── Sinais Vitais ─────────────────────────────────────────────────────────
    # Estratégia: tenta EHRbase AQL primeiro; se vazio usa FHIR como fallback
    registos = []
    fonte = "EHRbase"

    if ehr:
        with st.spinner("A consultar sinais vitais no EHRbase (AQL)..."):
            registos = query_sinais_vitais_aql(numero_utente)

    if not registos:
        with st.spinner("A consultar sinais vitais no HAPI FHIR..."):
            registos = get_sinais_vitais_fhir_proxy(numero_utente, HAPI_URL)
            fonte = "HAPI FHIR"

    if not registos:
        st.info(
            "📭 Ainda não existem sinais vitais registados para este utente. "
            "Regista observações na página **Observações**."
        )
        st.stop()

    st.caption(f"📡 Fonte de dados: **{fonte}** · {len(registos)} registos encontrados")

    # ── DataFrame ─────────────────────────────────────────────────────────────
    df = pd.DataFrame(registos)

    # Normalizar nomes de colunas conforme a fonte
    if "tipo" not in df.columns and "name" in df.columns:
        df = df.rename(columns={"name": "tipo"})
    if "data" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "data"})

    # Converter datas
    if "data" in df.columns:
        df["data_dt"] = pd.to_datetime(df["data"], errors="coerce", utc=True)
        df["data_fmt"] = df["data_dt"].dt.strftime("%d/%m/%Y %H:%M")
    else:
        df["data_dt"] = None
        df["data_fmt"] = "—"

    # ── Cards com valor mais recente ──────────────────────────────────────────
    st.markdown("### 📌 Valores Mais Recentes")

    tipos_unicos = df["tipo"].dropna().unique().tolist()
    cols_cards = st.columns(min(len(tipos_unicos), 4))

    for i, tipo in enumerate(tipos_unicos[:8]):
        df_tipo = df[df["tipo"] == tipo].sort_values("data_dt", ascending=False)
        ultimo = df_tipo.iloc[0] if not df_tipo.empty else None

        # Encontrar emoji e unidade do mapa
        emoji = "📊"
        unidade_default = ""
        for info in MAPA_SINAIS_VITAIS.values():
            if info["nome"].lower() in tipo.lower():
                emoji = info["emoji"]
                unidade_default = info["unidade"]
                break

        valor = ultimo["valor"] if ultimo is not None and pd.notna(ultimo.get("valor")) else "—"
        unidade = ultimo.get("unidade", unidade_default) if ultimo is not None else unidade_default
        data_str = ultimo.get("data_fmt", "—") if ultimo is not None else "—"

        col_idx = i % min(len(tipos_unicos), 4)
        with cols_cards[col_idx]:
            st.markdown(
                f"""
                <div class="vital-card">
                    <div class="vc-emoji">{emoji}</div>
                    <div class="vc-label">{tipo}</div>
                    <div class="vc-value">{f"{valor:.1f}" if isinstance(valor, float) else valor}</div>
                    <div class="vc-unit">{unidade}</div>
                    <div class="vc-date">📅 {data_str}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Abas: Gráficos + Tabela ───────────────────────────────────────────────
    tab_graficos, tab_tabela = st.tabs(["📈 Gráficos", "📋 Tabela de Registos"])

    with tab_graficos:
        if "data_dt" in df.columns and df["data_dt"].notna().any():
            # Um gráfico por tipo de sinal vital
            for tipo in tipos_unicos:
                df_tipo = (
                    df[df["tipo"] == tipo]
                    .dropna(subset=["data_dt", "valor"])
                    .sort_values("data_dt")
                )
                if df_tipo.empty or len(df_tipo) < 1:
                    continue

                unidade = df_tipo["unidade"].iloc[0] if "unidade" in df_tipo.columns else ""
                emoji = "📊"
                for info in MAPA_SINAIS_VITAIS.values():
                    if info["nome"].lower() in tipo.lower():
                        emoji = info["emoji"]
                        break

                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=df_tipo["data_dt"],
                        y=df_tipo["valor"],
                        mode="lines+markers",
                        name=tipo,
                        line=dict(color="#0d7377", width=2.5),
                        marker=dict(size=8, color="#14a085", symbol="circle"),
                        hovertemplate=f"<b>{tipo}</b><br>Valor: %{{y:.1f}} {unidade}<br>Data: %{{x|%d/%m/%Y %H:%M}}<extra></extra>",
                    )
                )

                fig.update_layout(
                    title=dict(
                        text=f"{emoji} {tipo}",
                        font=dict(size=15, color="#e2e8f0"),
                    ),
                    template="plotly_dark",
                    paper_bgcolor="rgba(17,24,39,0.5)",
                    plot_bgcolor="rgba(10,14,26,0.5)",
                    height=300,
                    margin=dict(l=40, r=20, t=50, b=40),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor="rgba(30,41,59,0.8)",
                        title="Data",
                        title_font=dict(color="#64748b"),
                    ),
                    yaxis=dict(
                        showgrid=True,
                        gridcolor="rgba(30,41,59,0.8)",
                        title=f"{unidade}",
                        title_font=dict(color="#64748b"),
                    ),
                    hoverlabel=dict(
                        bgcolor="#111827",
                        bordercolor="#0d7377",
                        font=dict(color="#e2e8f0"),
                    ),
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Dados de data insuficientes para gerar gráficos.")

    with tab_tabela:
        cols_show = [c for c in ["data_fmt", "tipo", "valor", "unidade"] if c in df.columns]
        df_display = df[cols_show].rename(
            columns={
                "data_fmt": "Data/Hora",
                "tipo": "Tipo de Sinal Vital",
                "valor": "Valor",
                "unidade": "Unidade",
            }
        )
        st.dataframe(
            df_display.sort_values("Data/Hora", ascending=False)
              .reset_index(drop=True),
            use_container_width=True,
            height=400,
        )

        # Export CSV
        csv = df_display.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            "⬇️ Exportar CSV",
            data=csv,
            file_name=f"sinais_vitais_{numero_utente}.csv",
            mime="text/csv",
        )

elif pesquisar and not numero_utente.strip():
    st.warning("⚠️ Introduz o N.º de Utente SNS para pesquisar.")
