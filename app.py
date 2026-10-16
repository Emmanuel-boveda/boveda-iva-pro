import streamlit as st
import pandas as pd
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Bóveda de Saldos a Favor de IVA",
    page_icon="💼",
    layout="wide"
)

# -----------------------------------------------------------------------------
# OCULTAR CABECERA, MENÚ Y GATO DE GITHUB
# -----------------------------------------------------------------------------
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# INICIALIZAR ALMACENAMIENTO EN LA SESIÓN
# -----------------------------------------------------------------------------
if "declaraciones" not in st.session_state:
    st.session_state.declaraciones = pd.DataFrame(columns=[
        "id", "periodo", "tipo", "fecha_presentacion", "numero_operacion", "saldo_original", "saldo_disponible", "estado"
    ])

if "historial_aplicaciones" not in st.session_state:
    st.session_state.historial_aplicaciones = pd.DataFrame(columns=[
        "fecha_aplicacion", "monto_total_aplicado", "detalle_desglose"
    ])

st.title("💼 Bóveda Inteligente de Saldos a Favor de IVA")
st.markdown("""
Controla tus saldos a favor de IVA, gestiona declaraciones normales y complementarias automáticamente, y aplica tus acreditamientos bajo el criterio **FIFO** (Primero en entrar, primero en salir) con el desglose exacto que exige el SAT.
""")

# -----------------------------------------------------------------------------
# MENÚ LATERAL DE NAVEGACIÓN
# -----------------------------------------------------------------------------
menu = st.sidebar.selectbox(
    "Navegación",
    ["1. Registrar Declaración", "2. Bóveda de Saldos", "3. Aplicar Acreditamiento (FIFO)", "4. Historial y Reportes"]
)

# -----------------------------------------------------------------------------
# SECCIÓN 1: REGISTRAR DECLARACIÓN (Normal o Complementaria)
# -----------------------------------------------------------------------------
if menu == "1. Registrar Declaración":
    st.header("📥 Registrar Declaración con Saldo a Favor")
    st.info("Al subir una complementaria para un periodo ya existente, el sistema archivará la anterior y dejará vigente la nueva.")

    with st.form("form_declaracion"):
        col1, col2 = st.columns(2)

        with col1:
            anio = st.selectbox("Año del Periodo", options=[2024, 2025, 2026, 2027], index=2)
            mes = st.selectbox("Mes del Periodo", options=[
                "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
            ])
            periodo_str = f"{mes} {anio}"

            tipo_dec = st.selectbox("Tipo de Declaración", ["Normal", "Complementaria"])
            fecha_pres = st.date_input("Fecha de Presentación del Acuse", value=datetime.today())

        with col2:
            num_operacion = st.text_input("Número de Operación", placeholder="Ej. 240012345678")
            saldo_favor = st.number_input("Importe del Saldo a Favor ($)", min_value=0.0, format="%.2f", step=100.0)

        submitted = st.form_submit_button("Guardar en la Bóveda")

        if submitted:
            if not num_operacion:
                st.error("El número de operación es obligatorio.")
            elif saldo_favor <= 0:
                st.error("El saldo a favor debe ser mayor a cero.")
            else:
                df = st.session_state.declaraciones

                # Si es complementaria o ya existe una normal para el mismo periodo, sustituir
                mask_vigente = (df["periodo"] == periodo_str) & (df["estado"] == "Vigente")

                if mask_vigente.any():
                    df.loc[mask_vigente, "estado"] = "Sustituida / Sin Efecto"

                nuevo_id = f"{periodo_str}-{tipo_dec}-{datetime.now().strftime('%H%M%S')}"
                nuevo_reg = {
                    "id": nuevo_id,
                    "periodo": periodo_str,
                    "tipo": tipo_dec,
                    "fecha_presentacion": fecha_pres.strftime("%Y-%m-%d"),
                    "numero_operacion": num_operacion,
                    "saldo_original": saldo_favor,
                    "saldo_disponible": saldo_favor,
                    "estado": "Vigente"
                }

                st.session_state.declaraciones = pd.concat([df, pd.DataFrame([nuevo_reg])], ignore_index=True)
                st.success(f"¡Declaración de {periodo_str} guardada y actualizada con éxito en la bóveda!")

# -----------------------------------------------------------------------------
# SECCIÓN 2: BÓVEDA DE SALDOS (Visualización y Eliminación)
# -----------------------------------------------------------------------------
elif menu == "2. Bóveda de Saldos":
    st.header("🔒 Bóveda de Saldos Vigentes")
    st.markdown("Consulta el estado actual de tus saldos a favor o elimina registros ingresados por error.")

    df = st.session_state.declaraciones

    if df.empty:
        st.warning("No hay declaraciones registradas todavía en la bóveda.")
    else:
        tab1