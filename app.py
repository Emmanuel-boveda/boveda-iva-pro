import streamlit as st
import pandas as pd
import pypdf
import re
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Bóveda IVA Pro",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# ESTILOS CSS PERSONALIZADOS (OCULTA CABECERA, ÍCONO DE GITHUB Y MENÚ)
# -----------------------------------------------------------------------------
st.markdown("""
    <style>
    /* Oculta la barra superior de Streamlit (Gato de GitHub, Menú, Fork/Tenedor) */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Estilos generales */
    .stApp {
        background-color: #f8f9fa;
    }
    .main-header {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        color: #1e293b;
        text-align: center;
        padding: 1rem 0;
    }
    .card-box {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# ESTADO DE SESIÓN (SESSION STATE)
# -----------------------------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None
if 'username' not in st.session_state:
    st.session_state['username'] = ""

# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES DE LECTURA DE PDF (SAT / FED)
# -----------------------------------------------------------------------------
def extraer_datos_acuse_pdf(pdf_file):
    """Extrae datos clave de un acuse PDF del SAT o FED."""
    try:
        reader = pypdf.PdfReader(pdf_file)
        texto_completo = ""
        for page in reader.pages:
            texto_completo += page.extract_text() or ""
        
        # Búsqueda de patrones con expresiones regulares
        rfc_match = re.search(r'[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}', texto_completo)
        folio_match = re.search(r'Folio[:\s]+([A-Z0-9]+)', texto_completo, re.IGNORECASE)
        monto_match = re.search(r'\$\s*([\d,]+\.\d{2})', texto_completo)
        
        rfc = rfc_match.group(0) if rfc_match else "No detectado"
        folio = folio_match.group(1) if folio_match else "No detectado"
        monto = monto_match.group(1) if monto_match else "0.00"
        
        return {
            "RFC": rfc,
            "Folio/Número Control": folio,
            "Monto Declarado": monto,
            "Estado": "Procesado Exitosamente"
        }
    except Exception as e:
        return {"Error": f"No se pudo leer el PDF: {str(e)}"}

# -----------------------------------------------------------------------------
# MOTOR DE ACREDITAMIENTO FIFO DE IVA
# -----------------------------------------------------------------------------
def calcular_acreditamiento_fifo(df_saldos, df_aplicaciones):
    """Calcula la aplicación del saldo a favor del IVA con método FIFO."""
    # Lógica demostrativa FIFO
    df_saldos['Saldo_Restante'] = df_saldos['Monto_Original']
    resultados = []
    
    for idx, app in df_aplicaciones.iterrows():
        monto_a_cubrir = app['Monto_A_Acreditar']
        periodo_app = app['Periodo_Aplicacion']
        
        for s_idx, saldo in df_saldos.iterrows():
            if saldo['Saldo_Restante'] > 0 and monto_a_cubrir > 0:
                aplicado = min(saldo['Saldo_Restante'], monto_a_cubrir)
                df_saldos.at[s_idx, 'Saldo_Restante'] -= aplicado
                monto_a_cubrir -= aplicado
                
                resultados.append({
                    "Periodo Aplicación": periodo_app,
                    "Origen Saldo (Periodo)": saldo['Periodo_Origen'],
                    "Monto Aplicado": aplicado,
                    "Remanente Origen": df_saldos.at[s_idx, 'Saldo_Restante']
                })
            if monto_a_cubrir == 0:
                break
                
    return pd.DataFrame(resultados), df_saldos

# -----------------------------------------------------------------------------
# INTERFAZ DE USUARIO: VISTA DE AUTENTICACIÓN / BIENVENIDA
# -----------------------------------------------------------------------------
if not st.session_state['logged_in']:
    st.markdown("<h1 class='main-header'>🏛️ Bóveda IVA Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #64748b;'>Plataforma Inteligente de Gestión y Acreditamiento de IVA</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_planes = st.tabs(["🔐 Iniciar Sesión", "💳 Planes y Precios"])
        
        with tab_login:
            st.markdown("<div class='card-box'>", unsafe_allow_html=True)
            usuario = st.text_input("Usuario (Correo Electrónico)")
            password = st.text_input("Contraseña", type="password")
            
            if st.button("Iniciar Sesión", use_container_width=True):
                if usuario and password:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = usuario
                    st.success("¡Bienvenido a Bóveda IVA Pro!")
                    st.rerun()
                else:
                    st.error("Por favor ingresa usuario y contraseña.")
            st.markdown("</div>", unsafe_allow_html=True)
            
        with tab_planes:
            st.markdown("<div class='card-box'>", unsafe_allow_html=True)
            st.subheader("Planes Disponibles")
            st.write("• **Plan Básico:** Hasta 5 contribuyentes y seguimiento manual.")
            st.write("• **Plan Pro:** Contribuyentes ilimitados, lectura de acuses PDF y motor FIFO.")
            st.write("• **Plan Despacho (S.C.):** Acceso multiusuario con roles y auditoría automatizada.")
            st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# INTERFAZ PRINCIPAL (DESPUÉS DE INICIAR SESIÓN)
# -----------------------------------------------------------------------------
else:
    # Barra lateral de navegación
    st.sidebar.title("🏛️ Bóveda IVA Pro")
    st.sidebar.write(f"👤 **Usuario:** {st.session_state['username']}")
    
    menu = st.sidebar.radio(
        "Menú de Navegación",
        ["📊 Panel de Control", "📄 Lectura de Acuses PDF", "🔄 Motor FIFO (Acreditamiento)", "📁 Gestión de Devoluciones (FED)", "⚙️ Configuración"]
    )
    
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        st.session_state['logged_in'] = False
        st.rerun()

    # SECTION: PANEL DE CONTROL
    if menu == "📊 Panel de Control":
        st.title("📊 Panel General de Control")
        st.markdown("Visión global de saldos a favor de IVA y estado de trámites ante el SAT.")
        
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Saldo A Favor Disponible", "$128,450.00 MXN", "+12%")
        col_b.metric("Trámites FED en Proceso", "3 Devoluciones", "En revisión")
        col_c.metric("IVA Acreditado este Mes", "$45,200.00 MXN", "FIFO Aplicado")
        
        st.divider()
        st.subheader("Resumen de Saldos por Periodo")
        datos_demo = {
            "Periodo": ["Ene 2025", "Feb 2025", "Mar 2025", "Abr 2025"],
            "Saldo Inicial": [50000, 40000, 30000, 60000],
            "Acreditado": [10000, 10000, 15000, 0],
            "Remanente": [40000, 30000, 15000, 60000]
        }
        st.dataframe(pd.DataFrame(datos_demo), use_container_width=True)

    # SECTION: LECTURA DE ACUSES PDF
    elif menu == "📄 Lectura de Acuses PDF":
        st.title("📄 Extractor Automático de Acuses SAT / FED")
        st.write("Sube tus acuses de declaración o trámite de devolución en formato PDF para extraer la información automáticamente.")
        
        uploaded_file = st.file_uploader("Cargar Acuse PDF", type=["pdf"])
        if uploaded_file is not None:
            st.info("Procesando documento...")
            resultado = extraer_datos_acuse_pdf(uploaded_file)
            st.success("Extracción completada")
            st.json(resultado)

    # SECTION: MOTOR FIFO
    elif menu == "🔄 Motor FIFO (Acreditamiento)":
        st.title("🔄 Motor de Acreditamiento Automático (FIFO)")
        st.write("Aplica el principio de Primeras Entradas, Primeras Salidas para remanentes de IVA a favor.")
        
        st.subheader("1. Saldos a Favor Registrados")
        saldos_data = pd.DataFrame([
            {"Periodo_Origen": "2024-01", "Monto_Original": 25000.00},
            {"Periodo_Origen": "2024-02", "Monto_Original": 18000.00},
            {"Periodo_Origen": "2024-03", "Monto_Original": 32000.00}
        ])
        st.dataframe(saldos_data, use_container_width=True)
        
        st.subheader("2. Acreditamiento Requerido")
        monto_requerido = st.number_input("Monto de IVA a acreditar en el periodo actual:", min_value=0.0, value=30000.00)
        
        if st.button("Calcular Acreditamiento FIFO"):
            apps = pd.DataFrame([{"Periodo_Aplicacion": datetime.now().strftime("%Y-%m"), "Monto_A_Acreditar": monto_requerido}])
            df_res, df_saldos_mod = calcular_acreditamiento_fifo(saldos_data.copy(), apps)
            
            st.success("Cálculo realizado con éxito")
            st.write("**Detalle de la Aplicación:**")
            st.dataframe(df_res, use_container_width=True)
            st.write("**Estado de Saldos de Origen:**")
            st.dataframe(df_saldos_mod, use_container_width=True)

    # SECTION: GESTIÓN DE DEVOLUCIONES
    elif menu == "📁 Gestión de Devoluciones (FED)":
        st.title("📁 Control de Devoluciones (FED)")
        st.write("Seguimiento detallado a solicitudes de devolución de IVA presentadas ante la autoridad fiscal.")
        
        fed_data = pd.DataFrame([
            {"Folio FED": "FED12938491", "RFC": "ABC120304XYZ", "Monto Solicitado": 85000.00, "Fecha Presentación": "2025-01-15", "Estatus": "Autorizada"},
            {"Folio FED": "FED12938822", "RFC": "ABC120304XYZ", "Monto Solicitado": 43200.00, "Fecha Presentación": "2025-02-10", "Estatus": "En Requerimiento"},
            {"Folio FED": "FED12939010", "RFC": "XYZ980706LMN", "Monto Solicitado": 120000.00, "Fecha Presentación": "2025-03-01", "Estatus": "En Revisión"}
        ])
        st.dataframe(fed_data, use_container_width=True)

    # SECTION: CONFIGURACIÓN
    elif menu == "⚙️ Configuración":
        st.title("⚙️ Configuración del Sistema")
        st.write("Ajustes generales del sistema y claves de acceso.")
        
        st.subheader("Conexión con Supabase / Base de Datos")
        st.text_input("URL de Supabase", type="password", value="https://xyz.supabase.co")
        st.text_input("Anon Key / Service Key", type="password", value="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
        
        if st.button("Guardar Configuración"):
            st.success("Configuración guardada correctamente.")