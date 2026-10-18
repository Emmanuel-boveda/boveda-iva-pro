import os
import re
from datetime import datetime, timedelta
import pandas as pd
import pypdf
from supabase import create_client, Client
import gradio as gr

# --- CONFIGURACIÓN DE SUPABASE ---
# Intenta obtener de Render Environment Variables o de secretos de Streamlit
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Si no están en variables de entorno, intenta cargarlas desde secrets.toml si existe
if not SUPABASE_URL or not SUPABASE_KEY:
    try:
        import streamlit as st
        SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
        SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        pass

def get_supabase_client():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            return None
    return None

supabase = get_supabase_client()

# --- FUNCIÓN DE LOGS ---
def registrar_log(email, accion, detalles):
    try:
        if supabase:
            supabase.table("logs_actividad").insert({
                "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "usuario_email": email,
                "accion": accion,
                "detalles": detalles
            }).execute()
    except Exception:
        pass

# --- CONSULTA DE SALDOS ---
def cargar_saldos(email):
    try:
        if not supabase: 
            return pd.DataFrame(columns=["ID", "RFC", "Periodo_Mes", "Periodo_Anio", "Num_Operacion", "Saldo_Disponible", "Estatus"])
        response = supabase.table("saldos_iva").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=["ID", "RFC", "Periodo_Mes", "Periodo_Anio", "Num_Operacion", "Saldo_Disponible", "Estatus"])
        df = pd.DataFrame(data)
        return df.rename(columns={
            "id": "ID", "rfc": "RFC", "periodo_mes": "Periodo_Mes", "periodo_anio": "Periodo_Anio",
            "tipo_declaracion": "Tipo_Declaracion", "num_operacion": "Num_Operacion",
            "fecha_presentacion": "Fecha_Presentacion", "saldo_original": "Saldo_Original",
            "saldo_disponible": "Saldo_Disponible", "estatus": "Estatus"
        })
    except Exception:
        return pd.DataFrame()

# --- AUTENTICACIÓN ---
def validar_login(email, password):
    email = email.strip().lower()
    if not email or not password:
        return "❌ Por favor ingresa usuario y contraseña.", gr.update(visible=True), gr.update(visible=False)
    
    if not supabase:
        return "❌ Error de conexión con Supabase. Revisa las llaves de acceso.", gr.update(visible=True), gr.update(visible=False)

    try:
        res = supabase.table("usuarios_saas").select("*").eq("email", email).execute()
        usuarios = res.data
        if not usuarios:
            return "❌ El usuario no existe o no tiene una cuenta registrada.", gr.update(visible=True), gr.update(visible=False)
        
        user_data = usuarios[0]
        if user_data.get("password") == password:
            if user_data.get("activo") == False:
                return "❌ Tu suscripción está suspendida o inactiva.", gr.update(visible=True), gr.update(visible=False)
            
            fecha_exp = user_data.get("fecha_expiracion") or user_data.get("fecha_expiración")
            if fecha_exp:
                exp_date = datetime.strptime(str(fecha_exp), "%Y-%m-%d").date()
                if datetime.now().date() > exp_date:
                    return "❌ Tu suscripción ha expirado.", gr.update(visible=True), gr.update(visible=False)
            
            registrar_log(email, "LOGIN", "Inicio de sesión exitoso en Gradio")
            df_saldos = cargar_saldos(email)
            return f"¡Bienvenido {email}!", gr.update(visible=False), gr.update(visible=True)
        else:
            return "❌ Contraseña incorrecta.", gr.update(visible=True), gr.update(visible=False)
    except Exception as e:
        return f"Error: {e}", gr.update(visible=True), gr.update(visible=False)

# --- CONSTRUCCIÓN DE INTERFAZ GRADIO ---
with gr.Blocks(theme=gr.themes.Soft(), title="Bóveda IVA Pro") as demo:
    
    # Vista de Login
    with gr.Column(visible=True) as panel_login:
        gr.Markdown("""
            <div style="max-width: 480px; margin: 30px auto; padding: 20px; background: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center;">
                <h2 style="color: #1e3c72; margin-bottom: 5px;">🏛️ Bóveda IVA Pro</h2>
                <p style="color: #64748b; font-size: 0.9rem;">Plataforma inteligente de gestión y acreditamiento de IVA.</p>
            </div>
        """)
        with gr.Row():
            with gr.Column(scale=1): pass
            with gr.Column(scale=2):
                txt_user = gr.Textbox(label="Usuario (Correo Electrónico)", placeholder="correo@ejemplo.com")
                txt_pass = gr.Textbox(label="Contraseña de Acceso", type="password")
                btn_ingresar = gr.Button("Iniciar Sesión", variant="primary")
                lbl_msg = gr.Markdown()
            with gr.Column(scale=1): pass

    # Vista Principal de la App
    with gr.Column(visible=False) as panel_app:
        gr.Markdown("""
            <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 15px 20px; border-radius: 10px; color: white; margin-bottom: 15px;">
                <h2 style="margin:0;">🏛️ Bóveda IVA Pro</h2>
                <p style="margin:0; font-size: 0.9rem; color: #e0e7ff;">Panel Principal de Acreditamiento e IVA</p>
            </div>
        """)
        
        with gr.Tabs():
            with gr.TabItem("📊 Resumen de Bóveda"):
                btn_refrescar = gr.Button("🔄 Cargar Saldos Disponibles")
                tabla_saldos = gr.DataFrame(headers=["ID", "RFC", "Periodo_Mes", "Periodo_Anio", "Num_Operacion", "Saldo_Disponible", "Estatus"])
                btn_refrescar.click(fn=lambda: cargar_saldos(txt_user.value), outputs=tabla_saldos)

            with gr.TabItem("💸 Aplicar Acreditamiento FIFO"):
                gr.Markdown("### Motor de Acreditamiento")
                # Próximos componentes del motor FIFO

    btn_ingresar.click(
        fn=validar_login,
        inputs=[txt_user, txt_pass],
        outputs=[lbl_msg, panel_login, panel_app]
    )

if _name_ == "_main_":
    import os
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
