import os
import re
import urllib.parse
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

# --- CONFIGURACIÓN DE NÚMERO DE WHATSAPP PARA VENTAS ---
TELEFONO_WHATSAPP = "527226513054"  # Tu número configurado

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
    ruta = "./Plantilla_Carga_Masiva_BovedaIVA_v2.xlsx"
    datos_ejemplo = [
        {
            "RFC": "XAXX010101000", "Periodo_Mes": "Enero", "Ejercicio": 2026,
            "Tipo_Declaracion": "Normal", "Num_Operacion": "100200300",
            "Fecha_Presentacion": "2026-02-17", "Saldo_Original": 15000, "Remanente": 15000
        },
        {
            "RFC": "XAXX010101000", "Periodo_Mes": "Febrero", "Ejercicio": 2026,
            "Tipo_Declaracion": "Normal", "Num_Operacion": "100200301",
            "Fecha_Presentacion": "2026-03-17", "Saldo_Original": 22500, "Remanente": 10000
        }
    ]
    df_plantilla = pd.DataFrame(datos_ejemplo)
    df_plantilla.to_excel(ruta, index=False, engine='openpyxl')
    return ruta

PLANTILLA_EXCEL_PATH = obtener_o_crear_plantilla_excel()

def calcular_codigo_invitacion(email_referidor):
    if not email_referidor or "@" not in email_referidor:
        return "", ""
    email_clean = email_referidor.strip().lower()
    partes = email_clean.split("@")[0].strip()
    solo_letras = re.sub(r'[^a-z]', '', partes)
    num_letras = len(solo_letras)
    codigo = f"{solo_letras}{num_letras:02d}"
    return codigo, email_clean

