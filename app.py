import os
import re
from datetime import datetime
import pandas as pd
import pypdf
from supabase import create_client, Client
import gradio as gr

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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

# --- LÓGICA DE DATOS ---
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
            "saldo_disponible": "Saldo_Disponible", "estatus": "Estatus",
            "folio_fed": "Folio_FED", "fecha_ingreso_fed": "Fecha_Ingreso_FED", "observaciones_fed": "Observaciones_FED"
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

def exportar_dataframe_excel(df, nombre_archivo):
    if df.empty:
        return None
    ruta_archivo = f"./{nombre_archivo}.xlsx"
    try:
        df.to_excel(ruta_archivo, index=False, engine='openpyxl')
        return ruta_archivo
    except Exception:
        return None

def obtener_o_crear_plantilla_excel():
    ruta = "./Plantilla_Carga_Masiva_BovedaIVA.xlsx"
    if not os.path.exists(ruta):
        datos_ejemplo = [
            {
                "RFC": "XAXX010101000", "Periodo_Mes": "Enero", "Periodo_Anio": 2026,
                "Tipo_Declaracion": "Normal", "Num_Operacion": "100200300",
                "Fecha_Presentacion": "2026-02-17", "Saldo_Original": 15000
            },
            {
                "RFC": "XAXX010101000", "Periodo_Mes": "Febrero", "Periodo_Anio": 2026,
                "Tipo_Declaracion": "Normal", "Num_Operacion": "100200301",
                "Fecha_Presentacion": "2026-03-17", "Saldo_Original": 22500
            }
        ]
        df_plantilla = pd.DataFrame(datos_ejemplo)
        df_plantilla.to_excel(ruta, index=False, engine='openpyxl')
    return ruta

PLANTILLA_EXCEL_PATH = obtener_o_crear_plantilla_excel()

def procesar_carga_masiva_excel(email, plan, archivo_excel):
    if archivo_excel is None:
        return "❌ Por favor sube un archivo Excel válido.", gr.update(), gr.update(), gr.update()
    
    ruta_file = archivo_excel.name if hasattr(archivo_excel, 'name') else archivo_excel
    try:
        df_excel = pd.read_excel(ruta_file, engine='openpyxl')
    except Exception as e:
        return f"❌ Error al leer el archivo Excel: {str(e)}", gr.update(), gr.update(), gr.update()

    columnas_requeridas = ["RFC", "Periodo_Mes", "Periodo_Anio", "Tipo_Declaracion", "Num_Operacion", "Fecha_Presentacion", "Saldo_Original"]
    for col in columnas_requeridas:
        if col not in df_excel.columns:
            return f"❌ Formato incorrecto. Falta la columna obligatoria: '{col}'. Descarga la plantilla guía.", gr.update(), gr.update(), gr.update()

    rfcs_actuales = obtener_rfcs_unicos(email)
    limite_rfc = 5 if ("basico" in str(plan).lower() or "básico" in str(plan).lower()) else 999999

    registros_creados = 0
    registros_omitidos = 0

    for idx, row in df_excel.iterrows():
        try:
            rfc_limpio = str(row["RFC"]).upper().strip()
            num_op_limpio = str(row["Num_Operacion"]).replace(".0", "").strip()
            mes = str(row["Periodo_Mes"]).capitalize().strip()
            anio = int(row["Periodo_Anio"])
            tipo_dec = str(row["Tipo_Declaracion"]).strip()
            fecha_pres = str(row["Fecha_Presentacion"]).split()[0]
            saldo_orig = float(row["Saldo_Original"])

            if not rfc_limpio or rfc_limpio == "NAN" or not num_op_limpio or num_op_limpio == "NAN":
                registros_omitidos += 1
                continue

            if rfc_limpio not in rfcs_actuales and len(rfcs_actuales) >= limite_rfc:
                registros_omitidos += 1
                continue

            check_dup = supabase.table("saldos_iva").select("id").eq("usuario_email", email).eq("num_operacion", num_op_limpio).execute()
            if check_dup.data:
                registros_omitidos += 1
                continue

            supabase.table("saldos_iva").insert({
                "usuario_email": email, "rfc": rfc_limpio, "periodo_mes": mes,
                "periodo_anio": anio, "tipo_declaracion": tipo_dec, "num_operacion": num_op_limpio,
                "fecha_presentacion": fecha_pres, "saldo_original": saldo_orig,
                "saldo_disponible": saldo_orig, "estatus": "Vigente"
            }).execute()

            registros_creados += 1
            if rfc_limpio not in rfcs_actuales:
                rfcs_actuales.append(rfc_limpio)

        except Exception:
            registros_omitidos += 1

    registrar_log(email, "CARGA_MASIVA_EXCEL", f"Registros ingresados: {registros_creados} | Omitidos: {registros_omitidos}")
    rfcs_actualizados = obtener_rfcs_unicos(email)
    val_init = rfcs_actualizados[0] if rfcs_actualizados else None

    msg = f"✅ **Carga Masiva Finalizada:** {registros_creados} declaraciones registradas exitosamente."
    if registros_omitidos > 0:
        msg += f" (Se omitieron {registros_omitidos} filas por estar duplicadas o incompletas)."

    upd = gr.update(choices=rfcs_actualizados, value=val_init)
    return msg, upd, upd, upd

