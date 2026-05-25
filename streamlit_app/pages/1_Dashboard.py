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
from utils.style import apply_custom_style
from utils.ehrbase_client import (
    get_ehr_by_subject,
    query_sinais_vitais_aql,
    get_sinais_vitais_fhir_proxy,
    MAPA_SINAIS_VITAIS,
)

# ─── Configuração ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard — SyncHealth",
    page_icon="📊",
    layout="wide",
)

HAPI_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:9090/fhir")

# Aplicar estilo premium global
apply_custom_style()

# ─── Auth ─────────────────────────────────────────────────────────────────────
token = require_auth()
headers = get_auth_headers()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="premium-card">
        <h1 style="font-size: 1.8rem; font-weight: 700; margin:0;">Dashboard de Sinais Vitais</h1>
        <p style="margin: 0.3rem 0 0 0; font-size: 0.9rem;">Consulta de histórico clínico integrado por número de utente SNS</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Pesquisa por N.º de Utente ───────────────────────────────────────────────
col_search, col_btn = st.columns([4, 1])
with col_search:
    numero_utente = st.text_input(
        "N.º de Utente SNS",
        placeholder="Introduza o N.º de Utente SNS (Ex: 123456789)",
        label_visibility="collapsed",
        key="dashboard_sns_input",
    )
with col_btn:
    pesquisar = st.button("Pesquisar", use_container_width=True, type="primary")

st.markdown("<br>", unsafe_allow_html=True)

# ─── Resultados ───────────────────────────────────────────────────────────────
if pesquisar and numero_utente.strip():
    numero_utente = numero_utente.strip()

    # 1. Buscar dados do paciente no FHIR (necessário para obter o FHIR Patient ID
    #    que é o subject_id com que o backend criou o EHR no EHRbase)
    import requests as req
    patient_info = None
    patient_fhir_id = None
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
                patient_fhir_id = patient_info.get("id", "")  # ex: "pat-1"
    except Exception:
        pass

    # 2. Verificar se existe EHR no EHRbase usando o FHIR Patient ID como subject_id
    #    (o backend guardou o EHR com subject_id=patient_fhir_id e namespace=pt_sns_utente)
    ehr = None
    if patient_fhir_id:
        with st.spinner("A consultar o EHRbase..."):
            ehr = get_ehr_by_subject(patient_fhir_id)

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
            <div class="premium-card" style="background: rgba(255, 255, 255, 0.75) !important;">
                <table style="width:100%; border:none; border-collapse:collapse;">
                    <tr>
                        <td style="width:65px; vertical-align:middle;">
                            <span style="font-size:2.5rem;">{'👩' if genero.lower() in ['female','feminino','f'] else '👨'}</span>
                        </td>
                        <td style="vertical-align:middle;">
                            <strong style="font-size:1.3rem; font-family:'Outfit';">{nome}</strong><br>
                            <span style="font-size:0.88rem; line-height:1.6;">
                                SNS: <strong>{numero_utente}</strong> &nbsp;·&nbsp;
                                Género: {genero} &nbsp;·&nbsp;
                                FHIR ID: {fhir_id} &nbsp;·&nbsp;
                                Telemóvel: {contacto_tel} &nbsp;·&nbsp;
                                Email: {contacto_email}
                            </span>
                        </td>
                        <td style="text-align:right; vertical-align:middle;">
                            <span class="tag-badge" style="background: {'rgba(6, 182, 212, 0.1)' if ehr else 'rgba(239,68,68,0.1)'} !important; 
                                   border: 1px solid {'rgba(6, 182, 212, 0.3)' if ehr else 'rgba(239,68,68,0.3)'} !important; 
                                   border-radius:20px; padding:6px 14px; font-size:0.8rem; font-weight:600;
                                   color:{'var(--accent-cyan)' if ehr else '#ef4444'};">
                                {'EHR Ativo' if ehr else 'Sem Registo EHR'}
                            </span>
                        </td>
                    </tr>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"Nenhum paciente encontrado com o N.º de Utente SNS {numero_utente}.")

    # ── Sinais Vitais ─────────────────────────────────────────────────────────
    # Estratégia: tenta EHRbase AQL primeiro; se vazio usa FHIR como fallback
    registos = []
    fonte = "EHRbase"

    if ehr and patient_fhir_id:
        with st.spinner("A consultar sinais vitais no EHRbase (AQL)..."):
            registos = query_sinais_vitais_aql(patient_fhir_id)

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
    st.markdown("### Valores Mais Recentes")

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

        valor_fmt = f"{valor:.1f}" if isinstance(valor, float) else valor

        col_idx = i % min(len(tipos_unicos), 4)
        with cols_cards[col_idx]:
            st.markdown(
                f"""
                <div class="premium-card" style="padding: 1rem !important; text-align: center; margin-bottom: 1rem !important; min-height: 120px; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; height: 35px; overflow: hidden; display: flex; align-items: center; justify-content: center;">{tipo}</div>
                    <div style="font-size: 2.2rem; font-weight: 700; line-height: 1.1; margin: 0.2rem 0; font-family:'Outfit';">
                        {valor_fmt} <span style="font-size: 0.95rem; font-weight: 500;">{unidade}</span>
                    </div>
                    <div style="font-size: 0.7rem; margin-top: 0.5rem; opacity: 0.7;">{data_str}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Abas: Gráficos + Tabela ───────────────────────────────────────────────
    tab_graficos, tab_tabela = st.tabs(["Gráficos", "Tabela de Registos"])

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
                        line=dict(color="#06b6d4", width=2.5),
                        marker=dict(size=8, color="#0f172a", line=dict(color="#06b6d4", width=2), symbol="circle"),
                        hovertemplate=f"<b>{tipo}</b><br>Valor: %{{y:.1f}} {unidade}<br>Data: %{{x|%d/%m/%Y %H:%M}}<extra></extra>",
                    )
                )

                fig.update_layout(
                    title=dict(
                        text=f"{emoji} {tipo} ({unidade})",
                        font=dict(size=14, color="#f1f5f9", family="Outfit"),
                    ),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    height=280,
                    margin=dict(l=40, r=20, t=50, b=40),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor="rgba(255, 255, 255, 0.05)",
                        title="Data",
                        title_font=dict(color="#94a3b8", size=11),
                        tickfont=dict(color="#94a3b8", size=10),
                    ),
                    yaxis=dict(
                        showgrid=True,
                        gridcolor="rgba(255, 255, 255, 0.05)",
                        title_font=dict(color="#94a3b8", size=11),
                        tickfont=dict(color="#94a3b8", size=10),
                    ),
                    hoverlabel=dict(
                        bgcolor="#1e293b",
                        bordercolor="#06b6d4",
                        font=dict(color="#f1f5f9"),
                    ),
                )
                
                # Envolver o gráfico no nosso design de card glassmorphism
                st.markdown('<div class="premium-card" style="padding: 1.5rem !important;">', unsafe_allow_html=True)
                st.plotly_chart(fig, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
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

        st.markdown("<br>", unsafe_allow_html=True)
        # Export CSV
        csv = df_display.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            "Exportar CSV",
            data=csv,
            file_name=f"sinais_vitais_{numero_utente}.csv",
            mime="text/csv",
        )

elif pesquisar and not numero_utente.strip():
    st.warning("Introduza o N.º de Utente SNS para pesquisar.")
