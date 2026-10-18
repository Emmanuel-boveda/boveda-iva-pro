import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pypdf
import re
from supabase import create_client, Client

# Configuración de la página
st.set_page_config(
    page_title="Bóveda IVA Pro - SaaS Fiscal", 
    page_icon="🏛️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- OCULTAR ELEMENTOS Y MENÚS DE STREAMLIT (PROTECCIÓN DE CÓDIGO) ---
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .viewerBadge_link__1S137 {display: none;}
    div[data-testid="stDecoration"] {display: none;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- CONEXIÓN A SUPABASE ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_supabase()
except Exception as e:
    st.error(f"Error al conectar con Supabase: {e}")

# --- FUNCIÓN DE REGISTRO DE AUDITORÍA (LOGS) ---
def registrar_log(email, accion, detalles):
    try:
        supabase.table("logs_actividad").insert({
            "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "usuario_email": email,
            "accion": accion,
            "detalles": detalles
        }).execute()
    except Exception as e:
        pass

# --- SISTEMA DE AUTENTICACIÓN (LOGIN Y COMPRA DE PLANES) ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_email"] = ""
    st.session_state["plan_activo"] = ""
    st.session_state["fecha_expiracion"] = ""
    st.session_state["codigo_referido"] = ""

if not st.session_state["autenticado"]:
    st.markdown("""
        <div style="max-width: 500px; margin: 40px auto 20px auto; padding: 25px; background: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border: 1px solid #cbd5e1; text-align: center;">
            <h2 style="color: #1e3c72; margin-bottom: 10px;">🏛️ Bóveda IVA Pro</h2>
            <p style="color: #64748b; font-size: 0.95rem; margin-bottom: 0;">Plataforma inteligente de gestión y acreditamiento de IVA.</p>
        </div>
    """, unsafe_allow_html=True)
    
    tab_login, tab_planes = st.tabs(["🔐 Iniciar Sesión", "💳 Conoce los Planes y Precios"])
    
    with tab_login:
        col1, col2, col3 = st.columns([1, 1.3, 1])
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("form_login"):
                usuario_input = st.text_input("Usuario (Correo Electrónico)").strip().lower()
                password_input = st.text_input("Contraseña de Acceso", type="password")
                btn_login = st.form_submit_button("Iniciar Sesión", use_container_width=True)
                
                if btn_login:
                    if not usuario_input or not password_input:
                        st.error("Por favor ingresa usuario y contraseña.")
                    else:
                        try:
                            res = supabase.table("usuarios_saas").select("*").eq("email", usuario_input).execute()
                            usuarios = res.data
                            
                            if not usuarios:
                                st.error("❌ El usuario no existe o no tiene una cuenta registrada.")
                            else:
                                user_data = usuarios[0]
                                if user_data.get("password") == password_input:
                                    if user_data.get("activo") == False:
                                        st.error("❌ Tu suscripción está suspendida o inactiva. Contacta a soporte.")
                                    else:
                                        fecha_exp = user_data.get("fecha_expiracion") or user_data.get("fecha_expiración")
                                        if fecha_exp:
                                            exp_date = datetime.strptime(str(fecha_exp), "%Y-%m-%d").date()
                                            if datetime.now().date() > exp_date:
                                                st.error("❌ Tu suscripción ha expirado. Realiza tu renovación para continuar.")
                                                st.stop()
                                        
                                        codigo_ref = user_data.get("codigo_referido")
                                        if not codigo_ref:
                                            base_nombre = usuario_input.split("@")[0].upper()
                                            if fecha_exp:
                                                try:
                                                    dt_exp = datetime.strptime(str(fecha_exp), "%Y-%m-%d")
                                                    digitos_fecha = dt_exp.strftime("%d%m")
                                                except:
                                                    digitos_fecha = datetime.now().strftime("%d%m")
                                            else:
                                                digitos_fecha = datetime.now().strftime("%d%m")
                                            
                                            codigo_ref = f"{base_nombre}{digitos_fecha}"
                                        
                                        st.session_state["autenticado"] = True
                                        st.session_state["usuario_email"] = usuario_input
                                        st.session_state["plan_activo"] = user_data.get("plan", "Plan Básico")
                                        st.session_state["fecha_expiracion"] = str(