def generar_pdf_expediente_fed_real(datos_saldo, logo_path=None):
    rfc_raw = str(datos_saldo.get("RFC", "N/A"))
    rfc = re.sub(r'[^a-zA-Z0-9]', '_', rfc_raw)
    id_reg = str(datos_saldo.get("ID", "0"))
    filename = f"./Expediente_FED_{rfc}_{id_reg}.pdf"

    doc = SimpleDocTemplate(
        filename, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()
    story = []

    primary_color = colors.HexColor("#1e3c72")
    secondary_color = colors.HexColor("#2a5298")
    accent_color = colors.HexColor("#dc2626")
    light_bg = colors.HexColor("#f8fafc")
    dark_text = colors.HexColor("#0f172a")

    style_title = ParagraphStyle('DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, textColor=primary_color, leading=20)
    style_subtitle = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#475569"), leading=12)
    style_h2 = ParagraphStyle('SectionHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=primary_color, spaceBefore=10, spaceAfter=5, leading=14)
    style_body = ParagraphStyle('BodyDark', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=dark_text, leading=11)
    style_badge = ParagraphStyle('BadgeText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=1)

    header_elements = []
    if logo_path and os.path.exists(logo_path):
        try:
            img_logo = RLImage(logo_path, width=1.5*72, height=0.6*72)
            header_elements.append(img_logo)
        except Exception:
            header_elements.append(Paragraph("<b>BÓVEDA IVA PRO</b>", style_title))
    else:
        header_elements.append(Paragraph("<b>BÓVEDA IVA PRO</b><br/><font size=7 color='#64748b'>SISTEMA DE AUDITORÍA E INTEGRIDAD</font>", style_title))

    header_table_data = [
        [
            header_elements[0],
            Paragraph(f"<font size=8><b>DICTAMEN TÉCNICO FED</b><br/>SOLICITUD DE DEVOLUCIÓN DE IVA<br/><b>ESTATUS: {datos_saldo.get('Estatus', 'EN TRÁMITE FED')}</b></font>", ParagraphStyle('RHeader', parent=style_subtitle, alignment=2))
        ]
    ]
    t_header = Table(header_table_data, colWidths=[300, 240])
    t_header.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(t_header)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=2, color=primary_color, spaceAfter=8))

    banner_text = f"🔒 <b>ESTATUS: SALDO BLOQUEADO EN BÓVEDA POR TRÁMITE FED EN PROCESO</b>" if "TRÁMITE" in str(datos_saldo.get('Estatus')).upper() else f"<b>ESTATUS DEL SALDO: {datos_saldo.get('Estatus')}</b>"
    banner_bg = accent_color if "TRÁMITE" in str(datos_saldo.get('Estatus')).upper() else primary_color
    t_banner = Table([[Paragraph(banner_text, style_badge)]], colWidths=[540])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), banner_bg),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 8))

    monto_orig = float(datos_saldo.get("Saldo_Original", 0))
    monto_disp = float(datos_saldo.get("Saldo_Disponible", 0))

    datos_gen = [
        [Paragraph("<b>RFC Contribuyente:</b>", style_body), Paragraph(str(rfc_raw), style_body), Paragraph("<b>Folio Interno Bóveda:</b>", style_body), Paragraph(f"FED-{id_reg}", style_body)],
        [Paragraph("<b>Periodo / Ejercicio Origen:</b>", style_body), Paragraph(f"{datos_saldo.get('Periodo_Mes')} {datos_saldo.get('Periodo_Anio')}", style_body), Paragraph("<b>Fecha de Ingreso SAT:</b>", style_body), Paragraph(str(datos_saldo.get('Fecha_Ingreso_FED', datetime.now().strftime('%Y-%m-%d'))), style_body)],
        [Paragraph("<b>Tipo de Declaración:</b>", style_body), Paragraph(str(datos_saldo.get('Tipo_Declaracion', 'Normal')), style_body), Paragraph("<b>Número de Operación SAT:</b>", style_body), Paragraph(str(datos_saldo.get('Num_Operacion', 'N/A')), style_body)],
        [Paragraph("<b>Fecha de Presentación:</b>", style_body), Paragraph(str(datos_saldo.get('Fecha_Presentacion', 'N/A')), style_body), Paragraph("<b>Folio Trámite FED SAT:</b>", style_body), Paragraph(str(datos_saldo.get('Folio_FED', 'En Proceso')), style_body)],
        [Paragraph("<b>Monto Original Declarante:</b>", style_body), Paragraph(f"${monto_orig:,.2f} MXN", style_body), Paragraph("<b>Monto Solicitado FED:</b>", style_body), Paragraph(f"<font color='#16a34a'><b>${monto_disp:,.2f} MXN</b></font>", style_body)]
    ]
    t_datos_gen = Table(datos_gen, colWidths=[120, 150, 120, 150])
    t_datos_gen.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), light_bg),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_datos_gen)
    story.append(Spacer(1, 8))

    story.append(Paragraph("1. FUNDAMENTACIÓN E INTEGRACIÓN JURÍDICA", style_h2))
    texto_ley = (
        "El presente expediente respalda la solicitud de devolución del saldo a favor de Impuesto al Valor Agregado conforme a los "
        "<b>Artículos 22 e integración del 22-D del Código Fiscal de la Federación (CFF)</b>, así como el <b>Artículo 6 de la Ley del Impuesto al Valor Agregado (LIVA)</b>. "
        "El saldo deriva de operaciones reales efectivamente pagadas, contando con acuse de presentación oficial ante el SAT."
    )
    story.append(Paragraph(texto_ley, style_body))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. CADENA DE TRAZABILIDAD E HISTORIAL DE SALDOS (MÉTODO FIFO)", style_h2))
    fifo_data = [
        [Paragraph("<b>Concepto</b>", style_body), Paragraph("<b>Folio / Referencia</b>", style_body), Paragraph("<b>Saldo Orig.</b>", style_body), Paragraph("<b>Aplicado</b>", style_body), Paragraph("<b>Remanente FED</b>", style_body)],
        [Paragraph(f"Declaración {datos_saldo.get('Periodo_Mes')} {datos_saldo.get('Periodo_Anio')}", style_body), Paragraph(str(datos_saldo.get('Num_Operacion')), style_body), Paragraph(f"${monto_orig:,.2f}", style_body), Paragraph(f"${monto_orig - monto_disp:,.2f}", style_body), Paragraph(f"${monto_disp:,.2f}", style_body)],
        [Paragraph(f"<b>🔒 SOLICITUD FED / BLOQUEO</b>", style_body), Paragraph(str(datos_saldo.get('Folio_FED', 'TRÁMITE FED')), style_body), Paragraph(f"<b>${monto_orig:,.2f}</b>", style_body), Paragraph("<b>$0.00</b>", style_body), Paragraph(f"<b>${monto_disp:,.2f}</b>", style_body)]
    ]
    t_fifo = Table(fifo_data, colWidths=[160, 100, 95, 90, 95])
    t_fifo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), secondary_color),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    for i in range(5): fifo_data[0][i].style.textColor = colors.white
    story.append(t_fifo)
    story.append(Spacer(1, 10))

    log_text = Paragraph(
        f"<font size=7 color='#64748b'><b>REGISTRO DE AUDITORÍA:</b> Generado por Bóveda IVA Pro | "
        f"Fecha de Emisión: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ID Certificado: BIVAPRO-FED-{id_reg}</font>", style_body
    )
    story.append(log_text)
    story.append(Spacer(1, 20))

    firmas_data = [
        [
            Paragraph("__________________________________________<br/><b>Contador Público Responsable</b><br/>Firma y Cédula Profesional", ParagraphStyle('F1', parent=style_body, alignment=1)),
            Paragraph("__________________________________________<br/><b>Representante Legal / Contribuyente</b><br/>Firma de Conformidad", ParagraphStyle('F2', parent=style_body, alignment=1))
        ]
    ]
    t_firmas = Table(firmas_data, colWidths=[270, 270])
    t_firmas.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(t_firmas)

    doc.build(story)
    return filename

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
    if match_rfc: datos["rfc"] = match_rfc.group(1).upper()

    match_op = re.search(r"Número\s+de\s+operación[:\s]*([0-9]+(?:\.[0-9]+)?)", texto, re.IGNORECASE)
    if match_op:
        raw_op = match_op.group(1)
        datos["num_operacion"] = str(int(float(raw_op))) if "." in raw_op else raw_op

    match_fecha = re.search(r"Fecha\s+y\s+hora\s+de\s+presentación[:\s]*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    if match_fecha:
        try:
            dt_p = datetime.strptime(match_fecha.group(1), "%d/%m/%Y")
            datos["fecha_pres"] = dt_p.strftime("%Y-%m-%d")
        except Exception: pass

    match_anio = re.search(r"Ejercicio[:\s]*(\d{4})", texto, re.IGNORECASE)
    if match_anio:
        try: datos["anio"] = int(match_anio.group(1))
        except Exception: pass

    meses_validos = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    for m in meses_validos:
        if re.search(rf"(?:Período|Periodo)[^\n]*?{m}", texto, re.IGNORECASE):
            datos["mes"] = m; break
    else:
        for m in meses_validos:
            if re.search(rf"\b{m}\b", texto, re.IGNORECASE):
                datos["mes"] = m; break

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
                try: datos["saldo_favor"] = int(match_afavor.group(1).replace(",", ""))
                except Exception: pass

    return datos, texto

# --- SESIÓN Y AUTENTICACIÓN ---
def login_usuario(email, password):
    email = email.strip().lower()
    if not email or not password:
        return "❌ Ingresa usuario y contraseña.", gr.update(visible=True), gr.update(visible=False), "", "", ""
    if not supabase:
        return "❌ Error de conexión con Supabase.", gr.update(visible=True), gr.update(visible=False), "", "", ""
    try:
        res = supabase.table("usuarios_saas").select("*").eq("email", email).execute()
        usuarios = res.data
        if not usuarios:
            return "❌ Usuario no registrado.", gr.update(visible=True), gr.update(visible=False), "", "", ""
        
        user_data = usuarios[0]
        if user_data.get("password") == password:
            if user_data.get("activo") == False:
                return "❌ Suscripción suspendida.", gr.update(visible=True), gr.update(visible=False), "", "", ""
            
            tipo_plan = user_data.get("plan", "Plan Básico")
            fecha_exp_str = str(user_data.get("fecha_expiracion", "Indefinida"))
            
            header_html = f'<div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 18px; border-radius: 10px; color: white; margin-bottom: 15px;"><h2 style="margin:0; font-size: 1.8rem;">🏛️ Bóveda IVA Pro</h2><p style="margin:5px 0 0 0; color: #e0e7ff;">Bienvenido, <b>{email}</b> | Plan: <b>{tipo_plan}</b> | Vence: <b>{fecha_exp_str}</b></p></div>'

            return (
                "¡Acceso concedido!", gr.update(visible=False), gr.update(visible=True),
                header_html, email, tipo_plan
            )
        else:
            return "❌ Contraseña incorrecta.", gr.update(visible=True), gr.update(visible=False), "", "", ""
    except Exception as e:
        return f"Error al validar acceso: {e}", gr.update(visible=True), gr.update(visible=False), "", "", ""

def inicializar_panel_usuario(email):
    rfcs = obtener_rfcs_unicos(email)
    val_inicial = rfcs[0] if rfcs else None
    upd = gr.update(choices=rfcs, value=val_inicial)
    return upd, upd, upd

def actualizar_vista_resumen(email, rfc):
    if not rfc:
        return "### Selecciona o registra un cliente.", pd.DataFrame(), gr.update(choices=[], value=None), None, gr.update(choices=[], value=None)
    df = cargar_saldos(email)
    if df.empty:
        return "### No hay datos registrados.", pd.DataFrame(), gr.update(choices=[], value=None), None, gr.update(choices=[], value=None)
    
    df_cliente = df[df["RFC"] == rfc].copy()
    if df_cliente.empty:
        return f"### Sin registros para {rfc}", pd.DataFrame(), gr.update(choices=[], value=None), None, gr.update(choices=[], value=None)
    
    df_cliente["Mes_Num"] = df_cliente["Periodo_Mes"].apply(mes_a_numero)
    df_cliente = df_cliente.sort_values(by=["Periodo_Anio", "Mes_Num"]).drop(columns=["Mes_Num"])
    
    total_disp = int(df_cliente[df_cliente["Estatus"] == "Vigente"]["Saldo_Disponible"].sum()) if not df_cliente.empty else 0
    metric_html = f"<h3>SALDO TOTAL VIGENTE — {rfc}: <span style='color:#16a34a;'>${total_disp:,} MXN</span></h3>"
    
    ids_lista = df_cliente["ID"].tolist()
    ids_fed = df_cliente[df_cliente["Estatus"].isin(["Vigente", "En Trámite FED"])]["ID"].tolist()

    ruta_excel = exportar_dataframe_excel(df_cliente, f"Resumen_Boveda_{rfc}")
    
    upd_ids = gr.update(choices=ids_lista, value=ids_lista[0] if ids_lista else None)
    upd_fed = gr.update(choices=ids_fed, value=ids_fed[0] if ids_fed else None)
    
    return metric_html, df_cliente, upd_ids, ruta_excel, upd_fed

def procesar_solicitud_fed(email, id_saldo, folio_fed, fecha_ingreso, obs, logo_file):
    if not id_saldo:
        return "❌ Selecciona un saldo válido.", None
    try:
        res = supabase.table("saldos_iva").select("*").eq("id", int(id_saldo)).execute()
        if not res.data:
            return "❌ No se encontró el saldo.", None
        
        datos_saldo = res.data[0]
        
        supabase.table("saldos_iva").update({
            "estatus": "En Trámite FED",
            "folio_fed": str(folio_fed) if folio_fed else f"FED-{id_saldo}",
            "fecha_ingreso_fed": str(fecha_ingreso),
            "observaciones_fed": str(obs)
        }).eq("id", int(id_saldo)).execute()

        datos_saldo["Estatus"] = "En Trámite FED"
        datos_saldo["Folio_FED"] = folio_fed
        datos_saldo["Fecha_Ingreso_FED"] = fecha_ingreso

        logo_path = logo_file.name if hasattr(logo_file, 'name') else logo_file
        pdf_path = generar_pdf_expediente_fed_real(datos_saldo, logo_path)

        registrar_log(email, "CONGELAR_FED", f"Saldo ID: {id_saldo} congelado por trámite FED {folio_fed}")
        return f"✅ Saldo con ID {id_saldo} congelado exitosamente para Trámite FED.", pdf_path
    except Exception as e:
        return f"Error al congelar saldo para FED: {e}", None

def resolver_tramite_fed(email, id_saldo, accion_resolucion, num_deposito, confirma_accion):
    if not confirma_accion:
        return "❌ Debes confirmar la casilla de verificación antes de procesar la resolución."
    if not id_saldo:
        return "❌ Selecciona un ID de saldo en trámite."

    try:
        if accion_resolucion == "Aprobado / Devuelto por el SAT":
            if not num_deposito:
                return "❌ Por favor ingresa el Número de Depósito / Autorización del SAT."
            
            supabase.table("saldos_iva").update({
                "saldo_disponible": 0,
                "estatus": "Devuelto / Pagado",
                "observaciones_fed": f"Aprobado SAT. Depósito: {num_deposito}"
            }).eq("id", int(id_saldo)).execute()

            registrar_log(email, "PAGO_FED_APROBADO", f"Saldo ID: {id_saldo} devuelto por el SAT. Depósito: {num_deposito}")
            return f"🎉 Saldo ID {id_saldo} marcado como DEVUELTO Y PAGADO por el SAT. El registro ha sido archivado en $0."

        elif accion_resolucion == "Rechazado / Desistido (Descongelar)":
            supabase.table("saldos_iva").update({
                "estatus": "Vigente"
            }).eq("id", int(id_saldo)).execute()

            registrar_log(email, "DESCONGELAR_FED", f"Saldo ID: {id_saldo} descongelado por rechazo o desistimiento.")
            return f"🔄 Saldo ID {id_saldo} ha sido DESCONGELADO y reincorporado como Vigente en el Motor FIFO."

        return "Acción no reconocida."
    except Exception as e:
        return f"Error al resolver trámite FED: {e}"

def guardar_declaracion_pdf(email, plan, rfc, mes, anio, tipo_dec, num_op, fecha_pres, saldo_orig, confirma_mod):
    rfc_limpio = rfc.upper().strip()
    num_op_limpio = str(num_op).replace(".0", "").strip()
    
    if not num_op_limpio:
        return "❌ El número de operación es obligatorio.", gr.update(), gr.update(), gr.update()
    
    try:
        check_dup = supabase.table("saldos_iva").select("id").eq("usuario_email", email).eq("num_operacion", num_op_limpio).execute()
        if check_dup.data:
            return f"❌ El Número de Operación '{num_op_limpio}' ya está registrado.", gr.update(), gr.update(), gr.update()

        supabase.table("saldos_iva").insert({
            "usuario_email": email, "rfc": rfc_limpio, "periodo_mes": mes,
            "periodo_anio": int(anio), "tipo_declaracion": tipo_dec, "num_operacion": num_op_limpio,
            "fecha_presentacion": str(fecha_pres), "saldo_original": float(saldo_orig),
            "saldo_disponible": float(saldo_orig), "estatus": "Vigente"
        }).execute()
        
        registrar_log(email, "CARGA_DECLARACION_PDF", f"RFC: {rfc_limpio} | Monto: ${saldo_orig} MXN")
        rfcs_nuevos = obtener_rfcs_unicos(email)
        upd = gr.update(choices=rfcs_nuevos, value=rfc_limpio)
        
        return "¡Declaración registrada correctamente!", upd, upd, upd
    except Exception as e:
        return f"Error al registrar: {e}", gr.update(), gr.update(), gr.update()

def ejecutar_fifo(email, rfc, monto, mes_dest, anio_dest):
    if not rfc: return "❌ Selecciona un RFC.", pd.DataFrame()
    if monto <= 0: return "❌ Ingresa un monto mayor a cero.", pd.DataFrame()
    
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
                "usuario_email": email, "fecha_aplicacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "rfc": rfc, "periodo_origen": f"{row['Periodo_Mes']} {row['Periodo_Anio']}",
                "num_operacion_origen": folio_limpio, "saldo_anterior": float(saldo_anterior),
                "monto_aplicado": float(usar), "remanente_nuevo": float(remanente_nuevo),
                "periodo_destino": periodo_destino_str
            }
            supabase.table("historial_acreditamientos").insert(payload_historial).execute()
            
            desglose_sat.append({
                "Declaración Destino": periodo_destino_str, "Periodo Origen": f"{row['Periodo_Mes']} {row['Periodo_Anio']}",
                "Folio SAT": folio_limpio, "Monto Acreditado": f"${usar:,} MXN", "Remanente": f"${remanente_nuevo:,} MXN"
            })

        registrar_log(email, "EJECUCION_FIFO", f"RFC: {rfc} | Aplicado en {periodo_destino_str} | Monto: ${monto} MXN")
        return f"¡Acreditamiento FIFO aplicado con éxito!", pd.DataFrame(desglose_sat)
    except Exception as e:
        return f"Error al ejecutar: {e}", pd.DataFrame()

