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

def generar_pdf_expediente_fed_real(email, datos_saldo, logo_path=None):
    rfc_raw = str(datos_saldo.get("RFC", "N/A"))
    rfc = re.sub(r'[^a-zA-Z0-9]', '_', rfc_raw)
    id_reg = str(datos_saldo.get("ID", "0"))
    num_op_origen = str(datos_saldo.get("Num_Operacion", "N/A"))
    periodo_origen_str = f"{datos_saldo.get('Periodo_Mes')} {datos_saldo.get('Periodo_Anio')}"
    
    # VALIDACIÓN ESTRICTA DE INTEGRIDAD: Verificar folios de destino en el historial
    if supabase and num_op_origen != "N/A":
        try:
            res_hist = supabase.table("historial_acreditamientos").select("*").eq("num_operacion_origen", num_op_origen).execute()
            if res_hist.data:
                for reg in res_hist.data:
                    periodo_dest = reg.get("periodo_destino", "Desconocido")
                    # Buscamos si la declaración destino existe en la tabla de saldos del contribuyente para asegurar que tiene número de operación registrado
                    res_val_dest = supabase.table("saldos_iva").select("num_operacion").eq("usuario_email", email).eq("rfc", rfc_raw).eq("periodo_mes", periodo_dest.split()[0]).execute()
                    if not res_val_dest.data or not res_val_dest.data[0].get("num_operacion"):
                        raise ValueError(
                            f"AVISO DE INTEGRIDAD FISCAL: No se localiza el Número de Operación (Folio SAT) correspondiente a la declaración de aplicación destino ({periodo_dest}). "
                            "Para generar el expediente FED conforme a los requerimientos normativos, es obligatorio que la declaración donde se aplicó el acreditamiento "
                            "esté previamente registrada en la Bóveda con su respectivo Folio SAT."
                        )
        except ValueError as ve:
            raise ve
        except Exception:
            pass

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

    style_title = ParagraphStyle('DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=15, textColor=primary_color, leading=18)
    style_subtitle = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor("#475569"), leading=11)
    style_h2 = ParagraphStyle('SectionHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=primary_color, spaceBefore=10, spaceAfter=5, leading=12)
    style_body = ParagraphStyle('BodyDark', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=dark_text, leading=11)
    style_th = ParagraphStyle('TableHead', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, leading=10)
    style_badge = ParagraphStyle('BadgeText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=1)

    # 1. ENCABEZADO
    header_elements = []
    if logo_path and os.path.exists(logo_path):
        try:
            img_logo = RLImage(logo_path, width=1.5*72, height=0.6*72)
            header_elements.append(img_logo)
        except Exception:
            header_elements.append(Paragraph("<b>BÓVEDA IVA PRO</b>", style_title))
    else:
        header_elements.append(Paragraph("<b>BÓVEDA IVA PRO</b><br/><font size=7 color='#64748b'>SISTEMA DE AUDITORÍA E INTEGRIDAD FISCAL</font>", style_title))

    header_table_data = [
        [
            header_elements[0],
            Paragraph(f"<font size=8><b>DICTAMEN TÉCNICO FED</b><br/>SOLICITUD DE DEVOLUCIÓN DE IVA<br/><b>ESTATUS: {datos_saldo.get('Estatus', 'EN TRÁMITE FED')}</b></font>", ParagraphStyle('RHeader', parent=style_subtitle, alignment=2))
        ]
    ]
    t_header = Table(header_table_data, colWidths=[280, 260])
    t_header.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(t_header)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=6))

    # BANNER DE ESTATUS
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

    # DATOS GENERALES
    datos_gen = [
        [Paragraph("<b>RFC Contribuyente:</b>", style_body), Paragraph(str(rfc_raw), style_body), Paragraph("<b>Folio Interno Bóveda:</b>", style_body), Paragraph(f"FED-{id_reg}", style_body)],
        [Paragraph("<b>Periodo / Ejercicio Origen:</b>", style_body), Paragraph(periodo_origen_str, style_body), Paragraph("<b>Fecha de Ingreso SAT:</b>", style_body), Paragraph(str(datos_saldo.get('Fecha_Ingreso_FED', datetime.now().strftime('%Y-%m-%d'))), style_body)],
        [Paragraph("<b>Tipo de Declaración:</b>", style_body), Paragraph(str(datos_saldo.get('Tipo_Declaracion', 'Normal')), style_body), Paragraph("<b>Número de Operación SAT:</b>", style_body), Paragraph(num_op_origen, style_body)],
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

    # 1. FUNDAMENTACIÓN E INTEGRACIÓN JURÍDICA
    story.append(Paragraph("1. FUNDAMENTACIÓN E INTEGRACIÓN JURÍDICA", style_h2))
    texto_ley = (
        "El presente expediente respalda la solicitud de devolución del saldo a favor de Impuesto al Valor Agregado conforme a los "
        "<b>Artículos 22 e integración del 22-D del Código Fiscal de la Federación (CFF)</b>, así como el <b>Artículo 6 de la Ley del Impuesto al Valor Agregado (LIVA)</b>. "
        "El saldo deriva de operaciones reales efectivamente pagadas, contando con acuse de presentación oficial ante el SAT."
    )
    story.append(Paragraph(texto_ley, style_body))
    story.append(Spacer(1, 8))

    # 2. DETERMINACIÓN ARITMÉTICA E HISTORIAL FIFO DE APLICACIONES
    story.append(Paragraph("2. DETERMINACIÓN ARITMÉTICA E HISTORIAL FIFO DE APLICACIONES", style_h2))
    
    fifo_table_data = [
        [Paragraph("Concepto / Evento", style_th), Paragraph("Folio / Referencia SAT", style_th), Paragraph("Saldo Orig.", style_th), Paragraph("Monto Aplicado", style_th), Paragraph("Remanente Saldo", style_th)]
    ]

    # Renglón 1: Declaración Origen Inicial
    fifo_table_data.append([
        Paragraph(f"<b>Declaración Origen ({periodo_origen_str})</b>", style_body),
        Paragraph(num_op_origen, style_body),
        Paragraph(f"${monto_orig:,.2f}", style_body),
        Paragraph("$0.00", style_body),
        Paragraph(f"${monto_orig:,.2f}", style_body)
    ])

    # Buscar Acreditamientos Previos en el Historial de Supabase consultando el folio real de destino
    remanente_corredor = monto_orig
    total_acreditado_prev = 0

    try:
        if supabase and num_op_origen != "N/A":
            res_hist = supabase.table("historial_acreditamientos").select("*").eq("num_operacion_origen", num_op_origen).order("id").execute()
            if res_hist.data:
                for reg in res_hist.data:
                    monto_apl = float(reg.get("monto_aplicado", 0))
                    dest_str = str(reg.get("periodo_destino", "Declaración Destino"))
                    total_acreditado_prev += monto_apl
                    remanente_corredor -= monto_apl
                    
                    # Buscar el folio específico de la declaración destino registrada en la bóveda
                    mes_dest_key = dest_str.split()[0]
                    res_folio_dest = supabase.table("saldos_iva").select("num_operacion").eq("usuario_email", email).eq("rfc", rfc_raw).eq("periodo_mes", mes_dest_key).execute()
                    folio_dest_encontrado = res_folio_dest.data[0].get("num_operacion", "") if res_folio_dest.data else ""

                    fifo_table_data.append([
                        Paragraph(f"(-) Acreditamiento aplicado en <b>{dest_str}</b>", style_body),
                        Paragraph(folio_dest_encontrado, style_body),  # <- Folio SAT de la declaración destino obligatoriamente vinculado
                        Paragraph(f"${monto_orig:,.2f}", style_body),
                        Paragraph(f"<font color='#dc2626'>-${monto_apl:,.2f}</font>", style_body),
                        Paragraph(f"${remanente_corredor:,.2f}", style_body)
                    ])
    except Exception:
        pass

    # Si no se hallaron registros individuales pero hay diferencia previa
    if total_acreditado_prev == 0 and (monto_orig - monto_disp) > 0:
        dif_prev = monto_orig - monto_disp
        remanente_corredor = monto_disp
        fifo_table_data.append([
            Paragraph("(-) Acreditamientos previos acumulados", style_body),
            Paragraph("", style_body),
            Paragraph(f"${monto_orig:,.2f}", style_body),
            Paragraph(f"<font color='#dc2626'>-${dif_prev:,.2f}</font>", style_body),
            Paragraph(f"${remanente_corredor:,.2f}", style_body)
        ])

    # Renglón Final: Bloqueo FED
    fifo_table_data.append([
        Paragraph("<b>🔒 SOLICITUD FED / BLOQUEO EN BÓVEDA</b>", style_body),
        Paragraph(str(datos_saldo.get('Folio_FED', 'TRÁMITE FED')), style_body),
        Paragraph(f"<b>${monto_orig:,.2f}</b>", style_body),
        Paragraph("<b>$0.00</b>", style_body),
        Paragraph(f"<font color='#16a34a'><b>${monto_disp:,.2f}</b></font>", style_body)
    ])

    t_fifo = Table(fifo_table_data, colWidths=[160, 100, 95, 90, 95])
    t_fifo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 3.5), ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
    ]))
    story.append(t_fifo)
    story.append(Spacer(1, 10))

    # 3. MARCO LEGAL Y DECLARACIÓN BAJO PROTESTA
    story.append(Paragraph("3. DECLARACIÓN BAJO PROTESTA DE DECIR VERDAD Y MARCO LEGAL", style_h2))
    texto_protesta = (
        "Bajo protesta de decir verdad, el contribuyente y/o su representante legal manifiestan que la información y montos aquí asentados "
        "derivan de operaciones contables y fiscales reales, soportadas con Comprobantes Fiscales Digitales por Internet (CFDI) válidos, "
        "efectivamente pagados y bancarizados. Así mismo, se certifica que el saldo solicitado no ha sido objeto de compensación ni acreditamiento duplicado, "
        "cumpliendo estrictamente con las disposiciones de los artículos 22 y 22-D del Código Fiscal de la Federación (CFF)."
    )
    story.append(Paragraph(texto_protesta, style_body))
    story.append(Spacer(1, 8))

    log_text = Paragraph(
        f"<font size=7 color='#64748b'><b>REGISTRO DE AUDITORÍA:</b> Generado por Bóveda IVA Pro | "
        f"Fecha de Emisión: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ID Certificado: BIVAPRO-FED-{id_reg}</font>", style_body
    )
    story.append(log_text)
    story.append(Spacer(1, 20))

    # FIRMA ÚNICA (REPRESENTANTE LEGAL / CONTRIBUYENTE)
    firmas_data = [
        [
            Paragraph("__________________________________________<br/><b>Representante Legal / Contribuyente</b><br/>Firma de Conformidad", ParagraphStyle('F1', parent=style_body, alignment=1))
        ]
    ]
    t_firmas = Table(firmas_data, colWidths=[540])
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
            fecha_exp_str = str
