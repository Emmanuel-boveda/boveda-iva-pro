import streamlit as st
import pandas as pd
import os
from datetime import datetime
import pypdf
import re

# Configuración de la página
st.set_page_config(page_title="Bóveda de Saldos a Favor de IVA - Multi-RFC", layout="wide")

st.title("🏛️ Bóveda de Saldos a Favor de IVA (Multi-Cliente)")
st.markdown("---")

# Archivos de base de datos local
DB_SALDOS = "boveda_iva_saldos.csv"
DB_HISTORIAL = "boveda_iva_historial.csv"

# Inicializar bases de datos si no existen
if not os.path.exists(DB_SALDOS):
    df_saldos = pd.DataFrame(columns=[
        "ID", "RFC", "Periodo_Mes", "Periodo_Anio", "Tipo_Declaracion", 
        "Num_Operacion", "Fecha_Presentacion", "Saldo_Original", "Saldo_Disponible", "Estatus"
    ])
    df_saldos.to_csv(DB_SALDOS, index=False)

if not os.path.exists(DB_HISTORIAL):
    df_historial = pd.DataFrame(columns=[
        "Fecha_Aplicacion", "RFC", "Periodo_Origen", "Num_Operacion_Origen", 
        "Saldo_Anterior", "Monto_Aplicado", "Remanente_Nuevo"
    ])
    df_historial.to_csv(DB_HISTORIAL, index=False)

def cargar_saldos():
    df = pd.read_csv(DB_SALDOS)
    if "Num_Operacion" in df.columns:
        df["Num_Operacion"] = df["Num_Operacion"].astype(str).str.replace(r"\.0$", "", regex=True)
    if "RFC" in df.columns:
        df["RFC"] = df["RFC"].astype(str).str.upper().str.strip()
    return df

def guardar_saldos(df):
    df.to_csv(DB_SALDOS, index=False)

def cargar_historial():
    df = pd.read_csv(DB_HISTORIAL)
    if "Num_Operacion_Origen" in df.columns:
        df["Num_Operacion_Origen"] = df["Num_Operacion_Origen"].astype(str).str.replace(r"\.0$", "", regex=True)
    if "RFC" in df.columns:
        df["RFC"] = df["RFC"].astype(str).str.upper().str.strip()
    return df

def guardar_historial(df):
    df.to_csv(DB_HISTORIAL, index=False)

def mes_a_numero(mes_str):
    """Convierte el nombre del mes en un número para permitir un ordenamiento cronológico perfecto."""
    meses_dict = {
        "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
        "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12
    }
    return meses_dict.get(str(mes_str).capitalize(), 1)

