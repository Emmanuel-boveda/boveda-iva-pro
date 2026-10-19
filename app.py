import os
import re
from datetime import datetime, timedelta
import pandas as pd
import pypdf
from supabase import create_client, Client
import gradio as gr

# --- CONFIGURACIÓN DE SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_supabase_client():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            return None
    return None

supabase = get_supabase_client()

# --- REGISTRO DE AUDITORÍA (LOGS) ---
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

# --- FUNCIONES DE DATOS Y LÓGICA GENERAL ---
def mes_a_numero(mes_str):
    meses_dict = {
        "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
        "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12
    }
    return meses_dict.get(str(mes_str).capitalize(), 1)

def cargar_saldos(email):
    try:
        if not supabase:
            return pd.DataFrame()
        response = supabase.table("saldos_iva").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        return df.rename(columns={
            "id": "ID", "rfc": "RFC", "periodo_mes": "Periodo_Mes", "periodo_anio": "Periodo_Anio",
            "tipo_declaracion": "Tipo_Declaracion", "num_operacion": "Num_Operacion",
            "fecha_presentacion": "Fecha_Presentacion", "saldo_original": "Saldo_Original",
            "saldo_disponible": "Saldo_Disponible", "estatus": "Estatus"
        })
    except Exception:
        return pd.DataFrame()

def cargar_historial(email):
    try:
        if not supabase:
            return pd.DataFrame()
        response = supabase.table("historial_acreditamientos").select("*").eq("usuario_email", email).execute()
        data = response.data
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        column_map = {
            "id": "ID", "usuario_email": "Usuario_Email", "fecha_aplicacion": "Fecha_Aplicacion",
            "rfc": "RFC", "periodo_origen": "Periodo_Origen", "periodo_destino": "Declaracion_Aplicada_Destino",
            "num_operacion_origen": "Num_Operacion_Origen", "saldo_anterior": "Saldo_Anterior",
            "monto_aplicado": "Monto_Aplicado", "remanente_nuevo": "Remanente_Nuevo"
        }
        df = df.rename(columns=column_map)
        if "Declaracion_Aplicada_Destino" not in df.columns:
            df["Declaracion_Aplicada_Destino"] = "No especificado"
        return df
    except Exception:
        return pd.DataFrame()

def obtener_rfcs_unicos(email):
    df_saldos = cargar_saldos(email)
    df_hist = cargar_historial(email)
    rfcs = set()
    if not df_saldos.empty and "RFC" in df_saldos.columns:
        rfcs.update(df_saldos["RFC"].dropna().unique().tolist())
    if not df_hist.empty and "RFC" in df_hist.columns:
        rfcs.update(df_hist["RFC"].dropna().unique().tolist())
    return sorted(list(rfcs))