def generar_html_tabla_planes(email_referidor=""):
    codigo, email_ref = calcular_codigo_invitacion(email_referidor)
    
    ref_txt_mensual = f" (Referido por: {email_ref} | Código: {codigo})" if email_ref else ""
    ref_txt_anual = f" (Referido por: {email_ref} | Código: {codigo} | SOLICITO PROMOCIÓN ANUAL: +1 mes gratis para mi cuenta y +2 meses gratis para {email_ref}, sujeto a que ambos contemos con suscripción anual activa)." if email_ref else ""

    msg_bm = urllib.parse.quote(f"Hola, deseo contratar el Plan Básico Mensual ($49 MXN) de Bóveda IVA Pro.{ref_txt_mensual}")
    msg_ba = urllib.parse.quote(f"Hola, deseo contratar el Plan Básico Anual ($399 MXN) de Bóveda IVA Pro.{ref_txt_anual}")
    msg_im = urllib.parse.quote(f"Hola, deseo contratar el Plan Ilimitado Mensual ($99 MXN) de Bóveda IVA Pro.{ref_txt_mensual}")
    msg_ia = urllib.parse.quote(f"Hola, deseo contratar el Plan Ilimitado Anual ($999 MXN) de Bóveda IVA Pro.{ref_txt_anual}")

    link_bm = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_bm}"
    link_ba = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_ba}"
    link_im = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_im}"
    link_ia = f"https://wa.me/{TELEFONO_WHATSAPP}?text={msg_ia}"

    banner_ref = ""
    if email_ref:
        banner_ref = f"""
        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 20px; font-size: 0.9rem;">
            🎉 <b>¡Código de referido activado ({codigo}) para {email_ref}!</b><br/>
            Al contratar cualquier <b>Plan Anual</b>, recibes <b>+1 MES GRATIS</b> y tu colega recibe <b>+2 MESES GRATIS</b>.<br/>
            <i>(Requisito indispensable: Ambos deben contar o adquirir una suscripción Anual, ya sea Básica o Ilimitada).</i>
        </div>
        """

    return f"""
    <div style="max-width: 900px; margin: 10px auto; padding: 10px;">
        {banner_ref}
        <h3 style="color: #1e3c72; text-align: center; margin-bottom: 20px; font-size: 1.4rem;">💳 Planes y Suscripciones — Bóveda IVA Pro</h3>
        <div style="display: flex; gap: 20px; justify-content: center; flex-wrap: wrap;">
            
            <!-- PLAN BÁSICO -->
            <div style="background: #ffffff; border: 2px solid #cbd5e1; border-radius: 12px; padding: 25px; width: 320px; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                <h3 style="color: #1e3c72; margin-top: 0; font-size: 1.3rem;">Plan Básico</h3>
                <p style="font-size: 0.85rem; color: #64748b;">Hasta 5 RFCs de clientes.</p>
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 15px 0;">
                <p style="font-size: 1.8rem; font-weight: bold; color: #0f172a; margin: 5px 0;">$49 <span style="font-size: 0.9rem; font-weight: normal; color: #64748b;">MXN / mes</span></p>
                <p style="font-size: 1.1rem; font-weight: bold; color: #16a34a; margin: 5px 0;">o $399 <span style="font-size: 0.8rem; font-weight: normal; color: #64748b;">MXN / año</span></p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin-bottom: 20px;">Precios con IVA incluido</p>
                
                <a href="{link_bm}" target="_blank" style="display: block; background: #25d366; color: white; padding: 12px; text-decoration: none; border-radius: 8px; font-weight: bold; margin-bottom: 10px;">💬 Contratar Mensual ($49)</a>
                <a href="{link_ba}" target="_blank" style="display: block; background: #128c7e; color: white; padding: 12px; text-decoration: none; border-radius: 8px; font-weight: bold;">💬 Contratar Anual ($399)</a>
            </div>

            <!-- PLAN ILIMITADO -->
            <div style="background: #ffffff; border: 2px solid #2a5298; border-radius: 12px; padding: 25px; width: 320px; text-align: center; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); position: relative;">
                <div style="position: absolute; top: -12px; right: 20px; background: #2a5298; color: white; padding: 3px 12px; border-radius: 10px; font-size: 0.75rem; font-weight: bold;">MÁS POPULAR</div>
                <h3 style="color: #2a5298; margin-top: 0; font-size: 1.3rem;">Plan Ilimitado</h3>
                <p style="font-size: 0.85rem; color: #64748b;">RFCs e importaciones ilimitadas.</p>
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 15px 0;">
                <p style="font-size: 1.8rem; font-weight: bold; color: #0f172a; margin: 5px 0;">$99 <span style="font-size: 0.9rem; font-weight: normal; color: #64748b;">MXN / mes</span></p>
                <p style="font-size: 1.1rem; font-weight: bold; color: #16a34a; margin: 5px 0;">o $999 <span style="font-size: 0.8rem; font-weight: normal; color: #64748b;">MXN / año</span></p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin-bottom: 20px;">Precios con IVA incluido</p>
                
                <a href="{link_im}" target="_blank" style="display: block; background: #25d366; color: white; padding: 12px; text-decoration: none; border-radius: 8px; font-weight: bold; margin-bottom: 10px;">💬 Contratar Mensual ($99)</a>
                <a href="{link_ia}" target="_blank" style="display: block; background: #128c7e; color: white; padding: 12px; text-decoration: none; border-radius: 8px; font-weight: bold;">💬 Contratar Anual ($999)</a>
            </div>

        </div>
    </div>
    """

def actualizar_enlace_referido(email_ref_input):
    codigo, email_ref = calcular_codigo_invitacion(email_ref_input)
    html_actualizado = generar_html_tabla_planes(email_ref_input)
    if email_ref:
        msg_info = f"✅ Código de referido activado: **{codigo}** (para {email_ref}). Al seleccionar un **Plan Anual**, se sumará **+1 mes gratis** para el nuevo cliente y **+2 meses gratis** para {email_ref} *(Requisito: Ambas partes deben contar con membresía anual activa)*."
    else:
        msg_info = "ℹ️ Ingresa el correo para aplicar la promoción. *(Nota: Aplica +1 mes gratis para el nuevo cliente y +2 meses para quien refirió al contratar cualquier Plan Anual, siempre que ambas partes cuenten con suscripción anual activa)*."
    return html_actualizado, msg_info

def procesar_carga_masiva_excel(email, plan, archivo_excel):
    if archivo_excel is None:
        return "❌ Por favor sube un archivo Excel válido.", gr.update(), gr.update(), gr.update()
    
    ruta_file = archivo_excel.name if hasattr(archivo_excel, 'name') else archivo_excel
    try:
        df_excel = pd.read_excel(ruta_file, engine='openpyxl')
    except Exception as e:
        return f"❌ Error al leer el archivo Excel: {str(e)}", gr.update(), gr.update(), gr.update()

    df_excel.columns = [str(c).strip().capitalize() for c in df_excel.columns]
    col_map_inversa = {
        "Rfc": "RFC", "Periodo_mes": "Periodo_Mes", "Periodo_anio": "Periodo_Anio", 
        "Ejercicio
