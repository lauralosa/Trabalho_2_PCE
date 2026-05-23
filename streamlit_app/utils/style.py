"""
style.py — Centralizador de estilos CSS personalizados para o PCE Dashboard.
Aplica a estética Pastel Premium baseada no mockup de inspiração (Light mode, lavanda e rosa).
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

        /* Aplicar fonte global */
        html, body, [class*="css"], .stMarkdown {
            font-family: 'Outfit', 'Inter', sans-serif;
            color: #1c2b3e !important;
        }

        /* Ajustes no fundo principal */
        .main .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }

        /* Sidebar elegante e clean (Light mode) */
        section[data-testid="stSidebar"] {
            background-color: #dce7f5 !important;
            border-right: 1px solid rgba(28, 43, 62, 0.08);
        }

        /* Esconder links automáticos feios do Streamlit */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            padding-top: 2rem;
        }

        /* Inputs estilizados (caixas de texto, selects e números) */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stNumberInput > div > div > input,
        .stTextArea > div > div > textarea,
        .stDateInput > div > div > input,
        .stTimeInput > div > div > input {
            border-radius: 16px !important;
            border: 1px solid rgba(28, 43, 62, 0.12) !important;
            background-color: rgba(255, 255, 255, 0.9) !important;
            color: #1c2b3e !important;
            font-weight: 500 !important;
            padding: 0.4rem 1rem !important;
            box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.02) !important;
            transition: all 0.2s ease;
        }
        
        .stTextInput > div > div > input:focus,
        .stSelectbox > div > div:focus,
        .stNumberInput > div > div > input:focus {
            border-color: #f2afc6 !important;
            box-shadow: 0 0 0 3px rgba(242, 175, 198, 0.25) !important;
        }

        /* Estilização para Rádios e Checkboxes */
        div[data-testid="stMarkdownContainer"] p {
            font-weight: 500;
        }

        /* Botões Redondos Estilo Premium (Semelhante ao Week/Today da Imagem) */
        .stButton > button {
            background-color: #1c2b3e !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 20px !important;
            font-weight: 600 !important;
            padding: 0.5rem 1.8rem !important;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
            box-shadow: 0 4px 6px rgba(28, 43, 62, 0.08) !important;
            text-transform: none;
            letter-spacing: 0.3px;
        }
        .stButton > button:hover {
            background-color: #2c3e50 !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 6px 12px rgba(28, 43, 62, 0.15) !important;
            color: #ffffff !important;
        }
        .stButton > button:active {
            transform: translateY(0.5px) !important;
        }

        /* Botão Primário Especial (Rosa de Acento) */
        .stButton > button[kind="primary"] {
            background-color: #f2afc6 !important;
            color: #1c2b3e !important;
            font-weight: 700 !important;
            box-shadow: 0 4px 10px rgba(242, 175, 198, 0.3) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #fcaec1 !important;
            box-shadow: 0 6px 15px rgba(242, 175, 198, 0.45) !important;
            color: #1c2b3e !important;
        }

        /* Cards em Glassmorphism Premium (Branco translúcido com blur) */
        .premium-card {
            background: rgba(255, 255, 255, 0.65) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255, 255, 255, 0.5) !important;
            border-radius: 24px !important;
            padding: 1.8rem 2rem !important;
            box-shadow: 0 10px 30px rgba(28, 43, 62, 0.04) !important;
            margin-bottom: 1.5rem !important;
            color: #1c2b3e !important;
        }

        /* Estilo dos Cards Métricos Nativos */
        [data-testid="metric-container"] {
            background: rgba(255, 255, 255, 0.65) !important;
            backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            border-radius: 20px !important;
            padding: 1.2rem !important;
            box-shadow: 0 8px 24px rgba(28, 43, 62, 0.03) !important;
        }
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            color: #1c2b3e !important;
            font-weight: 700 !important;
            font-size: 1.8rem !important;
        }
        [data-testid="metric-container"] [data-testid="stMetricLabel"] {
            color: #5c6e84 !important;
            font-weight: 600 !important;
            font-size: 0.85rem !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Estilização para Abas (Tabs) */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px !important;
            background: rgba(255, 255, 255, 0.4) !important;
            border-radius: 20px !important;
            padding: 5px !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 16px !important;
            color: #5c6e84 !important;
            font-weight: 600 !important;
            padding: 0.5rem 1.2rem !important;
            transition: all 0.2s ease !important;
            border: none !important;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1c2b3e !important;
            color: #ffffff !important;
            box-shadow: 0 4px 10px rgba(28, 43, 62, 0.1) !important;
        }

        /* Badges e tags */
        .tag-badge {
            background-color: rgba(28, 43, 62, 0.08) !important;
            color: #1c2b3e !important;
            border-radius: 12px !important;
            padding: 4px 10px !important;
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            display: inline-block;
        }

        /* Alertas customizados */
        .stAlert {
            border-radius: 18px !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            background-color: rgba(255, 255, 255, 0.6) !important;
            backdrop-filter: blur(8px) !important;
            box-shadow: 0 4px 12px rgba(28, 43, 62, 0.02) !important;
        }

        /* Tabelas e Dataframes */
        div[data-testid="stDataFrame"] {
            background-color: rgba(255, 255, 255, 0.6) !important;
            border-radius: 18px !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(28, 43, 62, 0.02) !important;
        }

        /* Divisores customizados */
        hr {
            border-color: rgba(28, 43, 62, 0.08) !important;
            margin: 1.5rem 0 !important;
        }

        /* Animações e transições */
        * {
            transition: background-color 0.2s ease, border-color 0.2s ease;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