def extraer_datos_pdf(uploaded_file):
    """Extrae con precisión los datos del acuse oficial del SAT."""
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
        "fecha_pres": datetime.now().date()
    }
    
    # 1. Extraer RFC
    match_rfc = re.search(r"RFC[:\s]*([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})", texto, re.IGNORECASE)
    if match_rfc:
        datos["rfc"] = match_rfc.group(1).upper()

    # 2. Extraer Número de Operación / Folio
    match_op = re.search(r"Número\s+de\s+operación[:\s]*([0-9]+(?:\.[0-9]+)?)", texto, re.IGNORECASE)
    if match_op:
        raw_op = match_op.group(1)
        datos["num_operacion"] = str(int(float(raw_op))) if "." in raw_op else raw_op
        
    # 3. Extraer Fecha de Presentación
    match_fecha = re.search(r"Fecha\s+y\s+hora\s+de\s+presentación[:\s]*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    if match_fecha:
        try:
            datos["fecha_pres"] = datetime.strptime(match_fecha.group(1), "%d/%m/%Y").date()
        except:
            pass

    match_anio = re.search(r"Ejercicio[:\s]*(\d{4})", texto, re.IGNORECASE)
    if match_anio:
        try:
            datos["anio"] = int(match_anio.group(1))
        except:
            pass

    # 4. Extraer Mes del Periodo
    meses_validos = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    for m in meses_validos:
        if re.search(rf"(?:Período|Periodo)[^\n]*?{m}", texto, re.IGNORECASE):
            datos["mes"] = m
            break
    else:
        for m in meses_validos:
            if re.search(rf"\b{m}\b", texto, re.IGNORECASE):
                datos["mes"] = m
                break

    # 5. Extraer Saldo a Favor de IVA
    if "Impuesto al Valor Agregado" in texto:
        partes_iva = texto.split("Impuesto al Valor Agregado")
        if len(partes_iva) > 1:
            bloque_iva = partes_iva[1][:200]
            match_afavor = re.search(r"A\s+favor[:\s]*([\d,]+)", bloque_iva, re.IGNORECASE)
            if match_afavor:
                monto_str = match_afavor.group(1).replace(",", "")
                try:
                    datos["saldo_favor"] = int(monto_str)
                except:
                    pass

    return datos, texto

# --- BARRA LATERAL (MULTI-RFC Y NAVEGACIÓN) ---
st.sidebar.header("📁 Control Multi-Cliente")
df_global = cargar_saldos()

lista_rfcs = sorted(df_global["RFC"].unique().tolist()) if not df_global.empty else []

st.sidebar.markdown("---")
rfc_seleccionado = ""
if lista_rfcs:
    rfc_seleccionado = st.sidebar.selectbox("Seleccionar Cliente (RFC Activo)", lista_rfcs)
else:
    st.sidebar.info("No hay RFCs registrados aún. Carga una declaración o saldo inicial.")

st.sidebar.markdown("---")
opcion = st.sidebar.radio(
    "Navegación", 
    ["📊 Resumen de Bóveda", "➕ Registrar Saldo Inicial / Remanente", "📥 Nueva Declaración", "💸 Aplicar Acreditamiento", "📜 Historial de Aplicaciones"],
    key="menu_navegacion"
)

# 1. RESUMEN DE BÓVEDA (Ordenado Cronológicamente)
if opcion == "📊 Resumen de Bóveda":
    st.header("Saldos a Favor en Bóveda (Por Cliente)")
    
    if df_global.empty:
        st.info("No hay registros en la bóveda de ningún cliente.")
    elif not rfc_seleccionado:
        st.warning("Selecciona un RFC en el menú lateral.")
    else:
        df_cliente = df_global[df_global["RFC"] == rfc_seleccionado].copy()
        
        # Ordenar cronológicamente por Año y Mes
        if not df_cliente.empty:
            df_cliente["Mes_Num"] = df_cliente["Periodo_Mes"].apply(mes_a_numero)
            df_cliente = df_cliente.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
        
        st.subheader(f"Contribuyente RFC: {rfc_seleccionado}")
        
        df_mostrar = df_cliente.copy()
        df_mostrar["Saldo_Original"] = df_mostrar["Saldo_Original"].apply(lambda x: f"${int(x):,}")
        df_mostrar["Saldo_Disponible"] = df_mostrar["Saldo_Disponible"].apply(lambda x: f"${int(x):,}")
        
        st.dataframe(df_mostrar, use_container_width=True)
        
        df_vigentes = df_cliente[df_cliente["Estatus"] == "Vigente"]
        total_disponible = int(df_vigentes["Saldo_Disponible"].sum()) if not df_vigentes.empty else 0
        st.metric(label=f"Total Saldos Disponibles (Vigentes) - {rfc_seleccionado}", value=f"${total_disponible:,}")
        
        st.markdown("---")
        st.subheader("⚙️ Administrar Registros de este Cliente")
        
        lista_registros = [f"ID {row['ID']} - {row['Periodo_Mes']} {row['Periodo_Anio']} (Saldo Disp: ${int(row['Saldo_Disponible']):,})" for index, row in df_cliente.iterrows()]
        
        if lista_registros:
            seleccion_str = st.selectbox("Selecciona el registro a administrar:", lista_registros)
            
            if seleccion_str:
                id_seleccionado = int(seleccion_str.split(" - ")[0].replace("ID ", ""))
                fila_actual = df_global[df_global["ID"] == id_seleccionado].iloc[0]
                
                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    with st.expander("📝 Editar este registro"):
                        with st.form(f"form_editar_{id_seleccionado}"):
                            nuevo_saldo_disp = st.number_input("Nuevo Saldo Disponible ($)", min_value=0, step=1, value=int(fila_actual["Saldo_Disponible"]))
                            nuevo_estatus = st.selectbox("Estatus", ["Vigente", "Agotado", "Sustituido"], index=["Vigente", "Agotado", "Sustituido"].index(fila_actual["Estatus"]))
                            nuevo_num_op = st.text_input("Número de Operación", value=str(fila_actual["Num_Operacion"]))
                            
                            guardar_cambios = st.form_submit_button("Guardar Cambios")
                            if guardar_cambios:
                                df_global.loc[df_global["ID"] == id_seleccionado, "Saldo_Disponible"] = int(nuevo_saldo_disp)
                                df_global.loc[df_global["ID"] == id_seleccionado, "Estatus"] = nuevo_estatus
                                df_global.loc[df_global["ID"] == id_seleccionado, "Num_Operacion"] = str(nuevo_num_op).replace(".0", "")
                                guardar_saldos(df_global)
                                st.success("¡Registro actualizado con éxito!")
                                st.rerun()
                
                with col_btn2:
                    with st.expander("🗑️ Eliminar este registro"):
                        st.warning("⚠️ Esta acción eliminará permanentemente este registro.")
                        confirmar_eliminar = st.checkbox("Confirmo que deseo eliminar este registro", key=f"chk_del_{id_seleccionado}")
                        if st.button("Eliminar Registro Definitivamente", type="primary"):
                            if confirmar_eliminar:
                                df_global = df_global[df_global["ID"] != id_seleccionado]
                                guardar_saldos(df_global)
                                st.success("¡Registro eliminado correctamente!")
                                st.rerun()
                            else:
                                st.error("Debes marcar la casilla de confirmación.")

# 2. REGISTRAR SALDO INICIAL / REMANENTE
elif opcion == "➕ Registrar Saldo Inicial / Remanente":
    st.header("Cargar Saldo Inicial de Papel de Trabajo (Multi-RFC)")
    
    with st.form("form_inicial"):
        col1, col2 = st.columns(2)
        with col1:
            rfc = st.text_input("RFC del Contribuyente", rfc_seleccionado if rfc_seleccionado else "XAXX010101000")
            mes = st.selectbox("Mes de Origen", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
            anio = st.number_input("Año de Origen", min_value=2020, max_value=2030, value=2025)
            num_op = st.text_input("Número de Operación Original")
        with col2:
            fecha_pres = st.date_input("Fecha de Presentación", datetime.now())
            saldo_orig = st.number_input("Saldo a Favor Original ($)", min_value=0, step=1, value=0)
            saldo_disp = st.number_input("Saldo Disponible Actual (Remanente anterior) ($)", min_value=0, step=1, value=0)
        
        submit = st.form_submit_button("Guardar Saldo Inicial")
        
        if submit:
            df = cargar_saldos()
            num_op_limpio = str(num_op).replace(".0", "").strip()
            rfc_limpio = rfc.upper().strip()
            
            # Validación anti-duplicados por número de operación si se proporciona
            if num_op_limpio and not df.empty and num_op_limpio in df["Num_Operacion"].values:
                st.error(f"⚠️ El Número de Operación '{num_op_limpio}' ya se encuentra registrado en la Bóveda.")
            else:
                nuevo_id = int(df["ID"].max()) + 1 if not df.empty else 1
                nueva_fila = {
                    "ID": nuevo_id, "RFC": rfc_limpio, "Periodo_Mes": mes, "Periodo_Anio": int(anio),
                    "Tipo_Declaracion": "Inicial", "Num_Operacion": num_op_limpio, 
                    "Fecha_Presentacion": str(fecha_pres), "Saldo_Original": int(saldo_orig), 
                    "Saldo_Disponible": int(saldo_disp), "Estatus": "Vigente" if saldo_disp > 0 else "Agotado"
                }
                df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)
                guardar_saldos(df)
                st.success(f"¡Saldo Inicial registrado para el RFC {rfc_limpio}!")
                st.rerun()

# 3. NUEVA DECLARACIÓN CON LECTOR DE PDF Y VALIDACIÓN ANTI-DUPLICADOS
elif opcion == "📥 Nueva Declaración":
    st.header("Registrar Nueva Declaración con Saldo a Favor")
    st.write("Sube el archivo PDF del acuse del SAT. El sistema detectará automáticamente el RFC, periodo y monto.")
    
    archivo_pdf = st.file_uploader("Cargar Acuse / Declaración en PDF (SAT)", type=["pdf"])
    
    def_rfc = rfc_seleccionado if rfc_seleccionado else "XAXX010101000"
    def_num_op = ""
    def_saldo = 0
    def_mes_idx = 0
    def_anio = 2026
    def_fecha = datetime.now()
    
    meses_lista = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    if archivo_pdf is not None:
        datos_extraidos, texto_completo = extraer_datos_pdf(archivo_pdf)
        if datos_extraidos:
            st.success("¡PDF leído con éxito! Cliente y datos detectados:")
            def_rfc = datos_extraidos["rfc"] if datos_extraidos["rfc"] else def_rfc
            def_num_op = str(datos_extraidos["num_operacion"]).replace(".0", "")
            def_saldo = int(datos_extraidos["saldo_favor"])
            def_anio = int(datos_extraidos["anio"])
            def_fecha = datos_extraidos["fecha_pres"]
            if datos_extraidos["mes"] in meses_lista:
                def_mes_idx = meses_lista.index(datos_extraidos["mes"])
            
            with st.expander("Ver texto extraído del PDF (para validación)"):
                st.text(texto_completo[:1200])

    with st.form("form_declaracion"):
        col1, col2 = st.columns(2)
        with col1:
            rfc = st.text_input("RFC del Contribuyente (Detectado del PDF)", value=def_rfc)
            mes = st.selectbox("Mes del Periodo", meses_lista, index=def_mes_idx)
            anio = st.number_input("Año del Periodo", min_value=2020, max_value=2030, value=def_anio)
            tipo_dec = st.selectbox("Tipo de Declaración", ["Normal", "Complementaria - Modificación", "Complementaria - Dejar sin Efecto"])
        with col2:
            num_op = st.text_input("Número de Operación / Folio SAT", value=def_num_op)
            fecha_pres = st.date_input("Fecha de Presentación ante el SAT", value=def_fecha)
            saldo_orig = st.number_input("Monto Saldo a Favor Declarado ($)", min_value=0, step=1, value=def_saldo)
        
        submit_dec = st.form_submit_button("Registrar Declaración en Bóveda")
        
        if submit_dec:
            df = cargar_saldos()
            rfc_limpio = rfc.upper().strip()
            num_op_limpio = str(num_op).replace(".0", "").strip()
            
            # Validación: Evitar duplicados exactos por número de operación (siempre que no sea complementaria de sustitución)
            if num_op_limpio and not df.empty and (df["Num_Operacion"] == num_op_limpio).any() and "Complementaria" not in tipo_dec:
                st.error(f"⚠️ El número de operación '{num_op_limpio}' ya se encuentra registrado en el sistema. No se permiten declaraciones duplicadas.")
            else:
                filtro_existente = (df["RFC"] == rfc_limpio) & (df["Periodo_Mes"] == mes) & (df["Periodo_Anio"] == anio)
                
                if "Complementaria" in tipo_dec and df[filtro_existente].shape[0] > 0:
                    df.loc[filtro_existente, "Estatus"] = "Sustituido"
                    st.warning(f"Se aplicó Efecto de Sustitución sobre la declaración previa de {mes} {anio} para el RFC {rfc_limpio}.")
                
                nuevo_id = int(df["ID"].max()) + 1 if not df.empty else 1
                nueva_fila = {
                    "ID": nuevo_id, "RFC": rfc_limpio, "Periodo_Mes": mes, "Periodo_Anio": int(anio),
                    "Tipo_Declaracion": tipo_dec, "Num_Operacion": num_op_limpio, 
                    "Fecha_Presentacion": str(fecha_pres), "Saldo_Original": int(saldo_orig), 
                    "Saldo_Disponible": int(saldo_orig), "Estatus": "Vigente"
                }
                df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)
                guardar_saldos(df)
                st.success(f"¡Declaración registrada correctamente para el cliente {rfc_limpio}!")
                st.rerun()

