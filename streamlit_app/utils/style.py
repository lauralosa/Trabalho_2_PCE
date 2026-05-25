"""
style.py — Centralizador de estilos CSS personalizados para o PCE Dashboard.
Estética: Midnight Glass (Dark Mode) - Premium, Glassmorphism, Cyan Accents.
"""
import streamlit as st

def apply_custom_style():
    """
    Injeta o CSS personalizado global em qualquer página Streamlit.
    """
    st.markdown(
        """
        <style>
        /* Importar fontes modernas e elegantes */
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap');

        /* Variáveis de Tema - Midnight Glass */
        :root {
            --bg-base: #0f172a;        /* Azul noite profundo (Slate 900) */
            --bg-sidebar: #1e293b;    /* Slate 800 */
            --text-primary: #f1f5f9;  /* Slate 100 */
            --text-muted: #94a3b8;    /* Slate 400 */
            --accent-cyan: #06b6d4;   /* Cyan 500 */
            --accent-cyan-hover: #22d3ee; /* Cyan 400 */
            --glass-bg: rgba(30, 41, 59, 0.7);
            --glass-border: rgba(255, 255, 255, 0.1);
        }

        /* Aplicar fonte global e forçar dark mode base */
        html, body, [class*="css"], .stMarkdown {
            font-family: 'Outfit', 'Inter', sans-serif;
            color: var(--text-primary) !important;
        }

        /* Fundo principal e Contentor */
        .stApp {
            background-color: var(--bg-base) !important;
            background-image: 
                radial-gradient(circle at 15% 50%, rgba(6, 182, 212, 0.08), transparent 25%),
                radial-gradient(circle at 85% 30%, rgba(14, 165, 233, 0.08), transparent 25%);
        }

        .main .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }

        /* Sidebar elegante e clean (Dark mode) */
        section[data-testid="stSidebar"] {
            background-color: var(--bg-sidebar) !important;
            border-right: 1px solid var(--glass-border) !important;
        }
        
        /* Ocultar fundo nativo da sidebar */
        [data-testid="stSidebar"] > div:first-child {
            background-color: transparent !important;
        }

        /* Esconder links automáticos feios do Streamlit */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            padding-top: 2rem;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] span {
            color: var(--text-muted);
        }

        /* Inputs estilizados (caixas de texto, selects e números) */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stNumberInput > div > div > input,
        .stTextArea > div > div > textarea,
        .stDateInput > div > div > input,
        .stTimeInput > div > div > input {
            border-radius: 12px !important;
            border: 1px solid var(--glass-border) !important;
            background-color: rgba(15, 23, 42, 0.8) !important;
            color: var(--text-primary) !important;
            font-weight: 400 !important;
            padding: 0.4rem 1rem !important;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2) !important;
            transition: all 0.3s ease;
        }
        
        /* Garantir que o texto do selectbox nunca é cortado */
        .stSelectbox > div > div {
            min-height: 2.6rem !important;
            height: auto !important;
            overflow: visible !important;
            line-height: 1.5 !important;
            display: flex !important;
            align-items: center !important;
        }
        .stSelectbox [data-baseweb="select"] > div:first-child {
            overflow: visible !important;
            white-space: normal !important;
            line-height: 1.5 !important;
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        
        /* Focus dos inputs (Efeito Neon Cyan) */
        .stTextInput > div > div > input:focus,
        .stSelectbox > div > div:focus,
        .stNumberInput > div > div > input:focus {
            border-color: var(--accent-cyan) !important;
            box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.25),
                        0 0 15px rgba(6, 182, 212, 0.15) !important;
        }

        /* Labels dos inputs */
        .stTextInput label, .stSelectbox label, .stNumberInput label, .stDateInput label, .stTimeInput label {
            color: var(--text-muted) !important;
            font-weight: 500 !important;
        }

        /* Botões Redondos Estilo Premium */
        .stButton > button {
            background-color: var(--bg-sidebar) !important;
            color: var(--text-primary) !important;
            border: 1px solid var(--glass-border) !important;
            border-radius: 16px !important;
            font-weight: 600 !important;
            padding: 0.5rem 1.8rem !important;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2) !important;
            text-transform: none;
            letter-spacing: 0.3px;
        }
        .stButton > button:hover {
            background-color: #334155 !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 15px rgba(0, 0, 0, 0.3) !important;
            border-color: rgba(255, 255, 255, 0.2) !important;
        }
        .stButton > button:active {
            transform: translateY(0.5px) !important;
        }

        /* Botão Primário Especial (Cyan Neon Acento) */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--accent-cyan), #0284c7) !important;
            color: #ffffff !important;
            border: none !important;
            font-weight: 700 !important;
            box-shadow: 0 4px 15px rgba(6, 182, 212, 0.3) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, var(--accent-cyan-hover), #0369a1) !important;
            box-shadow: 0 6px 20px rgba(6, 182, 212, 0.45) !important;
        }

        /* Cards em Glassmorphism Premium (Translúcido com blur) */
        .premium-card {
            background: var(--glass-bg) !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
            border: 1px solid var(--glass-border) !important;
            border-radius: 20px !important;
            padding: 1.8rem 2rem !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
            margin-bottom: 1.5rem !important;
            color: var(--text-primary) !important;
        }
        
        /* Títulos dentro de cards */
        .premium-card h1, .premium-card h2, .premium-card h3 {
            color: #ffffff !important;
        }
        /* Texto secundário dentro de cards */
        .premium-card p {
            color: var(--text-muted) !important;
        }

        /* Estilo dos Cards Métricos Nativos */
        [data-testid="metric-container"] {
            background: var(--glass-bg) !important;
            backdrop-filter: blur(12px) !important;
            border: 1px solid var(--glass-border) !important;
            border-radius: 16px !important;
            padding: 1.2rem !important;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2) !important;
        }
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            color: var(--accent-cyan) !important;
            font-weight: 700 !important;
            font-size: 1.8rem !important;
            text-shadow: 0 0 10px rgba(6, 182, 212, 0.2);
        }
        [data-testid="metric-container"] [data-testid="stMetricLabel"] {
            color: var(--text-muted) !important;
            font-weight: 600 !important;
            font-size: 0.85rem !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Estilização para Abas (Tabs) */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px !important;
            background: rgba(15, 23, 42, 0.5) !important;
            border-radius: 14px !important;
            padding: 6px !important;
            border: 1px solid var(--glass-border) !important;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 10px !important;
            color: var(--text-muted) !important;
            font-weight: 600 !important;
            padding: 0.5rem 1.2rem !important;
            transition: all 0.3s ease !important;
            border: none !important;
        }
        .stTabs [aria-selected="true"] {
            background-color: var(--bg-sidebar) !important;
            color: var(--accent-cyan) !important;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2) !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
        }

        /* Badges e tags */
        .tag-badge {
            background: rgba(6, 182, 212, 0.1) !important;
            color: var(--accent-cyan) !important;
            border: 1px solid rgba(6, 182, 212, 0.2) !important;
            border-radius: 12px !important;
            padding: 4px 10px !important;
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            display: inline-block;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Alertas customizados */
        .stAlert {
            border-radius: 16px !important;
            border: 1px solid var(--glass-border) !important;
            background-color: var(--glass-bg) !important;
            backdrop-filter: blur(8px) !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
        }

        /* Tabelas e Dataframes */
        div[data-testid="stDataFrame"] {
            background-color: var(--bg-sidebar) !important;
            border-radius: 16px !important;
            border: 1px solid var(--glass-border) !important;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2) !important;
        }
        /* Headers da tabela em dark mode */
        div[data-testid="stDataFrame"] th {
            background-color: #0f172a !important;
            color: var(--text-muted) !important;
            border-bottom: 1px solid var(--glass-border) !important;
        }
        div[data-testid="stDataFrame"] td {
            background-color: var(--bg-sidebar) !important;
            color: var(--text-primary) !important;
            border-bottom: 1px solid rgba(255,255,255,0.05) !important;
        }

        /* Info de códigos LOINC */
        .loinc-info {
            background-color: rgba(30, 41, 59, 0.8) !important;
            color: var(--text-muted) !important;
        }
        .loinc-code {
            color: var(--accent-cyan) !important;
            background-color: rgba(6, 182, 212, 0.1) !important;
            border: 1px solid rgba(6, 182, 212, 0.2) !important;
        }

        /* Divisores customizados */
        hr {
            border-color: rgba(255, 255, 255, 0.08) !important;
            margin: 1.5rem 0 !important;
        }

        /* Animações e transições globais */
        * {
            transition: background-color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
