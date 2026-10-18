import streamlit as st
st.markdown("""
    <style>
    /* Ocultar barra superior y encabezado */
    header, [data-testid="stHeader"], #MainMenu {
        display: none !important;
        visibility: hidden !important;
        height: 0px !important;
    }
    
    /* Ocultar pie de página, marca de agua y barra flotante inferior */
    footer, [data-testid="stFooter"], [data-testid="stStatusWidget"],
    .stAppViewerFooter, [class*="ViewerFooter"], [class*="stBottom"],
    [data-testid="stElementToolbar"], [data-testid="stToolbar"],
    button[title="View fullscreen"], [data-testid="stDecoration"],
    div[class*="stActionButton"] {
        display: none !important;
        visibility: hidden !important;
        height: 0px !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }

    /* Ajustar espacios */
    .main .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0rem !important;
    }
    </style>
""", unsafe_allow_html=True)
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

# --- OCULTAR ELEMENTOS, MARCA DE AGUA Y FULLSCREEN DE STREAMLIT ---
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Ocultar cualquier badge o botón flotante inferior de Streamlit */
    .viewerBadge_link__1S137 {display: none !important;}
    div[data-testid="stToolbar"] {visibility: hidden !important; display: none !important;}
    button[title="View fullscreen"] {visibility: hidden !important; display: none !important;}
    
    /* Bloqueo total por posicionamiento para elementos flotantes en esquinas */
    footer, .css-1rs6os {visibility: hidden; display: none;}
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

        link_basico = f"https://wa.me/5217226513054?text=Hola,%20deseo%20comprar%20el%20Plan%20B%C3%A1sico%20de%20B%C3%B3veda%20IVA%20Pro{ref_text}"
        link_ilimitado = f"https://wa.me/5217226513054?text=Hola,%20deseo%20comprar%20el%20Plan%20Ilimitado%20de%20B%C3%B3veda%20IVA%20Pro{ref_text}"

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
            st.markdown(f'<a href="{link_basico}" target="_blank"><div style="text-align:center; background:#22c55e; color:white; padding:12px; border-radius:8px; font-weight:bold; text-decoration:none; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">Adquirir Plan Básico en WhatsApp</div></a>', unsafe_allow_html=True)

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
            st.markdown(f'<a href="{link_ilimitado}" target="_blank"><div style="text-align:center; background:#1e3c72; color:white; padding:12px; border-radius:8px; font-weight:bold; text-decoration:none; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">Adquirir Plan Ilimitado en WhatsApp</div></a>', unsafe_allow_html=True)

    st.stop()

# --- SI YA ESTÁ AUTENTICADO ---
usuario_email = st.session_state["usuario_email"]
tipo_plan = st.session_state["plan_activo"]
fecha_exp_sesion = st.session_state["fecha_expiracion"]
codigo_usuario = st.session_state.get("codigo_referido", usuario_email.split("@")[0].upper())

plan_normalizado = str(tipo_plan).lower()
limite_rfc = 5 if ("basico" in plan_normalizado or "básico" in plan_normalizado) else 999999

st.markdown(f"""
<div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;">
    <h1 style="margin:0; font-size: 2rem;">🏛️ Bóveda IVA Pro</h1>
    <p style="margin:5px 0 0 0; color: #e0e7ff;">
        Bienvenido, <b>{usuario_email}</b> | Plan: <b>{tipo_plan}</b> | ⏳ Vence: <b>{fecha_exp_sesion}</b> | 🎁 Tu Código: <b>{codigo_usuario}</b>
    </p>
</div>
""", unsafe_allow_html=True)

# --- BARRA LATERAL ---
if st.sidebar.button("🚪 Cerrar Sesión"):
    registrar_log(usuario_email, "LOGOUT", "Cierre de sesión")
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.markdown("---")

with st.sidebar.expander("🎁 ¡Gana 2 Meses Gratis!"):
    st.write("Comparte tu código con colegas contadores:")
    st.code(codigo_usuario, language=None)
    st.caption("<b>Condición:</b> Válido únicamente para usuarios con <b>Licencia Anual</b>.<br><br>"
               "Si un colega contrata un <b>Plan Anual</b> usando tu código:<br>"
               "• Él recibe <b>15 días GRATIS</b> extras.<br>"
               "• Tú recibes <b>2 meses GRATIS</b> en tu suscripción.", unsafe_allow_html=True)