# 4. APLICAR ACREDITAMIENTO
elif opcion == "💸 Aplicar Acreditamiento":
    st.header(f"Aplicar Acreditamiento de IVA - Cliente: {rfc_seleccionado if rfc_seleccionado else 'Ninguno'}")
    
    if not rfc_seleccionado:
        st.warning("Por favor selecciona un RFC en el menú lateral para aplicarle acreditamientos.")
    else:
        df_saldos = cargar_saldos()
        df_historial = cargar_historial()
        
        # Filtrar saldos vigentes del cliente seleccionado y ordenarlos cronológicamente para el motor FIFO
        df_cliente_vigentes = df_saldos[(df_saldos["RFC"] == rfc_seleccionado) & (df_saldos["Estatus"] == "Vigente")].copy()
        if not df_cliente_vigentes.empty:
            df_cliente_vigentes["Mes_Num"] = df_cliente_vigentes["Periodo_Mes"].apply(mes_a_numero)
            df_cliente_vigentes = df_cliente_vigentes.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
        
        if df_cliente_vigentes.empty:
            st.warning(f"El contribuyente {rfc_seleccionado} no tiene saldos disponibles para acreditar en este momento.")
        else:
            monto_a_aplicar = st.number_input(f"Monto de IVA a pagar a acreditar para {rfc_seleccionado} ($)", min_value=0, step=1, value=0)
            
            if st.button("Aplicar Acreditamiento FIFO"):
                if monto_a_aplicar <= 0:
                    st.error("Ingresa un monto mayor a cero.")
                elif monto_a_aplicar > df_cliente_vigentes["Saldo_Disponible"].sum():
                    st.error("El monto a acreditar supera el saldo total disponible de este cliente.")
                else:
                    st.subheader("📋 Datos para llenar en el Portal del SAT:")
                    st.markdown("---")
                    
                    remanente_por_aplicar = int(monto_a_aplicar)
                    
                    for idx, row in df_cliente_vigentes.iterrows():
                        if remanente_por_aplicar <= 0:
                            break
                        
                        saldo_anterior = int(row["Saldo_Disponible"])
                        usar = min(saldo_anterior, remanente_por_aplicar)
                        remanente_nuevo = saldo_anterior - usar
                        remanente_por_aplicar -= usar
                        
                        folio_limpio = str(row['Num_Operacion']).replace(".0", "")
                        
                        st.success(f"""
                        * **Periodo de Origen:** {row['Periodo_Mes']} {row['Periodo_Anio']}
                        * **Número de Operación:** {folio_limpio}
                        * **Fecha de Presentación:** {row['Fecha_Presentacion']}
                        * **Saldo Anterior:** ${saldo_anterior:,}
                        * **Monto Aplicado Ahorita:** ${usar:,}
                        * **Nuevo Remanente que Queda:** ${remanente_nuevo:,}
                        """)
                        
                        df_saldos.loc[df_saldos["ID"] == row["ID"], "Saldo_Disponible"] = remanente_nuevo
                        if remanente_nuevo == 0:
                            df_saldos.loc[df_saldos["ID"] == row["ID"], "Estatus"] = "Agotado"
                        
                        nueva_bitacora = {
                            "Fecha_Aplicacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "RFC": rfc_seleccionado,
                            "Periodo_Origen": f"{row['Periodo_Mes']} {row['Periodo_Anio']}",
                            "Num_Operacion_Origen": folio_limpio,
                            "Saldo_Anterior": saldo_anterior,
                            "Monto_Aplicado": usar,
                            "Remanente_Nuevo": remanente_nuevo
                        }
                        df_historial = pd.concat([df_historial, pd.DataFrame([nueva_bitacora])], ignore_index=True)
                    
                    guardar_saldos(df_saldos)
                    guardar_historial(df_historial)
                    st.balloons()

