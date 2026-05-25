from __future__ import annotations
import streamlit as st
import requests
import os

# Configuração de URLs
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:5000")


def do_login(username: str, password: str) -> dict | None:
    """
    Chama o endpoint /token do FastAPI e retorna
    o token de acesso ou None em caso de falha.
    """
    try:
        response = requests.post(
            f"{FASTAPI_URL}/token",
            data={"username": username, "password": password},
            timeout=5,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except requests.exceptions.ConnectionError:
        st.error("Não foi possível ligar ao servidor FastAPI. Verifique se está a correr.")
        return None


def show_login_sidebar():
    """
    Mostra o formulário de login na sidebar.
    Gere o estado de autenticação em st.session_state.
    Retorna True se o utilizador está autenticado.
    """
    st.sidebar.markdown(
        """
        <div style='text-align:center; padding: 20px 0 25px 0;'>
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">⚕️</div>
            <h2 style='margin:0; font-size:1.3rem; font-weight:700; font-family: Outfit;'>
                SyncHealth
            </h2>
            <p style='margin:2px 0 0 0; font-size:0.8rem; font-weight: 500;'>
                Plataforma de Integração Clínica
            </p>
            <p style='margin:10px 0 0 0; font-size:0.7rem;'>
                Universidade do Minho
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Já está autenticado
    if "token" in st.session_state and st.session_state.token:
        st.sidebar.success(f"Autenticado como **{st.session_state.username}**")
        if st.sidebar.button("Terminar Sessão", use_container_width=True):
            for key in ["token", "username"]:
                st.session_state.pop(key, None)
            st.rerun()
        return True

    # Formulário de login
    st.sidebar.markdown("### Entrar")
    with st.sidebar.form("login_form", clear_on_submit=False):
        username = st.text_input("Utilizador", value="admin", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)

        if submitted:
            result = do_login(username, password)
            if result:
                st.session_state.token = result["access_token"]
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Credenciais inválidas.")

    return False


def require_auth():
    """
    Helper para páginas que exigem autenticação.
    Chama show_login_sidebar() e bloqueia a página se não estiver autenticado.
    """
    authenticated = show_login_sidebar()
    if not authenticated:
        st.info("Efetue o login na barra lateral para continuar.")
        st.stop()
    return st.session_state.token


def get_auth_headers() -> dict:
    """Retorna os headers HTTP com o token Bearer."""
    token = st.session_state.get("token", "")
    return {"Authorization": f"Bearer {token}"}