with st.sidebar.expander("🔒 Cambiar Contraseña"):
    with st.form("form_cambiar_pass"):
        pass_actual = st.text_input("Contraseña Actual", type="password")
        pass_nueva = st.text_input("Nueva Contraseña", type="password")
        pass_confirmar = st.text_input("Confirmar Nueva Contraseña", type="password")
        btn_actualizar_pass = st.form_submit_button("Actualizar Contraseña")
        
        if btn_actualizar_pass:
            if not pass_actual or not pass_nueva or not pass_confirmar:
                st.error("Completa todos los campos.")
            elif pass_nueva != pass_confirmar:
                st.error("Las nuevas contraseñas no coinciden.")
            else:
                try:
                    res = supabase.table("usuarios_saas").select("password").eq("email", usuario_email).execute()
                    if res.data and res.data[0].get("password") == pass_actual:
                        supabase.table("usuarios_saas").update({"password": pass_nueva}).eq("email", usuario_email).execute()
                        registrar_log(usuario_email, "CAMBIO_PASSWORD", "Contraseña actualizada exitosamente")
                        st.success("¡Contraseña actualizada con éxito!")
                    else:
                        st.error("La contraseña actual es incorrecta.")
                except Exception as e:
                    st.error(f"Error al cambiar contraseña: {e}")

st.sidebar.markdown("---")

# --- FUNCIONES DE DATOS ---
def cargar_saldos(email):
    try:
        response = supabase.table("saldos_iva").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=["id", "usuario_email", "rfc", "periodo_mes", "periodo_anio", "tipo_declaracion", "num_operacion", "fecha_presentacion", "saldo_original", "saldo_disponible", "estatus"])
        df = pd.DataFrame(data)
        return df.rename(columns={
            "id": "ID", "rfc": "RFC", "periodo_mes": "Periodo_Mes", "periodo_anio": "Periodo_Anio",
            "tipo_declaracion": "Tipo_Declaracion", "num_operacion": "Num_Operacion",
            "fecha_presentacion": "Fecha_Presentacion", "saldo_original": "Saldo_Original",
            "saldo_disponible": "Saldo_Disponible", "estatus": "Estatus"
        })
    except Exception as e:
        st.error(f"Error al cargar saldos: {e}")
        return pd.DataFrame()

def cargar_historial(email):
    try:
        response = supabase.table("historial_acreditamientos").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=["id", "usuario_email", "fecha_aplicacion", "rfc", "periodo_origen", "periodo_destino", "num_operacion_origen", "saldo_anterior", "monto_aplicado", "remanente_nuevo"])
        df = pd.DataFrame(data)
        
        column_map = {
            "id": "ID", 
            "usuario_email": "Usuario_Email", 
            "fecha_aplicacion": "Fecha_Aplicacion", 
            "rfc": "RFC", 
            "periodo_origen": "Periodo_Origen",
            "periodo_destino": "Declaracion_Aplicada_Destino", 
            "num_operacion_origen": "Num_Operacion_Origen", 
            "saldo_anterior": "Saldo_Anterior", 
            "monto_aplicado": "Monto_Aplicado", 
            "remanente_nuevo": "Remanente_Nuevo"
        }
        df = df.rename(columns=column_map)
        if "Declaracion_Aplicada_Destino" not in df.columns:
            df["Declaracion_Aplicada_Destino"] = "No especificado"
        return df
    except Exception as e:
        st.error(f"Error al cargar historial: {e}")
        return pd.DataFrame()