# 5. HISTORIAL DE APLICACIONES
elif opcion == "📜 Historial de Aplicaciones":
    st.header(f"Historial de Acreditamientos - Cliente: {rfc_seleccionado if rfc_seleccionado else 'Todos'}")
    df_hist = cargar_historial()
    
    if df_hist.empty:
        st.info("Aún no se han realizado aplicaciones de acreditamiento.")
    else:
        if rfc_seleccionado and "RFC" in df_hist.columns:
            df_hist_cliente = df_hist[df_hist["RFC"] == rfc_seleccionado]
        else:
            df_hist_cliente = df_hist
            
        if df_hist_cliente.empty:
            st.info(f"No hay historial de aplicaciones para el RFC {rfc_seleccionado}.")
        else:
            df_hist_mostrar = df_hist_cliente.copy()
            for col in ["Saldo_Anterior", "Monto_Aplicado", "Remanente_Nuevo"]:
                if col in df_hist_mostrar.columns:
                    df_hist_mostrar[col] = df_hist_mostrar[col].apply(lambda x: f"${int(x):,}")
                    
            st.dataframe(df_hist_mostrar, use_container_width=True)
            st.download_button(
                label="📥 Descargar Bitácora en Excel/CSV",
                data=df_hist_cliente.to_csv(index=False).encode('utf-8'),
                file_name=f"historial_acreditamientos_{rfc_seleccionado if rfc_seleccionado else 'general'}.csv",
                mime="text/csv"
            )