def extraer_datos_pdf(file_obj):
    texto = ""
    try:
        reader = pypdf.PdfReader(file_obj)
        for page in reader.pages:
            texto += page.extract_text() or ""
    except Exception:
        return None, ""

    datos = {
        "rfc": "", "num_operacion": "", "saldo_favor": 0, "mes": "Enero",
        "anio": 2026, "fecha_pres": datetime.now().strftime("%Y-%m-%d"),
        "tipo_declaracion": "Normal"
    }
    
    match_rfc = re.search(r"RFC[:\s]*([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})", texto, re.IGNORECASE)
    if match_rfc:
        datos["rfc"] = match_rfc.group(1).upper()

    match_op = re.search(r"Número\s+de\s+operación[:\s]*([0-9]+(?:\.[0-9]+)?)", texto, re.IGNORECASE)
    if match_op:
        raw_op = match_op.group(1)
        datos["num_operacion"] = str(int(float(raw_op))) if "." in raw_op else raw_op

    match_fecha = re.search(r"Fecha\s+y\s+hora\s+de\s+presentación[:\s]*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    if match_fecha:
        try:
            dt_p = datetime.strptime(match_fecha.group(1), "%d/%m/%Y")
            datos["fecha_pres"] = dt_p.strftime("%Y-%m-%d")
        except Exception:
            pass

    match_anio = re.search(r"Ejercicio[:\s]*(\d{4})", texto, re.IGNORECASE)
    if match_anio:
        try:
            datos["anio"] = int(match_anio.group(1))
        except Exception:
            pass

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
                except Exception:
                    pass

    return datos, texto

# --- LÓGICA DE EVENTOS EN INTERFAZ ---
def login_usuario(email, password):
    email = email.strip().lower()
    if not email or not password:
        return "❌ Por favor ingresa usuario y contraseña.", gr.update(visible=True), gr.update(visible=False), "", "", "", "", gr.update(), gr.update(), gr.update()
    if not supabase:
        return "❌ Error de conexión con Supabase. Revisa las variables de entorno en Render.", gr.update(visible=True), gr.update(visible=False), "", "", "", "", gr.update(), gr.update(), gr.update()
    try:
        res = supabase.table("usuarios_saas").select("*").eq("email", email).execute()
        usuarios = res.data
        if not usuarios:
            return "❌ El usuario no existe o no tiene una cuenta registrada.", gr.update(visible=True), gr.update(visible=False), "", "", "", "", gr.update(), gr.update(), gr.update()
        
        user_data = usuarios[0]
        if user_data.get("password") == password:
            if user_data.get("activo") == False:
                return "❌ Tu suscripción está suspendida o inactiva.", gr.update(visible=True), gr.update(visible=False), "", "", "", "", gr.update(), gr.update(), gr.update()
            
            fecha_exp = user_data.get("fecha_expiracion") or user_data.get("fecha_expuración")
            if fecha_exp:
                exp_date = datetime.strptime(str(fecha_exp), "%Y-%m-%d").date()
                if datetime.now().date() > exp_date:
                    return "❌ Tu suscripción ha expirado. Realiza tu renovación.", gr.update(visible=True), gr.update(visible=False), "", "", "", "", gr.update(), gr.update(), gr.update()
            
            codigo_ref = user_data.get("codigo_referido")
            if not codigo_ref:
                base_nombre = email.split("@")[0].upper()
                digitos_fecha = datetime.now().strftime("%d%m")
                codigo_ref = f"{base_nombre}{digitos_fecha}"

            tipo_plan = user_data.get("plan", "Plan Básico")
            fecha_exp_str = str(fecha_exp) if fecha_exp else "Indefinida"
            
            registrar_log(email, "LOGIN", "Inicio de sesión exitoso en Gradio")

            header_html = f"""
            <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 18px; border-radius: 10px; color: white; margin-bottom: 15px;">
                <h2 style="margin:0; font-size: 1.8rem;">🏛️ Bóveda IVA Pro</h2>
                <p style="margin:5px 0 0 0; color: #e0e7ff;">
                    Bienvenido, <b>{email}</b> | Plan: <b>{tipo_plan}</b> | ⏳ Vence: <b>{fecha_exp_str}</b> | 🎁 Tu Código: <b>{codigo_ref}</b>
                </p>
            </div>
            """
            
            rfcs = obtener_rfcs_unicos(email)
            val_inicial = rfcs[0] if rfcs else ""
            rfc_dropdown_update = gr.update(choices=rfcs, value=val_inicial)

            return (
                "¡Acceso concedido!",
                gr.update(visible=False),
                gr.update(visible=True),
                header_html,
                email,
                tipo_plan,
                rfc_dropdown_update,  # Resumen
                rfc_dropdown_update,  # FIFO
                rfc_dropdown_update   # Historial
            )
        else:
            return "❌ Contraseña incorrecta.", gr.update(visible=True), gr.update(visible=False), "", "", "", "", gr.update(), gr.update(), gr.update()
    except Exception as e:
        return f"Error al validar el acceso: {e}", gr.update(visible=True), gr.update(visible=False), "", "", "", "", gr.update(), gr.update(), gr.update()

def actualizar_vista_resumen(email, rfc):
    if not rfc:
        return "### Selecciona o registra un cliente.", pd.DataFrame(), gr.update(choices=[])
    df = cargar_saldos(email)
    if df.empty:
        return "### No hay datos registrados.", pd.DataFrame(), gr.update(choices=[])
    
    df_cliente = df[df["RFC"] == rfc].copy()
    if df_cliente.empty:
        return f"### Sin registros para {rfc}", pd.DataFrame(), gr.update(choices=[])
    
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
        except Exception:
            return "🟢 Vigente"

    df_cliente["Estatus_Caducidad"] = df_cliente["Fecha_Presentacion"].apply(evaluar_semaforo)
    total_disp = int(df_cliente[df_cliente["Estatus"] == "Vigente"]["Saldo_Disponible"].sum()) if not df_cliente.empty else 0
    metric_html = f"<h3>SALDO TOTAL VIGENTE — {rfc}: <span style='color:#16a34a;'>${total_disp:,} MXN</span></h3>"
    
    ids_lista = df_cliente["ID"].tolist()
    return metric_html, df_cliente, gr.update(choices=ids_lista, value=ids_lista[0] if ids_lista else None)

def eliminar_registro_saldos(email, id_registro, confirma):
    if not confirma:
        return "❌ Debes confirmar la casilla para eliminar."
    if not id_registro:
        return "❌ Selecciona un ID válido."
    try:
        supabase.table("saldos_iva").delete().eq("id", int(id_registro)).execute()
        registrar_log(email, "ELIMINAR_REGISTRO_BOVEDA", f"ID: {id_registro} eliminado")
        return "¡Registro eliminado correctamente de la Bóveda!"
    except Exception as e:
        return f"Error al eliminar: {e}"

def eliminar_cliente_completo(email, rfc_a_eliminar, confirma):
    if not confirma:
        return "❌ Debes confirmar la casilla para eliminar al cliente.", gr.update(), gr.update(), gr.update()
    if not rfc_a_eliminar:
        return "❌ Selecciona un cliente / RFC válido.", gr.update(), gr.update(), gr.update()
    
    try:
        # Eliminar saldos e historial del cliente en Supabase
        supabase.table("saldos_iva").delete().eq("usuario_email", email).eq("rfc", rfc_a_eliminar).execute()
        supabase.table("historial_acreditamientos").delete().eq("usuario_email", email).eq("rfc", rfc_a_eliminar).execute()
        
        registrar_log(email, "ELIMINAR_CLIENTE", f"RFC: {rfc_a_eliminar} borrado completamente")
        
        # Obtener lista actualizada de RFCs
        rfcs_actualizados = obtener_rfcs_unicos(email)
        nuevo_val = rfcs_actualizados[0] if rfcs_actualizados else ""
        upd = gr.update(choices=rfcs_actualizados, value=nuevo_val)
        
        return f"✅ Cliente **{rfc_a_eliminar}** y todo su historial fueron eliminados correctamente.", upd, upd, upd
    except Exception as e:
        return f"Error al eliminar cliente: {e}", gr.update(), gr.update(), gr.update()

def procesar_pdf(file_obj):
    if file_obj is None:
        return "", "", 0, "Enero", 2026, datetime.now().strftime("%Y-%m-%d"), "Normal"
    datos, _ = extraer_datos_pdf(file_obj.name if hasattr(file_obj, 'name') else file_obj)
    if datos:
        return (
            datos.get("rfc", ""),
            datos.get("num_operacion", ""),
            datos.get("saldo_favor", 0),
            datos.get("mes", "Enero"),
            datos.get("anio", 2026),
            datos.get("fecha_pres", datetime.now().strftime("%Y-%m-%d")),
            datos.get("tipo_declaracion", "Normal")
        )
    return "", "", 0, "Enero", 2026, datetime.now().strftime("%Y-%m-%d"), "Normal"

def guardar_declaracion_pdf(email, plan, rfc, mes, anio, tipo_dec, num_op, fecha_pres, saldo_orig, confirma_mod):
    rfc_limpio = rfc.upper().strip()
    num_op_limpio = str(num_op).replace(".0", "").strip()
    rfcs_actuales = obtener_rfcs_unicos(email)
    limite_rfc = 5 if ("basico" in str(plan).lower() or "básico" in str(plan).lower()) else 999999
    
    if rfc_limpio not in rfcs_actuales and len(rfcs_actuales) >= limite_rfc:
        return "🚫 Has alcanzado el límite de RFCs de tu plan.", gr.update(), gr.update(), gr.update()
    if not num_op_limpio:
        return "❌ El número de operación es obligatorio.", gr.update(), gr.update(), gr.update()
    
    try:
        check_dup = supabase.table("saldos_iva").select("id").eq("usuario_email", email).eq("num_operacion", num_op_limpio).execute()
        if check_dup.data:
            return f"❌ El Número de Operación '{num_op_limpio}' ya está registrado.", gr.update(), gr.update(), gr.update()
        
        if "Complementaria" in tipo_dec or confirma_mod:
            supabase.table("saldos_iva").update({"estatus": "Sustituido"}).eq("usuario_email", email).eq("rfc", rfc_limpio).eq("periodo_mes", mes).eq("periodo_anio", int(anio)).execute()

        supabase.table("saldos_iva").insert({
            "usuario_email": email,
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
        
        registrar_log(email, "CARGA_DECLARACION_PDF", f"RFC: {rfc_limpio} | Monto: ${saldo_orig} MXN")
        
        rfcs_nuevos = obtener_rfcs_unicos(email)
        upd = gr.update(choices=rfcs_nuevos, value=rfc_limpio)
        
        return "¡Declaración registrada correctamente!", upd, upd, upd
    except Exception as e:
        return f"Error al registrar: {e}", gr.update(), gr.update(), gr.update()

def ejecutar_fifo(email, rfc, monto, mes_dest, anio_dest):
    if not rfc:
        return "❌ Selecciona un RFC.", pd.DataFrame()
    if monto <= 0:
        return "❌ Ingresa un monto mayor a cero.", pd.DataFrame()
    
    df_saldos = cargar_saldos(email)
    df_vigentes = df_saldos[(df_saldos["RFC"] == rfc) & (df_saldos["Estatus"] == "Vigente")].copy()
    if df_vigentes.empty:
        return "❌ No hay saldos vigentes disponibles para este cliente.", pd.DataFrame()
    
    df_vigentes["Mes_Num"] = df_vigentes["Periodo_Mes"].apply(mes_a_numero)
    df_vigentes = df_vigentes.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
    
    if monto > df_vigentes["Saldo_Disponible"].sum():
        return "❌ El monto excede el saldo total disponible.", pd.DataFrame()
    
    remanente_por_aplicar = int(monto)
    periodo_destino_str = f"{mes_dest} {anio_dest}"
    desglose_sat = []

    try:
        for idx, row in df_vigentes.iterrows():
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
                "usuario_email": email,
                "fecha_aplicacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "rfc": rfc,
                "periodo_origen": f"{row['Periodo_Mes']} {row['Periodo_Anio']}",
                "num_operacion_origen": folio_limpio,
                "saldo_anterior": float(saldo_anterior),
                "monto_aplicado": float(usar),
                "remanente_nuevo": float(remanente_nuevo),
                "periodo_destino": periodo_destino_str
            }
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

        registrar_log(email, "EJECUCION_FIFO", f"RFC: {rfc} | Aplicado en {periodo_destino_str} | Monto: ${monto} MXN")
        return f"¡Acreditamiento FIFO aplicado con éxito para {periodo_destino_str}!", pd.DataFrame(desglose_sat)
    except Exception as e:
        return f"Error al ejecutar: {e}", pd.DataFrame()

def obtener_historial_vista(email, rfc):
    df_hist = cargar_historial(email)
    if df_hist.empty:
        return pd.DataFrame(), gr.update(choices=[])
    df_cliente = df_hist[df_hist["RFC"] == rfc] if rfc else df_hist
    if df_cliente.empty:
        return pd.DataFrame(), gr.update(choices=[])
    
    cols = [c for c in ["ID", "Fecha_Aplicacion", "RFC", "Periodo_Origen", "Declaracion_Aplicada_Destino", "Num_Operacion_Origen", "Saldo_Anterior", "Monto_Aplicado", "Remanente_Nuevo"] if c in df_cliente.columns]
    df_disp = df_cliente[cols]
    ids = df_disp["ID"].tolist()
    return df_disp, gr.update(choices=ids, value=ids[0] if ids else None)

def eliminar_historial_item(email, id_item, confirma):
    if not confirma:
        return "❌ Debes confirmar la casilla para eliminar."
    if not id_item:
        return "❌ Selecciona un ID válido."
    try:
        supabase.table("historial_acreditamientos").delete().eq("id", int(id_item)).execute()
        registrar_log(email, "ELIMINAR_REGISTRO_HISTORIAL", f"ID: {id_item} eliminado")
        return "¡Registro de historial eliminado correctamente!"
    except Exception as e:
        return f"Error al eliminar: {e}"

# --- CONSTRUCCIÓN DE INTERFAZ GRADIO ---
with gr.Blocks(theme=gr.themes.Soft(), title="Bóveda IVA Pro") as demo:
    
    # Estados internos de sesión
    state_email = gr.State("")
    state_plan = gr.State("")

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

    # Vista Principal de la App (Protegida)
    with gr.Column(visible=False) as panel_app:
        html_header = gr.HTML()
        
        with gr.Tabs():
            with gr.TabItem("📊 Resumen y Bóveda"):
                with gr.Row():
                    drop_rfc_resumen = gr.Dropdown(label="Seleccionar RFC del Cliente", choices=[], interactive=True)
                    btn_actualizar_resumen = gr.Button("🔄 Actualizar Datos")
                
                html_metricas = gr.HTML()
                tabla_saldos_resumen = gr.DataFrame(label="Saldos Registrados en la Bóveda")
                
                with gr.Row():
                    drop_id_del = gr.Dropdown(label="Seleccionar ID de Declaración a Eliminar", choices=[])
                    chk_confirma_del = gr.Checkbox(label="Confirmo eliminar este registro individual")
                    btn_eliminar_reg = gr.Button("🗑️ Eliminar Registro Seleccionado", variant="stop")
                lbl_del_res = gr.Markdown()

                gr.Markdown("---")
                gr.Markdown("### ⚠️ Gestión de Clientes")
                with gr.Row():
                    chk_confirma_del_cliente = gr.Checkbox(label="Confirmo ELIMINAR COMPLETAMENTE al cliente seleccionado arriba y todo su historial")
                    btn_eliminar_cliente = gr.Button("🚨 Eliminar Cliente Completo", variant="stop")
                lbl_del_cliente_res = gr.Markdown()

            with gr.TabItem("📥 Carga de Declaraciones (PDF)"):
                gr.Markdown("### Sube la declaración en formato PDF para extraer los datos automáticamente o regístrala de forma manual.")
                with gr.Row():
                    file_pdf = gr.File(label="Subir Declaración PDF del SAT", file_types=[".pdf"])
                
                with gr.Row():
                    txt_rfc_pdf = gr.Textbox(label="RFC del Contribuyente")
                    drop_mes_pdf = gr.Dropdown(label="Periodo (Mes)", choices=["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], value="Enero")
                    num_anio_pdf = gr.Number(label="Ejercicio (Año)", value=2026, precision=0)
                
                with gr.Row():
                    drop_tipo_pdf = gr.Dropdown(label="Tipo de Declaración", choices=["Normal", "Complementaria - Modificación", "Complementaria - Dejar sin Efecto"], value="Normal")
                    txt_num_op_pdf = gr.Textbox(label="Número de Operación / Folio SAT")
                    date_pres_pdf = gr.Textbox(label="Fecha de Presentación (YYYY-MM-DD)", value=datetime.now().strftime("%Y-%m-%d"))
                
                with gr.Row():
                    num_saldo_pdf = gr.Number(label="Monto del Saldo a Favor ($)", value=0)
                    chk_mod_pdf = gr.Checkbox(label="Sustituir declaración anterior del mismo periodo")
                
                btn_guardar_pdf = gr.Button("💾 Registrar en Bóveda", variant="primary")
                lbl_guardar_pdf_res = gr.Markdown()

            with gr.TabItem("⚙️ Motor FIFO / Acreditamiento"):
                gr.Markdown("### Aplica tus saldos a favor vigentes de manera cronológica (método FIFO).")
                with gr.Row():
                    drop_rfc_fifo = gr.Dropdown(label="Seleccionar RFC", choices=[], interactive=True)
                    num_monto_fifo = gr.Number(label="Monto a Aplicar ($)")
                with gr.Row():
                    drop_mes_dest = gr.Dropdown(label="Periodo Destino (Mes)", choices=["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], value="Enero")
                    num_anio_dest = gr.Number(label="Ejercicio Destino (Año)", value=2026, precision=0)
                
                btn_ejecutar_fifo = gr.Button("🚀 Ejecutar Acreditamiento FIFO", variant="primary")
                lbl_fifo_res = gr.Markdown()
                tabla_fifo_desglose = gr.DataFrame(label="Desglose del Acreditamiento Aplicado")

            with gr.TabItem("📜 Historial"):
                with gr.Row():
                    drop_rfc_hist = gr.Dropdown(label="Filtrar por RFC", choices=[], interactive=True)
                    btn_ver_hist = gr.Button("🔍 Consultar Historial")
                
                tabla_historial = gr.DataFrame(label="Historial de Acreditamientos Aplicados")
                with gr.Row():
                    drop_id_hist = gr.Dropdown(label="ID de Historial a Eliminar", choices=[])
                    chk_confirma_hist = gr.Checkbox(label="Confirmo eliminar este registro del historial")
                    btn_del_hist = gr.Button("🗑️ Eliminar Historial Seleccionado", variant="stop")
                lbl_hist_del_res = gr.Markdown()

    # --- ENLACES DE EVENTOS ---
    btn_ingresar.click(
        fn=login_usuario,
        inputs=[txt_user, txt_pass],
        outputs=[lbl_msg, panel_login, panel_app, html_header, state_email, state_plan, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    # Actualizar vista de Resumen al seleccionar cliente
    drop_rfc_resumen.change(
        fn=actualizar_vista_resumen,
        inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_del]
    )

    btn_actualizar_resumen.click(
        fn=actualizar_vista_resumen,
        inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_del]
    )

    btn_eliminar_reg.click(
        fn=eliminar_registro_saldos,
        inputs=[state_email, drop_id_del, chk_confirma_del],
        outputs=[lbl_del_res]
    ).then(
        fn=actualizar_vista_resumen,
        inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_del]
    )

    # Eliminar cliente completo
    btn_eliminar_cliente.click(
        fn=eliminar_cliente_completo,
        inputs=[state_email, drop_rfc_resumen, chk_confirma_del_cliente],
        outputs=[lbl_del_cliente_res, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    # Procesar PDF automáticamente
    file_pdf.change(
        fn=procesar_pdf,
        inputs=[file_pdf],
        outputs=[txt_rfc_pdf, txt_num_op_pdf, num_saldo_pdf, drop_mes_pdf, num_anio_pdf, date_pres_pdf, drop_tipo_pdf]
    )

    btn_guardar_pdf.click(
        fn=guardar_declaracion_pdf,
        inputs=[state_email, state_plan, txt_rfc_pdf, drop_mes_pdf, num_anio_pdf, drop_tipo_pdf, txt_num_op_pdf, date_pres_pdf, num_saldo_pdf, chk_mod_pdf],
        outputs=[lbl_guardar_pdf_res, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    # FIFO
    btn_ejecutar_fifo.click(
        fn=ejecutar_fifo,
        inputs=[state_email, drop_rfc_fifo, num_monto_fifo, drop_mes_dest, num_anio_dest],
        outputs=[lbl_fifo_res, tabla_fifo_desglose]
    )

    # Historial
    btn_ver_hist.click(
        fn=obtener_historial_vista,
        inputs=[state_email, drop_rfc_hist],
        outputs=[tabla_historial, drop_id_hist]
    )

    btn_del_hist.click(
        fn=eliminar_historial_item,
        inputs=[state_email, drop_id_hist, chk_confirma_hist],
        outputs=[lbl_hist_del_res]
    ).then(
        fn=obtener_historial_vista,
        inputs=[state_email, drop_rfc_hist],
        outputs=[tabla_historial, drop_id_hist]
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