def mes_a_numero(mes_str):
    meses_dict = {"Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12}
    return meses_dict.get(str(mes_str).capitalize(), 1)

def extraer_datos_pdf(uploaded_file):
    texto = ""
    try:
        reader = pypdf.PdfReader(uploaded_file)
        for page in reader.pages:
            texto += page.extract_text() or ""
    except Exception as e:
        st.error(f"Error al leer el PDF: {e}")
        return None

    datos = {
        "rfc": "", 
        "num_operacion": "", 
        "saldo_favor": 0, 
        "mes": "Enero", 
        "anio": 2026, 
        "fecha_pres": datetime.now().date(),
        "tipo_declaracion": "Normal"
    }
    
    match_rfc = re.search(r"RFC[:\s]*([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})", texto, re.IGNORECASE)
    if match_rfc: datos["rfc"] = match_rfc.group(1).upper()

    match_op = re.search(r"Número\s+de\s+operación[:\s]*([0-9]+(?:\.[0-9]+)?)", texto, re.IGNORECASE)
    if match_op:
        raw_op = match_op.group(1)
        datos["num_operacion"] = str(int(float(raw_op))) if "." in raw_op else raw_op
        
    match_fecha = re.search(r"Fecha\s+y\s+hora\s+de\s+presentación[:\s]*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    if match_fecha:
        try: datos["fecha_pres"] = datetime.strptime(match_fecha.group(1), "%d/%m/%Y").date()
        except: pass

    match_anio = re.search(r"Ejercicio[:\s]*(\d{4})", texto, re.IGNORECASE)
    if match_anio:
        try: datos["anio"] = int(match_anio.group(1))
        except: pass

    meses_validos = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    for m in meses_validos:
        if re.search(rf"(?:Período|Periodo)[^\n]*?{m}", texto, re.IGNORECASE):
            datos["mes"] = m
            break
    else:
        for m in meses_validos:
            if re.search(rf"\b{m}\b", texto, re.IGNORECASE):
                datos["mes"] = m
                break

    if re.search(r"dejar\s+sin\s+efecto", texto, re.IGNORECASE):
        datos["tipo_declaracion"] = "Complementaria - Dejar sin Efecto"
    elif re.search(r"complementaria|modificación|modificacion", texto, re.IGNORECASE):
        datos["tipo_declaracion"] = "Complementaria - Modificación"
    else:
        datos["tipo_declaracion"] = "Normal"

    if "Impuesto al Valor Agregado" in texto:
        partes_iva = texto.split("Impuesto al Valor Agregado")
        if len(partes_iva) > 1:
            bloque_iva = partes_iva[1][:200]
            match_afavor = re.search(r"A\s+favor[:\s]*([\d,]+)", bloque_iva, re.IGNORECASE)
            if match_afavor:
                try: 
                    datos["saldo_favor"] = int(match_afavor.group(1).replace(",", ""))
                except: 
                    pass

    return datos, texto

# --- NAVEGACIÓN LATERAL ---
df_global = cargar_saldos(usuario_email)
lista_rfcs = sorted(df_global["RFC"].unique().tolist()) if not df_global.empty else []

rfc_seleccionado = st.sidebar.selectbox("📂 Seleccionar Cliente (RFC)", lista_rfcs) if lista_rfcs else ""
if not lista_rfcs:
    st.sidebar.info("No hay clientes registrados.")

st.sidebar.markdown(f"**Uso del Plan:** {len(lista_rfcs)} / {'5' if limite_rfc == 5 else 'Ilimitado'} RFCs")
st.sidebar.markdown(f"**Vencimiento:** {fecha_exp_sesion}")
st.sidebar.markdown("---")

opcion = st.sidebar.radio("Navegación Módulos", [
    "📊 Resumen de Bóveda", 
    "➕ Registrar Saldo Inicial / Remanente", 
    "📥 Nueva Declaración (PDF)", 
    "💸 Aplicar Acreditamiento", 
    "📜 Historial de Aplicaciones",
    "📈 Dashboard Directivo y Devoluciones"
])

# --- MÓDULOS ---
if opcion == "📊 Resumen de Bóveda":
    st.subheader("📊 Saldos a Favor Disponibles y Papeles de Trabajo")
    if df_global.empty or not rfc_seleccionado:
        st.info("Selecciona un RFC en la barra lateral o registra declaraciones.")
    else:
        df_cliente = df_global[df_global["RFC"] == rfc_seleccionado].copy()
        if not df_cliente.empty:
            df_cliente["Mes_Num"] = df_cliente["Periodo_Mes"].apply(mes_a_numero)
            df_cliente = df_cliente.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
            
            hoy = datetime.now().date()
            def evaluar_semaforo(fecha_str):
                try:
                    f_pres = datetime.strptime(str(fecha_str), "%Y-%m-%d").date()
                    limite_prescripcion = f_pres + timedelta(days=5*365)
                    dias_restantes = (limite_prescripcion - hoy).days
                    
                    if dias_restantes < 0:
                        return "🔴 Prescrito (>5 años)"
                    elif dias_restantes <= 365:
                        return "🔴 Riesgo Inminente (<1 año)"
                    elif dias_restantes <= 730:
                        return "🟡 Atención (1-2 años)"
                    else:
                        return "🟢 Vigente (>2 años)"
                except:
                    return "🟢 Vigente"

            df_cliente["Estatus_Caducidad"] = df_cliente["Fecha_Presentacion"].apply(evaluar_semaforo)

        total_disp = int(df_cliente[df_cliente["Estatus"] == "Vigente"]["Saldo_Disponible"].sum()) if not df_cliente.empty else 0
        st.metric(label=f"SALDO TOTAL VIGENTE — {rfc_seleccionado}", value=f"${total_disp:,} MXN")
        
        st.markdown("### Detalle de Saldos y Semáforo de Caducidad (Art. 22 CFF)")
        st.dataframe(df_cliente, use_container_width=True)
        
        csv_reporte = df_cliente.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Papel de Trabajo Ejecutivo (Excel/CSV)",
            data=csv_reporte,
            file_name=f"PapelDeTrabajo_{rfc_seleccionado}.csv",
            mime="text/csv"
        )

        st.markdown("---")
        st.markdown("### 🗑️ Zona de Corrección / Eliminar Declaración Erónea")
        if not df_cliente.empty:
            id_a_borrar = st.selectbox("Selecciona el ID del registro que deseas eliminar por error:", df_cliente["ID"].tolist(), format_func=lambda x: f"ID: {x} | Periodo: {df_cliente[df_cliente['ID'] == x]['Periodo_Mes'].values[0]} {df_cliente[df_cliente['ID'] == x]['Periodo_Anio'].values[0]} | Folio: {df_cliente[df_cliente['ID'] == x]['Num_Operacion'].values[0]} | Monto: ${df_cliente[df_cliente['ID'] == x]['Saldo_Disponible'].values[0]:,.2f}")
            
            confirma_borrar = st.checkbox("⚠️ Estoy seguro de que deseo eliminar permanentemente este registro de la Bóveda.")
            
            if st.button("🗑️ Eliminar Registro de la Bóveda"):
                if not confirma_borrar:
                    st.error("❌ Debes marcar la casilla de confirmación para poder eliminar el registro.")
                else:
                    try:
                        supabase.table("saldos_iva").delete().eq("id", int(id_a_borrar)).execute()
                        registrar_log(usuario_email, "ELIMINAR_REGISTRO_BOVEDA", f"RFC: {rfc_seleccionado} | Registro ID: {id_a_borrar} eliminado")
                        st.success("¡Registro eliminado correctamente de la Bóveda!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar: {e}")

elif opcion == "➕ Registrar Saldo Inicial / Remanente":
    st.subheader("➕ Carga de Saldo Inicial / Papel de Trabajo")
    with st.form("form_inicial"):
        col1, col2 = st.columns(2)
        with col1:
            rfc = st.text_input("RFC del Contribuyente", rfc_seleccionado if rfc_seleccionado else "XAXX010101000")
            mes = st.selectbox("Mes de Origen", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
            anio = st.number_input("Año de Origen", min_value=2020, max_value=2030, value=2025)
            num_op = st.text_input("Número de Operación Original")
        with col2:
            fecha_pres = st.date_input("Fecha de Presentación", datetime.now())
            saldo_orig = st.number_input("Saldo a Favor Original ($ MXN)", min_value=0, step=1, value=0)
            saldo_disp = st.number_input("Saldo Disponible Actual ($ MXN)", min_value=0, step=1, value=0)
        
        if st.form_submit_button("Guardar Saldo en Nube"):
            rfc_limpio = rfc.upper().strip()
            num_op_limpio = str(num_op).replace(".0", "").strip()
            
            if rfc_limpio not in lista_rfcs and len(lista_rfcs) >= limite_rfc:
                st.error(f"🚫 Has alcanzado el límite de {limite_rfc} RFCs de tu plan.")
            elif not num_op_limpio:
                st.error("❌ El número de operación es obligatorio.")
            else:
                try:
                    check_duplicado = supabase.table("saldos_iva").select("id").eq("usuario_email", usuario_email).eq("num_operacion", num_op_limpio).execute()
                    if check_duplicado.data:
                        st.error(f"❌ El Número de Operación '{num_op_limpio}' ya se encuentra registrado en tu Bóveda. No se permiten duplicados.")
                    else:
                        supabase.table("saldos_iva").insert({
                            "usuario_email": usuario_email,
                            "rfc": rfc_limpio,
                            "periodo_mes": mes,
                            "periodo_anio": int(anio),
                            "tipo_declaracion": "Inicial",
                            "num_operacion": num_op_limpio,
                            "fecha_presentacion": str(fecha_pres),
                            "saldo_original": float(saldo_orig),
                            "saldo_disponible": float(saldo_disp),
                            "estatus": "Vigente" if saldo_disp > 0 else "Agotado"
                        }).execute()
                        
                        registrar_log(usuario_email, "REGISTRO_SALDO_INICIAL", f"RFC: {rfc_limpio} | Monto: ${saldo_disp} MXN")
                        st.success("¡Saldo inicial registrado con éxito!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

elif opcion == "📥 Nueva Declaración (PDF)":
    st.subheader("📥 Carga Automatizada de Acuse del SAT (PDF)")
    archivo_pdf = st.file_uploader("Cargar Acuse en Formato PDF", type=["pdf"])
    
    def_rfc, def_num_op, def_saldo, def_mes_idx, def_anio = rfc_seleccionado or "XAXX010101000", "", 0, 0, 2026
    def_fecha = datetime.now()
    def_tipo_dec = "Normal"
    meses_lista = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    tipos_dec_lista = ["Normal", "Complementaria - Modificación", "Complementaria - Dejar sin Efecto"]
    def_tipo_dec_idx = 0

    if archivo_pdf is not None:
        datos_extraidos, _ = extraer_datos_pdf(archivo_pdf)
        if datos_extraidos:
            st.success("✨ ¡Lectura Exitosa del Acuse SAT!")
            def_rfc = datos_extraidos["rfc"] or def_rfc
            def_num_op = str(datos_extraidos["num_operacion"]).replace(".0", "")
            def_saldo = int(datos_extraidos["saldo_favor"])
            def_anio = int(datos_extraidos["anio"])
            def_fecha = datos_extraidos["fecha_pres"]
            def_tipo_dec = datos_extraidos["tipo_declaracion"]
            if datos_extraidos["mes"] in meses_lista:
                def_mes_idx = meses_lista.index(datos_extraidos["mes"])
            if def_tipo_dec in tipos_dec_lista:
                def_tipo_dec_idx = tipos_dec_lista.index(def_tipo_dec)

    with st.form("form_declaracion"):
        col1, col2 = st.columns(2)
        with col1:
            rfc = st.text_input("RFC del Contribuyente", value=def_rfc)
            mes = st.selectbox("Mes del Periodo", meses_lista, index=def_mes_idx)
            anio = st.number_input("Año del Periodo", min_value=2020, max_value=2030, value=def_anio)
            tipo_dec = st.selectbox("Tipo de Declaración", tipos_dec_lista, index=def_tipo_dec_idx)
        with col2:
            num_op = st.text_input("Número de Operación / Folio SAT", value=def_num_op)
            fecha_pres = st.date_input("Fecha de Presentación ante el SAT", value=def_fecha)
            saldo_orig = st.number_input("Monto Saldo a Favor Declarado ($ MXN)", min_value=0, step=1, value=def_saldo)
        
        rfc_verif = rfc.upper().strip()
        existe_previo = False
        if not df_global.empty and rfc_verif in df_global["RFC"].values:
            check_periodo = df_global[
                (df_global["RFC"] == rfc_verif) & 
                (df_global["Periodo_Mes"] == mes) & 
                (df_global["Periodo_Anio"] == int(anio)) & 
                (df_global["Estatus"] == "Vigente")
            ]
            if not check_periodo.empty:
                folios_existentes = [str(x).strip() for x in check_periodo["Num_Operacion"].values]
                if num_op.strip() not in folios_existentes:
                    existe_previo = True

        if existe_previo:
            st.warning(f"⚠️ **Atención:** Ya existe un saldo vigente registrado con otro número de operación para el periodo **{mes} {anio}** en este RFC. Cargar este nuevo acuse sustituirá o modificará el saldo anterior.")
            confirmar_cambio = st.checkbox("Confirmo que deseo registrar/modificar este periodo con este nuevo acuse.")
        else:
            confirmar_cambio = True

        if st.form_submit_button("Registrar Declaración en Nube"):
            rfc_limpio, num_op_limpio = rfc.upper().strip(), str(num_op).replace(".0", "").strip()
            if rfc_limpio not in lista_rfcs and len(lista_rfcs) >= limite_rfc:
                st.error(f"🚫 Has alcanzado el límite de {limite_rfc} RFCs de tu plan.")
            elif not num_op_limpio:
                st.error("❌ El número de operación es obligatorio.")
            elif existe_previo and not confirmar_cambio:
                st.error("❌ Debes confirmar la casilla de que deseas modificar la declaración existente.")
            else:
                try:
                    check_duplicado = supabase.table("saldos_iva").select("id").eq("usuario_email", usuario_email).eq("num_operacion", num_op_limpio).execute()
                    if check_duplicado.data:
                        st.error(f"❌ El Número de Operación '{num_op_limpio}' ya se encuentra registrado en tu Bóveda. No se permiten duplicados.")
                    else:
                        if "Complementaria" in tipo_dec or existe_previo:
                            supabase.table("saldos_iva").update({"estatus": "Sustituido"}).eq("usuario_email", usuario_email).eq("rfc", rfc_limpio).eq("periodo_mes", mes).eq("periodo_anio", int(anio)).execute()
                        
                        supabase.table("saldos_iva").insert({
                            "usuario_email": usuario_email,
                            "rfc": rfc_limpio,
                            "periodo_mes": mes,
                            "periodo_anio": int(anio),
                            "tipo_declaracion": tipo_dec,
                            "num_operacion": num_op_limpio,
                            "fecha_presentacion": str(fecha_pres),
                            "saldo_original": float(saldo_orig),
                            "saldo_disponible": float(saldo_orig),
                            "estatus": "Vigente"
                        }).execute()
                        
                        registrar_log(usuario_email, "CARGA_DECLARACION_PDF", f"RFC: {rfc_limpio} | Periodo: {mes} {anio} | Monto: ${saldo_orig} MXN")
                        st.success("¡Declaración registrada correctamente!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar: {e}")

elif opcion == "💸 Aplicar Acreditamiento":
    st.subheader("💸 Motor de Acreditamiento FIFO")
    if not rfc_seleccionado:
        st.warning("Selecciona un RFC en la barra lateral.")
    else:
        df_saldos = cargar_saldos(usuario_email)
        df_cliente_vigentes = df_saldos[(df_saldos["RFC"] == rfc_seleccionado) & (df_saldos["Estatus"] == "Vigente")].copy()
        if not df_cliente_vigentes.empty:
            df_cliente_vigentes["Mes_Num"] = df_cliente_vigentes["Periodo_Mes"].apply(mes_a_numero)
            df_cliente_vigentes = df_cliente_vigentes.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
        
        if df_cliente_vigentes.empty:
            st.warning("No hay saldos vigentes disponibles para este cliente (o están congelados por trámite de devolución).")
        else:
            meses_lista = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            mes_actual_idx = datetime.now().month - 1
            
            col1, col2, col3 = st.columns([1.5, 1, 1])
            with col1:
                monto_a_aplicar = st.number_input("Monto de IVA a acreditar ($ MXN)", min_value=0, step=1, value=0)
            with col2:
                mes_destino = st.selectbox("Declaración Destino (Mes)", meses_lista, index=mes_actual_idx)
            with col3:
                anio_destino = st.number_input("Año Destino", min_value=2020, max_value=2030, value=datetime.now().year)

            periodo_destino_str = f"{mes_destino} {anio_destino}"

            if st.button("Ejecutar Consumo FIFO en Nube"):
                if monto_a_aplicar <= 0:
                    st.error("Ingresa un monto mayor a cero.")
                elif monto_a_aplicar > df_cliente_vigentes["Saldo_Disponible"].sum():
                    st.error("El monto excede el saldo total disponible.")
                else:
                    remanente_por_aplicar = int(monto_a_aplicar)
                    desglose_sat = []
                    try:
                        for idx, row in df_cliente_vigentes.iterrows():
                            if remanente_por_aplicar <= 0: break
                            saldo_anterior = int(row["Saldo_Disponible"])
                            saldo_original = int(row.get("Saldo_Original", saldo_anterior))
                            usar = min(saldo_anterior, remanente_por_aplicar)
                            remanente_nuevo = saldo_anterior - usar
                            remanente_por_aplicar -= usar
                            folio_limpio = str(row['Num_Operacion']).replace(".0", "")
                            
                            nuevo_estatus = "Agotado" if remanente_nuevo == 0 else "Vigente"
                            
                            supabase.table("saldos_iva").update({
                                "saldo_disponible": float(remanente_nuevo),
                                "estatus": nuevo_estatus
                            }).eq("id", int(row["ID"])).execute()
                            
                            payload_historial = {
                                "usuario_email": usuario_email,
                                "fecha_aplicacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "rfc": rfc_seleccionado,
                                "periodo_origen": f"{row['Periodo_Mes']} {row['Periodo_Anio']}",
                                "num_operacion_origen": folio_limpio,
                                "saldo_anterior": float(saldo_anterior),
                                "monto_aplicado": float(usar),
                                "remanente_nuevo": float(remanente_nuevo)
                            }
                            
                            try:
                                payload_historial["periodo_destino"] = periodo_destino_str
                                supabase.table("historial_acreditamientos").insert(payload_historial).execute()
                            except:
                                payload_historial.pop("periodo_destino", None)
                                supabase.table("historial_acreditamientos").insert(payload_historial).execute()
                            
                            desglose_sat.append({
                                "Declaración / Periodo Aplicado (Destino)": periodo_destino_str,
                                "Periodo de Origen": f"{row['Periodo_Mes']} {row['Periodo_Anio']}",
                                "Fecha de Presentación": str(row.get('Fecha_Presentacion', 'N/A')),
                                "Número de Operación / Folio SAT": folio_limpio,
                                "Saldo Original Declarado": f"${saldo_original:,} MXN",
                                "Saldo Insoluto Anterior": f"${saldo_anterior:,} MXN",
                                "Monto Acreditado / Aplicado": f"${usar:,} MXN",
                                "Saldo Remanente Posterior": f"${remanente_nuevo:,} MXN"
                            })
                        
                        registrar_log(usuario_email, "EJECUCION_FIFO", f"RFC: {rfc_seleccionado} | Aplicado en {periodo_destino_str} | Monto: ${monto_a_aplicar} MXN")
                        
                        st.session_state["tabla_resultado_sat"] = pd.DataFrame(desglose_sat)
                        st.balloons()
                        st.success(f"¡Acreditamiento FIFO aplicado con éxito para la declaración de **{periodo_destino_str}**!")
                    except Exception as e:
                        st.error(f"Error al ejecutar: {e}")

            if "tabla_resultado_sat" in st.session_state and not st.session_state["tabla_resultado_sat"].empty:
                st.markdown("---")
                st.subheader("📋 Datos exactos para capturar en el Portal del SAT:")
                st.dataframe(st.session_state["tabla_resultado_sat"], use_container_width=True)
                
                csv_sat = st.session_state["tabla_resultado_sat"].to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Desglose SAT (CSV/Excel)",
                    data=csv_sat,
                    file_name=f"Desglose_SAT_{rfc_seleccionado}.csv",
                    mime="text/csv"
                )

elif opcion == "📜 Historial de Aplicaciones":
    st.subheader("📜 Bitácora de Acreditamientos y Reportes")
    df_hist = cargar_historial(usuario_email)
    if df_hist.empty:
        st.info("No hay aplicaciones registradas en la nube.")
    else:
        df_hist_cliente = df_hist[df_hist["RFC"] == rfc_seleccionado] if rfc_seleccionado and "RFC" in df_hist.columns else df_hist
        if df_hist_cliente.empty:
            st.info("No hay historial para este cliente.")
        else:
            cols_order = [c for c in ["ID", "Fecha_Aplicacion", "RFC", "Periodo_Origen", "Declaracion_Aplicada_Destino", "Num_Operacion_Origen", "Saldo_Anterior", "Monto_Aplicado", "Remanente_Nuevo"] if c in df_hist_cliente.columns]
            df_hist_display = df_hist_cliente[cols_order]
            
            st.dataframe(df_hist_display, use_container_width=True)
            
            csv_hist = df_hist_display.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Exportar Bitácora Ejecutiva a CSV (Excel)", 
                data=csv_hist, 
                file_name=f"BitacoraAcreditamientos_{rfc_seleccionado}.csv", 
                mime="text/csv"
            )

            st.markdown("---")
            st.markdown("### 🗑️ Zona de Corrección / Eliminar Registro de Historial")
            id_a_borrar_hist = st.selectbox(
                "Selecciona el ID del registro de historial que deseas eliminar:", 
                df_hist_cliente["ID"].tolist(), 
                format_func=lambda x: f"ID: {x} | Fecha: {df_hist_cliente[df_hist_cliente['ID'] == x]['Fecha_Aplicacion'].values[0]} | Origen: {df_hist_cliente[df_hist_cliente['ID'] == x]['Periodo_Origen'].values[0]} | Aplicado: ${df_hist_cliente[df_hist_cliente['ID'] == x]['Monto_Aplicado'].values[0]:,.2f}"
            )
            
            confirma_borrar_hist = st.checkbox("⚠️ Estoy seguro de que deseo eliminar permanentemente este registro del Historial.")
            
            if st.button("🗑️ Eliminar Registro del Historial"):
                if not confirma_borrar_hist:
                    st.error("❌ Debes marcar la casilla de confirmación para poder eliminar el registro.")
                else:
                    try:
                        supabase.table("historial_acreditamientos").delete().eq("id", int(id_a_borrar_hist)).execute()
                        registrar_log(usuario_email, "ELIMINAR_REGISTRO_HISTORIAL", f"RFC: {rfc_seleccionado} | Historial ID: {id_a_borrar_hist} eliminado")
                        st.success("¡Registro de historial eliminado correctamente!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar: {e}")

elif opcion == "📈 Dashboard Directivo y Devoluciones":
    st.subheader("📈 Dashboard de Métricas Directivas y Expediente de Devolución (FED)")
    if not rfc_seleccionado:
        st.warning("Selecciona un RFC en la barra lateral para ver sus métricas y generar reportes.")
    else:
        df_saldos_cli = df_global[df_global["RFC"] == rfc_seleccionado] if not df_global.empty else pd.DataFrame()
        df_hist_cli = cargar_historial(usuario_email)
        df_hist_cli = df_hist_cli[df_hist_cli["RFC"] == rfc_seleccionado] if not df_hist_cli.empty and "RFC" in df_hist_cli.columns else pd.DataFrame()

        total_ahorro = int(df_hist_cli["Monto_Aplicado"].sum()) if not df_hist_cli.empty else 0
        saldo_vigente_actual = int(df_saldos_cli[df_saldos_cli["Estatus"] == "Vigente"]["Saldo_Disponible"].sum()) if not df_saldos_cli.empty else 0

        col_kpi1, col_kpi2 = st.columns(2)
        with col_kpi1:
            st.metric(label=f"💰 Ahorro Total en Efectivo — {rfc_seleccionado}", value=f"${total_ahorro:,} MXN")
        with col_kpi2:
            st.metric(label=f"💼 Saldo Vigente en Bóveda — {rfc_seleccionado}", value=f"${saldo_vigente_actual:,} MXN")

        st.markdown("---")
        
        if not df_hist_cli.empty and "Declaracion_Aplicada_Destino" in df_hist_cli.columns:
            st.markdown("### 📊 Evolución de Acreditamientos por Periodo Destino")
            df_grafica = df_hist_cli.groupby("Declaracion_Aplicada_Destino")["Monto_Aplicado"].sum().reset_index()
            st.bar_chart(df_grafica.set_index("Declaracion_Aplicada_Destino"))

        st.markdown("---")
        st.markdown("### 📄 Generador de Expediente y Gestión de Devoluciones (FED - SAT)")
        st.info("Genera el reporte ejecutivo oficial para adjuntar en tu solicitud de devolución ante el SAT, o gestiona el estatus del saldo congelado en caso de rechazo o desistimiento.")
        
        if not df_saldos_cli.empty:
            saldo_a_devolver_id = st.selectbox("Selecciona el Saldo (Origen):", df_saldos_cli["ID"].tolist(), format_func=lambda x: f"ID: {x} | Periodo: {df_saldos_cli[df_saldos_cli['ID'] == x]['Periodo_Mes'].values[0]} {df_saldos_cli[df_saldos_cli['ID'] == x]['Periodo_Anio'].values[0]} | Disp: ${df_saldos_cli[df_saldos_cli['ID'] == x]['Saldo_Disponible'].values[0]:,.2f} | Estatus: {df_saldos_cli[df_saldos_cli['ID'] == x]['Estatus'].values[0]}")
            
            row_actual = df_saldos_cli[df_saldos_cli["ID"] == saldo_a_devolver_id].iloc[0]
            estatus_actual = row_actual["Estatus"]

            col_b1, col_b2 = st.columns(2)
            
            with col_b1:
                if st.button("📄 Generar Expediente Formal"):
                    row_sel = row_actual
                    
                    reporte_devolucion = f"""EXPEDIENTE DE SOLICITUD DE DEVOLUCIÓN DE SALDO A FAVOR DE IVA
RFC DEL CONTRIBUYENTE: {rfc_seleccionado}
FECHA DE GENERACIÓN: {datetime.now().strftime('%d/%m/%Y')}
--------------------------------------------------------------------------------
1. DATOS DE ORIGEN DEL SALDO A FAVOR:
- Periodo de Origen: {row_sel['Periodo_Mes']} {row_sel['Periodo_Anio']}
- Tipo de Declaración: {row_sel['Tipo_Declaracion']}
- Número de Operación / Folio SAT: {row_sel['Num_Operacion']}
- Fecha de Presentación: {row_sel['Fecha_Presentacion']}
- Saldo Original Declarado: ${row_sel['Saldo_Original']:,.2f} MXN
- Saldo Disponible Actual (Remanente a Solicitar): ${row_sel['Saldo_Disponible']:,.2f} MXN
--------------------------------------------------------------------------------
2. HISTORIAL DE APLICACIONES PREVIAS (MÉTODO FIFO):
"""
                    if not df_hist_cli.empty:
                        df_aplicaciones_previas = df_hist_cli[df_hist_cli["Num_Operacion_Origen"] == str(row_sel['Num_Operacion'])]
                        if not df_aplicaciones_previas.empty:
                            for idx, app in df_aplicaciones_previas.iterrows():
                                reporte_devolucion += f"• Aplicado en Declaración Destino: {app['Declaracion_Aplicada_Destino']} | Monto Usado: ${app['Monto_Aplicado']:,.2f} MXN | Fecha: {app['Fecha_Aplicacion']}\n"
                        else:
                            reporte_devolucion += "No registra aplicaciones previas (saldo íntegro).\n"
                    else:
                        reporte_devolucion += "No registra aplicaciones previas.\n"

                    reporte_devolucion += "--------------------------------------------------------------------------------\n"
                    reporte_devolucion += "Este documento sirve como papel de trabajo auxiliar para la captura en el Formato Electrónico de Devoluciones (FED) del SAT."

                    st.text_area("Vista Previa:", value=reporte_devolucion, height=200)
                    
                    st.download_button(
                        label="📥 Descargar Expediente en TXT",
                        data=reporte_devolucion.encode('utf-8'),
                        file_name=f"ExpedienteDevolucion_{rfc_seleccionado}_{row_sel['Periodo_Mes']}_{row_sel['Periodo_Anio']}.txt",
                        mime="text/plain"
                    )

            with col_b2:
                st.markdown("<br>", unsafe_allow_html=True)
                
                if estatus_actual == "En Trámite de Devolución":
                    if st.button("🔓 Reactivar Saldo (Devolución Rechazada / Desistida)", help="Vuelve a poner el saldo como 'Vigente' para que el motor FIFO pueda utilizarlo nuevamente."):
                        try:
                            supabase.table("saldos_iva").update({"estatus": "Vigente"}).eq("id", int(saldo_a_devolver_id)).execute()
                            registrar_log(usuario_email, "REACTIVAR_SALDO_DEVOLUCION", f"RFC: {rfc_seleccionado} | Saldo ID: {saldo_a_devolver_id} reactivado por rechazo/desistimiento")
                            st.success("¡Saldo reactivado con éxito! Ahora vuelve a estar disponible para acreditamiento FIFO.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al reactivar saldo: {e}")
                else:
                    if st.button("🔒 Congelar Saldo (En Trámite de Devolución)", help="Evita que este saldo sea utilizado por el motor FIFO mientras el SAT resuelve."):
                        try:
                            supabase.table("saldos_iva").update({"estatus": "En Trámite de Devolución"}).eq("id", int(saldo_a_devolver_id)).execute()
                            registrar_log(usuario_email, "CONGELAR_SALDO_DEVOLUCION", f"RFC: {rfc_seleccionado} | Saldo ID: {saldo_a_devolver_id} congelado por trámite FED")
                            st.success("¡Saldo congelado correctamente! Ya no aparecerá disponible para acreditamiento FIFO.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al congelar saldo: {e}")