def obtener_historial_vista(email, rfc):
    df_hist = cargar_historial(email)
    if df_hist.empty: return pd.DataFrame(), None
    df_cliente = df_hist[df_hist["RFC"] == rfc] if rfc else df_hist
    if df_cliente.empty: return pd.DataFrame(), None
    
    cols = [c for c in ["ID", "Fecha_Aplicacion", "RFC", "Periodo_Origen", "Declaracion_Aplicada_Destino", "Num_Operacion_Origen", "Saldo_Anterior", "Monto_Aplicado", "Remanente_Nuevo"] if c in df_cliente.columns]
    df_disp = df_cliente[cols]
    ruta_excel_hist = exportar_dataframe_excel(df_disp, f"Historial_Acreditamientos_{rfc if rfc else 'General'}")
    return df_disp, ruta_excel_hist

# --- INTERFAZ GRADIO (Configuración compatible con 6.0) ---
with gr.Blocks(title="Bóveda IVA Pro") as demo:
    
    state_email = gr.State("")
    state_plan = gr.State("")

    # 1. Panel de Login
    with gr.Column(visible=True) as panel_login:
        gr.Markdown("""
            <div style="max-width: 480px; margin: 40px auto; padding: 25px; background: white; border-radius: 12px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <h2 style="color: #1e3c72; margin-bottom: 5px;">🏛️ Bóveda IVA Pro</h2>
                <p style="color: #64748b; font-size: 0.9rem;">Plataforma inteligente de gestión y acreditamiento de IVA.</p>
            </div>
        """)
        with gr.Row():
            with gr.Column(scale=1): pass
            with gr.Column(scale=2):
                txt_user = gr.Textbox(label="Usuario (Correo)", placeholder="correo@ejemplo.com")
                txt_pass = gr.Textbox(label="Contraseña", type="password")
                btn_ingresar = gr.Button("Iniciar Sesión", variant="primary")
                lbl_msg = gr.Markdown()
            with gr.Column(scale=1): pass

    # 2. Panel de Aplicación
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
                    file_descargar_resumen = gr.File(label="📥 Descargar Resumen en Excel", interactive=False)

                gr.Markdown("---")
                gr.Markdown("### 🏛️ Módulo FED (Formato Electrónico de Devoluciones) — Devolución de IVA")
                with gr.Row():
                    drop_id_fed = gr.Dropdown(label="Seleccionar ID de Saldo a Solicitar en Devolución FED", choices=[])
                    txt_folio_fed = gr.Textbox(label="Folio de Trámite SAT / Registro Único", placeholder="AV2026101899211")
                    date_ingreso_fed = gr.Textbox(label="Fecha de Ingreso SAT", value=datetime.now().strftime("%Y-%m-%d"))
                
                with gr.Row():
                    file_logo_fed = gr.File(label="Subir Logo del Despacho / Empresa (Opcional para PDF)", file_types=[".png", ".jpg", ".jpeg"])
                    txt_obs_fed = gr.Textbox(label="Observaciones o Referencia Interna", placeholder="Trámite de devolución ejercicio 2025")

                with gr.Row():
                    btn_congelar_fed = gr.Button("🔒 Congelar Saldo y Generar Expediente FED (PDF)", variant="primary")
                    file_pdf_fed_descarga = gr.File(label="📄 Descargar / Visualizar Expediente FED (PDF)", interactive=False)
                
                lbl_fed_res = gr.Markdown()

                gr.Markdown("#### ⚖️ Resolución del Trámite FED")
                with gr.Row():
                    rad_resolucion_fed = gr.Radio(choices=["Aprobado / Devuelto por el SAT", "Rechazado / Desistido (Descongelar)"], label="Seleccionar Resultado del SAT", value="Aprobado / Devuelto por el SAT")
                    txt_deposito_sat = gr.Textbox(label="Número de Depósito / Autorización SAT (Requerido si fue Aprobado)", placeholder="DEP-9821873")
                    chk_confirma_resolucion = gr.Checkbox(label="Confirmo aplicar esta resolución definitiva")
                    btn_resolver_fed = gr.Button("⚙️ Procesar Resolución FED", variant="stop")
                
                lbl_resolucion_res = gr.Markdown()

            with gr.TabItem("📥 Carga de Declaraciones (PDF / Excel)"):
                gr.Markdown("### 1. Carga Individual por PDF del SAT")
                file_pdf = gr.File(label="Subir Declaración PDF del SAT", file_types=[".pdf"])
                with gr.Row():
                    txt_rfc_pdf = gr.Textbox(label="RFC Contribuyente")
                    drop_mes_pdf = gr.Dropdown(label="Periodo (Mes)", choices=["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], value="Enero")
                    num_anio_pdf = gr.Number(label="Ejercicio (Año)", value=2026, precision=0)
                with gr.Row():
                    drop_tipo_pdf = gr.Dropdown(label="Tipo Declaración", choices=["Normal", "Complementaria - Modificación", "Complementaria - Dejar sin Efecto"], value="Normal")
                    txt_num_op_pdf = gr.Textbox(label="Número de Operación SAT")
                    date_pres_pdf = gr.Textbox(label="Fecha Presentación (YYYY-MM-DD)", value=datetime.now().strftime("%Y-%m-%d"))
                with gr.Row():
                    num_saldo_pdf = gr.Number(label="Saldo a Favor ($)", value=0)
                    chk_mod_pdf = gr.Checkbox(label="Sustituir declaración anterior")
                
                btn_guardar_pdf = gr.Button("💾 Registrar Declaración Individual", variant="primary")
                lbl_guardar_pdf_res = gr.Markdown()

                gr.Markdown("---")
                gr.Markdown("### 2. Carga Masiva para Despachos (vía Excel)")
                gr.Markdown("Si manejas múltiples clientes o quieres importar tu papel de trabajo histórico, descarga la plantilla de Excel, copia tus datos e impórtala de golpe.")
                
                with gr.Row():
                    file_plantilla_descarga = gr.File(label="📥 Descargar Plantilla Guía en Excel", value=PLANTILLA_EXCEL_PATH, interactive=False)
                    file_excel_masivo = gr.File(label="📤 Cargar Plantilla Excel de Declaraciones", file_types=[".xlsx", ".xls"])
                
                btn_procesar_masivo = gr.Button("🚀 Importar Declaraciones Masivas a la Bóveda", variant="primary")
                lbl_masivo_res = gr.Markdown()

            with gr.TabItem("⚙️ Motor FIFO / Acreditamiento"):
                with gr.Row():
                    drop_rfc_fifo = gr.Dropdown(label="Seleccionar RFC", choices=[], interactive=True)
                    num_monto_fifo = gr.Number(label="Monto a Aplicar ($)")
                with gr.Row():
                    drop_mes_dest = gr.Dropdown(label="Periodo Destino (Mes)", choices=["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], value="Enero")
                    num_anio_dest = gr.Number(label="Ejercicio Destino (Año)", value=2026, precision=0)
                
                btn_ejecutar_fifo = gr.Button("🚀 Ejecutar Acreditamiento FIFO", variant="primary")
                lbl_fifo_res = gr.Markdown()
                tabla_fifo_desglose = gr.DataFrame(label="Desglose Acreditamiento")

            with gr.TabItem("📜 Historial"):
                with gr.Row():
                    drop_rfc_hist = gr.Dropdown(label="Filtrar por RFC", choices=[], interactive=True)
                    btn_ver_hist = gr.Button("🔍 Consultar Historial")
                
                tabla_historial = gr.DataFrame(label="Historial de Acreditamientos")
                file_descargar_historial = gr.File(label="📥 Descargar Historial en Excel", interactive=False)

    # --- EVENTOS Y VÍNCULOS ---
    btn_ingresar.click(
        fn=login_usuario, inputs=[txt_user, txt_pass],
        outputs=[lbl_msg, panel_login, panel_app, html_header, state_email, state_plan]
    ).then(
        fn=inicializar_panel_usuario, inputs=[state_email],
        outputs=[drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    drop_rfc_resumen.change(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed]
    )

    btn_actualizar_resumen.click(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed]
    )

    btn_congelar_fed.click(
        fn=procesar_solicitud_fed, inputs=[state_email, drop_id_fed, txt_folio_fed, date_ingreso_fed, txt_obs_fed, file_logo_fed],
        outputs=[lbl_fed_res, file_pdf_fed_descarga]
    ).then(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed]
    )

    btn_resolver_fed.click(
        fn=resolver_tramite_fed, inputs=[state_email, drop_id_fed, rad_resolucion_fed, txt_deposito_sat, chk_confirma_resolucion],
        outputs=[lbl_resolucion_res]
    ).then(
        fn=actualizar_vista_resumen, inputs=[state_email, drop_rfc_resumen],
        outputs=[html_metricas, tabla_saldos_resumen, drop_id_fed, file_descargar_resumen, drop_id_fed]
    )

    file_pdf.change(
        fn=extraer_datos_pdf, inputs=[file_pdf],
        outputs=[txt_rfc_pdf, txt_num_op_pdf, num_saldo_pdf, drop_mes_pdf, num_anio_pdf, date_pres_pdf, drop_tipo_pdf]
    )

    btn_guardar_pdf.click(
        fn=guardar_declaracion_pdf, inputs=[state_email, state_plan, txt_rfc_pdf, drop_mes_pdf, num_anio_pdf, drop_tipo_pdf, txt_num_op_pdf, date_pres_pdf, num_saldo_pdf, chk_mod_pdf],
        outputs=[lbl_guardar_pdf_res, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    btn_procesar_masivo.click(
        fn=procesar_carga_masiva_excel, inputs=[state_email, state_plan, file_excel_masivo],
        outputs=[lbl_masivo_res, drop_rfc_resumen, drop_rfc_fifo, drop_rfc_hist]
    )

    btn_ejecutar_fifo.click(
        fn=ejecutar_fifo, inputs=[state_email, drop_rfc_fifo, num_monto_fifo, drop_mes_dest, num_anio_dest],
        outputs=[lbl_fifo_res, tabla_fifo_desglose]
    )

    btn_ver_hist.click(
        fn=obtener_historial_vista, inputs=[state_email, drop_rfc_hist],
        outputs=[tabla_historial, file_descargar_historial]
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port, theme=gr.themes.Soft())
