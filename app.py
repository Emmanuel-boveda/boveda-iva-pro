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
                                        
                                        # GENERACIÓN DE CÓDIGO DE REFERIDO CON DIGITOS VERIFICADORES (Ej: CONTADOR1610)
                                        codigo_ref = user_data.get("codigo_referido")
                                        if not codigo_ref:
                                            base_nombre = usuario_input.split("@")[0].upper()
                                            if fecha_exp:
                                                try:
                                                    dt_exp = datetime.strptime(str(fecha_exp), "%Y-%m-%d")
                                                    digitos_fecha = dt_exp.strftime("%d%m") # Día y mes de expiración/anualidad
                                                except:
                                                    digitos_fecha = datetime.now().strftime("%d%m")
                                            else:
                                                digitos_fecha = datetime.now().strftime("%d%m")
                                            
                                            codigo_ref = f"{base_nombre}{digitos_fecha}"
                                        
                                        st.session_state["autenticado"] = True
                                        st.session_state["usuario_email"] = usuario_input
                                        st.session_state["plan_activo"] = user_data.get("plan", "Plan Básico")
                                        st.session_state["fecha_expiracion"] = str(fecha_exp) if fecha_exp else "Indefinida"
                                        st.session_state["codigo_referido"] = codigo_ref
                                        
                                        registrar_log(usuario_input, "LOGIN", "Inicio de sesión exitoso")
                                        
                                        st.success("¡Acceso concedido! Entrando al sistema...")
                                        st.rerun()
                                else:
                                    st.error("❌ Contraseña incorrecta.")
                        except Exception as e:
                            st.error(f"Error al validar el acceso: {e}")

    with tab_planes:
        st.markdown("<br>", unsafe_allow_html=True)
        st.info("🧾 **Precios en Pesos Mexicanos (MXN) con IVA INCLUIDO.** Al realizar tu pago por WhatsApp, compártenos tu Constancia de Situación Fiscal para emitirte tu factura correspondiente al instante.")
        st.success("""🎁 **¡Programa de Beneficios Compartidos por Referidos Anuales!**

*(Aplica únicamente cuando ambas partes cuentan o adquieren una **Licencia Anual**)*

• **Para ti (Nuevo Cliente):** Ingresa el código de un colega con Licencia Anual al contratar tu **Plan Anual** y obtén **15 días GRATIS extras**.
• **Para quien te recomendó:** Le regalamos **2 meses GRATIS** aplicados a su suscripción anual.""")
        
        cod_invitacion_ingresado = st.text_input("¿Tienes un Código de Invitación de algún colega? (Opcional):", placeholder="Ej: JUANITA1610").strip().upper()
        
        col_p1, col_p2 = st.columns(2)
        ref_text = f"%20(C%C3%B3digo%20Referido:%20{cod_invitacion_ingresado}%20-%20Aplica%2015%20d%C3%ADas%20extra%20en%20Anual)" if cod_invitacion_ingresado else ""

        with col_p1:
            st.markdown("""
                <div style="padding: 22px; border: 2px solid #3b82f6; border-radius: 12px; background: #f8fafc; text-align: center; height: 100%;">
                    <h3 style="color: #1e3c72; margin-top: 0; margin-bottom: 5px;">Plan Básico</h3>
                    <p style="color: #2563eb; font-weight: bold; font-size: 0.85rem; margin-bottom: 15px;">PRECIOS EN MXN — IVA INCLUIDO</p>
                    <div style="background: white; padding: 12px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 15px;">
                        <p style="font-size: 1.4rem; font-weight: bold; color: #0f172a; margin:0;">$49 MXN <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">/ mes</span></p>
                        <hr style="margin: 8px 0; border: 0; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 1.4rem; font-weight: bold; color: #16a34a; margin:0;">$399 MXN <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">/ año (Aplica Referidos)</span></p>
                    </div>
                    <ul style="text-align: left; font-size: 0.9rem; color: #334155; padding-left: 15px; margin-bottom: 20px;">
                        <li>Hasta <b>5 RFCs</b> de contribuyentes</li>
                        <li>Motor FIFO automático</li>
                        <li>Lectura de acuses PDF SAT</li>
                        <li>Papeles de Trabajo en Excel/CSV</li>
                        <li>Soporte técnico por WhatsApp</li>
                    </ul>
                </div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f'<a href="https://wa.me/5217226513054?text=Hola,%20deseo%20comprar%20el%20Plan%20B%C3%A1sico%20de%20B%C3%B3veda%20IVA%20Pro{ref_text}" target="_blank"><div style="text-align:center; background:#22c55e; color:white; padding:12px; border-radius:8px; font-weight:bold; text-decoration:none; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">Adquirir Plan Básico en WhatsApp</div></a>', unsafe_allow_html=True)

        with col_p2:
            st.markdown("""
                <div style="padding: 22px; border: 2px solid #1e3c72; border-radius: 12px; background: #f0fdf4; text-align: center; height: 100%;">
                    <h3 style="color: #1e3c72; margin-top: 0; margin-bottom: 5px;">Plan Ilimitado</h3>
                    <p style="color: #16a34a; font-weight: bold; font-size: 0.85rem; margin-bottom: 15px;">PRECIOS EN MXN — IVA INCLUIDO — IDEAL PARA DESPACHOS</p>
                    <div style="background: white; padding: 12px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 15px;">
                        <p style="font-size: 1.4rem; font-weight: bold; color: #0f172a; margin:0;">$99 MXN <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">/ mes</span></p>
                        <hr style="margin: 8px 0; border: 0; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 1.4rem; font-weight: bold; color: #16a34a; margin:0;">$999 MXN <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">/ año (Aplica Referidos)</span></p>
                    </div>
                    <ul style="text-align: left; font-size: 0.9rem; color: #334155; padding-left: 15px; margin-bottom: 20px;">
                        <li>RFCs <b>Ilimitados</b> de contribuyentes</li>
                        <li>Motor FIFO automático</li>
                        <li>Lectura avanzada PDF SAT</li>
                        <li>Papeles de Trabajo en Excel/CSV</li>
                        <li>Prioridad en atención y soporte</li>
                    </ul>
                </div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f'<a href="