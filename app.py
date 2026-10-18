import pandas as pd
from datetime import datetime, timedelta
import pypdf
import re
from supabase import create_client, Client
import gradio as gr

# --- CONFIGURACIÓN DE SUPABASE (Tus credenciales de secrets) ---
# Nota: En Gradio desplegado en Render, asegúrate de configurar estas variables en las Environment Variables de Render, 
# o puedes dejar tus keys directo aquí si lo prefieres.
import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "TU_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "TU_SUPABASE_KEY")

@gr.on_load
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        return None

supabase = init_supabase()

# --- FUNCIÓN DE REGISTRO DE AUDITORÍA (LOGS) ---
def registrar_log(email, accion, detalles):
    try:
        if supabase:
            supabase.table("logs_actividad").insert({
                "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "usuario_email": email,
                "accion": accion,
                "detalles": detalles
            }).execute()
    except Exception as e:
        pass

# --- FUNCIONES DE DATOS ---
def cargar_saldos(email):
    try:
        if not supabase: return pd.DataFrame()
        response = supabase.table("saldos_iva").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=["id", "usuario_email", "rfc", "periodo_mes", "periodo_anio", "tipo_declaracion", "num_operacion", "fecha_presentacion", "saldo_original", "saldo_disponible", "estatus"])
        df = pd.DataFrame(data)
        return df.rename(columns={
            "id": "ID", "usuario_email": "Usuario_Email", "rfc": "RFC", "periodo_mes": "Periodo_Mes", "periodo_anio": "Periodo_Anio",
            "tipo_declaracion": "Tipo_Declaracion", "num_operacion": "Num_Operacion",
            "fecha_presentacion": "Fecha_Presentacion", "saldo_original": "Saldo_Original",
            "saldo_disponible": "Saldo_Disponible", "estatus": "Estatus"
        })
    except Exception as e:
        return pd.DataFrame()

def mes_a_numero(mes_str):
    meses_dict = {"Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12}
    return meses_dict.get(str(mes_str).capitalize(), 1)

# --- LÓGICA DE AUTENTICACIÓN ---
def validar_login(email, password):
    email = email.strip().lower()
    if not email or not password:
        return "❌ Por favor ingresa usuario y contraseña.", gr.update(visible=True), gr.update(visible=False)
    try:
        res = supabase.table("usuarios_saas").select("*").eq("email", email).execute()
        usuarios = res.data
        if not usuarios:
            return "❌ El usuario no existe o no tiene una cuenta registrada.", gr.update(visible=True), gr.update(visible=False)
        
        user_data = usuarios[0]
        if user_data.get("password") == password:
            if user_data.get("activo") == False:
                return "❌ Tu suscripción está suspendida o inactiva. Contacta a soporte.", gr.update(visible=True), gr.update(visible=False)
            
            fecha_exp = user_data.get("fecha_expiracion") or user_data.get("fecha_expiración")
            if fecha_exp:
                exp_date = datetime.strptime(str(fecha_exp), "%Y-%m-%d").date()
                if datetime.now().date() > exp_date:
                    return "❌ Tu suscripción ha expirado. Realiza tu renovación.", gr.update(visible=True), gr.update(visible=False)
            
            registrar_log(email, "LOGIN", "Inicio de sesión exitoso en Gradio")
            return f"¡Bienvenido {email}!", gr.update(visible=False), gr.update(visible=True)
        else:
            return "❌ Contraseña incorrecta.", gr.update(visible=True), gr.update(visible=False)
    except Exception as e:
        return f"Error de conexión: {e}", gr.update(visible=True), gr.update(visible=False)

# --- INTERFAZ PRINCIPAL CON GRADIO (100% BLANCA Y LIMPIA) ---
with gr.Blocks(theme=gr.themes.Soft(), title="Bóveda IVA Pro - SaaS Fiscal") as demo:
    
    # Contenedor de Login
    with gr.Column(visible=True) as panel_login:
        gr.Markdown("""
            <div style="max-width: 500px; margin: 40px auto 10px auto; padding: 25px; background: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border: 1px solid #cbd5e1; text-align: center;">
                <h2 style="color: #1e3c72; margin-bottom: 10px;">🏛️ Bóveda IVA Pro</h2>
                <p style="color: #64748b; font-size: 0.95rem; margin: 0;">Plataforma inteligente de gestión y acreditamiento de IVA.</p>
            </div>
        """)
        with gr.Row():
            with gr.Column(scale=1): pass
            with gr.Column(scale=2):
                txt_user = gr.Textbox(label="Usuario (Correo Electrónico)")
                txt_pass = gr.Textbox(label="Contraseña de Acceso", type="password")
                btn_ingresar = gr.Button("Iniciar Sesión", variant="primary")
                lbl_msg = gr.Markdown()
            with gr.Column(scale=1): pass

    # Contenedor Principal de la App (Se muestra tras iniciar sesión)
    with gr.Column(visible=False) as panel_app:
        gr.Markdown("""
            <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;">
                <h1 style="margin:0; font-size: 2rem;">🏛️ Bóveda IVA Pro</h1>
                <p style="margin:5px 0 0 0; color: #e0e7ff;">Módulo de Gestión Fiscal Activo - Interfaz Profesional Libre de Marcas de Agua</p>
            </div>
        """)
        
        with gr.Tabs():
            with gr.TabItem("📊 Resumen de Bóveda"):
                gr.Markdown("### Aquí puedes visualizar el estado de tus saldos y papeles de trabajo.")
                btn_cargar = gr.Button("Cargar / Refrescar Saldos")
                tabla_saldos = gr.DataFrame()
                btn_cargar.click(fn=lambda: cargar_saldos("ejemplo@correo.com"), outputs=tabla_saldos)
                
            with gr.TabItem("➕ Registrar Saldo / Declaración"):
                gr.Markdown("### Registro manual o carga de acuses de saldos a favor.")
                # Aquí puedes integrar tus inputs de PDF y formularios anteriores de manera idéntica.
                
            with gr.TabItem("💸 Aplicar Acreditamiento FIFO"):
                gr.Markdown("### Motor de acreditamiento automático.")

    # Conexión del botón de login
    btn_ingresar.click(
        fn=validar_login,
        inputs=[txt_user, txt_pass],
        outputs=[lbl_msg, panel_login, panel_app]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)